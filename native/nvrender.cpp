// nvrender.cpp -- the native renderer: a General MIDI piano file to the dry
// WAV and room sidecar blockrender writes, with no Python at runtime.
//
//     nvrender EXPORT.nvx IN.mid OUT.wav [--tuner=NAME [--a=HZ | --c=HZ]]
//
// --tuner: any of midilib's tuners, computed here (native/tuner.cpp) in place
// of the export's table, at the reference pitch a= or c= -- blockrender's
// `IN.mid OUT.wav NAME a=HZ`.
//
// EXPORT.nvx is examples/native_export.py's: the render's constants, the
// tuning table, the trims, the piano classes and the kernel's libraries.
// Then, all native: the file read (midi.cpp), its song (channel.cpp), its
// table (prepare.cpp: notes, register, length, damper tracks), its render
// (render.cpp, through synthkernel.c's libraries), the WAV (32-bit, as
// blockrender.write_wav) and OUT.room.json (the room's bands, as
// blockrender's sidecar). Bit for bit blockrender's whole-table CPU render
// (TUNING_STREAM=0).
//
// THE BEND PASSES (native/bend.cpp): a channel's wheel and RPNs (bend range,
// fine and coarse tuning) as its tuning, folded into its notes; what moves
// after its first note, a GESTURE, as a bend row that a voice that bends
// rides (a guitar; a piano cannot be bent, so under it the gesture moves
// nothing, as in blockrender); a fader (CC7, CC11) moving under its notes as
// a row.
//
// THE DRUMS the engine has (the export's kit table: a set's key, its class,
// pitch and seat) play from the song as blockrender plays them: the kit's
// pitch, the seat, the one-shot's hold.
//
// Refused (exit 2) -- Python renders them: a file the reader refuses (an
// NRPN, MPE, an exclusive past a reset...), a note no native class plays
// (other instruments, the other drums), an MTS tuning select (gm2's store),
// a drum channel's wheel or tuning (its drums would ride it).

#include <algorithm>
#include <array>
#include <climits>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <tuple>
#include <dlfcn.h>
#include <functional>
#include <map>
#include "gsdisplay.h"
#include <unistd.h>
#include <set>
#include <string>
#include <sys/mman.h>
#include <vector>

#include "pycompat.h"
#include "gpufile.h"

struct NvSirRow {                       // (nv_song_sirens: a rotor's row -- nvrender.cpp's twin)
    long long ch;
    std::vector<float> r, l;
    std::vector<double> c;
};
void nv_song_sirens(void *song, const NoteClass *const *K, int nK, double total, double SR, long long BLK, int sbase,
                    std::vector<NvSirRow> *sirp);

extern "C" {
void *nv_midi_read(const uint8_t *buf, long long len, int *err);
void nv_midi_map_kits(const int *ids, int n);
void nv_midi_map_kits_play(int on);
void nv_song_mapk_base(int base);
int nv_midi_n_dedit(void *p);
void nv_midi_dedit(void *p, int i, int *iv, double *t);
int nv_midi_user_drum(void *p, int set, int key, int *iv);
void nv_song_user_drum(void *s, int i, int uq, int umask, const int *uv);
int nv_midi_n_efx(void *p);
int nv_midi_n_cmx(void *p);
void nv_midi_cmx(void *p, int i, int *iv, double *dv);
void nv_midi_efx(void *p, int i, int *iv, double *t);
void nv_amp_ref_steps(int k, double base, int n, const double *starts, const double *levels);
void nv_chorus_share_steps(int q, int n, const double *ts, const double *vals);
void nv_chorus_share_steps_n(int q, int n, const double *ts, const double *vals);
void nv_chorus_taps(int q, int n, const double *taps);
const char *nv_play_why(void);
void nv_tremolo_wave(long long ch, int n, const double *khp);
void nv_midi_free(void *p);
double nv_midi_total(void *p);
int nv_midi_display_n(void *p);
const uint8_t *nv_midi_display(void *p, int i, int *n, double *t);
int nv_midi_n_notes(void *p);
int nv_midi_n_ccs(void *p);
int nv_midi_n_pws(void *p);
int nv_midi_master(void *p);
int nv_midi_mvol(void *p, double sr, long long *s, double *g, int cap);
void nv_render_mvol(const long long *s, const double *g, int n);
int nv_midi_otun(void *p, int ch, double *out);
int nv_midi_n_mts(void *p);
void nv_midi_mts(void *p, int i, double *t, long *seq, int *bank, int *prog, double *hz);
int nv_midi_gs(void *p);
int nv_midi_gs_setup(void *p, int which, int key, int *v);
void nv_midi_note(void *p, int i, int *iv, double *dv);
void nv_midi_cc(void *p, int i, int *iv, double *t);
void nv_midi_song(void *p, void *song, const double *trim);
int nv_midi_note_bsel(void *p, int i);
int nv_midi_ats(void *p, int ch, double *t, int *v, int cap);
int nv_midi_ccs(void *p, int ch, int cc, double *t, int *v, int cap);
extern "C" void nv_mouth_track(unsigned long long seed, int n, const double *st, const double *cdf,
                               const double *dwell, double glide, double step, long lgn, float *out);
int nv_midi_pts(void *p, int ch, int key, double *t, int *v, int cap);
int nv_midi_banked(void *p);
int nv_midi_chprog_bsel(void *p, int i);
void *nv_song_new(void);
void nv_song_free(void *s);
void nv_song_tuning(void *s, long long ch, double t, const double *freq);
void nv_song_eastern(void *s, const double *freq_e, int raga_on, int sa, const double *sw, int nsw);
int nv_raga_info(const char *spec, double sa_hz, double *out, int *have, int *sa_note, double *sw, int *nsw);
int nv_tuning_table(const char *name, int ref_note, double ref_hz, double *out, int *have);
int nv_midi_n_pitch(void *p);
void nv_midi_pw(void *p, int i, int *iv, double *t);
void nv_midi_pitch(void *p, int i, int *iv, long *seq, double *t, double *v);
int nv_bend_btun(void *midi, void *song, double bend_range, double *out);
void nv_bend_grid(int blk, double sr);
long long nv_efx_reverb_ir(double sr, int rtype, double pre_ms, int time, double damp_hz, double *hL, double *hR,
                           long long cap);
long long nv_efx_gate_ir(double sr, int gtype, double pre_ms, double gate_ms, double *hL, double *hR, long long cap);
int nv_efx_conv(const double *x, long long nx, const double *h, long long nh, long long k, long long m, double *out);
void nv_tremolo_brmap(long long ch, int n, const long long *from, const long long *to);
int nv_midi_mpe_manager(void *p, int ch, double t);
int nv_midi_has_mpe(void *p);
void nv_bend_fader_channels(const int *fch, int n);
int nv_bend_stream(void *midi, int ch, int with_master, double bend_range, double *t, double *r, int cap);
void nv_bend_rows(const double *t, const double *r, int n, long nblk, int blk, double sr, float *BR, double *BC);
void nv_song_mpe(void *s, long long ch, int note, double on, double r0, double row, int mgr);
int nv_meend_note(const double *wt, const int *wp, int nw, double on, double off, double nc, const double *sw,
                  int nsw, double rst, double strength, long nblk, int blk, double sr, double *r0, float *BR,
                  double *BC);
int nv_bend_gesture(void *midi, void *song, double bend_range, int ch, long nblk, int blk, double sr, float *BR,
                    double *BC);
void nv_play_growth(long long *cap0, long long *need);
int nv_bend_fader(void *midi, void *song, int ch, long nblk, int blk, double sr, double tau, double fader_tail,
                  double stamp_s, double stamped_share, int vol0, int expr0, float *L, const unsigned char *swell);
int nv_midi_n_chprogs(void *p);
void nv_midi_chprog(void *p, int i, int *iv);
void nv_song_channel(void *s, long long ch, double btun, const double *otun, int fader);
void nv_song_finish(void *s, double total);
long long nv_prepare(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                     PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind, double scale,
                     double full_db_s, double residual, double beta, long long blk, double total, double ring_floor,
                     double ring_max, double *out, double knee_db, double ln10_20, double xdec_nepers, double SR,
                     void **dm, int with_register);
int nv_render(void *sv, void *sx, void *sd, long N, int BLK, int nblk, long long P, double *const *d,
              float *const *f, long *const *l, int *const *ii, const float *G, const float *S, const float *BR,
              const double *BC, const float *BL, const float *noRows, const float *sh, long CHUNK, double xdec_nepers,
              double SR, double master_gain, const float *DM, const long *DMO, const long *DMB, const long *DMN,
              float *L, float *R, void *slo, const int *lsr, float *const *lob, const float *LANG, long lgn,
              const MoogCols *moog, const int *fsr, const int *fty, const float *const *fpar, const float *FCT,
              long fgn, const unsigned char *rowsel, int post);
void nv_render_post(float *L, float *R, long N, double SR, double master_gain, int clip);
int nv_render_win(void *sv, void *sx, void *sd, long N, int BLK, int nblk, long long P, double *const *d,
                  float *const *f, long *const *l, int *const *ii, const float *G, const float *S, const float *BR,
                  const double *BC, const float *BL, const float *noRows, const float *sh, long CHUNK,
                  double xdec_nepers, double SR, double master_gain, const float *DM, const long *DMO,
                  const long *DMB, const long *DMN, float *L, float *R, void *slo, const int *lsr,
                  float *const *lob, const float *LANG, long lgn, const MoogCols *moog, const int *fsr,
                  const int *fty, const float *const *fpar, const float *FCT, long fgn,
                  const unsigned char *rowsel, int post, long n0, long wn, const long long *live,
                  long long nlive);
void nv_buf_free(void *p);
void *nv_livebus_raw_new(int kind, const double *p, double sr);
void nv_livebus_raw(void *h, const float *x0, const float *x1, long n, float *y0, float *y1);
void nv_livebus_free(void *h);
void nv_render_post_win(float *L, float *R, long n0, long N, double SR, double master_gain, int clip);
// THE STREAMING RENDER (--stream): engine.cpp's sink and refusals, register.cpp's replay,
// prepare.cpp's ring
void nv_play_set_sink(const void *s);
void nv_play_set_reg_sink(const void *s);
double nv_cab_gain(const NoteClass *k, double f);
int nv_stream_note(int j, int *i, int *band, double *land);
long nv_damp_track(void *song, int i, const double *rows, long long nr, double land, double SR, long long blk,
                   long long nblk, double full_db_s, double residual, double knee_db, long long *b0, double *f0,
                   float *dc, long cap);
long long nv_play_own_end(int j, long long dflt);
int nv_chorus_row(double *r, int kind, double send, int nc, const double *cents, double sr, double *cp, int *ci_out);
void *nv_leslie_new(int nch, const long long *chans, const int *nreq, const double *req, double sr, const double *L,
                    const double *gs, const double *place);
void nv_leslie_free(void *h);
int nv_leslie_row(void *h, double *r, double *cp, float *lob, int *on);
long nv_amp_segment(const double *const *live, long nl, double a, double b, double drive, double ref, double imb,
                    double sr, double **out, long *src_i);
void nv_stream_refuse(const char *why);
const char *nv_stream_why(void);
void nv_stream_reset(void);
long long nv_play_replay(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                         PyRandom *rs, double *qacc, double *azimuth, const int *kind, long long blk);
long long nv_ring_last(const double *rows, long long n, double floor_, double sr);
void *nv_gsd_new(const NoteClass *const *K, void *song, const int *kind, double sr);
long nv_gsd_note(void *h, int j, int ni, const double *R, long long i0, long long iown, long long i1, double **out,
                 long long *last);
void nv_gsd_free(void *h);
void *nv_mf104_new(void *song, const int *kind, double sr);
long nv_mf104_note(void *h, double *R, long long i0, long long i1, double **out, long long *last);
void nv_mf104_free(void *h);
int nv_song_moog_dup_of(void *s, int r, int *parent, long long *gp, long long *gs);
int nv_tremolo_row(const double *row, const double *c, long long ch, const double *H, int nh, double sr, double *out);
void *nv_scan_new(const double *X);
void nv_scan_row(void *h, double *r, int depth, int chorus, int row0, double nmax, double sr, double *cp, int *nch,
                 int *nsd);
// a stream's scanner channel: its mix channel, band rows, depth, chorus
struct ScanCh {
    long long ch;
    int row0, depth, chorus;
};
int nv_chorus_dev_row(double *r, const double *G, const double *TV, int ntv, double share, int kmax, double sr,
                      double *cp, int *ix, int cap);
int nv_play_sink_note(void);
long long nv_play_own_end(int j, long long dflt);
long long nv_tremolo_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                            const double *cfg, const char *mask, long long nmask, double sr);
long long nv_leslie_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                           const int *nreq, const double *req, double sr, const double *L, void **lobe,
                           long long **flips, long long *nflips);
long long nv_amp_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                        const double *drives, const double *refs, const double *imbs, double sr);
void nv_breath_rows(unsigned long long seed, long nblk, int blk, double sr, const double *p, float *br, double *bc,
                    float *tl, float *nl);
void nv_scan_rows(const double *X, long nblk, int blk, double sr, int depth, int chorus, float *br, double *bc);
long long nv_scan_expand(const double *X, double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                         const int *row0s, const int *depths, const int *choruses, double sr);
long nv_leslie_angles(int nch, const int *nreq, const double *req, long n_samples, double sr, int blk,
                      const double *L, float *LANG);
long long nv_leslie_expand_gs(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                              const int *nreq, const double *req, double sr, const double *L, void **lobe,
                              long long **flips, long long *nflips, const double *gs, const double *place);
long nv_leslie_angles_gs(int nch, const int *nreq, const double *req, long n_samples, double sr, int blk,
                         const double *L, float *LANG, const double *gs);
void nv_npy_noise(long long n0, long n, unsigned long long seed, int normal, double *out);
int nv_efx_chain(const double *X, double SR, int msb, int lsb, const int *p, const int *snd,
                 const int *ctl, int ncv, const int *cv_src, const int *cv_val, double *rec,
                 double *recb, int *has_b, const char **why);
}

// the export's constants, in native_export.py's order
enum { K_SR, K_BLK, K_CHUNK, K_MASTER, K_RING_FLOOR, K_RING_MAX, K_XDEC, K_REG_SCALE, K_FULL, K_RESIDUAL, K_BETA,
       K_KNEE, K_LN10_20, K_RETRIGGER, K_NYQ_OM, K_SVDC, K_FIXED_TOUCH, K_REFLECT, K_BANDS, K_SH = K_BANDS + 9,
       K_PRESS_DB = K_SH + 4, K_THRESH, K_BEND_RANGE, K_TAU, K_FADER_TAIL, K_STAMP_S, K_STAMPED_SHARE,
       K_BEND_SEMIS, K_GM_VOL, K_GM_EXPR, K_GSPLACE,         // (K_GSPLACE: 13, a GS chorus's outputs)
       K_MAPKITS = K_GSPLACE + 13,                          // (the maps' own drum sets: n, then 32)
       K_EFX = K_MAPKITS + 33 };                            // (a file's insertion effect's tables: their own layout)

// blockrender.EMIT_COLS
static const char *COLS[NCOLS] = {
    "om", "p0", "p0R", "aL", "aR", "aM", "mch", "px", "pz", "az", "dr", "nf", "non", "noff", "fa", "re", "ch",
    "logr", "logrA", "aft", "sus", "cv", "cc", "crl", "sj", "csc", "cbw", "tbav", "tau", "tcut", "gb", "gt",
    "gc", "vd", "vr", "vp", "vdl", "delL", "delR", "gr", "cr", "br", "pl", "fx", "mk", "rdl", "fmw", "nfr",
    "fmp", "fmpR"};
static const char *VF[] = {"aL", "aR", "nf", "fa", "re", "ch", "logr", "logrA", "aft", "sus", "cv", "cc", "crl",
                           "sj", "csc", "cbw", "tbav", "tau", "tcut", "gb", "gt", "gc", "vd", "vr", "vp", "vdl",
                           "delL", "delR"};

static int col(const char *name)
{
    for (int c = 0; c < NCOLS; c++)
        if (!strcmp(COLS[c], name))
            return c;
    return -1;
}

// tremolo.expand (live.cpp's nv_tremolo_expand): each channel's (rate, depth,
// stereo, scatter) as the library takes them
// AN INSERTION EFFECT's EQ on one row (gsefx.eq_gain: e = lo dB, mid Hz, Q, mid dB, hi dB, lo Hz,
// hi Hz, the type's more mids): its gain at the row's frequency on aL, aR, aM (EMIT_COLS)
static void eq_row(const std::vector<double> &e, double *row)
{
    double f = row[11];
    double x = f / e[5], y = f / e[6];
    x = x * x;
    y = y * y;
    double db = e[0] / (1.0 + x) + e[4] * y / (1.0 + y);
    for (size_t j = 1; j < e.size(); j += j == 1 ? 6 : 3) {     // (the mid, then the type's more)
        double mf = e[j], q = e[j + 1], mg = e[j + 2];
        if (mf != 0.0 && mg != 0.0) {
            double u = q * (f / mf - mf / (f + 1e-6 * (f <= 0.0 ? 1.0 : 0.0)));
            db += mg / (1.0 + u * u);
        }
    }
    double g = pow(10.0, db / 20.0);
    for (int c : {3, 4, 5})
        row[c] = row[c] * g;
}

// --stream: the streaming render (what it does not reproduce yet refuses it: nv_stream_refuse)
// A STREAMED ROW, STORED IN ITS TABLE's TYPES (streamrender's store: typed
// columns, each the dtype prepare gives it -- FINAL_DTYPES): float32 where the
// column is, int32 and int64 where those are, float64 for the rest. A window
// reads every column cast to that type anyway, so nothing a sample sees moves;
// a row is about half the 50 float64s it was
static int g_pk[NCOLS], g_po[NCOLS], g_rowB = 8 * NCOLS;
static void pack_layout(const int *fin)
{
    int o = 0;
    for (int c = 0; c < NCOLS; c++) {
        g_pk[c] = fin[c] == 1 || fin[c] == 3 ? fin[c] : fin[c] == 2 ? 2 : 0;
        g_po[c] = o;
        o += g_pk[c] == 1 || g_pk[c] == 3 ? 4 : 8;
    }
    g_rowB = o;
}
static void pack_row(const double *x, unsigned char *b)
{
    for (int c = 0; c < NCOLS; c++)
        switch (g_pk[c]) {
        case 1: { float v = (float)x[c]; memcpy(b + g_po[c], &v, 4); break; }
        case 2: { long long v = (long long)x[c]; memcpy(b + g_po[c], &v, 8); break; }
        case 3: { int32_t v = (int32_t)x[c]; memcpy(b + g_po[c], &v, 4); break; }
        default: memcpy(b + g_po[c], &x[c], 8);
        }
}
static inline double unpack(const unsigned char *b, int c)
{
    switch (g_pk[c]) {
    case 1: { float v; memcpy(&v, b + g_po[c], 4); return (double)v; }
    case 2: { long long v; memcpy(&v, b + g_po[c], 8); return (double)v; }
    case 3: { int32_t v; memcpy(&v, b + g_po[c], 4); return (double)v; }
    default: { double v; memcpy(&v, b + g_po[c], 8); return v; }
    }
}

static bool g_stream = false;
static bool g_stream_why_only = false;      // (--stream-why: the scan's reasons, no render)
static bool g_gpu = false;                  // (--gpu: the stream's windows on the GPU, gpufile.h)
// a note's rows as a sink is handed them (engine.cpp's NvPlaySink)
struct StreamSinkDesc {
    void *ctx;
    void (*note)(void *ctx, const double *at, long long i0, long long i1, double next_on);
};
static void stream_cast(double *r, const int *kind)    // (nv_play_full's cast: as the table holds them)
{
    for (int c = 0; c < NCOLS; c++)
        if (kind[c] == 1)
            r[c] = (double)(float)r[c];
        else if (kind[c] == 2)
            r[c] = (double)(int32_t)r[c];
}
// a stream's register sink (register.cpp's RegSinkDesc): a channel's ready
// rows with their (phase, seq), and the horizon after each note
struct StreamRegDesc {
    void *ctx;
    void (*rows)(void *ctx, int rank, const double *rows, const long long *phase, const long long *seq, long n);
    void (*horizon)(void *ctx, double h);
};
// A STREAM's CHORUS DEVICE (a kind 2 entry): its record, its own voices, its
// share's steps (none: G[5]; samp: in samples, else seconds) and the passes its
// channel makes (pass A's loudest row's)
struct StreamDev {
    std::vector<double> G, TV, ts, vs;
    bool samp = false;
    int kmax = 0;
    double share_at(double non, double sr) const
    {
        if (ts.empty())
            return G[5];
        double x = samp ? non : non / sr;
        long i = (long)(std::upper_bound(ts.begin(), ts.end(), x) - ts.begin()) - 1;
        return vs[i < 0 ? 0 : i >= (long)vs.size() ? (long)vs.size() - 1 : i];
    }
};
// PASS A: the scan -- the ring's end and the channels heard, nothing kept
struct StreamScan {
    const int *kind = nullptr;
    double floor_ = 0.0, sr = 0.0;
    int cM = 0;
    long long rl = 0, rows = 0;
    std::set<long long> heard;
    std::vector<double> buf;
    void *gsd = nullptr;                    // (the delays' repeats: their ring and their last)
    void *mf = nullptr;                     // (the MF-104M's: its layers walked as they land)
    std::map<long long, std::vector<double>> nons;      // (each channel's onsets: a chorus device's loudest)
    std::map<long long, double> noffs;      // (...and its last release: an amplifier's products end by it)
    std::set<long long> regch;              // (the register's channels: a scanner's refusal)
    void rec(const double *x, long n)
    {
        for (long r = 0; r < n; r++) {
            const long long m_ = (long long)x[NCOLS * r + cM];
            auto nf_ = noffs.find(m_);
            if (nf_ == noffs.end())
                noffs[m_] = x[NCOLS * r + 13];
            else
                nf_->second = std::max(nf_->second, x[NCOLS * r + 13]);
            std::vector<double> &v = nons[m_];
            double t = x[NCOLS * r + 12];
            if (v.empty() || v.back() != t)
                v.push_back(t);
        }
    }
    int jn = 0;
    long long glast = 0;
    static void note(void *c_, const double *at, long long i0, long long i1, double)
    {
        StreamScan &c = *(StreamScan *)c_;
        long long n = i1 - i0;
        if (n <= 0)
            return;
        c.buf.assign(at, at + NCOLS * n);
        for (long long r = 0; r < n; r++) {
            stream_cast(c.buf.data() + NCOLS * r, c.kind);
            c.heard.insert((long long)c.buf[NCOLS * r + c.cM]);
        }
        c.rec(c.buf.data(), n);
        if (c.mf) {                         // (the MF-104M's: its dry share, its repeats)
            double *g = nullptr;
            long long gl = 0;
            long m = nv_mf104_note(c.mf, c.buf.data(), i0, i1, &g, &gl);
            if (m > 0) {
                c.rec(g, m);
                c.rl = std::max(c.rl, nv_ring_last(g, m, c.floor_, c.sr));
                c.rows += m;
            }
            free(g);
            c.glast = std::max(c.glast, gl);
        }
        c.rl = std::max(c.rl, nv_ring_last(c.buf.data(), n, c.floor_, c.sr));
        c.rows += n;
        const int j = c.jn++;
        if (c.gsd) {
            double *g = nullptr;
            long long gl = 0;
            long m = nv_gsd_note(c.gsd, j, nv_play_sink_note(), c.buf.data(), i0, nv_play_own_end(j, i1), i1, &g, &gl);
            if (m > 0) {
                c.rec(g, m);
                c.rl = std::max(c.rl, nv_ring_last(g, m, c.floor_, c.sr));
                c.rows += m;
            }
            free(g);
            c.glast = std::max(c.glast, gl);
        }
    }
    // ...and the register's strings' (cast already)
    static void reg_rows(void *c_, int, const double *at, const long long *, const long long *, long n)
    {
        StreamScan &c = *(StreamScan *)c_;
        if (n <= 0)
            return;
        for (long r = 0; r < n; r++) {
            c.heard.insert((long long)at[NCOLS * r + c.cM]);
            c.regch.insert((long long)at[NCOLS * r + c.cM]);
        }
        c.rec(at, n);
        c.rl = std::max(c.rl, nv_ring_last(at, n, c.floor_, c.sr));
        c.rows += n;
    }
    static void reg_horizon(void *, double) {}
};

static long long tremolo_expand(double **rowsp, long long *Pp, void **dm, const std::map<int, std::vector<double>> &chans,
                                const std::vector<char> *mask, double sr)
{
    std::vector<long long> ch;
    std::vector<double> cfg;
    for (auto &kv : chans) {
        ch.push_back(kv.first);
        cfg.insert(cfg.end(), kv.second.begin(), kv.second.begin() + 4);
    }
    return nv_tremolo_expand(rowsp, Pp, dm, (int)ch.size(), ch.data(), cfg.data(), mask ? mask->data() : nullptr,
                             mask ? (long long)mask->size() : 0, sr);
}

// A CLASS IN THE EXPORT, mapped from the file where it lies (copy on write):
// only the classes a song plays are ever read in -- prepare's way, which
// builds the voices a file uses and no others
struct ClassRef {
    unsigned char *p = nullptr;
    unsigned char *data() const { return p; }
};

struct Export {
    std::vector<double> k, freq, trim;
    std::vector<ClassRef> classes;
    std::vector<int> cmap, kind, fin;     // cmap: the programs' keys, then the drum sets'
    std::vector<double> kit_f0, kit_seat;
    std::vector<int> mk_ids, mk_map;            // MKIT: the maps' own drum sets, their keys' classes
    std::vector<unsigned long long> kit_choke;
    std::vector<int> kit_skind;
    std::vector<double> kit_spar;
    std::string room, libs[3];
    OrganSpec *organs = nullptr;          // ORGA: the registered organs' tables, mapped as the classes
    std::vector<int> cls_organ, prog_organ;   // each class's organ, each program's (-1 none, -2 not the engine's)
    std::vector<double> les;              // LESL: the rotating speaker's constants
    std::string lobe_lib;                 // ...and synth_voice_lobe's library
    std::vector<double> scan;             // SCAN: the scanner's constants and tables
    // VARS (bank select): the slots' classes at each key (cmap's, slot by
    // slot), the entries (each layer's slot, semitones, velocities; its
    // trims, a GS file's second), GS's table [map][program][msb] and GM 2's
    // [program][lsb] -- entry 0 the capital tone
    int nslot = 0;
    std::vector<int> vmap;
    std::vector<int> dmap;                // DRON: K's drone region (256; none: all -1)
    struct VarEnt {
        std::vector<std::array<int, 4>> ls;
        double trim[2] = {1.0, 1.0};
        int pcls = -1;                    // its program's class (_prep_breath's): -1 none, -2 one that breathes, not the engine's
    };
    std::vector<VarEnt> vents;
    std::vector<int> vgs, vgm2;
};

static bool read_export(const char *path, Export &E)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return false;
    char magic[4];
    int nk, csz, ncls;
    bool ok = fread(magic, 1, 4, f) == 4 && !memcmp(magic, "NVX1", 4) && fread(&nk, 4, 1, f) == 1
              && fread(&csz, 4, 1, f) == 1 && fread(&ncls, 4, 1, f) == 1 && csz == (int)sizeof(NoteClass);
    if (ok) {
        E.k.resize(nk); E.freq.resize(128); E.trim.resize(512); E.cmap.resize(2 * NV_K_DRUMS);
        E.kit_f0.resize(16384); E.kit_seat.resize(16384); E.kit_choke.resize(2 * 16384);
        E.kit_skind.resize(16384); E.kit_spar.resize(NV_SPAR * 16384);
        E.kind.resize(NCOLS); E.fin.resize(NCOLS);
        ok = fread(E.k.data(), 8, nk, f) == (size_t)nk && fread(E.freq.data(), 8, 128, f) == 128
             && fread(E.trim.data(), 8, 512, f) == 512;
        void *m = MAP_FAILED;
        long len = 0;
        if (ok) {                           // (the classes mapped, not read: nothing loaded until used)
            const long off = ftell(f);
            fseek(f, 0, SEEK_END);
            len = ftell(f);
            m = len > off ? mmap(nullptr, (size_t)len, PROT_READ | PROT_WRITE, MAP_PRIVATE, fileno(f), 0)
                          : MAP_FAILED;
            ok = m != MAP_FAILED && off + (long)csz * ncls <= len && off % alignof(NoteClass) == 0;
            if (ok)                         // (no readahead: a class's few fields, not the classes around it)
                madvise(m, (size_t)len, MADV_RANDOM);
            for (int i = 0; ok && i < ncls; i++)
                E.classes.push_back(ClassRef{(unsigned char *)m + off + (long)csz * i});
            ok = ok && fseek(f, off + (long)csz * ncls, SEEK_SET) == 0;
        }
        ok = ok && fread(E.cmap.data(), 4, 2 * NV_K_DRUMS, f) == 2 * NV_K_DRUMS
             && fread(E.kit_f0.data(), 8, 16384, f) == 16384 && fread(E.kit_seat.data(), 8, 16384, f) == 16384
             && fread(E.kit_choke.data(), 8, 2 * 16384, f) == 2 * 16384
             && fread(E.kit_skind.data(), 4, 16384, f) == 16384 && fread(E.kit_spar.data(), 8, NV_SPAR * 16384, f) == NV_SPAR * 16384
             && fread(E.kind.data(), 4, NCOLS, f) == NCOLS
             && fread(E.fin.data(), 4, NCOLS, f) == NCOLS;
        std::string *ss[4] = {&E.room, &E.libs[0], &E.libs[1], &E.libs[2]};
        for (int i = 0; ok && i < 4; i++) {
            int n;
            ok = fread(&n, 4, 1, f) == 1;
            if (ok) {
                ss[i]->resize(n);
                ok = fread(&(*ss[i])[0], 1, n, f) == (size_t)n;
            }
        }
        // ORGA: the registered organs' tables -- after their pad, mapped where
        // they lie (an organ's pages read in as its notes play) -- each class's
        // organ, each program's
        char om[4];
        int norg = 0, osz = 0, opad = 0;
        ok = ok && fread(om, 1, 4, f) == 4 && !memcmp(om, "ORGA", 4) && fread(&norg, 4, 1, f) == 1
             && fread(&osz, 4, 1, f) == 1 && osz == (int)sizeof(OrganSpec) && fread(&opad, 4, 1, f) == 1;
        if (ok) {
            const long ooff = ftell(f) + opad;
            ok = ooff % (long)alignof(OrganSpec) == 0 && ooff + (long)sizeof(OrganSpec) * norg <= len;
            E.organs = (OrganSpec *)((unsigned char *)m + ooff);
            E.cls_organ.resize(ncls);
            E.prog_organ.resize(128);
            ok = ok && fseek(f, ooff + (long)sizeof(OrganSpec) * norg, SEEK_SET) == 0
                 && fread(E.cls_organ.data(), 4, ncls, f) == (size_t)ncls && fread(E.prog_organ.data(), 4, 128, f) == 128;
        }
        // LESL: the rotating speaker's constants (leslie.cpp's) and the lobe's kernel
        char lt[4];
        long pos = ftell(f);
        if (ok && fread(lt, 1, 4, f) == 4 && !memcmp(lt, "LESL", 4)) {
            int nl = 0, n = 0;
            ok = fread(&nl, 4, 1, f) == 1;
            if (ok) {
                E.les.resize(nl);
                ok = fread(E.les.data(), 8, nl, f) == (size_t)nl && fread(&n, 4, 1, f) == 1;
            }
            if (ok) {
                E.lobe_lib.resize(n);
                ok = fread(&E.lobe_lib[0], 1, n, f) == (size_t)n;
            }
            // SCAN: the scanner's constants and circuit tables (scanner.cpp's)
            pos = ftell(f);
            if (ok && fread(lt, 1, 4, f) == 4 && !memcmp(lt, "SCAN", 4)) {
                int ns = 0;
                ok = fread(&ns, 4, 1, f) == 1;
                if (ok) {
                    E.scan.resize(ns);
                    ok = fread(E.scan.data(), 8, ns, f) == (size_t)ns;
                }
            } else {
                fseek(f, pos, SEEK_SET);
            }
        // VBOD: the voice parts a track's name declares (voice.c's table)
        {
            long vp = ftell(f);
            char vt[4];
            int vh[3];
            if (ok && fread(vt, 1, 4, f) == 4 && !memcmp(vt, "VBOD", 4) && fread(vh, 4, 3, f) == 3) {
                std::vector<char> blob(vh[2] + 1, 0);
                std::vector<double> vr(vh[0]), vc(vh[0]);
                ok = fread(blob.data(), 1, vh[2], f) == (size_t)vh[2] && fread(vr.data(), 8, vh[0], f) == (size_t)vh[0]
                     && fread(vc.data(), 8, vh[0], f) == (size_t)vh[0];
                if (ok)
                    nv_voice_bodies_set(vh[0], blob.data(), vr.data(), vc.data(), vh[1]);
            } else {
                fseek(f, vp, SEEK_SET);
            }
        }
        // VARS: bank select (native.variation_tables) -- the slots and their
        // classes at each key, the entries a program change selects, GS's and GM 2's tables
        {
            long vp = ftell(f);
            char vt[4];
            int vl = 0;
            if (ok && fread(vt, 1, 4, f) == 4 && !memcmp(vt, "VARS", 4) && fread(&vl, 4, 1, f) == 1) {
                int ns = 0, ne = 0;
                ok = fread(&ns, 4, 1, f) == 1;
                std::vector<int> pvl(3 * (size_t)ns);
                ok = ok && fread(pvl.data(), 4, pvl.size(), f) == pvl.size();
                E.vmap.resize(128 * (size_t)ns);
                ok = ok && fread(E.vmap.data(), 4, E.vmap.size(), f) == E.vmap.size() && fread(&ne, 4, 1, f) == 1;
                E.vents.assign(1, Export::VarEnt{});
                for (int e = 0; ok && e < ne; e++) {
                    int h[3];
                    Export::VarEnt v;
                    ok = fread(h, 4, 3, f) == 3;
                    v.ls.resize(ok ? h[2] : 0);
                    for (auto &l : v.ls)
                        ok = ok && fread(l.data(), 4, 4, f) == 4;
                    E.vents.push_back(v);
                }
                E.vgs.resize(5 * 128 * 128);
                E.vgm2.resize(128 * 128);
                ok = ok && fread(E.vgs.data(), 4, E.vgs.size(), f) == E.vgs.size()
                     && fread(E.vgm2.data(), 4, E.vgm2.size(), f) == E.vgm2.size();
                for (int e = 1; ok && e <= ne; e++)
                    ok = fread(E.vents[e].trim, 8, 2, f) == 2;
                for (int e = 1; ok && e <= ne; e++)
                    ok = fread(&E.vents[e].pcls, 4, 1, f) == 1;
                E.nslot = ns;
            } else {
                fseek(f, vp, SEEK_SET);
            }
        }
        // DRON: K's drone region (a bagpipe's drones), 256 class indices
        {
            long dp = ftell(f);
            char dt[4];
            int dl = 0;
            if (ok && fread(dt, 1, 4, f) == 4 && !memcmp(dt, "DRON", 4) && fread(&dl, 4, 1, f) == 1 && dl == 4 * 256) {
                E.dmap.resize(256);
                ok = fread(E.dmap.data(), 4, 256, f) == 256;
            } else {
                fseek(f, dp, SEEK_SET);
            }
        }
        // MKIT: the maps' own drum sets, after the 128: their keys' classes
        // and tables, appended where set 128 + j's would be (kit_f0's ...)
        {
            long mp = ftell(f);
            char mt[4];
            int ml = 0, nm = 0;
            if (ok && fread(mt, 1, 4, f) == 4 && !memcmp(mt, "MKIT", 4) && fread(&ml, 4, 1, f) == 1
                && fread(&nm, 4, 1, f) == 1) {
                size_t n = 128 * (size_t)nm;
                E.mk_ids.resize(nm);
                E.mk_map.resize(n);
                std::vector<double> f0(n), seat(n), spar(NV_SPAR * n);
                std::vector<unsigned long long> ch(2 * n);
                std::vector<int> sk(n);
                ok = fread(E.mk_ids.data(), 4, nm, f) == (size_t)nm && fread(E.mk_map.data(), 4, n, f) == n
                     && fread(f0.data(), 8, n, f) == n && fread(seat.data(), 8, n, f) == n
                     && fread(ch.data(), 8, 2 * n, f) == 2 * n && fread(sk.data(), 4, n, f) == n
                     && fread(spar.data(), 8, NV_SPAR * n, f) == NV_SPAR * n;
                E.kit_f0.insert(E.kit_f0.end(), f0.begin(), f0.end());
                E.kit_seat.insert(E.kit_seat.end(), seat.begin(), seat.end());
                E.kit_choke.insert(E.kit_choke.end(), ch.begin(), ch.end());
                E.kit_skind.insert(E.kit_skind.end(), sk.begin(), sk.end());
                E.kit_spar.insert(E.kit_spar.end(), spar.begin(), spar.end());
            } else {
                fseek(f, mp, SEEK_SET);
            }
        }
        } else {
            fseek(f, pos, SEEK_SET);
        }
    }
    fclose(f);
    return ok;
}

// Python's repr of a float (json's): the shortest round-trip digits, fixed
// for an exponent from -4 to 15, else d.ddde+XX
static std::string pyrepr(double v)
{
    if (std::isinf(v))
        return v > 0 ? "Infinity" : "-Infinity";
    if (std::isnan(v))
        return "NaN";
    char buf[64];
    auto r = std::to_chars(buf, buf + sizeof buf, v, std::chars_format::scientific);
    std::string s(buf, r.ptr);
    size_t e = s.find('e');
    std::string mant = s.substr(0, e);
    int ex = atoi(s.c_str() + e + 1);
    bool neg = mant[0] == '-';
    if (neg)
        mant = mant.substr(1);
    std::string digits;
    for (char c : mant)
        if (c != '.')
            digits += c;
    std::string out;
    if (ex >= -4 && ex < 16) {
        if (ex >= 0) {
            if ((int)digits.size() <= ex + 1) {
                out = digits + std::string(ex + 1 - digits.size(), '0') + ".0";
            } else {
                out = digits.substr(0, ex + 1) + "." + digits.substr(ex + 1);
            }
        } else {
            out = "0." + std::string(-ex - 1, '0') + digits;
        }
    } else {
        out = digits.substr(0, 1);
        if (digits.size() > 1)
            out += "." + digits.substr(1);
        char eb[16];
        snprintf(eb, sizeof eb, "e%c%02d", ex < 0 ? '-' : '+', ex < 0 ? -ex : ex);
        out += eb;
    }
    return (neg ? "-" : "") + out;
}

static bool write_wav(const char *path, const float *L, const float *R, long n, int sr)
{
    FILE *f = fopen(path, "wb");
    if (!f)
        return false;
    uint32_t data = (uint32_t)(n * 2 * 4);
    auto u32 = [&](uint32_t v) { fwrite(&v, 4, 1, f); };
    auto u16 = [&](uint16_t v) { fwrite(&v, 2, 1, f); };
    fwrite("RIFF", 1, 4, f); u32(36 + data); fwrite("WAVE", 1, 4, f);
    fwrite("fmt ", 1, 4, f); u32(16); u16(1); u16(2); u32((uint32_t)sr); u32((uint32_t)sr * 8); u16(8); u16(32);
    fwrite("data", 1, 4, f); u32(data);
    std::vector<int32_t> buf(2 * n);
    for (long i = 0; i < n; i++) {
        for (int c = 0; c < 2; c++) {
            double x = c ? (double)R[i] : (double)L[i];
            x = x < -1.0 ? -1.0 : (x > 1.0 ? 1.0 : x);         // np.clip
            buf[2 * i + c] = (int32_t)(x * 2147483647.0);    // astype('<i4'): toward zero
        }
    }
    fwrite(buf.data(), 4, buf.size(), f);
    fclose(f);
    return true;
}

int main(int argc, char **argv)
{
    if (argc < 4) {
        fprintf(stderr, "usage: nvrender EXPORT.nvx IN.mid OUT.wav [--tuner=NAME [--a=HZ | --c=HZ]]\n");
        return 1;
    }
    Export E;
    if (!read_export(argv[1], E)) {
        fprintf(stderr, "nvrender: cannot read %s (or it is not this build's)\n", argv[1]);
        return 1;
    }
    // the variations' keys after the drum sets' (NV_K_VAR + 128 x slot + key)
    E.dmap.resize(256, -1);                 // (the drones' region, NV_K_DRONE: before the variations)
    E.cmap.insert(E.cmap.end(), E.dmap.begin(), E.dmap.end());
    E.cmap.insert(E.cmap.end(), E.vmap.begin(), E.vmap.end());
    // ...and the maps' own drum sets' after them (a drum program 128 + j: nv_song_mapk_base)
    const int mapk_base = (int)E.cmap.size();
    nv_song_mapk_base(mapk_base);
    E.cmap.insert(E.cmap.end(), E.mk_map.begin(), E.mk_map.end());
    // each class's organ, its table here (the export's pointer was the exporter's)
    for (size_t i = 0; i < E.classes.size(); i++)
        ((NoteClass *)E.classes[i].data())->organ = E.cls_organ[i] >= 0 ? &E.organs[E.cls_organ[i]] : nullptr;
    for (size_t i = 0; i < E.classes.size(); i++) {     // a struck layer's class (sl_idx)
        NoteClass *nc = (NoteClass *)E.classes[i].data();
        nc->sl = nc->sl_on && nc->sl_idx >= 0 && nc->sl_idx < (int)E.classes.size()
                 ? (const NoteClass *)E.classes[nc->sl_idx].data() : nullptr;
    }
    // THE TUNER, if named: its table in place of the export's
    std::string tname, ra, rc, east = getenv("TUNING_EASTERN") ? getenv("TUNING_EASTERN") : "";
    long win = 0;                           // --window=W: the table rendered W samples at a time
    for (int i = 4; i < argc; i++) {
        if (!strncmp(argv[i], "--tuner=", 8))
            tname = argv[i] + 8;
        else if (!strncmp(argv[i], "--window=", 9))
            win = atol(argv[i] + 9);
        else if (!strcmp(argv[i], "--stream-why"))
            g_stream = g_stream_why_only = true;
        else if (!strcmp(argv[i], "--stream"))
            g_stream = true;
        else if (!strcmp(argv[i], "--gpu"))
            g_gpu = g_stream = true;        // (the GPU renders the stream's windows: streamrender's gpu=)
        else if (!strncmp(argv[i], "--eastern=", 10))
            east = argv[i] + 10;
        else if (!strncmp(argv[i], "--a=", 4))
            ra = argv[i] + 4;
        else if (!strncmp(argv[i], "--c=", 4))
            rc = argv[i] + 4;
    }
    if (!tname.empty()) {
        double F[128];
        int have[128];
        int r = nv_tuning_table(tname.c_str(), !ra.empty() ? 69 : !rc.empty() ? 60 : -1,
                                !ra.empty() ? atof(ra.c_str()) : !rc.empty() ? atof(rc.c_str()) : 0.0, F, have);
        if (r) {
            fprintf(stderr, "nvrender: tuner %s refused (%d)\n", tname.c_str(), r);
            return 1;
        }
        for (int n = 0; n < 128; n++)
            E.freq[n] = have[n] ? F[n] : 0.0;
    }
    const double SR = E.k[K_SR];
    const long long BLK = (long long)E.k[K_BLK];
    // THE FILE
    FILE *mf = fopen(argv[2], "rb");
    if (!mf) {
        fprintf(stderr, "nvrender: cannot read %s\n", argv[2]);
        return 1;
    }
    std::vector<uint8_t> bytes;
    for (int c; (c = fgetc(mf)) != EOF;)
        bytes.push_back((uint8_t)c);
    fclose(mf);
    int err = 0;
    if (E.k.size() >= K_MAPKITS + 33) {     // (kit_in_map: the maps' own drum sets)
        std::vector<int> mk;
        for (int q = 0; q < (int)E.k[K_MAPKITS] && q < 32; q++)
            mk.push_back((int)E.k[K_MAPKITS + 1 + q]);
        nv_midi_map_kits(mk.data(), (int)mk.size());
        // (the export's own tables for them: the reader plays them, else refuses them)
        nv_midi_map_kits_play(!E.mk_ids.empty() && E.mk_ids == mk);
    }
    void *midi = nv_midi_read(bytes.data(), (long long)bytes.size(), &err);
    if (!midi) {
        fprintf(stderr, "nvrender: refused: the reader (%d)\n", err);
        return 2;
    }
    if (E.k.size() <= K_GM_EXPR) {
        fprintf(stderr, "nvrender: %s is an export from before the bend passes (native_export.py again)\n", argv[1]);
        return 1;
    }

    // BANK SELECT: the entry a bank selects for a program (Song::bank's), 0
    // the capital; and the class indices a reader's note makes -- a
    // variation's layers each theirs (none, where no layer takes it)
    auto ent_of = [&](int p, int bs) -> int {
        if (!bs || E.vgs.empty() || p < 0 || p > 127)
            return 0;
        return bs <= 640 ? E.vgs[((size_t)((bs - 1) / 128) * 128 + p) * 128 + (bs - 1) % 128]
                         : E.vgm2[(size_t)p * 128 + (bs - 641)];
    };
    auto note_ks = [&](int i, const int *iv) -> std::vector<int> {
        int en = iv[4] ? 0 : ent_of(iv[3], nv_midi_note_bsel(midi, i));
        if (!en && iv[4] && iv[3] > 127)        // (a map's own drum set)
            return {mapk_base + 128 * (iv[3] - 128) + iv[1]};
        int u[13];
        if (!en && iv[4] && (iv[3] == 64 || iv[3] == 65)
            && ((nv_midi_user_drum(midi, iv[3] - 64, iv[1], u) >> 12) & 1))     // (a user set's key: its source's)
            return {NV_K_DRUMS + 128 * ((nv_midi_user_drum(midi, iv[3] - 64, iv[1], u) >> 11) & 1 ? u[11] : 0) + u[12]};
        if (!en)
            return {(iv[4] ? NV_K_DRUMS : 0) + 128 * iv[3] + iv[1]};
        std::vector<int> r;
        for (const auto &l : E.vents[en].ls) {
            int k = iv[1] + l[1];
            if (k >= 0 && k <= 127 && iv[2] >= l[2] && iv[2] <= l[3])
                r.push_back(NV_K_VAR + 128 * l[0] + k);
        }
        return r;
    };
    if (nv_midi_banked(midi) && E.vgs.empty()) {
        fprintf(stderr, "nvrender: %s is an export from before bank select (native_export.py again)\n", argv[1]);
        return 1;
    }
    std::vector<double> first(256, INFINITY);
    for (int i = 0, n = nv_midi_n_notes(midi); i < n; i++) {
        int iv[5];
        double dv[5];
        nv_midi_note(midi, i, iv, dv);
        if (dv[0] < first[iv[0] & 255])
            first[iv[0] & 255] = dv[0];
        const bool banked = !iv[4] && ent_of(iv[3], nv_midi_note_bsel(midi, i));
        const std::vector<int> nks = note_ks(i, iv);
        for (int kq : nks) {
        int cq = E.cmap[kq];
        if (cq < 0) {
            fprintf(stderr, "nvrender: refused: a note no native voice plays (program %d, key %d%s)\n", iv[3], iv[1],
                    iv[4] ? ", a drum" : banked ? ", a variation" : "");
            return 2;
        }
        const NoteClass *nc = (const NoteClass *)E.classes[cq].data();
        if (getenv("TUNING_AMP_DRIVE") && nc->amp_drive != 0.0) {
            fprintf(stderr, "nvrender: refused: TUNING_AMP_DRIVE (Python's audition)\n");
            return 2;
        }
        if (nc->init.vbody && (getenv("TUNING_LYRIC_LANG") || getenv("TUNING_VOCALISE") || getenv("TUNING_VOICE_PARTS"))) {
            fprintf(stderr, "nvrender: refused: a sung part's text or declared parts (Python's)\n");
            return 2;
        }
        if (getenv("TUNING_CLAV") && nc->clav_panel) {
            fprintf(stderr, "nvrender: refused: TUNING_CLAV (Python's audition)\n");
            return 2;
        }
        }
    }
    // A CHANNEL'S CC91 IS ITS DISTANCE (blockrender's _src_dist): each note
    // moved out along its ray by the engine (NoteIn.dist), the send below.
    // ITS CC93 IS THE CHORUS (_note_chorus_send): not the engine's yet --
    // a part whose first CC93 is past 0, or in a GS file any, is Python's
    {
        std::map<int, std::vector<int>> c93;
        for (int i = 0, n = nv_midi_n_ccs(midi); i < n; i++) {
            int iv[3];
            double t;
            nv_midi_cc(midi, i, iv, &t);
            if (iv[1] == 93)
                c93[iv[0]].push_back(iv[2]);
        }
        for (auto &kv : c93) {
            int mx = *std::max_element(kv.second.begin(), kv.second.end());
            bool sounds = first[kv.first & 255] < 1e300;     // (a channel with notes: em.channel's)
            // (chorus.expand: a send at FLOOR or under makes no copies)
            (void)sounds;
            bool moves = false;
            for (int v : kv.second)
                moves = moves || v != kv.second[0];
            if (nv_midi_gs(midi) && mx > 0 && E.k.size() < K_GSPLACE + 13) {
                fprintf(stderr, "nvrender: refused: a GS chorus send (CC93), an export without its outputs\n");
                return 2;
            }
        }
        // ...and a GS file's CC94, the GS delay's send (gsdelay): its outputs the export's
        for (int i = 0, n = nv_midi_n_ccs(midi); i < n; i++) {
            int iv[3];
            double t;
            nv_midi_cc(midi, i, iv, &t);
            if (iv[1] == 94 && iv[2] > 0 && nv_midi_gs(midi) && E.k.size() < K_GSPLACE + 13) {
                fprintf(stderr, "nvrender: refused: a GS delay send (CC94), an export without its outputs\n");
                return 2;
            }
        }
    }
    // THE FILE'S GS SETUP (blockrender.prepare): its reverb macro's room --
    // the export's, or another's voices (refused) -- unless TUNING_ROOM says;
    // its level and time (a delay's feedback) for the sidecar; its EQ
    std::string gs_tail = "\"tail_gain\": 1.0,\n \"tail_time\": 1.0";
    // ...and its delay (gsdelay.device: Delay 1, then the file's), packed as
    // NoteClass.dly_p: level, feedback, pre-LPF (0 none), time, taps; each
    // tap's time, level, output (0 l, 1 r, 2 c) and period
    double gs_dly[24] = {};
    bool gs_dly_on = false;
    {
        const char *ge = getenv("TUNING_GS_DELAY");
        if (nv_midi_gs(midi) && !(ge && (!*ge || !strcmp(ge, "0") || !strcmp(ge, "off")))
            && E.k.size() >= K_GSPLACE + 13) {
            // gsdelay.MACROS: level, pre-LPF, time (ms), ratio L, R (%), level C, L, R, feedback, to reverb
            static const int MAC[10][10] = {
                {64, 0, 340, 4, 4, 127, 0, 0, 16, 0}, {64, 0, 550, 4, 4, 127, 0, 0, 16, 0},
                {64, 0, 1000, 4, 4, 127, 0, 0, 8, 0}, {64, 0, 130, 4, 4, 127, 0, 0, 8, 0},
                {64, 0, 500, 50, 100, 0, 125, 60, 10, 0}, {64, 0, 700, 50, 100, 0, 125, 60, 7, 0},
                {64, 0, 1000, 50, 100, 0, 120, 64, 9, 0}, {64, 0, 260, 50, 100, 0, 120, 64, 8, 0},
                {64, 0, 700, 50, 100, 0, 114, 60, -3, 36}, {64, 0, 750, 88, 133, 97, 127, 67, -24, 0}};
            auto time_ms = [](int v) {          // (gsdelay.time_ms: DELAY TIME CENTER -> ms)
                v = std::max(1, std::min(0x73, v));
                static const double T[8][3] = {{0x69, 500.0, 50.0}, {0x5A, 200.0, 20.0}, {0x50, 100.0, 10.0},
                                               {0x46, 50.0, 5.0}, {0x37, 20.0, 2.0}, {0x2D, 10.0, 1.0},
                                               {0x23, 5.0, 0.5}, {0x14, 2.0, 0.2}};
                for (auto &r : T)
                    if (v >= r[0])
                        return r[1] + (v - r[0]) * r[2];
                return v * 0.1;
            };
            auto time_value = [&](double ms) {  // (the nearest, the first of equals: min)
                int b = 1;
                for (int v = 2; v < 0x74; v++)
                    if (fabs(time_ms(v) - ms) < fabs(time_ms(b) - ms))
                        b = v;
                return b;
            };
            auto ratio_value = [](double pct) {
                return std::max(1, std::min(0x78, (int)nearbyint(pct * 24.0 / 100.0)));
            };
            int v, m = 0;
            if (nv_midi_gs_setup(midi, 2, 0x50, &v))
                m = v;
            const int *M = MAC[m >= 0 && m <= 9 ? m : 0];
            // pre_lpf, time, ratio_l, ratio_r, level_c, level_l, level_r, level, feedback (40 01 51-59)
            int p[9] = {M[1], time_value(M[2]), ratio_value(M[3]), ratio_value(M[4]), M[5], M[6], M[7], M[0],
                        M[8] + 64};
            for (int q = 0; q < 9; q++)
                if (nv_midi_gs_setup(midi, 2, 0x51 + q, &v))
                    p[q] = v;
            double tc = time_ms(p[1]) / 1000.0;
            gs_dly[0] = p[7] / 127.0;
            gs_dly[1] = (p[8] - 64) / 64.0;
            gs_dly[2] = p[0] ? 12000.0 * pow(2.0, -p[0] / 1.5) : 0.0;
            gs_dly[3] = tc;
            int nt = 0;
            const double rr[3] = {1.0, p[2] * 100.0 / 24.0 / 100.0, p[3] * 100.0 / 24.0 / 100.0};
            const int lv[3] = {p[4], p[5], p[6]}, side[3] = {2, 0, 1};
            for (int q = 0; q < 3; q++)
                if (lv[q] > 0) {
                    gs_dly[5 + 4 * nt] = tc * rr[q];
                    gs_dly[6 + 4 * nt] = lv[q] / 127.0;
                    gs_dly[7 + 4 * nt] = side[q];
                    gs_dly[8 + 4 * nt] = tc;
                    nt++;
                }
            gs_dly[4] = nt;
            gs_dly_on = true;
        }
    }
    // ...and its chorus device (chorus.gs_device: Chorus 3, then the file's):
    // tau, rate, vd, fb, lpf (0 none), level; [0] -1 not a GS file's
    double gs_cho[6] = {-1.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    {
        const char *ge = getenv("TUNING_GS_CHORUS");
        if (nv_midi_gs(midi) && !(ge && (!*ge || !strcmp(ge, "0") || !strcmp(ge, "off")))) {
            // chorus.GS_MACROS: level, pre-LPF, feedback, delay, rate, depth
            static const int MAC[8][6] = {{64, 0, 0, 112, 3, 5}, {64, 0, 5, 80, 9, 19}, {64, 0, 8, 80, 3, 19},
                                          {64, 0, 16, 64, 9, 16}, {64, 0, 64, 127, 2, 24}, {64, 0, 112, 127, 1, 5},
                                          {64, 0, 0, 127, 0, 127}, {64, 0, 80, 127, 0, 127}};
            int v, m = 2;
            if (nv_midi_gs_setup(midi, 1, 0x38, &v))
                m = v;
            int p[6];
            for (int q = 0; q < 6; q++)
                p[q] = MAC[m >= 0 && m <= 7 ? m : 2][q];
            static const int ADDR[6] = {0x3A, 0x39, 0x3B, 0x3C, 0x3D, 0x3E};
            for (int q = 0; q < 6; q++)
                if (nv_midi_gs_setup(midi, 1, ADDR[q], &v))
                    p[q] = v;
            double swing = (p[5] + 1) / 3.2 / 1000.0 / 2.0;
            double rate = p[4] * 0.122;
            gs_cho[0] = p[3] * 0.2 / 1000.0 + swing;
            gs_cho[1] = rate;
            gs_cho[2] = 2.0 * M_PI * rate * swing;
            gs_cho[3] = std::min(0.99, p[2] * 0.763 / 100.0);
            gs_cho[4] = p[1] ? 12000.0 * pow(2.0, -p[1] / 1.5) : 0.0;
            gs_cho[5] = p[0] / 127.0;
        }
    }
    double gs_eq[4] = {0.0, 0.0, 0.0, 0.0};
    std::vector<int> gs_eq_off;
    {
        static const char *ROOMS[8] = {"studio", "chamber", "large_chamber", "hall", "grand_hall", "plate",
                                       "delay", "pan_delay"};
        static const int RTIME[8] = {80, 56, 64, 72, 64, 88, 32, 64};
        const char *tr = getenv("TUNING_ROOM");
        bool fx = !(tr && *tr);
        int mac = -1, lvl = 64, tim = -1, dfb = -1, v;
        if (fx && nv_midi_gs_setup(midi, 0, 0x30, &v))
            mac = v;
        if (fx && nv_midi_gs_setup(midi, 0, 0x33, &v))
            lvl = v;
        if (fx && nv_midi_gs_setup(midi, 0, 0x34, &v))
            tim = v;
        if (fx && nv_midi_gs_setup(midi, 0, 0x35, &v))
            dfb = v;
        if (mac >= 0 && mac <= 7 && E.room != ROOMS[mac]) {
            fprintf(stderr, "nvrender: refused: the GS reverb's room (%s), the export's %s\n", ROOMS[mac],
                    E.room.c_str());
            return 2;
        }
        gs_tail = "\"tail_gain\": " + pyrepr(lvl / 64.0) + ",\n \"tail_time\": "
                  + pyrepr(tim >= 0 ? pow(2.0, (tim - (mac >= 0 && mac <= 7 ? RTIME[mac] : 64)) / 64.0) : 1.0);
        if (mac == 6 || mac == 7)
            gs_tail += ",\n \"delay_fb\": " + std::to_string(dfb >= 0 ? dfb : mac == 6 ? 40 : 32);
        int e[4] = {0, 0x40, 0, 0x40};
        for (int q = 0; q < 4; q++)
            if (nv_midi_gs_setup(midi, 3, q, &v))
                e[q] = v;
        if (e[1] != 0x40 || e[3] != 0x40) {
            gs_eq[0] = e[0] ? 400.0 : 200.0;
            gs_eq[1] = e[2] ? 6000.0 : 3000.0;
            gs_eq[2] = std::max(-12, std::min(12, e[1] - 0x40));
            gs_eq[3] = std::max(-12, std::min(12, e[3] - 0x40));
            for (int c = 0; c < 32; c++)
                if (nv_midi_gs_setup(midi, 4, c, &v) && !v)
                    gs_eq_off.push_back(c);
        }
    }
    const double total = nv_midi_total(midi);
    // THE SONG
    void *song = nv_song_new();
    nv_song_tuning(song, -1, 0.0, E.freq.data());
    // THE `gm2` TUNER'S STORE (_prep_gm2_store, mts.TuningStore): the file's
    // MTS and RPN 0/3, 0/4 and GM System On, in message order, each channel's
    // table at each step -- a new one where its selection or its table moved
    {
        std::string tl = tname;
        for (char &c : tl)
            c = (char)tolower((unsigned char)c);
        if (tl == "gm2") {
            static const char *BUILTIN[] = {"even", "hybrid", "hybridharm", "hybrid440", "hybridharm440",
                                            "stretch", "werckmeister", "sankey", "meantone", "well", "pyth", "just",
                                            "linear", "linear5", "linearwell", "bechstein", "spiral", "semi", "path",
                                            "dynamic"};
            std::map<std::pair<int, int>, std::vector<double>> tabs;
            std::map<std::pair<int, int>, long> ver;
            long nver = 0;
            auto table = [&](int b, int p) -> std::vector<double> & {
                auto key = std::make_pair(b, p);
                auto it = tabs.find(key);
                if (it != tabs.end())
                    return it->second;
                std::vector<double> t(128);
                bool built = false;
                if (b == 0 && p >= 0 && p < (int)(sizeof BUILTIN / sizeof BUILTIN[0])) {
                    double F[128];
                    int have[128], all = 1;
                    if (nv_tuning_table(BUILTIN[p], !ra.empty() ? 69 : !rc.empty() ? 60 : -1,
                                        !ra.empty() ? atof(ra.c_str()) : !rc.empty() ? atof(rc.c_str()) : 0.0, F,
                                        have) == 0) {
                        for (int n = 0; n < 128; n++)
                            all = all && have[n];
                        if (all) {
                            t.assign(F, F + 128);
                            built = true;
                        }
                    }
                }
                if (!built)                 // (equal_table: GM's power-on)
                    for (int k = 0; k < 128; k++)
                        t[k] = 440.0 * pow(2.0, (k - 69) / 12.0);
                ver[key] = ++nver;
                return tabs[key] = t;
            };
            struct Ev {
                double t;
                long seq;
                int kind, ch, v, mi;
            };
            std::vector<Ev> ev;
            for (int i = 0, n = nv_midi_n_mts(midi); i < n; i++) {
                double t, hz[128];
                long sq;
                int b, p;
                nv_midi_mts(midi, i, &t, &sq, &b, &p, hz);
                ev.push_back(Ev{t, sq, 0, -1, 0, i});
            }
            for (int i = 0, n = nv_midi_n_pitch(midi); i < n; i++) {
                int iv[2];
                long sq;
                double t, v;
                nv_midi_pitch(midi, i, iv, &sq, &t, &v);
                if (iv[0] >= 0 && (iv[1] == 6 || iv[1] == 7))
                    ev.push_back(Ev{t, sq, iv[1] == 6 ? 1 : 2, iv[0], (int)v, -1});
                else if (iv[0] == -1 && iv[1] == 9)
                    ev.push_back(Ev{t, sq, 3, -1, 0, -1});
            }
            std::stable_sort(ev.begin(), ev.end(), [](const Ev &a, const Ev &b) {
                return a.t < b.t || (a.t == b.t && a.seq < b.seq);
            });
            std::set<int> chs;              // the first sixteen, and every channel a note is on
            for (int c = 0; c < 16; c++)
                chs.insert(c);
            for (int i = 0, n = nv_midi_n_notes(midi); i < n; i++) {
                int iv[5];
                double dv[5];
                nv_midi_note(midi, i, iv, dv);
                chs.insert(iv[0]);
            }
            std::map<int, std::pair<int, int>> sel;
            std::map<int, std::pair<std::pair<int, int>, long>> cur;
            auto snap = [&](double t) {
                for (int c : chs) {
                    auto s_ = sel.count(c) ? sel[c] : std::make_pair(0, 0);
                    std::vector<double> &tab = table(s_.first, s_.second);
                    auto id = std::make_pair(s_, ver[s_]);
                    auto it = cur.find(c);
                    if (it == cur.end() || it->second != id) {
                        cur[c] = id;
                        nv_song_tuning(song, c, t, tab.data());
                    }
                }
            };
            snap(0.0);
            for (const Ev &e : ev) {
                if (e.kind == 0) {          // (load: a copy, the dump's or the changes' keys over it)
                    double t, hz[128];
                    long sq;
                    int b, p;
                    nv_midi_mts(midi, e.mi, &t, &sq, &b, &p, hz);
                    std::vector<double> nt = table(b, p);
                    for (int k = 0; k < 128; k++)
                        if (!std::isnan(hz[k]))
                            nt[k] = hz[k];
                    tabs[std::make_pair(b, p)] = nt;
                    ver[std::make_pair(b, p)] = ++nver;
                } else if (e.kind == 1 || e.kind == 2) {
                    auto s_ = sel.count(e.ch) ? sel[e.ch] : std::make_pair(0, 0);
                    (e.kind == 1 ? s_.second : s_.first) = e.v;
                    sel[e.ch] = s_;
                } else {
                    sel.clear();            // (reset_selections: the tables kept)
                }
                snap(e.t);
            }
        }
    }
    // THE SECONDARY TUNING (_prep_eastern_tuning): an 'indian' class's table,
    // Sa at the primary's pitch for its key unless the spec names one; or the
    // primary tuner is itself a raga's (its Sa, no second table)
    {
        double FE[128], sw[12];
        int have[128], sa = -1, nsw = 0;
        std::string tl = tname;
        for (char &c : tl)
            c = (char)tolower((unsigned char)c);
        if (!east.empty()) {
            // (FREQ.get(its Sa's key): the primary's, 0 none)
            double probe[128];
            int ph[128], sa0 = -1, n0 = 0;
            double sw0[12];
            int r = nv_raga_info(east.c_str(), 0.0, probe, ph, &sa0, sw0, &n0);
            if (r) {
                fprintf(stderr, "nvrender: eastern %s refused (%d)\n", east.c_str(), r);
                return 1;
            }
            double sa_hz = sa0 >= 0 && sa0 < 128 ? E.freq[sa0] : 0.0;
            nv_raga_info(east.c_str(), sa_hz, FE, have, &sa, sw, &nsw);
            nv_song_eastern(song, FE, 1, sa, sw, nsw);
        } else if (tl.compare(0, 5, "raga:") == 0) {
            nv_raga_info(tl.c_str(), 0.0, FE, have, &sa, sw, &nsw);
            nv_song_eastern(song, nullptr, 1, sa, sw, nsw);
        }
    }
    nv_song_kits_n(song, E.kit_f0.data(), E.kit_seat.data(), (int)E.kit_f0.size());
    nv_song_chokes_n(song, E.kit_choke.data(), (int)E.kit_f0.size());
    if (!E.vgs.empty()) {                   // (bank select's tables, before the notes take their variations)
        std::vector<int> nls, ls;
        std::vector<double> vt;
        for (const auto &v : E.vents) {
            nls.push_back((int)v.ls.size());
            for (const auto &l : v.ls)
                ls.insert(ls.end(), l.begin(), l.end());
            vt.push_back(v.trim[nv_midi_gs(midi) ? 1 : 0]);
        }
        nv_song_vars(song, (int)E.vents.size(), nls.data(), ls.data(), vt.data(), E.vgs.data(), E.vgm2.data());
    }
    // ...and each variation's organ, a one-tone variation's slot's (its
    // tone's class, vents' pcls), for the song's organs
    // a variation entry's PROGRAM CLASS's organ (property_class_for_program's), NULL none
    auto ent_organ = [&](int en) -> const OrganSpec * {
        if (en <= 0 || en >= (int)E.vents.size() || E.vents[en].pcls < 0)
            return nullptr;
        int oi = E.cls_organ[E.vents[en].pcls];
        return oi >= 0 ? &E.organs[oi] : nullptr;
    };
    // ...and every organ it brings onto a channel (voice_classes: its own
    // class's, then each layer's at key 60 -- an organ can be a layer of a
    // tone whose own class is not one), in that order
    auto ent_organs = [&](int en) -> std::vector<const OrganSpec *> {
        std::vector<const OrganSpec *> out;
        if (en <= 0 || en >= (int)E.vents.size())
            return out;
        if (const OrganSpec *o = ent_organ(en))
            out.push_back(o);
        for (const auto &l : E.vents[en].ls) {
            const int kq = NV_K_VAR + 128 * l[0] + 60;
            const int cq = kq < (int)E.cmap.size() ? E.cmap[kq] : -1;
            if (cq >= 0 && E.cls_organ[cq] >= 0)
                out.push_back(&E.organs[E.cls_organ[cq]]);
        }
        return out;
    };
    {
        // (each slot's notes: their program class's organ -- every layer's)
        int ns = (int)(E.vmap.size() / 128);
        std::vector<const OrganSpec *> so(ns, nullptr);
        for (int en = 1; en < (int)E.vents.size(); en++)
            if (const OrganSpec *o = ent_organ(en))
                for (const auto &l : E.vents[en].ls)
                    if (l[0] >= 0 && l[0] < ns)
                        so[l[0]] = o;
        nv_song_slot_organs(song, ns, so.data());
        std::vector<int> off(1, 0);
        std::vector<const OrganSpec *> og;
        std::vector<std::vector<const OrganSpec *>> per(ns);
        for (int en = 1; en < (int)E.vents.size(); en++) {
            std::vector<const OrganSpec *> eo = ent_organs(en);
            for (const auto &l : E.vents[en].ls)
                if (l[0] >= 0 && l[0] < ns)
                    per[l[0]] = eo;
        }
        for (int i = 0; i < ns; i++) {
            og.insert(og.end(), per[i].begin(), per[i].end());
            off.push_back((int)og.size());
        }
        nv_song_slot_orgs(song, ns, off.data(), og.data());
    }
    nv_midi_song(midi, song, E.trim.data() + (nv_midi_gs(midi) ? 256 : 0));
    if (gs_eq[0] > 0.0)
        nv_song_gs_eq(song, gs_eq, (int)gs_eq_off.size(), gs_eq_off.data());
    {
        // THE DRUM INSTRUMENTS' OWN (dedit): the song's, for each drum note's onset
        int nd = nv_midi_n_dedit(midi);
        std::vector<int> div(4 * (size_t)nd);
        std::vector<double> dt(nd);
        for (int i = 0; i < nd; i++)
            nv_midi_dedit(midi, i, div.data() + 4 * i, dt.data() + i);
        if (nd)
            nv_song_dedit(song, nd, div.data(), dt.data());
    }
    if (gs_dly_on)
        nv_song_gs_delay(song, gs_dly, E.k.data() + K_GSPLACE);
    // THE CONTROLLER MATRIX's sums as they move (_CMXEV): its cutoff and LFO
    // rate into the notes' sound controls, its amplitude into their level and
    // the fader, its pitch and vibrato on the pitch stream (bend.cpp), its
    // tremolo below; its LFO filter depth, as Python's, nothing
    std::set<long long> cmx_cut, cmx_amp;
    std::map<long long, std::vector<std::pair<double, double>>> cmx_tva, cmx_rate;
    for (int i = 0, n = nv_midi_n_cmx(midi); i < n; i++) {
        int iv[2];
        double dv[2];
        nv_midi_cmx(midi, i, iv, dv);
        if (iv[0] == 1)
            cmx_tva[iv[1]].push_back(std::make_pair(dv[0], dv[1]));
        if (iv[0] == 5)
            cmx_rate[iv[1]].push_back(std::make_pair(dv[0], dv[1]));
        if (iv[0] == 3)
            cmx_cut.insert(iv[1]);
        if (iv[0] == 0)
            cmx_amp.insert(iv[1]);
        nv_song_cmx(song, iv[0], iv[1], dv[0], dv[1]);
    }
    // ITS PRESSURE (ats, pts): each channel's aftertouch, each key's polytouch
    for (int c = 0; c < 256; c++) {
        int na = nv_midi_ats(midi, c, nullptr, nullptr, 0);
        if (na > 0) {
            std::vector<double> tt(na);
            std::vector<int> vv(na);
            nv_midi_ats(midi, c, tt.data(), vv.data(), na);
            nv_song_pressure_events(song, c, -1, na, tt.data(), vv.data());
        }
        for (int key = 0; key < 128; key++) {
            int np = nv_midi_pts(midi, c, key, nullptr, nullptr, 0);
            if (np <= 0)
                continue;
            std::vector<double> tt(np);
            std::vector<int> vv(np);
            nv_midi_pts(midi, c, key, tt.data(), vv.data(), np);
            nv_song_pressure_events(song, c, key, np, tt.data(), vv.data());
        }
    }
    // THE REGISTERED ORGANS (_prep_organ_rows): each melodic channel's, as its
    // programs bring them (ch_progs, uniq_programs), one a family; their stop
    // words' events. A program whose organ the engine does not play: Python's
    std::vector<const OrganSpec *> prog_organ(128, nullptr);
    for (int p = 0; p < 128; p++)
        if (E.prog_organ[p] >= 0)
            prog_organ[p] = &E.organs[E.prog_organ[p]];
    // (each reader's note an organ's, its CC7 its swell, not a fader: _plain,
    // by its class -- its variation's where its bank selects one)
    std::vector<unsigned char> swell(nv_midi_n_notes(midi), 0);
    for (int i = 0; i < (int)swell.size(); i++) {
        int iv[5];
        double dv[5];
        nv_midi_note(midi, i, iv, dv);
        if (iv[4])
            continue;
        for (int q : note_ks(i, iv))
            if (q < (int)E.cmap.size() && E.cmap[q] >= 0 && E.cls_organ[E.cmap[q]] >= 0
                && E.organs[E.cls_organ[E.cmap[q]]].swells)
                swell[i] = 1;
    }
    std::vector<int> chs;               // the channels in ch_progs' order, each's programs (uniq_programs)
    std::map<int, std::vector<int>> uniq;
    std::set<int> organ_ch;
    {
        for (int i = 0, n = nv_midi_n_chprogs(midi); i < n; i++) {
            int iv[2];
            nv_midi_chprog(midi, i, iv);
            if (!uniq.count(iv[0]))
                chs.push_back(iv[0]);
            std::vector<int> &u = uniq[iv[0]];
            // (uniq_programs: a variation its own, program + 128 x its entry)
            const int en = ent_of(iv[1], nv_midi_chprog_bsel(midi, i)), pk = iv[1] + 128 * en;
            if (std::find(u.begin(), u.end(), pk) == u.end())
                u.push_back(pk);
            if (en && E.vents[en].pcls == -2) {
                fprintf(stderr, "nvrender: refused: a variation's breath the engine has not (program %d)\n", iv[1]);
                return 2;
            }
        }
        for (int c : chs) {
            std::vector<int> fams;
            // (a variation that is no organ beside an organ: its notes no organ's,
            // the organ's rows built as Python's _prep_organ_rows builds them)
            for (int pk : uniq[c]) {
                std::vector<const OrganSpec *> ogs;
                if (pk >= 128) {
                    ogs = ent_organs(pk / 128); // (a registered variation: its tone's organ, a layer's)
                } else {
                    const int p = pk;
                    if (E.prog_organ[p] == -2) {
                        fprintf(stderr, "nvrender: refused: an organ the engine does not play (program %d)\n", p);
                        return 2;
                    }
                    ogs.push_back(prog_organ[p]);
                }
                for (const OrganSpec *og : ogs) {
                    if (!og || std::find(fams.begin(), fams.end(), og->family) != fams.end())
                        continue;
                    fams.push_back(og->family);
                    organ_ch.insert(c);
                    nv_song_organ(song, c, og, prog_organ.data());
                }
            }
        }
    }
    // THE BEND PASSES (native/bend.cpp): each channel's tuning, from its wheel
    // and RPNs, into its notes' f0; a fader moving under its notes, a row --
    // its notes at unity, each riding it (br)
    double btun[256];
    nv_bend_grid((int)BLK, SR);                 // (the matrix's vibrato: a point a block)
    nv_bend_btun(midi, song, E.k[K_BEND_SEMIS], btun);
    // THE MEEND's CHANNELS (_MEEND_CH): a wheel (or a reset) on it and a note
    // of a class that meends -- no tuning of their own, no gesture: each note
    // its own (_prep_bend_rows' _MEEND_AT, below)
    std::map<int, std::vector<std::pair<double, int>>> wheel;
    for (int q = 0, nq = nv_midi_n_pws(midi); q < nq; q++) {
        int pv[2];
        double pt;
        nv_midi_pw(midi, q, pv, &pt);
        wheel[pv[0]].push_back(std::make_pair(pt, pv[1]));
    }
    // (a note's class for its meend: _prep_bend_rows reads the note before
    // its layers part, property_class_for_note(its program, its key) -- one
    // slot's at its key; a LAYERED variation's, its program's class (vents'
    // pcls: Sitar/Drone's sitar) -- and every layer of it, sharing its
    // channel, key and onset, rides that one meend: the tamboura too)
    auto meend_cls = [&](int i, const int *iv) -> int {
        std::vector<int> ks = note_ks(i, iv);
        if (ks.size() == 1)
            return E.cmap[ks[0]];
        const int en = iv[4] ? 0 : ent_of(iv[3], nv_midi_note_bsel(midi, i));
        return en ? E.vents[en].pcls : -1;
    };
    std::set<int> mch;
    for (int i = 0, n = nv_midi_n_notes(midi); i < n; i++) {
        int iv[5];
        double dv[5];
        nv_midi_note(midi, i, iv, dv);
        int cq = meend_cls(i, iv);
        if (!iv[4] && cq >= 0 && ((const NoteClass *)E.classes[cq].data())->meend && wheel.count(iv[0]))
            mch.insert(iv[0]);
    }
    for (int c : mch)
        btun[c & 255] = 0.0;
    // MPE's MEMBER NOTES (_mpe_member): a note on a channel that was a member
    // of a zone at its onset -- its channel no tuning and no gesture of its
    // own (each note its own pitch: _MPE_AT, below), the note riding its
    // manager's fader
    std::vector<int> fch_note;
    std::set<int> mpch;
    if (nv_midi_has_mpe(midi)) {
        const int nn = nv_midi_n_notes(midi);
        fch_note.assign(nn, -1);
        for (int i = 0; i < nn; i++) {
            int iv[5];
            double dv[5];
            nv_midi_note(midi, i, iv, dv);
            const int mg = nv_midi_mpe_manager(midi, iv[0], dv[0]);
            if (mg >= 0 && mg != iv[0]) {
                fch_note[i] = mg;
                mpch.insert(iv[0]);
            }
        }
    }
    nv_bend_fader_channels(fch_note.data(), (int)fch_note.size());
    for (int c : mpch)
        btun[c & 255] = 0.0;
    // the rows: each channel's gesture first (_prep_bend_rows: brow_of, at
    // br[256 + channel]), then the faders' (_LROW, at br[channel])
    std::vector<int> fch, gch;
    std::vector<double> br(512, -1.0);
    for (int c = 0; c < 256; c++)
        if (!mch.count(c) && !mpch.count(c)
            && nv_bend_gesture(midi, song, E.k[K_BEND_SEMIS], c, 0, (int)BLK, SR, nullptr, nullptr)) {
            br[256 + c] = (double)gch.size();
            gch.push_back(c);
        }
    br.resize(1024, -1.0);
    // ...then THE PLAYER'S BREATH (_prep_breath, _prep_breath_rows): each
    // channel, not an organ's, with a breathing class among its programs --
    // its pitch row with the tone's level, and its breath noise's (at
    // br[512 + channel] and br[768 + channel])
    std::vector<int> bch;
    std::vector<const NoteClass *> bcls;
    for (int c : chs) {
        if (organ_ch.count(c))
            continue;
        for (int pk : uniq[c]) {
            int cq = pk >= 128 ? E.vents[pk / 128].pcls : E.cmap[128 * pk + 60];
            const NoteClass *k = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
            if (k && k->breath) {
                br[512 + c] = (double)(gch.size() + 2 * bch.size());
                br[768 + c] = br[512 + c] + 1.0;
                bch.push_back(c);
                bcls.push_back(k);
                break;
            }
        }
    }
    const int nbr_ = 2 * (int)bch.size();
    // ...then the chests' wind (_prep_wind_rows: a row a family of each organ channel's ranks)
    const int nw = nv_song_organ_wind_rows(song, (int)gch.size() + nbr_);
    // ...then THE SCANNERS' (_prep_scanner_channels): each channel whose note
    // has one, as the file's notes come, at its first CC81's position (the
    // voice's own without one, or without the switch): six band rows each
    std::vector<long long> sch;
    std::vector<int> sdep, scho, srow;
    for (int i = 0, n = nv_song_n_notes(song); i < n; i++) {
        long long c;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, i, &c, iv, dv);
        if (iv[3] || iv[2] < 0 || iv[2] > 127 || std::find(sch.begin(), sch.end(), c) != sch.end())
            continue;
        int cq = E.cmap[nv_song_kidx(song, i)];
        const NoteClass *k = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
        if (!k || !k->scanner)
            continue;
        int depth = (k->scanner >> 2) & 3, cho = (k->scanner >> 4) & 1, v;
        if ((k->scanner & 2) && nv_song_first_cc(song, c, NV_CC_SCANNER, &v)) {
            // scanner.setting_from_cc: off, V1-V3, C1-C3 from 0, 18, 37, 55, 73, 91, 110
            static const int start[7] = {0, 18, 37, 55, 73, 91, 110};
            int pos = 0;
            for (int q = 0; q < 7; q++)
                if (v >= start[q])
                    pos = q;
            depth = pos == 0 ? 0 : (pos - 1) % 3 + 1;
            cho = pos >= 4;
        }
        if (!depth)
            continue;
        if (E.scan.empty()) {
            fprintf(stderr, "nvrender: %s is an export from before the scanner (native_export.py again)\n", argv[1]);
            return 1;
        }
        sch.push_back(c);
        sdep.push_back(depth);
        scho.push_back(cho);
        srow.push_back((int)gch.size() + nbr_ + nw + 6 * ((int)sch.size() - 1));
    }
    const int nsr = 6 * (int)sch.size();
    float one = 0.0f;
    for (int c = 0; c < 256; c++)
        if (nv_bend_fader(midi, song, c, 0, (int)BLK, SR, E.k[K_TAU], E.k[K_FADER_TAIL], E.k[K_STAMP_S],
                          E.k[K_STAMPED_SHARE], (int)E.k[K_GM_VOL], (int)E.k[K_GM_EXPR], &one, swell.data())) {
            br[c] = (double)(gch.size() + nbr_ + nw + nsr + fch.size());
            fch.push_back(c);
        }
    // ...and THE MEEND's NOTES, in the file's order: each one's ratio at Note
    // On, its row after the faders' where its wheel moves
    struct Meend {
        int ch;
        double on, off, nc, rst, st;
        std::vector<double> sw;
    };
    std::vector<Meend> mrows;
    const int mbase = (int)(gch.size() + nbr_ + nw + nsr + fch.size());
    for (int i = 0, n = nv_midi_n_notes(midi); i < n && !mch.empty(); i++) {
        int iv[5];
        double dv[5];
        nv_midi_note(midi, i, iv, dv);
        int c = iv[0];
        if (!mch.count(c) || iv[4])
            continue;
        int cq = meend_cls(i, iv);
        const NoteClass *mk = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
        if (!mk || !mk->meend)
            continue;
        double tab[128];
        nv_song_note_table(song, c, dv[0], mk->indian, tab);
        int ra = nv_song_raga_sa(song);
        bool east = nv_song_has_eastern(song) != 0;
        int sa = ra >= 0 && (mk->indian || !east) ? ra : mk->meend_tonic;
        int nt = iv[1];
        if (!(sa >= 0 && sa < 128 && tab[sa] > 0.0 && tab[nt] > 0.0))
            continue;
        Meend m;
        m.ch = c;
        m.on = dv[0];
        m.off = dv[1];
        double rsw[12];
        int nr = nv_song_raga_sw(song, rsw);
        if (nr >= 0 && (mk->indian || !east))
            m.sw.assign(rsw, rsw + nr);
        else
            for (int k2 = 0; k2 < 12; k2++)
                m.sw.push_back(1200.0 * log2(tab[sa + k2] / tab[sa]));
        m.nc = 1200.0 * log2(tab[nt] / tab[sa]);
        // the file's RPN 0 at Note On (the last at or before it), else the class's
        m.rst = mk->meend_range;
        for (int q = 0, nq = nv_midi_n_pitch(midi); q < nq; q++) {
            int pv[2];
            long sq;
            double pt, pvv;
            nv_midi_pitch(midi, q, pv, &sq, &pt, &pvv);
            if (pv[0] == c && pv[1] == 1 && pt <= m.on + 1e-9)
                m.rst = pvv;
        }
        m.st = mk->meend_strength;
        std::vector<double> wt;
        std::vector<int> wp;
        for (auto &w : wheel[c]) {
            wt.push_back(w.first);
            wp.push_back(w.second);
        }
        double r0;
        int moves = nv_meend_note(wt.data(), wp.data(), (int)wt.size(), m.on, m.off, m.nc, m.sw.data(),
                                  (int)m.sw.size(), m.rst, m.st, 0, (int)BLK, SR, &r0, nullptr, nullptr);
        double row = -1.0;
        if (moves) {
            row = (double)(mbase + (int)mrows.size());
            mrows.push_back(m);
        }
        nv_song_meend(song, c, nt, m.on, r0, row);
    }
    // ...and MPE's MEMBER NOTES' PITCH (_prep_mpe_pitch): the member's bend
    // times its manager's (the manager's without the master's), the value at
    // Note On into f0, what moves after -- the member's until its Note Off,
    // the manager's while it sounds -- a row of its own after the meends'
    struct MpeRow {
        std::vector<double> t, r;
        int mgr;
    };
    std::vector<MpeRow> prows;
    const int pbase = mbase + (int)mrows.size();
    if (!mpch.empty()) {
        std::map<std::pair<int, int>, std::pair<std::vector<double>, std::vector<double>>> stc;
        auto stream = [&](int c, int wm) -> const std::pair<std::vector<double>, std::vector<double>> & {
            auto key = std::make_pair(c, wm);
            auto it = stc.find(key);
            if (it != stc.end())
                return it->second;
            int n = nv_bend_stream(midi, c, wm, E.k[K_BEND_SEMIS], nullptr, nullptr, 0);
            std::pair<std::vector<double>, std::vector<double>> v;
            v.first.resize(n);
            v.second.resize(n);
            nv_bend_stream(midi, c, wm, E.k[K_BEND_SEMIS], v.first.data(), v.second.data(), n);
            return stc[key] = v;
        };
        auto val = [](const std::pair<std::vector<double>, std::vector<double>> &st, double tt) {
            double v = 1.0;
            for (size_t k = 0; k < st.first.size(); k++) {
                if (st.first[k] <= tt + 1e-9)
                    v = st.second[k];
                else
                    break;
            }
            return v;
        };
        for (int i = 0, n = nv_midi_n_notes(midi); i < n; i++) {
            if (fch_note[i] < 0)
                continue;
            int iv[5];
            double dv[5];
            nv_midi_note(midi, i, iv, dv);
            const int c = iv[0], mg = fch_note[i];
            const double on = dv[0], off = dv[1];
            const auto &ms = stream(c, 1);
            const auto &gs = stream(mg, 0);
            const double r0 = val(ms, on) * val(gs, on);
            double row = -1.0;
            bool bendable = !iv[4];
            if (bendable) {
                int cq = meend_cls(i, iv);
                if (cq >= 0)
                    bendable = ((const NoteClass *)E.classes[cq].data())->bendable != 0;
            }
            std::vector<double> mv;
            for (size_t k = 0; k < ms.first.size(); k++)
                if (on + 1e-9 < ms.first[k] && ms.first[k] <= off)
                    mv.push_back(ms.first[k]);
            for (size_t k = 0; k < gs.first.size(); k++)
                if (gs.first[k] > on + 1e-9)
                    mv.push_back(gs.first[k]);
            std::sort(mv.begin(), mv.end());
            mv.erase(std::unique(mv.begin(), mv.end()), mv.end());
            if (bendable && !mv.empty()) {
                MpeRow pr;
                pr.mgr = mg;
                bool any = false;
                for (double tt : mv) {
                    const double rr = val(ms, std::min(tt, off)) * val(gs, tt) / r0;
                    pr.t.push_back(tt);
                    pr.r.push_back(rr);
                    any = any || fabs(rr - 1.0) > 1e-9;
                }
                if (any) {
                    row = (double)(pbase + (int)prows.size());
                    prows.push_back(pr);
                }
            }
            nv_song_mpe(song, c, iv[1], on, r0, row, mg);
        }
    }
    for (int c = 0; c < 256; c++) {
        double ot[12];                      // THE CHANNEL's SCALE (_prep_octave_tuning, _OTUN)
        bool has_ot = nv_midi_otun(midi, c, ot) != 0;
        if (btun[c] != 0.0 || br[c] >= 0.0 || has_ot)
            nv_song_channel(song, c, btun[c], has_ot ? ot : nullptr, br[c] >= 0.0);
    }
    // A GESTURE'S STROKES (_prep_strokes): after the passes that read the
    // notes as written, before everything that reads the strokes
    std::vector<const NoteClass *> K(E.cmap.size(), nullptr);
    for (int q = 0; q < (int)E.cmap.size(); q++)
        if (E.cmap[q] >= 0)
            K[q] = (const NoteClass *)E.classes[E.cmap[q]].data();
    nv_song_strokes_k(song, K.data(), E.kit_skind.data(), E.kit_spar.data());   // (a gesture's strokes, _prep_strokes)
    // ...and A USER DRUM SET's keys (user_drum: GS's sets 65 and 66, programs
    // 64 and 65), each stroke and layer as its own key: another set's key --
    // its class, pitch and seat -- with its own play note (as pitch), level,
    // pan and receive switch, the file's drum edits over them
    for (int i = 0, nn = nv_song_n_notes(song); i < nn; i++) {
        long long c;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, i, &c, iv, dv);
        int u[13] = {0};
        int m = iv[3] && (iv[2] == 64 || iv[2] == 65) ? nv_midi_user_drum(midi, iv[2] - 64, iv[0], u) : 0;
        if (!((m >> 12) & 1))
            continue;
        const int sset = (m >> 11) & 1 ? u[11] : 0, snote = u[12];
        int uv[9] = {0}, um = 0;
        if ((m >> 1) & 1)
            uv[0] = u[1] - snote, um |= 1;          // (its play note: its pitch from the source's)
        if ((m >> 2) & 1)
            uv[1] = u[2], um |= 2;
        if ((m >> 4) & 1)
            uv[2] = u[4], um |= 4;
        if ((m >> 8) & 1)
            uv[6] = u[8], um |= 64;
        nv_song_user_drum(song, i, 128 * sset + snote, um, uv);
    }
    // ...then the valved glisses and the drones (_prep_gliss, _DRONE_PC), as
    // Python walks them: before every table kept by note (the matrix's, the
    // insertion chains'), which index the notes as walked (nv_prepare's
    // walks find them done)
    nv_song_gliss(song, K.data());
    if (nv_song_drones(song, K.data()) < 0) {
        fprintf(stderr, "nvrender: refused: drones Python's (two drone classes, or phrase breaks, on a channel)\n");
        return 2;
    }
    for (int i = 0, nn = cmx_cut.empty() && cmx_amp.empty() ? 0 : nv_song_n_notes(song); i < nn; i++) {
        long long c;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, i, &c, iv, dv);
        int q = nv_song_kidx(song, i);
        const NoteClass *k = (q >= 0 && q < (int)K.size()) ? K[q] : nullptr;
        if (k && k->organ && cmx_amp.count(c)) {
            fprintf(stderr, "nvrender: refused: an organ's registration under a controller matrix's amplitude\n");
            return 2;
        }
    }
    nv_song_finish(song, total);
    // THE TABLE
    NoteIn t;
    memset(&t, 0, sizeof t);
    t.sr = SR; t.retrigger_fade = E.k[K_RETRIGGER]; t.nyq_om = E.k[K_NYQ_OM];
    t.sv[0] = 0.0; t.sv[1] = 1.0; t.sound_vib_depth_cents = E.k[K_SVDC]; t.vibrato_delay = 0.0;
    t.gl[0] = 0.0; t.gl[1] = 0.05; t.gl[2] = 0.0;
    t.fx = -1.0; t.mk = 0.0; t.fm_omega = 0.0; t.fm_phase = 0.0;
    for (int i = 0; i < 9; i++)
        t.room_bands[i] = E.k[K_BANDS + i];
    t.reflect = E.k[K_REFLECT] != 0.0;
    t.fixed_touch = E.k[K_FIXED_TOUCH] != 0.0;
    PyRandom rs;
    pyr_seed(&rs, 0);                          // _prepare's random.seed(0)
    double qacc[18] = {0}, az = 0.0, out[48] = {0};
    double *rows = nullptr;
    void *dm[6] = {nullptr};
    // THE PARTS' INSERTION EFFECTS (a tone's own: blockrender's _EFXN): in the
    // note loop's order, each part's first effect note's reverb send its
    // distance from there on (_C91D), each mix channel's first its send
    // bus's and its EQ's (_REVERB_CH, _EFXEQ_CH), a part's CC91 steps gone
    std::map<long long, std::vector<double>> efx_eq;   // (lo, mid Hz, Q, mid dB, hi, lo Hz, hi Hz, mids...)
    std::map<long long, const double *> efx_trem;       // (a mix channel's first chain's tremolo)
    std::map<long long, double> efx_send;
    std::set<long long> efx_parts;
    // ...AND THE FILE'S (blockrender's _EFXEV, gsefx.chain): each note's
    // chain where its part is on the effect at its onset -- the last
    // assign, none after a reset -- built from the type and parameters its
    // onset finds (none where the type is not built: the tone's own not
    // played either); a mix channel's first chain note sets the channel's
    // amp, cabinet, EQ, chorus and send (_note_insertion_efx)
    std::vector<double> fxch;                    // the chains, NV_FXN each
    std::vector<int> note_fx;                   // each note's (-1 none, -2 on the effect with none)
    std::vector<unsigned char> fx_first;
    std::vector<double> fx_ts;                  // 0 and each event's time (mix_share's, the steps')
    std::map<long long, std::vector<double>> fx_share;     // a first chain's mix channel: its share at each
    std::map<long long, int> fx_cfn;            // a mix channel whose first chain has a chorus: that note
    std::vector<char> fx_cabbuf[2];
    const NoteClass *fx_cab[2] = {nullptr, nullptr};
    struct FxEv {
        double t;
        int kind, a, b;
    };
    std::vector<FxEv> fx_ev;
    {
        const char *ge = getenv("TUNING_GS_EFX");
        bool off = ge && (!*ge || !strcmp(ge, "0") || !strcmp(ge, "off"));
        bool parts = false;
        for (int i = 0, n = off ? 0 : nv_midi_n_efx(midi); i < n; i++) {
            int iv[3];
            double t;
            nv_midi_efx(midi, i, iv, &t);
            fx_ev.push_back(FxEv{t, iv[0], iv[1], iv[2]});
            parts = parts || iv[0] == 5;
        }
        if (!parts)
            fx_ev.clear();                      // (no part on it: nothing reads it)
        // (the block's layout: codes, then the records' header, records, laws, cabinets, tables)
        if (!fx_ev.empty() && (E.k.size() < K_EFX + 132
                               || E.k.size() < K_EFX + 132 + NV_EFX_NAT * E.k[K_EFX + 131] + 30 + 66 + 1024
                                                    + 128 + 5 * 19 + 128 * 6 * 5 + 2 * 5 + 5 * 128)) {
            fprintf(stderr, "nvrender: refused: the insertion effect (40 03), an export without its tables\n");
            return 2;
        }
        std::set<double> ts = {0.0};
        for (const FxEv &e : fx_ev)
            ts.insert(e.t);
        fx_ts.assign(ts.begin(), ts.end());
        const char *cb = getenv("TUNING_CABINET");
        for (int w = 0; w < 2 && !fx_ev.empty() && !(cb && !strcmp(cb, "0")); w++) {
            const double *C = E.k.data() + K_EFX + 132 + NV_EFX_NAT * (size_t)E.k[K_EFX + 131] + 30 + 33 * w;
            fx_cabbuf[w].assign(sizeof(NoteClass), 0);
            NoteClass *nc = (NoteClass *)fx_cabbuf[w].data();
            nc->cab_set = (int)C[0];
            nc->n_cab_fm = (int)C[1];
            nc->n_cab_afm = (int)C[2];
            nc->cab_floor = C[3];
            for (int r = 0; r < 4; r++)
                for (int x = 0; x < 3; x++) {
                    nc->cab_fm[r][x] = C[4 + 3 * r + x];
                    nc->cab_afm[r][x] = C[16 + 3 * r + x];
                }
            nc->cab_corner = C[28]; nc->cab_order = C[29]; nc->cab_cut = C[30]; nc->cab_bell = C[31];
            nc->cab_ref = C[32];
            fx_cab[w] = nc;
        }
    }
    // the events at or before t (state_at, assigned: et > t + 1e-9 stops)
    auto fx_prefix = [&](double t) {
        int p = 0;
        while (p < (int)fx_ev.size() && !(fx_ev[p].t > t + 1e-9))
            p++;
        return p;
    };
    // is part c on the effect after the first `pre` events? (gsefx.assigned)
    auto fx_on = [&](long long c, int pre) {
        bool on = false;
        for (int e = 0; e < pre; e++)
            if (fx_ev[e].kind == 0)
                on = false;
            else if (fx_ev[e].kind == 5 && fx_ev[e].a == c)
                on = fx_ev[e].b != 0;
        return on;
    };
    // the chain after the first `pre` events (gsefx.chain of state_at): its
    // index in fxch, -1 none (the type not built), -3 refused -- by prefix, memoised
    std::map<int, int> fx_memo;
    auto fx_chain = [&](int pre) -> int {
        auto it = fx_memo.find(pre);
        if (it != fx_memo.end())
            return it->second;
        int msb = 0, lsb = 0, p[21], snd[3] = {40, 0, 0};
        int ctl[4] = {0, 0x40, 0, 0x40};        // (Src1, Dep1, Src2, Dep2: 1B-1E)
        std::map<int, int> cvv;                 // (each source's value, 'cv')
        for (int n = 0; n < 21; n++)
            p[n] = -1;
        for (int e = 0; e < pre; e++) {
            const FxEv &v = fx_ev[e];
            if (v.kind == 0) {
                msb = lsb = 0;
                for (int n = 0; n < 21; n++)
                    p[n] = -1;
                snd[0] = 40; snd[1] = 0; snd[2] = 0;
                ctl[0] = 0; ctl[1] = 0x40; ctl[2] = 0; ctl[3] = 0x40;
                cvv.clear();
            } else if (v.kind == 1) {
                msb = v.a; lsb = v.b;
                for (int n = 0; n < 21; n++)
                    p[n] = -1;
            } else if (v.kind == 2 && v.a >= 1 && v.a <= 20) {
                p[v.a] = v.b;
            } else if (v.kind == 3) {
                snd[v.a - 0x17] = v.b;
            } else if (v.kind == 4) {
                ctl[v.a - 0x1B] = v.b;
            } else if (v.kind == 6) {
                cvv[v.a] = v.b;
            }
        }
        double rec[NV_FXN], recb[NV_FXN];
        int has_b = 0;
        const char *why = "";
        std::vector<int> cs, cv_;
        for (const auto &kv : cvv) {
            cs.push_back(kv.first);
            cv_.push_back(kv.second);
        }
        const int got = nv_efx_chain(E.k.data() + K_EFX, SR, msb, lsb, p, snd, ctl, (int)cs.size(), cs.data(),
                                     cv_.data(), rec, recb, &has_b, &why);
        if (got == -1)
            return fx_memo[pre] = -1;
        if (got < 0) {
            fprintf(stderr, "nvrender: refused: the insertion effect's %s (type %02X %02X)\n", why, msb, lsb);
            return fx_memo[pre] = -3;
        }
        if (has_b)                              // (branch B's record, just before A's: fc - NV_FXN)
            fxch.insert(fxch.end(), recb, recb + NV_FXN);
        int idx = (int)(fxch.size() / NV_FXN);
        fxch.insert(fxch.end(), rec, rec + NV_FXN);
        return fx_memo[pre] = idx;
    };
    {
        int nn = nv_song_n_notes(song);
        note_fx.assign(nn, -1);
        fx_first.assign(nn, 0);
        for (int i = 0; i < nn && !fx_ev.empty(); i++) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            int pre = fx_prefix(dv[0]);
            if (!fx_on(c, pre))
                continue;
            int cq = fx_chain(pre);
            if (cq == -3)
                return 2;
            {
                int kq = nv_song_kidx(song, i);
                const NoteClass *kk = (kq >= 0 && kq < (int)K.size()) ? K[kq] : nullptr;
                if (cq >= 0 && fxch[(size_t)NV_FXN * cq + 22] != 0.0 && kk && kk->init.kind == 6) {
                    fprintf(stderr, "nvrender: refused: a Moog on a 3D insertion effect\n");
                    return 2;
                }
            }
            note_fx[i] = cq >= 0 ? cq : -2;
        }
        std::vector<int> ord(nn);
        std::vector<double> on_(nn);
        std::vector<long long> ch_(nn);
        std::vector<int> key_(nn);
        for (int i = 0; i < nn; i++) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            ord[i] = i; on_[i] = dv[0]; ch_[i] = c; key_[i] = iv[0];
        }
        std::stable_sort(ord.begin(), ord.end(), [&](int a, int b) {
            if (on_[a] != on_[b])
                return on_[a] < on_[b];
            if (ch_[a] != ch_[b])
                return ch_[a] < ch_[b];
            return key_[a] < key_[b];
        });
        std::set<long long> mseen;
        for (int i : ord) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            int q = nv_song_kidx(song, i);
            const NoteClass *k = (q >= 0 && q < (int)K.size()) ? K[q] : nullptr;
            const int fx = note_fx[i];
            const double *fc = fx >= 0 ? fxch.data() + (size_t)NV_FXN * fx : nullptr;
            if (!fc && !(fx == -1 && k && k->efx_set && !iv[3]))
                continue;
            long long m = nv_song_mix(song, i);
            if (mseen.count(m))
                continue;
            mseen.insert(m);
            double rv = fc ? fc[12] : k->efx_rev;
            double d = (rv > 0.0 ? rv : 0.0) / 40.0;
            nv_song_efx_part(song, c, dv[0], d);      // (_C91D: each mix channel's first chain sets it)
            efx_parts.insert(c);
            efx_send[m] = d;
            if (fc ? fc[6] != 0.0 : k->efx_eq_set != 0) {
                if (fc) {
                    std::vector<double> e{fc[7], fc[8], fc[9], fc[10], fc[11], fc[60] ? fc[60] : 400.0,
                                          fc[61] ? fc[61] : 4000.0};
                    e.insert(e.end(), fc + 63, fc + 63 + 3 * (int)fc[62]);
                    efx_eq[m] = e;
                } else {
                    efx_eq[m] = {k->efx_eq[0], k->efx_eq[1], k->efx_eq[2], k->efx_eq[3], k->efx_eq[4], 400.0,
                                 4000.0};
                }
            }
            if (fc && fc[55] != 0.0)
                efx_trem[m] = fc;                    // (its tremolo: _TREM_CH's, at its first note)
            if (fc ? fc[14] != 0.0 : k->efx_cf != 0)
                fx_cfn[m] = i;                       // (its chorus or flanger: the channel's, _CHORUS_CH)
            if (fc && fc[208] != 0.0 && (fc - NV_FXN)[14] != 0.0)
                fx_cfn[m + 65536] = i;               // (...a parallel type's branch B's, its virtual channel's)
            if (fc) {
                fx_first[i] = 1;
                // ITS LEVEL OVER THE FILE (its amp's reference: 'steps') and
                // its chorus's share (gsefx.mix_share), at 0 and each event
                std::vector<double> st, lv, sh;
                for (double t : fx_ts) {
                    int pre = fx_prefix(t), cq = fx_chain(pre);
                    if (cq == -3)
                        return 2;
                    st.push_back(t * SR);
                    lv.push_back(cq >= 0 ? fxch[(size_t)NV_FXN * cq] : fc[0]);
                    double s = 0.0;
                    if (fx_on(m % 256, pre) && cq >= 0) {
                        const double *cc = fxch.data() + (size_t)NV_FXN * cq;
                        double a = cc[14] != 0.0 ? cc[20] : 0.0;
                        s = cc[21] >= 0.0 ? cc[21] : a * a / (1.0 + a * a);
                    }
                    sh.push_back(s);
                }
                nv_song_fx_steps(song, m, (int)st.size(), st.data(), lv.data());
                fx_share[m] = sh;
                if (fc[208] != 0.0) {
                    // ...A PARALLEL TYPE's BRANCH B's level steps (its valve's
                    // reference): at(events, vc, t) or B's first, its level
                    std::vector<double> lvb;
                    for (double t : fx_ts) {
                        int pre = fx_prefix(t), cq = fx_chain(pre);
                        const bool on = fx_on(m % 256, pre) && cq >= 0 && fxch[(size_t)NV_FXN * cq + 208] != 0.0;
                        lvb.push_back(on ? fxch[(size_t)NV_FXN * (cq - 1)] : (fc - NV_FXN)[0]);
                    }
                    nv_song_fx_steps(song, m + 65536, (int)st.size(), st.data(), lvb.data());
                }
                if (fc[208] != 0.0) {
                    // ...A PARALLEL TYPE's BRANCH B's share on its virtual
                    // channel (mix_share of it: at(events, vc, t), B or none)
                    std::vector<double> shb;
                    for (double t : fx_ts) {
                        int pre = fx_prefix(t), cq = fx_chain(pre);
                        double s = 0.0;
                        if (fx_on(m % 256, pre) && cq >= 0 && fxch[(size_t)NV_FXN * cq + 208] != 0.0) {
                            const double *cc = fxch.data() + (size_t)NV_FXN * (cq - 1);
                            double a = cc[14] != 0.0 ? cc[20] : 0.0;
                            s = cc[21] >= 0.0 ? cc[21] : a * a / (1.0 + a * a);
                        }
                        shb.push_back(s);
                    }
                    fx_share[m + 65536] = shb;
                }
            }
        }
        nv_song_fx(song, (int)(fxch.size() / NV_FXN), fxch.data(), nn, note_fx.data(), fx_first.data(),
                   fx_cab[0], fx_cab[1]);
        // (a parallel type's branch B -- the part's copy on its virtual
        // channel -- takes what the voice brings to its channel; a reed
        // organ's tremolo stop, and a Leslie's valve, not yet the engine's)
        for (int i = 0; i < nn; i++) {
            if (note_fx[i] < 0 || fxch[(size_t)NV_FXN * note_fx[i] + 208] == 0.0)
                continue;
            int cq = E.cmap[nv_song_kidx(song, i)];
            const NoteClass *k = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
            if (k && ((k->amp_drive != 0.0 && k->leslie) || nv_song_htrem(song, i))) {
                fprintf(stderr, "nvrender: refused: a parallel type's branch B on a reed organ's tremolo stop "
                                "or a Leslie's valve\n");
                return 2;
            }
        }
        if (!fx_ev.empty())                     // (a chain's delay's places: the outputs', a pan's)
            nv_song_fx_place(song, E.k.data() + K_GSPLACE,
                             E.k.data() + K_EFX + 132 + NV_EFX_NAT * (size_t)E.k[K_EFX + 131] + 30 + 66 + 512);
    }
    // THE FIRE SIRENS' ROTORS (_prep_siren, siren.py): each (channel, key)'s
    // notes in their order, its rotor carried key to key -- wound up by its
    // motor while held (to its gate where a held texture has one), coasting
    // after and between presses -- a row each, after the others: its speed a
    // block (the mean ratio), its phase summed from it, its level at each
    // edge; the note sounding to the rotor's floor or the next press
    typedef NvSirRow SirRow;
    std::vector<SirRow> sir;
    const int sbase = (int)(gch.size() + nbr_ + nw + nsr + fch.size() + mrows.size() + prows.size());
    nv_song_sirens(song, K.data(), (int)K.size(), total, SR, BLK, sbase, &sir);
    // THE MATRIX'S TREMOLO's ROWS (_prep_matrix_tremolo): for each channel
    // whose depth peaks past 0, a row for each row its notes can ride -- its
    // gesture's, its fader's, its breath's, none (-1) -- after the sirens'
    struct TremRow {
        long long ch, parent;
    };
    std::vector<TremRow> trows;
    std::map<long long, std::map<long long, long long>> tmap;
    std::map<long long, std::vector<double>> tcfg_m;
    const int tbase = sbase + (int)sir.size();
    for (auto &kv : cmx_tva) {
        long long c = kv.first;
        double pk = kv.second[0].second, tpk = kv.second[0].first;
        for (auto &e : kv.second)
            if (e.second > pk) {
                pk = e.second;
                tpk = e.first;
            }
        if (pk <= 0.0)
            continue;
        if (c >= 256 || organ_ch.count((int)c)) {
            fprintf(stderr, "nvrender: refused: a controller matrix's tremolo on an organ's channel\n");
            return 2;
        }
        std::vector<long long> par = {(long long)br[256 + c], (long long)br[c], -1, (long long)br[512 + c],
                                      (long long)br[768 + c]};
        for (long long p : par) {               // (a channel without one of them: -1, none, once)
            if (tmap[c].count(p))
                continue;
            tmap[c][p] = tbase + (long long)trows.size();
            trows.push_back(TremRow{c, p});
        }
        double rv = 0.0;                        // (_cmx_at('rate') where the depth peaks)
        auto cr = cmx_rate.find(c);
        if (cr != cmx_rate.end())
            for (auto &e : cr->second) {
                if (e.first > tpk + 1e-9)
                    break;
                rv = e.second;
            }
        tcfg_m[c] = {std::max(0.5, 5.5 + rv), pk, 0.0, 0.0};
    }
    // AN ALIASING SWEEP's ROWS (_prep_alias_sweep): a sawtooth swept from
    // f0 to f1 over T s through a sampler at fs with no filter -- each
    // harmonic folded about fs/2, its ratio to where it sat at the onset
    // block by block (from the onset's block's middle), its phase the cumsum
    // of (ratio - 1) x BLK; after the tremolos' rows
    struct AliasRow {
        std::vector<float> r;
        std::vector<double> c;
    };
    std::vector<AliasRow> arows;
    const int abase = tbase + (int)trows.size();
    {
        const long nblk_ = (long)(((long long)(total * SR) + (long long)SR) / (long long)BLK + 2);
        auto fold = [](double f, double fs) {           // tonelib.alias_fold (Python's float %: fmod here)
            f = fmod(f, fs);
            return f > fs / 2.0 ? fs - f : f;
        };
        for (int i = 0, n = nv_song_n_notes(song); i < n; i++) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            int q = nv_song_kidx(song, i);
            const NoteClass *k = (q >= 0 && q < (int)K.size()) ? K[q] : nullptr;
            if (!k || k->alias_sweep[4] <= 0.0)
                continue;
            const double f0 = k->alias_sweep[0], f1 = k->alias_sweep[1], T = k->alias_sweep[2], fs = k->alias_sweep[3];
            const int nh = (int)k->alias_sweep[4];
            const long long ab0 = (long long)(dv[0] * SR) / BLK;
            std::vector<double> atb(nblk_), af(nblk_);
            for (long b = 0; b < nblk_; b++) {
                atb[b] = ((double)(b - ab0) + 0.5) * (double)BLK / SR;
                double x = atb[b] / T;
                x = x < 0.0 ? 0.0 : (x > 1.0 ? 1.0 : x);        // (np.clip)
                af[b] = f0 * pow(f1 / f0, x);
            }
            std::vector<double> rws;
            for (int h = 1; h <= nh; h++) {
                const double nom = fold(h * f0, fs);
                if (nom < 20.0) {
                    rws.push_back(-1.0);
                    continue;
                }
                AliasRow row;
                row.r.resize(nblk_);
                row.c.assign(nblk_, 0.0);
                for (long b = 0; b < nblk_; b++) {
                    double fk = fmod(h * af[b], fs);
                    fk = fk > fs / 2.0 ? fs - fk : fk;
                    row.r[b] = (float)(atb[b] > 0.0 ? fk / nom : 1.0);
                }
                double acc = 0.0;
                for (long b = 0; b + 1 < nblk_; b++) {
                    acc = acc + ((double)row.r[b] - 1.0) * BLK;
                    row.c[b + 1] = acc;
                }
                rws.push_back((double)(abase + (int)arows.size()));
                arows.push_back(std::move(row));
            }
            nv_song_alias(song, c, iv[0], dv[0], rws.data(), (int)rws.size());
        }
    }
    bool rows_ = !fch.empty() || !gch.empty() || nw || nsr || nbr_ || !mrows.empty() || !prows.empty() || !sir.empty()
                 || !trows.empty()
                 || !arows.empty();
    nv_gsd_place_reset();                       // (blockrender's _GSD_PLACE: the render's)
    StreamScan scan;
    StreamSinkDesc scan_d{&scan, &StreamScan::note};
    StreamRegDesc scan_r{&scan, &StreamScan::reg_rows, &StreamScan::reg_horizon};
    if (g_stream) {                             // PASS A: the scan
        nv_stream_reset();
        scan.gsd = nv_gsd_new(K.data(), song, E.kind.data(), SR);
        scan.mf = nv_mf104_new(song, E.kind.data(), SR);
        scan.kind = E.kind.data();
        scan.floor_ = E.k[K_RING_FLOOR];
        scan.sr = SR;
        scan.cM = col("mch");
        nv_play_set_sink(&scan_d);
        nv_play_set_reg_sink(&scan_r);
    }
    long long P = nv_prepare(song, K.data(), &t, rows_ ? br.data() : nullptr, rows_ ? 1024 : 0, &rs, &rows,
                             qacc, &az, E.kind.data(),
                             E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK, total,
                             E.k[K_RING_FLOOR], E.k[K_RING_MAX], out, E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR,
                             dm, 1);
    nv_play_set_sink(nullptr);
    nv_play_set_reg_sink(nullptr);
    if (P == -3) {
        fprintf(stderr, "nvrender: refused: drones Python's (two drone classes, or phrase breaks, on a channel)\n");
        return 2;
    }
    if (g_stream && P >= 0) {
        // the table is the stream's: the passes see none, and the length is
        // the scan's ring (prepare.cpp's: min(ring + BLK, (total + RING_MAX) SR))
        P = 0;
        long long cap_ = (long long)((total + E.k[K_RING_MAX]) * SR);
        long long rl_ = scan.rl + BLK < cap_ ? scan.rl + BLK : cap_;
        if (scan.rows && rl_ > (long long)out[0])
            out[0] = (double)rl_;
        const long long srl_ = (long long)SR;     // (the delays' last repeat's release: prepare's glast)
        if (scan.glast > 0 && scan.glast + srl_ / 2 > (long long)out[0])
            out[0] = (double)(scan.glast + srl_ / 2);
    }
    {
        long long cap0, need;               // THE ROW STORE's guess too small: said, for raising it
        nv_play_growth(&cap0, &need);
        if (need > 0)
            fprintf(stderr, "nvrender: the row store grew: %lld rows needed, %lld guessed (%d notes; "
                            "register.cpp's ROWS_PER_NOTE)\n", need, cap0, nv_song_n_notes(song));
    }
    if (P < 0) {
        long long c = -1;
        int iv[4] = {-1, -1, -1, 0};
        double dv[2] = {0.0, 0.0};
        if (-P - 1 < nv_song_n_notes(song))     // (which: its part, program, key, onset)
            nv_song_get_note(song, (int)(-P - 1), &c, iv, dv);
        fprintf(stderr, "nvrender: refused: a note is not the engine's (%lld: channel %lld, program %d, key %d%s, "
                        "at %.3f s: %s)\n", P, c, iv[2], iv[0], iv[3] ? ", a drum" : "", dv[0], nv_play_why());
        return 2;
    }
    // (a stream's choruses: each channel's kind, send, voices and cents -- Pass::add)
    std::vector<long long> s_cch;
    std::vector<int> s_ckind, s_cnc;
    std::vector<double> s_csend, s_ccents;
    std::vector<StreamDev> s_cdev;
    // THE VALVE AMPLIFIERS (_prep_amplifier, tubeamp.expand): each channel's
    // drive its voice's -- times CC1's first (4 x cc/127) where the voice is
    // not on a rotor -- its products appended, before the speaker sees them
    // (a stream's: the settings kept, its segments walked as it goes -- Pass)
    std::vector<long long> s_ach;
    std::vector<double> s_adr, s_aref, s_aimb, s_asb;
    std::vector<std::vector<double>> s_ass, s_asl;
    {
        std::vector<long long> ach;
        std::vector<double> adr, aref, aimb;
        for (int k = 0, na = (int)nv_song_amp(song, -1, nullptr, nullptr); k < na; k++) {
            long long c;
            int rotor;
            double drv = nv_song_amp(song, k, &c, &rotor), ref, imb;
            nv_song_amp_cfg(song, k, &ref, &imb);
            double sb;
            const double *ss, *sl;
            int ns = nv_song_amp_steps_of(song, k, &sb, &ss, &sl);
            if (ns)                         // (its reference following the file's level: 'steps')
                nv_amp_ref_steps((int)ach.size(), sb, ns, ss, sl);
            s_asb.push_back(ns ? sb : 0.0);
            s_ass.push_back(ns ? std::vector<double>(ss, ss + ns) : std::vector<double>());
            s_asl.push_back(ns ? std::vector<double>(sl, sl + ns) : std::vector<double>());
            aref.push_back(ref);
            aimb.push_back(imb);
            int v;
            if (!rotor && nv_song_first_cc(song, c % 256, NV_CC_DRIVE, &v))     // (the part's CC12: gsefx.part_of)
                drv *= 4.0 * v / 127.0;
            ach.push_back(c);
            adr.push_back(drv);
        }
        s_ach = ach;
        s_adr = adr;
        s_aref = aref;
        s_aimb = aimb;
        if (!ach.empty())
            nv_amp_expand(&rows, &P, dm, (int)ach.size(), ach.data(), adr.data(), aref.data(), aimb.data(), SR);
    }
    // THE CLAVINET's TONE ROCKERS (_prep_clav_rockers): after the valve, before the tremolos
    if (g_stream && nv_song_clavs(song, nullptr, nullptr, 0))
        nv_stream_refuse("a clavinet's rockers");
    nv_clav_pass(song, rows, P);
    // THE ORGANS' TREMOLOS (_prep_tremolo, after the render's length is
    // known): a Tremolo stop's on the notes struck with it drawn, then the
    // wheel's on its channels' rows, the stop's sidebands among them
    // (a stream's: each pass's settings, row by row in Pass::add -- the stop's ranges,
    // the channels' settings and waveforms)
    std::vector<std::array<double, 4>> s_ht;            // (first row, end, rate, depth)
    std::map<long long, std::vector<double>> s_tch, s_twave;
    for (int which = 0; which < 2; which++) {
        int nt = nv_song_organ_tremolos(song, which, nullptr, nullptr, 0);
        if (!nt && !(which == 1 && (nv_song_trems(song, nullptr, nullptr, 0) || !tcfg_m.empty()
                                    || !efx_trem.empty())))
            continue;
        std::vector<int> tch(nt);
        std::vector<double> tcfg(4 * nt);
        nv_song_organ_tremolos(song, which, tch.data(), tcfg.data(), nt);
        // (each keyed by its notes' mix channels, em.channel's: an organ after
        // another tone on its channel stands on channel + TONE_SEG k)
        std::map<int, std::vector<double>> chans;
        for (int q = 0; q < nt; q++) {
            std::vector<double> cf(tcfg.begin() + 4 * q, tcfg.begin() + 4 * q + 4);
            for (int i = 0, nn = nv_song_n_notes(song); i < nn; i++) {
                long long ch;
                int iv[4];
                double dv[2];
                nv_song_get_note(song, i, &ch, iv, dv);
                if (ch != tch[q] || iv[3])
                    continue;
                int cq = E.cmap[nv_song_kidx(song, i)];
                if (cq >= 0 && E.cls_organ[cq] >= 0)
                    chans[(int)nv_song_mix(song, i)] = cf;
            }
        }
        if (which == 1) {                   // ...and an ordinary voice's (_note_tremolo), beside the organs'
            int nv_ = nv_song_trems(song, nullptr, nullptr, 0);
            std::vector<long long> vch(nv_);
            std::vector<double> vcfg(4 * nv_);
            nv_song_trems(song, vch.data(), vcfg.data(), nv_);
            for (int q = 0; q < nv_; q++)
                if (!chans.count((int)vch[q]))
                    chans[(int)vch[q]] = std::vector<double>(vcfg.begin() + 4 * q, vcfg.begin() + 4 * q + 4);
            // ...and the controller matrix's (_TREM_CH's first): its rows' map
            for (auto &kv : tcfg_m) {
                if (chans.count((int)kv.first)) {
                    fprintf(stderr, "nvrender: refused: a controller matrix's tremolo beside a voice's\n");
                    return 2;
                }
                chans[(int)kv.first] = kv.second;
                std::vector<long long> fr, to;
                for (auto &m : tmap[kv.first]) {
                    fr.push_back(m.first);
                    to.push_back(m.second);
                }
                nv_tremolo_brmap(kv.first, (int)fr.size(), fr.data(), to.data());
            }
            // ...and the insertion effect's (Tremolo, Auto Pan, the Tremolo
            // Chorus's: after the matrix's, which keeps its channel)
            const double *WV = E.k.data() + K_EFX + 132 + NV_EFX_NAT * (size_t)E.k[K_EFX + 131] + 30 + 66 + 1024 + 128;
            for (auto &kv : efx_trem) {
                if (tcfg_m.count(kv.first))
                    continue;
                if (chans.count((int)kv.first)) {
                    fprintf(stderr, "nvrender: refused: an insertion effect's tremolo beside a voice's\n");
                    return 2;
                }
                const double *fc = kv.second;
                chans[(int)kv.first] = {fc[56], fc[57], fc[58], 0.0};
                if (fc[55] == 1.0) {
                    const double *w = WV + 19 * (int)fc[59];
                    nv_tremolo_wave(kv.first, (int)w[0], w + 1);
                    s_twave[kv.first] = std::vector<double>(w + 1, w + 1 + 3 * (int)w[0]);
                }
            }
        }
        std::vector<char> mask;
        if (which == 0) {
            int nr = nv_song_n_htrem_rows(song, nullptr, 0);
            if (!nr)
                continue;
            std::vector<long long> ab(2 * nr);
            std::vector<double> hc(2 * nr);
            nv_song_n_htrem_rows(song, ab.data(), nr);
            nv_song_htrem_rows_cfg(song, hc.data(), nr);
            if (g_stream)
                for (int q = 0; q < nr; q++)
                    s_ht.push_back({(double)ab[2 * q], (double)ab[2 * q + 1], hc[2 * q], hc[2 * q + 1]});
            mask.assign(P, 0);
            // (each note's rows at its own stop's rate and depth, mono -- a
            // voice changed on the channel another tremolo, not the last one's)
            std::vector<double> rc(4 * (size_t)P, NAN);
            for (int q = 0; q < nr; q++)
                for (long long r = ab[2 * q]; r < ab[2 * q + 1] && r < P; r++) {
                    mask[r] = 1;
                    rc[4 * r] = hc[2 * q];
                    rc[4 * r + 1] = hc[2 * q + 1];
                    rc[4 * r + 2] = 0.0;
                    rc[4 * r + 3] = 0.0;
                }
            nv_tremolo_row_cfg(P, rc.data());
        }
        if (g_stream && which == 1) {
            for (auto &kv : chans)
                s_tch[kv.first] = kv.second;
            if (!tcfg_m.empty())
                nv_stream_refuse("a controller matrix's tremolo");
            if (!s_ht.empty() && !s_tch.empty())
                nv_stream_refuse("a tremolo stop's notes beside a channel's tremolo");
        }
        tremolo_expand(&rows, &P, dm, chans, which == 0 ? &mask : nullptr, SR);
    }
    // THE SCANNERS (_prep_scanner, scanner.expand): each channel's partials
    // on their band rows, the chorus's dry share and copies, tier B's copies
    std::vector<ScanCh> s_scn;              // (a stream's: row by row in Pass::add, held by note)
    if (g_stream)
        for (size_t q = 0; q < sch.size(); q++) {
            if (std::find(s_ach.begin(), s_ach.end(), sch[q]) != s_ach.end() || scan.regch.count(sch[q]))
                nv_stream_refuse("a scanner on a register's or an amplifier's channel");
            s_scn.push_back(ScanCh{sch[q], srow[q], sdep[q], scho[q]});
        }
    if (!sch.empty())
        nv_scan_expand(E.scan.data(), &rows, &P, dm, (int)sch.size(), sch.data(), srow.data(), sdep.data(),
                       scho.data(), SR);
    // THE CHORUS (_prep_chorus, chorus.expand; _note_chorus_send): each mix
    // channel whose part's first CC93 is past 0, at that send over 127, its
    // first note's comb (offsets_for); where the part has no CC93, the first
    // note whose class has a pedal of its own (chorus_send) or a detuned
    // pair -- in the order those notes came, before the speaker, which
    // colours the copies too
    {
        std::vector<long long> cch;
        std::vector<double> csend, ccents, cgsp;
        std::vector<int> cnc, ckind;
        std::vector<long long> csteps;          // (an entry's share steps: its mix channel's, -1 none)
        // ...or a moving CC93's (entry index: its changes in samples, their shares)
        std::map<size_t, std::pair<std::vector<double>, std::vector<double>>> cstepn;
        std::map<size_t, std::vector<double>> ctaps;     // (an entry's own voices: 8 each)
        std::vector<int> ord(nv_song_n_notes(song));
        for (size_t i = 0; i < ord.size(); i++)
            ord[i] = (int)i;
        // (the note loop's order: onset, channel, key -- sorted(notes))
        auto key = [&](int i) {
            long long ch;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &ch, iv, dv);
            return std::make_tuple(dv[0], ch, iv[0]);
        };
        std::stable_sort(ord.begin(), ord.end(), [&](int a, int b) { return key(a) < key(b); });
        std::vector<int> rank(ord.size());
        for (size_t p = 0; p < ord.size(); p++)
            rank[ord[p]] = (int)p;
        // (a mix channel's first insertion-effect chain's chorus or flanger:
        // a tone's device, or the file's, its share following the file)
        auto push_cf = [&](long long mch) {
            int i0 = fx_cfn[mch];
            cch.push_back(mch);
            csend.push_back(0.0);
            cnc.push_back(0);
            ckind.push_back(2);
            for (int q = 0; q < 8; q++)
                ccents.push_back(0.0);
            if (note_fx[i0] >= 0) {
                const double *fc = fxch.data() + (size_t)NV_FXN * note_fx[i0];
                if (mch >= 65536)
                    fc -= NV_FXN;                   // (a parallel type's branch B: its record)
                double G[40] = {fc[15], fc[16], fc[17], fc[18], fc[19], 0.0, 2.0};
                for (int q = 0; q < 13; q++)
                    G[7 + q] = E.k[K_GSPLACE + q];
                G[20] = 0.0; G[21] = 0.0; G[22] = 0.0; G[23] = 1.0;           // (left, at 0)
                G[24] = 1.0; G[25] = fc[31]; G[26] = 0.0; G[27] = 1.0;        // (...right, at its phase: pi, or Space D's)
                // ...or the type's own voices: the Hexa Chorus's six, the 3D Chorus's two
                const double *HX = E.k.data() + K_EFX + 132 + NV_EFX_NAT * (size_t)E.k[K_EFX + 131] + 30 + 66 + 1024
                                   + 128 + 5 * 19;
                std::vector<double> tv;
                if (fc[87] == 1.0) {
                    const double dd = fc[89], dv = (fc[90] - 0x40) / 20.0;
                    for (int k = 0; k < 6; k++) {
                        const double *P5 = HX + 5 * (6 * (int)fc[88] + k);
                        tv.insert(tv.end(), P5, P5 + 5);
                        tv.push_back(2.0 * M_PI * k / 6.0);
                        tv.push_back(0.5 * dd * (k / 5.0 - 0.5) / 1000.0);      // (HEXA_DLY_STEP_MS)
                        tv.push_back(std::max(0.0, 1.0 + dv * (k / 5.0 - 0.5)));
                    }
                } else if (fc[87] == 2.0) {
                    for (int k = 0; k < 2; k++) {
                        const double *P5 = HX + 5 * 128 * 6 + 5 * k;
                        tv.insert(tv.end(), P5, P5 + 5);
                        tv.push_back(k ? M_PI : 0.0);
                        tv.push_back(0.0);
                        tv.push_back(1.0);
                    }
                }
                if (!tv.empty()) {
                    G[6] = (double)(tv.size() / 8);
                    ctaps[cch.size() - 1] = tv;
                }
                cgsp.insert(cgsp.end(), G, G + 40);
                csteps.push_back(mch);
            } else {
                int cq0 = E.cmap[nv_song_kidx(song, i0)];
                const NoteClass *k0 = (const NoteClass *)E.classes[cq0].data();
                cgsp.insert(cgsp.end(), k0->cf_p, k0->cf_p + 40);
                csteps.push_back(-1);
            }
        };
        std::set<long long> seen;
        for (int i : ord) {
            long long ch;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &ch, iv, dv);
            long long mch = nv_song_mix(song, i);
            // (A PARALLEL TYPE's BRANCH B's chorus, on its virtual channel: at
            // the chain's first note -- after the part's own entry where the
            // chain made it, else ahead of what this note adds: _CHORUS_CH's order)
            const bool vcf = note_fx[i] >= 0 && fx_first[i] && fx_cfn.count(mch + 65536)
                             && !seen.count(mch + 65536);
            if (vcf && (!fx_cfn.count(mch) || seen.count(mch))) {
                seen.insert(mch + 65536);
                push_cf(mch + 65536);
            }
            if (seen.count(mch))
                continue;
            auto cfi = fx_cfn.find(mch);
            const bool cf = cfi != fx_cfn.end();
            if (cf && rank[i] >= rank[cfi->second]) {
                seen.insert(mch);
                push_cf(mch);
                if (vcf && !seen.count(mch + 65536)) {
                    seen.insert(mch + 65536);
                    push_cf(mch + 65536);
                }
                continue;
            }
            int nc = nv_song_ccs(song, mch % 256, 93, nullptr, nullptr, 0);
            if (nc <= 0) {
                // (no CC93: the voice's own pedal, or its pair, if it has one;
                // else a later note's may)
                int cq = E.cmap[nv_song_kidx(song, i)];
                const NoteClass *nk = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
                if (!nk || !(nk->cho_send || nk->pair_set))
                    continue;
                seen.insert(mch);
                if (cf) {
                    push_cf(mch);
                    continue;
                }
                csteps.push_back(-1);
                cgsp.insert(cgsp.end(), 40, 0.0);
                cch.push_back(mch);
                csend.push_back(nk->cho_send ? nk->cho_send : 1.0);
                cnc.push_back(nk->cho_send ? nk->n_cho : 2);
                ckind.push_back(nk->cho_send ? 0 : 1);
                for (int q = 0; q < 8; q++)
                    ccents.push_back(nk->cho_send ? (q < nk->n_cho ? nk->cho_cents[q] : 0.0)
                                     : q == 0 ? nk->pair_lo : q == 1 ? nk->pair_hi : 0.0);
                continue;
            }
            seen.insert(mch);
            std::vector<double> tt(nc);
            std::vector<int> vv(nc);
            nv_song_ccs(song, mch % 256, 93, tt.data(), vv.data(), nc);
            // (a GS file's CC93 that MOVES -- its values not all one, one past
            // 0 -- follows the song, from its first value whatever it is)
            bool vmoves = false;
            int vmax = vv[0];
            for (int v : vv) {
                vmoves = vmoves || v != vv[0];
                vmax = std::max(vmax, v);
            }
            const bool moving = gs_cho[0] >= 0.0 && vmoves && vmax > 0;
            if (vv[0] <= 0 && !moving) {
                if (cf)
                    seen.erase(mch);        // (no entry: the chain's comes at its note)
                continue;
            }
            if (cf) {
                push_cf(mch);               // (an entry here, the chain's in it)
                continue;
            }
            if (moving) {
                // ...ITS CC93 FOLLOWING THE SONG, as CC91 does (send_steps): the
                // share each row's onset finds, through the chorus pass's own
                // per-row share -- each change at its sample, its device's share
                auto cshare = [&](int v) {
                    double ca = v / 127.0 * gs_cho[5];
                    return ca * ca / (1.0 + ca * ca);
                };
                std::vector<double> st, sv;
                for (int q = 0; q < nc; q++) {
                    st.push_back((double)(long long)nearbyint(tt[q] * SR));
                    sv.push_back(cshare(vv[q]));
                }
                cstepn[cch.size()] = std::make_pair(st, sv);
                cch.push_back(mch);
                csend.push_back(0.0);
                cnc.push_back(0);
                ckind.push_back(2);
                for (int q = 0; q < 8; q++)
                    ccents.push_back(0.0);
                double G[40] = {gs_cho[0], gs_cho[1], gs_cho[2], gs_cho[3], gs_cho[4], sv[0], 2.0};
                for (int q = 0; q < 13; q++)
                    G[7 + q] = E.k[K_GSPLACE + q];
                G[20] = 0.0; G[21] = 0.0; G[22] = 0.0; G[23] = 1.0;           // (GS_TAPS: left, at 0)
                G[24] = 1.0; G[25] = M_PI; G[26] = 0.0; G[27] = 1.0;          // (...right, at pi)
                cgsp.insert(cgsp.end(), G, G + 40);
                csteps.push_back(-1);
                continue;
            }
            if (gs_cho[0] >= 0.0) {
                // A SOUND CANVAS FILE'S CHORUS is its device (chorus.gs_copies):
                // the share the device's added power takes out of the dry
                double a = vv[0] / 127.0 * gs_cho[5];
                if (a * a / (1.0 + a * a) <= 0.02)
                    continue;               // (chorus.expand: a send at FLOOR or under makes no copies)
                cch.push_back(mch);
                csend.push_back(0.0);
                cnc.push_back(0);
                ckind.push_back(2);
                for (int q = 0; q < 8; q++)
                    ccents.push_back(0.0);
                double G[40] = {gs_cho[0], gs_cho[1], gs_cho[2], gs_cho[3], gs_cho[4], a * a / (1.0 + a * a), 2.0};
                for (int q = 0; q < 13; q++)
                    G[7 + q] = E.k[K_GSPLACE + q];
                G[20] = 0.0; G[21] = 0.0; G[22] = 0.0; G[23] = 1.0;           // (GS_TAPS: left, at 0)
                G[24] = 1.0; G[25] = M_PI; G[26] = 0.0; G[27] = 1.0;          // (...right, at pi)
                cgsp.insert(cgsp.end(), G, G + 40);
                csteps.push_back(-1);
                continue;
            }
            int cq = E.cmap[nv_song_kidx(song, i)];
            const NoteClass *nk = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
            cch.push_back(mch);
            csend.push_back(vv[0] / 127.0);
            cnc.push_back(nk ? nk->n_cho : 0);
            ckind.push_back(0);
            csteps.push_back(-1);
            cgsp.insert(cgsp.end(), 40, 0.0);
            for (int q = 0; q < 8; q++)
                ccents.push_back(nk && q < nk->n_cho ? nk->cho_cents[q] : 0.0);
        }
        for (size_t q = 0; q < csteps.size(); q++)
            if (csteps[q] >= 0)             // (the file's chain: its share at each row's onset)
                nv_chorus_share_steps((int)q, (int)fx_ts.size(), fx_ts.data(), fx_share[csteps[q]].data());
        for (auto &kv : ctaps)              // (a type's own voices)
            nv_chorus_taps((int)kv.first, (int)(kv.second.size() / 8), kv.second.data());
        for (auto &kv : cstepn)             // (a moving CC93's: its steps, in samples)
            nv_chorus_share_steps_n((int)kv.first, (int)kv.second.first.size(), kv.second.first.data(),
                                    kv.second.second.data());
        if (g_stream)                       // (a stream's: row by row -- Pass::add; a device refused)
            for (size_t q = 0; q < cch.size(); q++) {
                StreamDev D;
                if (ckind[q] == 2) {
                    // the channel's passes, from its loudest row's share (nv_chorus_expand's
                    // np.all(|g| < FLOOR / 2) break, every row's): pass A's onsets
                    D.G.assign(cgsp.begin() + 40 * q, cgsp.begin() + 40 * q + 40);
                    if (ctaps.count(q))
                        D.TV = ctaps[q];
                    if (csteps[q] >= 0) {
                        D.ts = fx_ts;
                        D.vs = fx_share[csteps[q]];
                    } else if (cstepn.count(q)) {
                        D.ts = cstepn[q].first;
                        D.vs = cstepn[q].second;
                        D.samp = true;
                    }
                    double mx = 0.0, lo = INFINITY;
                    bool rows_ = false, any = false;
                    auto it = scan.nons.find(cch[q]);
                    if (it != scan.nons.end())
                        for (double t : it->second) {
                            double sh = D.share_at(t, SR);
                            mx = rows_ ? std::max(mx, sh) : sh;
                            rows_ = true;
                            any = any || sh > 0.0;
                            lo = std::min(lo, t);
                        }
                    if (rows_ && !D.ts.empty() && std::find(s_ach.begin(), s_ach.end(), cch[q]) != s_ach.end()) {
                        // (the products' onsets: inside [lo, the last release] -- the share's
                        // highest there no higher than the rows', or refused)
                        const double hi = scan.noffs[cch[q]];
                        double top = D.share_at(lo, SR);
                        const double u0 = D.samp ? lo : lo / SR, u1 = D.samp ? hi : hi / SR;
                        for (size_t i = 0; i < D.ts.size(); i++)
                            if (D.ts[i] > u0 && D.ts[i] <= u1)
                                top = std::max(top, D.vs[std::min(i, D.vs.size() - 1)]);
                        if (top > mx || (top > 0.0 && !any))
                            nv_stream_refuse("a chorus device's share rising on an amplifier's channel");
                    }
                    if (rows_ && any) {
                        const int ntap = !D.TV.empty() ? (int)(D.TV.size() / 8) : (int)D.G[6];
                        const double fb = D.G[3], fb2 = pow(fb, 2.0);
                        const double passes = fb2 < 1.0 ? (1.0 - pow(fb2, 16.0)) / (1.0 - fb2) : 16.0;
                        const double w = sqrt(mx / (double)ntap / passes);
                        for (int k = 1; k <= 16; k++) {
                            const double fk = pow(fb, (double)(k - 1));
                            if (fabs(w * fk) < 0.02 * 0.5 || (k > 1 && fb == 0.0))
                                break;
                            D.kmax = k;
                        }
                    }
                }
                s_cdev.push_back(D);
                s_cch.push_back(cch[q]);
                s_ckind.push_back(ckind[q]);
                s_csend.push_back(csend[q]);
                s_cnc.push_back(cnc[q]);
                s_ccents.insert(s_ccents.end(), ccents.begin() + 8 * q, ccents.begin() + 8 * q + 8);
            }
        if (!cch.empty())
            nv_chorus_expand(&rows, &P, dm, (int)cch.size(), cch.data(), csend.data(), cnc.data(), ccents.data(),
                             ckind.data(), cgsp.data(), SR);
    }
    // THE INSERTION EFFECTS' EQ (_prep_insertion_eq, gsefx.eq_gain): every
    // row of an effect's mix channel, the valve's products and the copies
    // included, at its frequency -- shelves at 400 Hz and 4 kHz, a peaking
    // mid (the table's float64 still: the cast is the render's last)
    if (!efx_eq.empty()) {                  // (a stream's rows take it in its store: Pass::add)
        const int cM = col("mch");
        for (long long r = 0; r < P; r++) {
            double *row = rows + NCOLS * r;
            auto it = efx_eq.find((long long)row[cM]);
            if (it != efx_eq.end())
                eq_row(it->second, row);
        }
    }
    // THE SPEAKER CABINETS (_prep_cabinet, cabinet.expand): every row on a
    // cabinet's channel through its response at the row's frequency, after
    // the amplifier, before the rotors
    nv_cabinet_pass(song, rows, P);         // (a stream's rows take it in its store: Pass::add)
    // THE ROTATING SPEAKERS (_prep_rotating_speaker, leslie.expand): each
    // Leslie channel's half-moon from its CC1s (leslie.zone), on its default
    // speed from 0 where the first is later; the cabinet, the crossover's
    // copies, the Doppler, each rotor row's lobe
    std::vector<long long> lch;
    std::vector<int> lnreq;
    std::vector<double> lreq, lgs;
    void *lobe[5] = {nullptr};
    const double *LES = E.les.data();
    for (int k = 0, nl = nv_song_leslie(song, -1, nullptr); k < nl; k++) {
        long long c;
        int kind = nv_song_leslie(song, k, &c);
        int nc = nv_song_ccs(song, c % 256, NV_CC_LESLIE, nullptr, nullptr, 0);     // (the part's CC80: gsefx.part_of)
        std::vector<double> ct(nc);
        std::vector<int> cv(nc);
        nv_song_ccs(song, c % 256, NV_CC_LESLIE, ct.data(), cv.data(), nc);
        if (E.les.empty()) {
            fprintf(stderr, "nvrender: %s is an export from before the Leslie (native_export.py again)\n", argv[1]);
            return 1;
        }
        int nq = 0;
        if (nc == 0 || ct[0] > 0.0) {
            lreq.push_back(0.0);
            lreq.push_back(kind == 2 ? LES[4] : LES[3]);
            nq++;
        }
        for (int q = 0; q < nc; q++) {
            lreq.push_back(ct[q]);
            lreq.push_back(cv[q] < 42 ? 0.0 : cv[q] < 85 ? LES[3] : LES[4]);     // leslie.zone
            nq++;
        }
        lch.push_back(c);
        lnreq.push_back(nq);
        lgs.insert(lgs.end(), 10, 0.0);
    }
    // ...AND THE INSERTION ROTARIES (rotary_setup): each mix channel's from
    // its first note through one, each rotor asked slow or fast as the
    // type's Speed stands at each change of the timeline; its spin times,
    // levels and microphones the first setting's
    {
        const long nles = (long)lch.size();
        int nn = nv_song_n_notes(song);
        for (int i = 0; i < nn; i++) {
            if (note_fx.empty() || note_fx[i] < 0 || !fx_first[i])
                continue;
            // (the part's, or -- a parallel type's -- branch B's on its virtual
            // channel: at(events, vc, t), B where the chain is one)
            const double *fc0 = fxch.data() + (size_t)NV_FXN * note_fx[i];
            for (int br = 0; br < 2; br++) {
            if (br && fc0[208] == 0.0)
                break;
            if ((br ? fc0 - NV_FXN : fc0)[140] == 0.0)
                continue;
            const long long m0 = nv_song_mix(song, i), m = br ? m0 + 65536 : m0;
            if (std::find(lch.begin() + nles, lch.end(), m) != lch.end())
                continue;
            if (std::find(lch.begin(), lch.begin() + nles, m) != lch.begin() + nles) {
                fprintf(stderr, "nvrender: refused: a Rotary on a Leslie's channel\n");
                return 2;
            }
            std::vector<double> hr, dr;
            const double *first = nullptr;
            for (double t : fx_ts) {
                int pre = fx_prefix(t), cq = fx_on(m0 % 256, pre) ? fx_chain(pre) : -1;
                if (cq == -3)
                    return 2;
                const double *sc = cq >= 0 ? fxch.data() + (size_t)NV_FXN * cq : nullptr;
                if (br && sc)
                    sc = sc[208] != 0.0 ? sc - NV_FXN : nullptr;
                if (!sc || sc[140] == 0.0)
                    continue;
                if (!first)
                    first = sc;
                hr.push_back(t);
                hr.push_back(sc[151] != 0.0 ? sc[144] : sc[143]);
                dr.push_back(t);
                dr.push_back(sc[151] != 0.0 ? sc[142] : sc[141]);
            }
            if (!first)
                continue;
            const double gs[10] = {1.0, first[147], first[148], first[145], first[146], first[149], first[150],
                                   1.0, first[152], (double)(dr.size() / 2)};
            lreq.insert(lreq.end(), hr.begin(), hr.end());
            lreq.insert(lreq.end(), dr.begin(), dr.end());
            lch.push_back(m);
            lnreq.push_back((int)(hr.size() / 2));
            lgs.insert(lgs.end(), gs, gs + 10);
            }
        }
    }
    // (a stream's rotors: its rows through them one at a time -- Pass::add)
    void *s_les = g_stream && !lch.empty()
                      ? nv_leslie_new((int)lch.size(), lch.data(), lnreq.data(), lreq.data(), SR, LES, lgs.data(),
                                      E.k.data() + K_GSPLACE)
                      : nullptr;
    if (!lch.empty() && nv_leslie_expand_gs(&rows, &P, dm, (int)lch.size(), lch.data(), lnreq.data(), lreq.data(),
                                            SR, LES, lobe, nullptr, nullptr, lgs.data(),
                                            E.k.data() + K_GSPLACE) < 0) {
        fprintf(stderr, "nvrender: refused: a Leslie by sidebands (leslie.KERNEL_LOBE off)\n");
        return 2;
    }
    const long N = (long)out[0];
    const int nblk = (int)out[1];
    // ...in prepare's final types (FINAL_DTYPES)
    auto fcol = [&](const char *name) {
        int c = col(name);
        std::vector<double> v(P);
        for (long long r = 0; r < P; r++) {
            double x = rows[NCOLS * r + c];
            switch (E.fin[c]) {
            case 1: x = (double)(float)x; break;
            case 2: x = (double)(long long)x; break;
            case 3: x = (double)(int32_t)x; break;
            }
            v[r] = x;
        }
        return v;
    };
    std::vector<double> dcols[3];
    const char *DN[3] = {"om", "p0", "p0R"};
    for (int q = 0; q < 3; q++)
        dcols[q] = fcol(DN[q]);
    std::vector<std::vector<float>> fcols(29);
    for (int q = 0; q < 28; q++) {
        std::vector<double> v = fcol(VF[q]);
        fcols[q].assign(v.begin(), v.end());
    }
    if (dm[1])
        fcols[28].assign((float *)dm[1], (float *)dm[1] + P);
    std::vector<long> lcols[2];
    const char *LN[2] = {"non", "noff"};
    for (int q = 0; q < 2; q++) {
        std::vector<double> v = fcol(LN[q]);
        lcols[q].assign(v.begin(), v.end());
    }
    std::vector<int> icols[4];
    const char *IN[3] = {"gr", "cr", "br"};
    for (int q = 0; q < 3; q++) {
        std::vector<double> v = fcol(IN[q]);
        icols[q].assign(v.begin(), v.end());
    }
    if (dm[0])
        icols[3].assign((int32_t *)dm[0], (int32_t *)dm[0] + P);
    double *dp[3] = {dcols[0].data(), dcols[1].data(), dcols[2].data()};
    float *fp[29];
    for (int q = 0; q < 29; q++)
        fp[q] = fcols[q].empty() ? nullptr : fcols[q].data();
    long *lp[2] = {lcols[0].data(), lcols[1].data()};
    int *ip[4] = {icols[0].data(), icols[1].data(), icols[2].data(), icols[3].empty() ? nullptr : icols[3].data()};
    // THE RENDER, through blockrender's kernel libraries
    void *fn[3];
    const char *FN[3] = {"synth_voice", "synth_voice_xdec", "synth_voice_damp"};
    for (int q = 0; q < 3; q++) {
        void *h = dlopen(E.libs[q].c_str(), RTLD_NOW | RTLD_LOCAL);
        fn[q] = h ? dlsym(h, FN[q]) : nullptr;
        if (!fn[q]) {
            fprintf(stderr, "nvrender: no %s in %s\n", FN[q], E.libs[q].c_str());
            return 1;
        }
    }
    float noRows[16] = {0}, sh[4];
    // THE ORGANS' GATES AND SWELLS (registration_blocks), and the swell's law
    const int ngr = nv_song_n_grows(song), nso = nv_song_n_organs(song);
    std::vector<float> Gt(ngr ? (size_t)ngr * nblk : 1, 1.0f), St(nso ? (size_t)nso * nblk : 1, 1.0f);
    double shd[4];
    for (int q = 0; q < 4; q++)
        shd[q] = E.k[K_SH + q];
    if (nso && nv_song_organ_rows(song, nblk, (int)BLK, SR, E.k[K_TAU], Gt.data(), St.data(), shd) < 0) {
        fprintf(stderr, "nvrender: refused: two organs with swell laws of their own\n");
        return 2;
    }
    for (int q = 0; q < 4; q++)
        sh[q] = (float)shd[q];
    // the rows (_prep_bend_arrays): a gesture's ratio and phase a block (its
    // channel's fader's level at each edge, where it has one); a fader's
    // ratio 1 and phase 0, its level; no rows, one of ones and no levels
    size_t ng = gch.size(), nr = std::max<size_t>(ng + nbr_ + nw + nsr + fch.size() + mrows.size() + prows.size() + sir.size()
                                                  + trows.size() + arows.size(), 1);
    std::vector<float> BRr(nr * nblk, 1.0f), BLr;
    std::vector<double> BCr(nr * nblk, 0.0);
    for (size_t r = 0; r < ng; r++)
        nv_bend_gesture(midi, song, E.k[K_BEND_SEMIS], gch[r], nblk, (int)BLK, SR, BRr.data() + r * nblk,
                        BCr.data() + r * nblk);
    if (!fch.empty() || nw || nbr_ || !sir.empty() || !trows.empty())
        BLr.assign(nr * (nblk + 1), 1.0f);
    for (size_t q = 0; q < arows.size(); q++) {  // the aliasing sweeps' (theirs: after the tremolos')
        if ((long)arows[q].r.size() != (long)nblk) {
            fprintf(stderr, "nvrender: refused: an aliasing sweep's rows not the render's length\n");
            return 2;
        }
        std::copy(arows[q].r.begin(), arows[q].r.end(), BRr.data() + ((size_t)abase + q) * nblk);
        std::copy(arows[q].c.begin(), arows[q].c.end(), BCr.data() + ((size_t)abase + q) * nblk);
    }
    for (size_t q = 0; q < sir.size(); q++) {   // the sirens' rotors (their place: after the rest)
        if ((long)sir[q].r.size() != (long)nblk) {
            fprintf(stderr, "nvrender: refused: a siren's rows not the render's length\n");
            return 2;
        }
        size_t rq = (size_t)sbase + q;
        std::copy(sir[q].r.begin(), sir[q].r.end(), BRr.data() + rq * nblk);
        std::copy(sir[q].c.begin(), sir[q].c.end(), BCr.data() + rq * nblk);
        std::copy(sir[q].l.begin(), sir[q].l.end(), BLr.data() + rq * (nblk + 1));
    }
    for (size_t q = 0; q < bch.size(); q++) {   // the breath's, after the gestures
        size_t r0 = ng + 2 * q;
        std::vector<float> nl(nblk + 1);
        nv_breath_rows(9173ULL + (unsigned long long)bch[q], nblk, (int)BLK, SR, bcls[q]->breath_p,
                       BRr.data() + r0 * nblk, BCr.data() + r0 * nblk, BLr.data() + r0 * (nblk + 1), nl.data());
        std::copy(nl.begin(), nl.end(), BLr.data() + (r0 + 1) * (nblk + 1));
        // ...TIMES THE CHANNEL's GESTURE where it has one (its wheel, its
        // tuning): the ratio a product in float64 kept as float32, the phase
        // the running sum of the product's (bend_blocks')
        size_t gr = (size_t)(std::find(gch.begin(), gch.end(), bch[q]) - gch.begin());
        if (gr < ng) {
            float *rr = BRr.data() + r0 * nblk;
            double *cc = BCr.data() + r0 * nblk;
            const float *g = BRr.data() + gr * nblk;
            for (long b = 0; b < nblk; b++)
                rr[b] = (float)((double)g[b] * (double)rr[b]);
            double acc = 0.0;
            for (long b = 0; b < nblk; b++) {
                cc[b] = acc;
                acc = acc + ((double)rr[b] - 1.0) * (double)BLK;
            }
        }
    }
    if (nw)                                 // the chests' wind, after the breath
        nv_song_organ_wind(song, nblk, (int)BLK, SR, Gt.data(), BRr.data() + (ng + nbr_) * nblk,
                           BCr.data() + (ng + nbr_) * nblk, BLr.data() + (ng + nbr_) * (nblk + 1));
    for (size_t q = 0; q < sch.size(); q++)     // the scanners', after the wind
        nv_scan_rows(E.scan.data(), nblk, (int)BLK, SR, sdep[q], scho[q], BRr.data() + (size_t)srow[q] * nblk,
                     BCr.data() + (size_t)srow[q] * nblk);
    if (!fch.empty()) {
        for (size_t r = 0; r < fch.size(); r++) {
            float *Lf = BLr.data() + (ng + nbr_ + nw + nsr + r) * (nblk + 1);
            nv_bend_fader(midi, song, fch[r], nblk, (int)BLK, SR, E.k[K_TAU], E.k[K_FADER_TAIL], E.k[K_STAMP_S],
                          E.k[K_STAMPED_SHARE], (int)E.k[K_GM_VOL], (int)E.k[K_GM_EXPR], Lf, swell.data());
            long gi = (long)br[256 + fch[r]];
            if (gi >= 0)                    // the channel's gesture rides its fader too
                std::copy(Lf, Lf + nblk + 1, BLr.data() + gi * (nblk + 1));
            for (size_t q = 0; q < bch.size(); q++)     // ...and its breath's, under it
                if (bch[q] == fch[r])
                    for (int b = 0; b < 2; b++) {
                        float *bl = BLr.data() + (ng + 2 * q + b) * (nblk + 1);
                        for (long e = 0; e <= nblk; e++)
                            bl[e] = bl[e] * Lf[e];
                    }
            for (size_t q = 0; q < sch.size(); q++)     // ...and its scanner's rows
                if (sch[q] == fch[r])
                    for (int b = 0; b < 6; b++)
                        std::copy(Lf, Lf + nblk + 1, BLr.data() + (size_t)(srow[q] + b) * (nblk + 1));
            for (size_t q = 0; q < prows.size(); q++)   // ...and its zone's MPE notes' rows (_own)
                if (prows[q].mgr == fch[r]) {
                    float *bl = BLr.data() + ((size_t)pbase + q) * (nblk + 1);
                    for (long e = 0; e <= nblk; e++)
                        bl[e] = bl[e] * Lf[e];
                }
            for (size_t q = 0; q < sir.size(); q++)     // ...and its sirens' levels, under it
                if (sir[q].ch == fch[r]) {
                    float *bl = BLr.data() + ((size_t)sbase + q) * (nblk + 1);
                    for (long e = 0; e <= nblk; e++)
                        bl[e] = bl[e] * Lf[e];
                }
        }
    }
    for (size_t q = 0; q < prows.size(); q++)      // MPE's notes' rows (after the meends')
        nv_bend_rows(prows[q].t.data(), prows[q].r.data(), (int)prows[q].t.size(), nblk, (int)BLK, SR,
                     BRr.data() + ((size_t)pbase + q) * nblk, BCr.data() + ((size_t)pbase + q) * nblk);
    for (size_t q = 0; q < mrows.size(); q++) {    // the meends', last (no fader rides them: _LROW's _own)
        const Meend &m = mrows[q];
        std::vector<double> wt;
        std::vector<int> wp;
        for (auto &w : wheel[m.ch]) {
            wt.push_back(w.first);
            wp.push_back(w.second);
        }
        double r0;
        size_t r = (size_t)mbase + q;
        nv_meend_note(wt.data(), wp.data(), (int)wt.size(), m.on, m.off, m.nc, m.sw.data(), (int)m.sw.size(),
                      m.rst, m.st, nblk, (int)BLK, SR, &r0, BRr.data() + r * nblk, BCr.data() + r * nblk);
    }
    // ...and THE MATRIX'S TREMOLO's (_prep_matrix_tremolo), last: each its
    // parent's ratio and phase, and its level times the depth's curve over
    // its peak (onepole_edges: the faders' glide, from 0)
    for (size_t q = 0; q < trows.size(); q++) {
        const long long c = trows[q].ch, p = trows[q].parent;
        const auto &tv = cmx_tva[c];
        double pk = tv[0].second;
        for (auto &e : tv)
            if (e.second > pk)
                pk = e.second;
        std::vector<std::pair<double, double>> segs = {{0.0, 0.0}};
        for (auto &e : tv)
            segs.push_back(std::make_pair(e.first, e.second / pk));
        std::vector<float> cur(nblk + 1);
        double v = 0.0, tau = E.k[K_TAU];
        for (size_t k = 0; k < segs.size(); k++) {
            double t0 = segs[k].first, target = segs[k].second;
            double t1 = k + 1 < segs.size() ? segs[k + 1].first : 1e18;
            for (long e = 0; e <= nblk; e++) {
                double te = (double)(e * (long)BLK) / SR;
                if (te >= t0 && te < t1)
                    cur[e] = (float)(target + (v - target) * exp(-(te - t0) / tau));
            }
            if (t1 < 1e17)
                v = target + (v - target) * exp(-(t1 - t0) / tau);
        }
        size_t r = (size_t)tbase + q;
        if (p >= 0) {
            std::copy(BRr.begin() + p * nblk, BRr.begin() + (p + 1) * nblk, BRr.begin() + r * nblk);
            std::copy(BCr.begin() + p * nblk, BCr.begin() + (p + 1) * nblk, BCr.begin() + r * nblk);
        }
        for (long e = 0; e <= nblk; e++)
            BLr[r * (nblk + 1) + e] = (p >= 0 ? BLr[p * (nblk + 1) + e] : 1.0f) * cur[e];
    }
    if (const char *dp_ = getenv("TUNING_NVRENDER_DUMP")) {
        // (a debugging dump: the table as prepared, the gates, swells and bend rows)
        auto put = [&](const char *ext, const void *p, size_t n) {
            FILE *df = fopen((std::string(dp_) + ext).c_str(), "wb");
            if (df) {
                fwrite(p, 1, n, df);
                fclose(df);
            }
        };
        put(".rows", rows, sizeof(double) * NCOLS * P);
        put(".G", Gt.data(), sizeof(float) * Gt.size());
        put(".S", St.data(), sizeof(float) * St.size());
        put(".BR", BRr.data(), sizeof(float) * BRr.size());
        put(".BC", BCr.data(), sizeof(double) * BCr.size());
        if (!BLr.empty())
            put(".BL", BLr.data(), sizeof(float) * BLr.size());
        put(".sh", sh, sizeof sh);
    }
    // ...and the rotors' angles on the kernel's grid (angle_table), the lobe's kernel
    std::vector<float> LANG;
    long lgn = 0;
    void *slo = nullptr;
    if (!lch.empty()) {
        lgn = nv_leslie_angles_gs((int)lch.size(), lnreq.data(), lreq.data(), N, SR, (int)BLK, LES, nullptr,
                                  lgs.data());
        LANG.resize((size_t)2 * lch.size() * lgn);
        nv_leslie_angles_gs((int)lch.size(), lnreq.data(), lreq.data(), N, SR, (int)BLK, LES, LANG.data(),
                            lgs.data());
        void *h = dlopen(E.lobe_lib.c_str(), RTLD_NOW | RTLD_LOCAL);
        slo = h ? dlsym(h, "synth_voice_lobe") : nullptr;
        if (!slo) {
            fprintf(stderr, "nvrender: no synth_voice_lobe in %s\n", E.lobe_lib.c_str());
            return 1;
        }
    }
    // THE MOVING FILTERS (filter_prep, efxfilter: a tone's insertion effect's
    // Phaser or wah): each mix channel's from its first note that has one, in
    // the note loop's order (_FILTER_CH); its control at each point of the
    // kernel's grid (FCT, float32), its rows' type and parameters -- through
    // synth_voice_lobe, which carries it; a table with no Leslie on no rotor
    std::vector<float> FCT;
    long fgn = 0;
    std::vector<int> fsrc, ftyc;
    std::vector<float> fpc_[3];
    // (...and each filtered channel's row, type and parameters, for a stream's
    // windows -- filter_prep's EF.columns -- with fmx, the most it lifts any
    // frequency: efxfilter.peak, the GPU's retirement's bound)
    struct FltCh {
        long long ch;
        int row, ty;
        float p[3], mx;
    };
    std::vector<FltCh> fltch;
    auto flt_peak = [](int ty, double pa, double pb, double pc) {
        (void)pc;
        if (ty == 1 || ty == 4)
            return std::max(1.0, (1.0 - pa) + pa / std::max(1e-3, 1.0 - std::fabs(pb)));
        if (ty == 2 || ty == 3)
            return std::max(1.0, (1.0 - pb) + pb * std::max(pa, 1.0));
        if (ty == 5)
            return std::max(1.0, pb * (pa + 1.0 + 0.7 + 0.5));
        return 1.0;
    };
    {
        std::vector<long long> fch_, fpart_;
        std::vector<const NoteClass *> fk_;
        // (a file's chain's: its type and parameters the first setting's, its
        // pedal each setting's from its time -- filter_setup's segs)
        struct FxFlt {
            double ty, pa, pb, pc;
            std::vector<double> ts, hz;
            std::vector<std::array<double, 6>> ctl;     // (each setting's control: kind, c1-c5)
        };
        std::vector<FxFlt> ff_;
        int nn = nv_song_n_notes(song);
        std::vector<int> ord(nn);
        std::vector<double> on_(nn);
        std::vector<long long> ch_(nn);
        std::vector<int> key_(nn);
        for (int i = 0; i < nn; i++) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            ord[i] = i; on_[i] = dv[0]; ch_[i] = c; key_[i] = iv[0];
        }
        std::stable_sort(ord.begin(), ord.end(), [&](int a, int b) {
            if (on_[a] != on_[b])
                return on_[a] < on_[b];
            if (ch_[a] != ch_[b])
                return ch_[a] < ch_[b];
            return key_[a] < key_[b];
        });
        for (int i : ord) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            int cq = E.cmap[nv_song_kidx(song, i)];
            const NoteClass *k = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
            long long m = nv_song_mix(song, i);
            if (std::find(fch_.begin(), fch_.end(), m) != fch_.end())
                continue;
            if (note_fx[i] >= 0) {
                // (the part's, then -- a parallel type's -- branch B's on its
                // virtual channel: at(events, vc, t), B where the chain is one)
                const double *fc0 = fxch.data() + (size_t)NV_FXN * note_fx[i];
                for (int br = 0; br < 2; br++) {
                    if (br && fc0[208] == 0.0)
                        break;
                    const double *fc = br ? fc0 - NV_FXN : fc0;
                    const long long mm = br ? m + 65536 : m;
                    if (!fx_first[i] || fc[50] == 0.0 || std::find(fch_.begin(), fch_.end(), mm) != fch_.end())
                        continue;
                    FxFlt F;
                    for (double t : fx_ts) {
                        int pre = fx_prefix(t), cq = fx_on(m % 256, pre) ? fx_chain(pre) : -1;
                        if (cq == -3)
                            return 2;
                        const double *sc = cq >= 0 ? fxch.data() + (size_t)NV_FXN * cq : nullptr;
                        if (br && sc)
                            sc = sc[208] != 0.0 ? sc - NV_FXN : nullptr;
                        if (!sc || sc[50] == 0.0)
                            continue;
                        if (!F.ctl.empty() && (sc[128] == 3.0) != (F.ctl[0][0] == 3.0))
                            continue;           // (not the first's family, vowel or not: filter_setup drops it)
                        if (F.ts.empty()) {
                            F.ty = sc[51]; F.pa = sc[52]; F.pb = sc[53]; F.pc = sc[134];
                        }
                        F.ts.push_back(t);
                        F.hz.push_back(sc[54]);
                        F.ctl.push_back({sc[128], sc[129], sc[130], sc[131], sc[132], sc[133]});
                    }
                    if (F.ts.empty())
                        continue;
                    fch_.push_back(mm);
                    fk_.push_back(nullptr);
                    fpart_.push_back(c);
                    ff_.push_back(F);
                }
                continue;
            }
            // (a tone's own effect's filter not where the file puts its part on one: _EFXN)
            if (!k || !k->flt_set || iv[3] || (note_fx[i] == -2 && k->flt_set == 1))
                continue;
            fch_.push_back(m);
            fk_.push_back(k);
            fpart_.push_back(c);
            ff_.push_back(FxFlt());
        }
        if (!fch_.empty()) {
            const long grid = (BLK % 128 == 0 && BLK / 128 <= 64) ? 128 : (long)BLK;     // (leslie.rotor_grid)
            fgn = N / grid + 2;
            // (each channel's first row: a vowel's three, every other one)
            std::vector<long> frow(fch_.size());
            long nfr = 0;
            for (size_t q = 0; q < fch_.size(); q++) {
                frow[q] = nfr;
                nfr += (!fk_[q] && !ff_[q].ctl.empty() && ff_[q].ctl[0][0] == 3.0)
                       || (fk_[q] && fk_[q]->flt_k == 4) ? 3 : 1;
            }
            FCT.assign((size_t)nfr * (size_t)fgn, 1.0f);
            const double step = (double)grid / SR;
            for (size_t q = 0; q < fch_.size(); q++) {
                const NoteClass *k = fk_[q];
                if (!k) {
                    // A FILE's FILTER (filter_setup): each grid point's setting's
                    // control -- a wah's pedal, a sweep's LFO on the absolute clock
                    // (an auto wah's Sens adding the part's loudness), a flanger's
                    // line (stepped), or the vowels' formants gliding
                    const FxFlt &F = ff_[q];
                    float *row = FCT.data() + (size_t)frow[q] * fgn;
                    auto seg = [&](double t) {
                        long i = (long)(std::upper_bound(F.ts.begin(), F.ts.end(), t) - F.ts.begin()) - 1;
                        return i < 0 ? 0 : (i > (long)F.ts.size() - 1 ? (long)F.ts.size() - 1 : i);
                    };
                    if (F.ctl[0][0] == 3.0) {
                        // THE HUMANIZER (efxfilter.steps): each formant's value at
                        // the settings, gliding at the first's time constant
                        static const double VOWEL_F[5][3] = {{730, 1090, 2440}, {270, 2290, 3010},
                                                             {300, 870, 2240}, {530, 1840, 2480}, {570, 840, 2410}};
                        const double glide = F.ctl[0][2];
                        const size_t ns = F.ts.size();
                        for (int fk = 0; fk < 3; fk++)
                            for (long p = 0; p < fgn; p++) {
                                double t = (double)p * step;
                                long i = seg(t);
                                double vi = VOWEL_F[(int)F.ctl[i][1]][fk], v;
                                if (glide <= 0.0 || ns < 2) {
                                    v = vi;
                                } else {
                                    double prev = VOWEL_F[(int)F.ctl[i > 0 ? i - 1 : 0][1]][fk];
                                    double kk = exp(-std::max(t - F.ts[i], 0.0) / glide);
                                    v = vi + (prev - vi) * (i > 0 ? kk : 0.0);
                                }
                                row[(size_t)fk * fgn + p] = (float)v;
                            }
                        continue;
                    }
                    // (an auto wah's Sens: the part's notes' envelope, gsefx.note_envelope)
                    std::vector<double> env;
                    bool sens = false;
                    for (auto &c : F.ctl)
                        sens = sens || (c[0] == 1.0 && c[5] != 0.0);
                    if (sens) {
                        const double ATT = 0.005, HOLD = 0.4, REL = 0.06;   // (WAH_ENV_*)
                        env.assign(fgn, 0.0);
                        for (int i = 0, nn = nv_song_n_notes(song); i < nn; i++) {
                            long long c;
                            int iv[4];
                            double dv[2];
                            nv_song_get_note(song, i, &c, iv, dv);
                            if (c != fpart_[q])
                                continue;
                            const double s = dv[0], e = dv[1], a = iv[1] / 127.0;
                            const double at_end = a * exp(-(e - s) / HOLD);
                            long p0 = (long)ceil(s / step - 1e-12), p1 = fgn;
                            while (p0 > 0 && (double)(p0 - 1) * step >= s)
                                p0--;                   // (searchsorted: the first point at or after s)
                            while (p0 < fgn && (double)p0 * step < s)
                                p0++;
                            for (long p = p0; p < fgn; p++) {
                                double t = (double)p * step;
                                if (!(t < e + 8.0 * REL)) {
                                    p1 = p;
                                    break;
                                }
                                double u = t - s, lv;
                                if (t <= e)
                                    lv = a * std::min(1.0, u / ATT) * exp(-u / HOLD);
                                else
                                    lv = at_end * exp(-std::max(t - e, 0.0) / REL);
                                env[p] = std::max(env[p], lv);
                            }
                            (void)p1;
                        }
                    }
                    for (long p = 0; p < fgn; p++) {
                        double t = (double)p * step;
                        long i = seg(t);
                        const std::array<double, 6> &c = F.ctl[i];
                        double v;
                        if (c[0] == 1.0) {
                            double lf = sin(2.0 * M_PI * c[3] * t);
                            if (std::isnan(c[4])) {     // a phaser: about its Manual
                                v = c[1] * pow(2.0, c[2] * lf);
                            } else {                    // an auto wah: up (or down) from it
                                double oc = c[2] * 0.5 * (1.0 + lf);
                                if (c[5] != 0.0 && !env.empty())
                                    oc = oc + c[5] * env[p];
                                v = c[1] * pow(2.0, (c[4] != 0.0 ? 1.0 : -1.0) * oc);
                            }
                        } else if (c[0] == 2.0) {       // a flanger's line, stepped or not
                            double held = std::isnan(c[4]) ? t : floor(t * c[4]) / c[4];
                            v = c[1] + c[2] * 0.5 * (1.0 + sin(2.0 * M_PI * c[3] * held));
                        } else {
                            v = F.hz[i];                // a wah's pedal
                        }
                        row[p] = (float)v;
                    }
                    continue;
                }
                if (k->flt_k == 4) {
                    // A DIDGERIDOO's MOUTH (efxfilter.mouth): the part's mod wheel
                    // where the file moves it -- the states closed to open along
                    // it, between two the centres interpolated, moving at the
                    // glide -- else its seeded wander (nv_mouth_track), the
                    // channel the seed
                    float *row = FCT.data() + (size_t)frow[q] * fgn;
                    const int nm = k->n_mouth;
                    int nc = nv_midi_ccs(midi, (int)fpart_[q], NV_CC_MOUTH, nullptr, nullptr, 0);
                    if (nc <= 0) {
                        nv_mouth_track((unsigned long long)(fch_[q] + k->mouth_seed), nm, &k->mouth_st[0][0],
                                       k->mouth_cdf, k->mouth_dw, k->mouth_glide, step, fgn, row);
                        continue;
                    }
                    std::vector<double> tt(nc);
                    std::vector<int> vv(nc);
                    nv_midi_ccs(midi, (int)fpart_[q], NV_CC_MOUTH, tt.data(), vv.data(), nc);
                    std::vector<std::pair<double, double>> ev;
                    for (int a = 0; a < nc; a++)
                        ev.push_back(std::make_pair(tt[a], (double)vv[a]));
                    std::sort(ev.begin(), ev.end());
                    std::vector<double> wt{0.0}, wv{0.0};
                    for (auto &e : ev) {
                        wt.push_back(e.first);
                        wv.push_back(e.second);
                    }
                    const double gl = k->mouth_glide;
                    for (long p = 0; p < fgn; p++) {
                        double t = (double)p * step;
                        long i = (long)(std::upper_bound(wt.begin(), wt.end(), t) - wt.begin()) - 1;
                        i = i < 0 ? 0 : (i > (long)wt.size() - 1 ? (long)wt.size() - 1 : i);
                        double pos;
                        if (gl <= 0.0) {
                            pos = wv[i];
                        } else {
                            double prev = wv[i > 0 ? i - 1 : 0];
                            double dt = t - wt[i];
                            double kk = exp(-(dt > 0.0 ? dt : 0.0) / gl);
                            pos = wv[i] + (prev - wv[i]) * (i > 0 ? kk : 0.0);
                        }
                        double x = pos < 0.0 ? 0.0 : (pos > 127.0 ? 127.0 : pos);
                        double u = x / 127.0 * (double)(nm - 1);
                        long j = (long)floor(u);
                        j = j < nm - 2 ? j : nm - 2;
                        double w = u - (double)j;
                        for (int fk = 0; fk < 3; fk++)
                            row[(size_t)fk * fgn + p] = (float)(k->mouth_wst[j][fk] * (1.0 - w)
                                                                 + k->mouth_wst[j + 1][fk] * w);
                    }
                    continue;
                }
                const double *c = k->flt_c;
                // (a plunger's: the part's aftertouch, sorted, from 0 at 0 -- efxfilter.steps)
                std::vector<double> at_t{0.0}, at_v{0.0};
                if (k->flt_k == 3) {
                    int na = nv_midi_ats(midi, (int)fpart_[q], nullptr, nullptr, 0);
                    std::vector<double> tt(na > 0 ? na : 1);
                    std::vector<int> vv(na > 0 ? na : 1);
                    nv_midi_ats(midi, (int)fpart_[q], tt.data(), vv.data(), na);
                    std::vector<std::pair<double, double>> ev;
                    for (int a = 0; a < na; a++)
                        ev.push_back(std::make_pair(tt[a], (double)vv[a]));
                    std::sort(ev.begin(), ev.end());
                    for (auto &e : ev) {
                        at_t.push_back(e.first);
                        at_v.push_back(e.second);
                    }
                }
                for (long p = 0; p < fgn; p++) {
                    double t = (double)p * step, v;
                    if (k->flt_k == 1) {            // a sweep: its LFO about its Manual (a phaser), or up or down from it
                        double lf = sin(2.0 * M_PI * c[2] * t);
                        if (std::isnan(c[3]))
                            v = c[0] * pow(2.0, c[1] * lf);
                        else {
                            double oc = c[1] * 0.5 * (1.0 + lf);
                            v = c[0] * pow(2.0, (c[3] != 0.0 ? 1.0 : -1.0) * oc);
                        }
                    } else if (k->flt_k == 3) {     // a plunger: the hand's pressure, glided, its corner
                        long i = (long)(std::upper_bound(at_t.begin(), at_t.end(), t) - at_t.begin()) - 1;
                        i = i < 0 ? 0 : (i > (long)at_t.size() - 1 ? (long)at_t.size() - 1 : i);
                        double st;
                        if (c[4] <= 0.0 || at_v.size() < 2) {
                            st = at_v[i];
                        } else {
                            double prev = at_v[i > 0 ? i - 1 : 0];
                            double dt = t - at_t[i];
                            double kk = exp(-(dt > 0.0 ? dt : 0.0) / c[4]);
                            st = at_v[i] + (prev - at_v[i]) * (i > 0 ? kk : 0.0);
                        }
                        double x = st < 0.0 ? 0.0 : (st > 127.0 ? 127.0 : st);
                        double u = 2.0 * x / 127.0 - 1.0;
                        double g = c[3] * u + (1.0 - c[3]) * pow(u, 3.0);
                        v = c[1] * pow(g < 0.0 ? c[0] / c[1] : c[2] / c[1], fabs(g));
                    } else {
                        v = c[0];                   // a pedal, held
                    }
                    FCT[(size_t)frow[q] * fgn + p] = (float)v;
                }
            }
            for (size_t q = 0; q < fch_.size(); q++) {
                FltCh c;
                double p[3];
                c.ch = fch_[q];
                c.row = (int)frow[q];
                if (fk_[q]) {
                    c.ty = fk_[q]->flt_ty;
                    for (int j = 0; j < 3; j++)
                        p[j] = fk_[q]->flt_p[j];
                } else {
                    c.ty = (int)ff_[q].ty;
                    p[0] = ff_[q].pa;
                    p[1] = ff_[q].pb;
                    p[2] = ff_[q].pc;
                }
                for (int j = 0; j < 3; j++)
                    c.p[j] = (float)p[j];
                c.mx = (float)flt_peak(c.ty, p[0], p[1], p[2]);
                fltch.push_back(c);
            }
            const int cMm = col("mch");
            fsrc.assign(P, -1);
            ftyc.assign(P, 0);
            for (int q = 0; q < 3; q++)
                fpc_[q].assign(P, 0.0f);
            for (long long r = 0; r < P; r++) {
                long long m = (long long)rows[NCOLS * r + cMm];
                for (size_t q = 0; q < fch_.size(); q++)
                    if (fch_[q] == m) {
                        fsrc[r] = (int)frow[q];
                        if (fk_[q]) {
                            ftyc[r] = fk_[q]->flt_ty;
                            for (int j = 0; j < 3; j++)
                                fpc_[j][r] = (float)fk_[q]->flt_p[j];
                        } else {
                            ftyc[r] = (int)ff_[q].ty;
                            fpc_[0][r] = (float)ff_[q].pa;
                            fpc_[1][r] = (float)ff_[q].pb;
                            fpc_[2][r] = (float)ff_[q].pc;
                        }
                        break;
                    }
            }
            if (lch.empty()) {                      // (no Leslie: every row on no rotor, a 1 x 1 LANG)
                lobe[0] = malloc(sizeof(int) * (size_t)(P > 0 ? P : 1));
                for (long long r = 0; r < P; r++)
                    ((int *)lobe[0])[r] = -1;
                const float dv[4] = {0.0f, 1.0f, 0.0f, 1.0f};       // (lph, lfl, lsh, lnm: LOBE_COLS)
                for (int q = 0; q < 4; q++) {
                    lobe[1 + q] = malloc(sizeof(float) * (size_t)(P > 0 ? P : 1));
                    for (long long r = 0; r < P; r++)
                        ((float *)lobe[1 + q])[r] = dv[q];
                }
                LANG.assign(1, 0.0f);
                lgn = 1;
                void *h = dlopen(E.lobe_lib.c_str(), RTLD_NOW | RTLD_LOCAL);
                slo = h ? dlsym(h, "synth_voice_lobe") : nullptr;
                if (!slo) {
                    fprintf(stderr, "nvrender: no synth_voice_lobe in %s\n", E.lobe_lib.c_str());
                    return 1;
                }
            }
        }
    }
    const float *fpar[3] = {fpc_[0].data(), fpc_[1].data(), fpc_[2].data()};
    // THE MOOGS' ROWS (_MOOG_FT, _MOOG_KN: no knob moves, no pitch or shape
    // rows) and their columns
    int nkn = 0;
    long knk = 1, kb0 = 0;
    int nft = nv_song_moog_tables(song, nullptr, nullptr, &nkn, &knk, &kb0);
    std::vector<float> FT((size_t)30 * nft), KN((size_t)9 * nkn * knk);
    std::vector<int> fxc, mkc, mpi, mki;
    std::vector<double> fmc[3], mpc;
    std::vector<float> mpr, mpk;
    MoogCols mc{};
    // (a stream's: these tables pass A's, each window its rows' columns -- Pass's render_to)
    if (nft) {
        nv_song_moog_tables(song, FT.data(), KN.data(), &nkn, &knk, &kb0);
        mc.knk = knk;
        mc.kb0 = kb0;
        std::vector<double> v = fcol("fx");
        fxc.assign(v.begin(), v.end());
        v = fcol("mk");
        mkc.assign(v.begin(), v.end());
        const char *FMN[3] = {"fmw", "fmp", "fmpR"};
        for (int q = 0; q < 3; q++)
            fmc[q] = fcol(FMN[q]);
        mc.FT = FT.data();
        mc.KN = KN.data();
        // ...ITS MOD SECTION's rows (moog.pitch_rows, shape_rows), one a filter
        // row, through the kernel library's own (synthkernel.c), where any moves
        void *kh = dlopen(E.libs[0].c_str(), RTLD_NOW | RTLD_LOCAL);
        auto pcells = (void (*)(int, const double *, const double *, const double *, const double *, double, int,
                                double *, double *))(kh ? dlsym(kh, "moog_pitch_cells") : nullptr);
        auto srows = (void (*)(int, const double *, const double *, const double *, const long *, const int *, int,
                               double, int, const long *, const int *, const int *, float *))(
            kh ? dlsym(kh, "moog_shape_rows") : nullptr);
        bool mpon = false, mkon = false;
        for (int r = 0; r < nft; r++) {
            int fl = (int)FT[30 * r + 12];
            mpon = mpon || (fl & 1);
            mkon = mkon || (fl & 14);
        }
        if ((mpon && !pcells) || (mkon && !srows)) {
            fprintf(stderr, "nvrender: no moog_pitch_cells / moog_shape_rows in %s\n", E.libs[0].c_str());
            return 1;
        }
        const double MGd = 128.0;           // (moog.MG: synthkernel's MOOG_GRID)
        // (where each row's own entries start: a repeat's row copies its
        // parent's, its pitch and shape rows its delay later -- _mf_dup's)
        std::vector<size_t> mpi_at(nft, 0), mki_at(nft, 0);
        for (int r = 0; r < nft && (mpon || mkon); r++) {
            int par;
            long long gp, gs;
            if (nv_song_moog_dup_of(song, r, &par, &gp, &gs)) {
                if (mpon) {
                    std::vector<int> e(mpi.begin() + mpi_at[par], mpi.begin() + mpi_at[par] + 3);
                    e[1] += (int)gp;
                    mpi_at[r] = mpi.size();
                    mpi.insert(mpi.end(), e.begin(), e.end());
                }
                if (mkon) {
                    std::vector<int> e(mki.begin() + mki_at[par], mki.begin() + mki_at[par] + 7);
                    e[1] += (int)gs;
                    mki_at[r] = mki.size();
                    mki.insert(mki.end(), e.begin(), e.end());
                }
                continue;
            }
            mpi_at[r] = mpi.size();
            mki_at[r] = mki.size();
            const MoogLayer *Lr;
            double sp[3];
            nv_song_moog_rows(song, r, &Lr, sp);
            long j0 = (long)py_floordiv(sp[0], MGd);
            long ce = (long)-py_floordiv(-sp[2], MGd);
            int n = (int)std::max(2L, ce - j0 + 1);
            if (mpon) {
                if (Lr->pitch_on) {
                    std::vector<double> gg(n), a0(n, sp[0]), toff(n, sp[1]), Pm((size_t)9 * n), dc(n), rr(n);
                    for (int q = 0; q < n; q++) {
                        gg[q] = (double)(j0 + q) * MGd;
                        std::copy(Lr->pitch_p, Lr->pitch_p + 9, Pm.begin() + 9 * q);
                    }
                    pcells(n, gg.data(), a0.data(), toff.data(), Pm.data(), SR, 128, dc.data(), rr.data());
                    mpi.insert(mpi.end(), {(int)mpc.size(), (int)j0, n});
                    double c = 0.0;
                    for (int q = 0; q < n; q++) {
                        if (q)
                            c = c + dc[q - 1];
                        mpc.push_back(c);
                        mpr.push_back((float)rr[q]);
                    }
                } else {
                    mpi.insert(mpi.end(), {0, 0, 1});
                }
            }
            if (mkon) {
                if (Lr->shape_on) {
                    int offs[3] = {-1, -1, -1}, nslot = 0;
                    for (int o = 0; o < 3; o++)
                        if ((Lr->shape_on >> (o + 1)) & 1)
                            offs[o] = 2 * 64 * nslot++;
                    int stride = nslot * 64 * 2;
                    std::vector<float> buf((size_t)n * stride, 0.0f);
                    long base = 0;
                    srows(1, Lr->shape_par, &sp[0], &sp[1], &j0, &n, 128, SR, 64, &base, &stride, offs, buf.data());
                    mki.insert(mki.end(), {(int)mpk.size(), (int)j0, n, stride, offs[0], offs[1], offs[2]});
                    mpk.insert(mpk.end(), buf.begin(), buf.end());
                } else {
                    mki.insert(mki.end(), {0, 0, 1, 0, -1, -1, -1});
                }
            }
        }
        if (mpon) {
            if (mpc.empty())
                mpc.push_back(0.0);
            if (mpr.empty())
                mpr.push_back(1.0f);
            mc.MPI = mpi.data(); mc.MPC = mpc.data(); mc.MPR = mpr.data();
        }
        if (mkon) {
            mc.MKI = mki.data(); mc.MPK = mpk.data();
        }
        mc.fx = fxc.data();
        mc.mk = mkc.data();
        for (int q = 0; q < 3; q++)
            mc.fm[q] = fmc[q].data();
    }
    // THE BUSES (render_partials, efxbus.Bus: a tone's insertion effect's
    // Lo-Fi or compressor): each mix channel's from its first effect note, in
    // the note loop's order (_BUS_CH); its rows rendered apart, the part
    // through its processor at the output's scale, added back before the post
    struct BusDef {
        long long ch;
        int kind;                           // efxbus's: 1 Lo-Fi, 2 a compressor
        const double *p;                    // its processor (NoteClass.bus_p's layout)
        double dry, wet;
        bool part;                          // a part's (every tone of it), else a mix channel's
        std::vector<std::pair<long long, long long>> spans;     // (samples) where it is on, a part's
        std::vector<std::pair<long long, long long>> keys;      // a keyed gate's: the channel's keys (samples)
    };
    std::vector<BusDef> buses;
    std::vector<unsigned char> busrow, rest;
    // A PART'S BUS over the file (gsefx.bus_setup, the file's insertion
    // effect): each part a 'part' event names, in order, its processor the
    // first chain with a bus it is on, on wherever its chain has one -- these
    // first (_BUS_CH's order), then the tones' own
    std::vector<std::array<double, 40>> pbus_p;
    {
        std::set<long long> pp;
        for (const FxEv &e : fx_ev)
            if (e.kind == 5)
                pp.insert(e.a);
        pbus_p.reserve(pp.size());
        for (long long c : pp) {
            const double *first = nullptr;
            long long start = -1;
            std::vector<std::pair<long long, long long>> spans;
            for (double t : fx_ts) {
                int pre = fx_prefix(t), cq = fx_on(c, pre) ? fx_chain(pre) : -1;
                if (cq == -3)
                    return 2;
                const double *fc = cq >= 0 ? fxch.data() + (size_t)NV_FXN * cq : nullptr;
                bool on = fc && fc[25] != 0.0;
                if (on && !first)
                    first = fc;
                if (on && start < 0)
                    start = (long long)nearbyint(t * SR);
                if (!on && start >= 0) {
                    spans.push_back(std::make_pair(start, (long long)nearbyint(t * SR)));
                    start = -1;
                }
            }
            if (start >= 0)
                spans.push_back(std::make_pair(start, (long long)1 << 62));
            if (!first)
                continue;
            std::array<double, 40> bp = {};
            for (int q = 0; q < 5; q++)
                bp[q] = first[26 + q];
            if (first[25] == 6.0)               // (Lo-Fi 2's: its record past 176)
                for (int q = 0; q < 27; q++)
                    bp[5 + q] = first[176 + q];
            pbus_p.push_back(bp);
            buses.push_back(BusDef{c, (int)first[25], pbus_p.back().data(), first[32], first[33], true, spans});
        }
    }
    {
        int nn = nv_song_n_notes(song);
        std::vector<int> ord(nn);
        std::vector<double> on_(nn);
        std::vector<long long> ch_(nn);
        std::vector<int> key_(nn);
        for (int i = 0; i < nn; i++) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            ord[i] = i; on_[i] = dv[0]; ch_[i] = c; key_[i] = iv[0];
        }
        std::stable_sort(ord.begin(), ord.end(), [&](int a, int b) {
            if (on_[a] != on_[b])
                return on_[a] < on_[b];
            if (ch_[a] != ch_[b])
                return ch_[a] < ch_[b];
            return key_[a] < key_[b];
        });
        for (int i : ord) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            int cq = E.cmap[nv_song_kidx(song, i)];
            const NoteClass *k = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
            long long m = nv_song_mix(song, i);
            bool seen = false;
            for (auto &b : buses)
                seen = seen || (!b.part && b.ch == m);
            if (k && k->ng_set && !seen) {
                // A VOICE's OWN GATE (blockrender: TONE_BUS + its mix channel,
                // before its insertion effect's), keyed by the channel's notes as played
                BusDef bd{m, 7, k->ng_p, 0.0, 1.0, false, {}, {}};
                for (int j = 0; j < nn; j++) {
                    long long c2;
                    int iv2[4];
                    double dv2[2];
                    nv_song_get_note(song, j, &c2, iv2, dv2);
                    if (c2 == c)
                        bd.keys.push_back(std::make_pair((long long)nearbyint(dv2[0] * SR),
                                                         (long long)nearbyint(dv2[1] * SR)));
                }
                std::sort(bd.keys.begin(), bd.keys.end());
                buses.push_back(bd);
                seen = true;
            }
            if (!k || !k->efx_set || !k->efx_bus || iv[3] || seen || note_fx[i] != -1)
                continue;
            buses.push_back(BusDef{m, k->efx_bus, k->bus_p, k->bus_p[10], k->bus_p[11], false, {}});
        }
        if (!buses.empty()) {
            const int cMb = col("mch");
            busrow.assign(P > 0 ? P : 1, 0);
            rest.assign(P > 0 ? P : 1, 1);
            for (long long r = 0; r < P; r++) {
                long long m = (long long)rows[NCOLS * r + cMb];
                for (size_t q = 0; q < buses.size(); q++)
                    if (buses[q].part ? m % 256 == buses[q].ch : buses[q].ch == m) {
                        if (busrow[r]) {
                            fprintf(stderr, "nvrender: refused: a row on two buses (a part's and its tone's)\n");
                            return 2;
                        }
                        busrow[r] = (unsigned char)(q + 1);
                        rest[r] = 0;
                    }
            }
        }
    }
    // efxbus's processors on a part's signal (in, at the output's scale), into y
    auto bus_process = [&](const BusDef &bd, std::vector<float> &x0, std::vector<float> &x1,
                           std::vector<float> &y0, std::vector<float> &y1) {
        const double *p = bd.p;
        long n = (long)x0.size();
        std::vector<float> *xs[2] = {&x0, &x1}, *ys[2] = {&y0, &y1};
        if (bd.kind == 1) {              // LoFi: the pre filter, the hold, the bits, the post filter
            const double step = p[0], q = p[1], pa = p[2], qa = p[3];
            std::vector<long long> start(n);
            for (long i = 0; i < n; i++) {
                double kk = floor((double)i / step);
                start[i] = (long long)ceil(kk * step);
            }
            for (int ear = 0; ear < 2; ear++) {
                std::vector<double> x(n);
                for (long i = 0; i < n; i++)
                    x[i] = (double)(*xs[ear])[i];
                if (pa != 0.0) {            // (scipy's lfilter, one pole: y = z + b0 x, z = a y)
                    double z = 0.0, b0 = 1.0 - pa;
                    for (long i = 0; i < n; i++) {
                        double yv = z + b0 * x[i];
                        z = x[i] * 0.0 - yv * -pa;
                        x[i] = yv;
                    }
                }
                std::vector<double> y(n);
                for (long i = 0; i < n; i++)
                    y[i] = nearbyint(x[start[i]] / q) * q;
                if (qa != 0.0) {
                    double z = 0.0, b0 = 1.0 - qa;
                    for (long i = 0; i < n; i++) {
                        double yv = z + b0 * y[i];
                        z = y[i] * 0.0 - yv * -qa;
                        y[i] = yv;
                    }
                }
                ys[ear]->resize(n);
                for (long i = 0; i < n; i++)
                    (*ys[ear])[i] = (float)y[i];
            }
        } else if (bd.kind == 7) {          // efxbus.NoiseGate, keyed: the body's compressor, the gate's poles
            const long long hold = (long long)p[0];
            const double c = p[1];
            std::vector<double> L(n), R(n), x(n), ref(n), g(n, 1.0);
            for (long i = 0; i < n; i++) {
                L[i] = (double)(*xs[0])[i];
                R[i] = (double)(*xs[1])[i];
                const double a = fabs(L[i]), b = fabs(R[i]);
                x[i] = b > a ? b : a;               // np.maximum(|L|, |R|)
            }
            // the running peak (dB): a peak held, falling c a sample, from p[11]
            double acc = -INFINITY;
            for (long i = 0; i < n; i++) {
                const double m = (double)i;
                const double lv = 20.0 * log10(x[i] > 1e-12 ? x[i] : 1e-12);
                const double t = lv + m * c;
                acc = (i == 0 || t > acc) ? t : acc;    // (np.maximum.accumulate)
                double r = acc - m * c;
                const double fl = p[11] - (m + 1.0) * c;
                ref[i] = fl > r ? fl : r;
            }
            // efxbus._Pole: lfilter([1 - a], [1, -a]) from a x[0], as its first window starts it
            auto pole = [&](double a, const std::vector<double> &in) {
                std::vector<double> y(n);
                double zz = a * in[0];
                const double b0 = 1.0 - a;
                for (long i = 0; i < n; i++) {
                    const double yv = zz + b0 * in[i];
                    zz = in[i] * 0.0 - yv * -a;
                    y[i] = yv;
                }
                return y;
            };
            if (p[2] != 0.0) {                      // the body: over sustain_db under the peak, to 1/ratio
                std::vector<double> e0 = pole(p[7], x), e1 = pole(p[8], x);
                for (long i = 0; i < n; i++) {
                    const double env = e1[i] > e0[i] ? e1[i] : e0[i];
                    double over = 20.0 * log10(env > 1e-12 ? env : 1e-12) - (ref[i] + p[3]);
                    over = over > 0.0 ? over : 0.0;
                    g[i] = pow(10.0, -over * (1.0 - 1.0 / p[4]) / 20.0) * p[5];
                }
            }
            // keyed: open over each key's span, held hold past its key-up
            std::vector<double> tgt(n, p[6]);
            for (const auto &kk : bd.keys) {
                if (!(kk.first < (long long)n && kk.second + hold > 0))
                    continue;
                long long a0 = kk.first > 0 ? kk.first : 0;
                long long a1 = std::min((long long)n, kk.second + hold);
                a1 = a1 > 0 ? a1 : 0;
                for (long long i = a0; i < a1; i++)
                    tgt[i] = 1.0;
            }
            std::vector<double> o0 = pole(p[9], tgt), o1 = pole(p[10], tgt);
            for (int ear = 0; ear < 2; ear++)
                ys[ear]->resize(n);
            for (long i = 0; i < n; i++) {
                const double gg = g[i] * (o1[i] > o0[i] ? o1[i] : o0[i]);
                (*ys[0])[i] = (float)(L[i] * gg);
                (*ys[1])[i] = (float)(R[i] * gg);
            }
        } else if (bd.kind == 3 || bd.kind == 4) {
            // A REVERB (efxbus.Reverb, GateReverb): the part (mono in) through
            // each ear's response, from rest (native/efxrev.c's, efxbus's)
            const long long cap = (long long)(10.0 * SR) + 64;
            std::vector<double> hL(cap), hR(cap);
            long long nh = bd.kind == 3 ? nv_efx_reverb_ir(SR, (int)p[0], p[1], (int)p[2], p[3], hL.data(), hR.data(), cap)
                                        : nv_efx_gate_ir(SR, (int)p[0], p[1], p[2], hL.data(), hR.data(), cap);
            std::vector<double> x((size_t)(nh - 1 + n), 0.0), o(n);
            for (long i = 0; i < n; i++)
                x[nh - 1 + i] = 0.5 * ((double)x0[i] + (double)x1[i]);
            const double *hs[2] = {hL.data(), hR.data()};
            for (int ear = 0; ear < 2; ear++) {
                nv_efx_conv(x.data(), (long long)x.size(), hs[ear], nh, nh - 1, n, o.data());
                ys[ear]->resize(n);
                for (long i = 0; i < n; i++)
                    (*ys[ear])[i] = (float)o[i];
            }
        } else if (bd.kind == 6) {
            // LO-FI 2 (efxbus.LoFi2): the radio off its station (its band,
            // fading and wandering with the detune), the hold and bits, the
            // noises (radio static, white or pink, a record's crackle, mains
            // hum: each its level and low pass, keyed to the absolute sample),
            // mono at its Pan or a stereo pair, the filter after
            static const double RATE2[6] = {16000, 11025, 8000, 6000, 5000, 4000};
            static const int BITS2[6] = {12, 10, 8, 7, 6, 5};
            static const double PB[4] = {0.049922035, -0.095993537, 0.050612699, -0.004408786};
            static const double PA[4] = {1.0, -2.494956002, 2.017265875, -0.522189400};
            static const double HUM[6][2] = {{1, 1.0}, {2, 0.5}, {3, 0.35}, {4, 0.15}, {5, 0.2}, {7, 0.1}};
            const double *q = p + 5;
            const int k = (int)q[0], fil = (int)q[1], dt = (int)q[2];
            const double full = pow(10.0, -40.0 / 20.0);           // (NOISE_FULL_DB)
            const double det = q[2] / 127.0;
            // (q: the record from 176 -- 0 Type, 1 Fil Type, 2 R.Detune, 3 R.Nz Lev, 4 W/P Sel, 5 W/P LPF,
            // 6 W/P Level, 7 Disc Type, 8 Disc LPF, 9 Disc Nz Lev, 10 Hum Type, 11 Hum LPF, 12 Hum Level,
            // 13 M/S, 14 Pan, 15-20 the filter after's b and a, 21-26 the radio's band's)
            const double radio_amp = full * q[3] / 127.0 * det, wp_amp = full * q[6] / 127.0;
            const double disc_amp = full * q[9] / 127.0, hum_amp = full * q[12] / 127.0;
            // scipy's lfilter (transposed direct form II), its memory carried
            auto lfilt = [](const double *b, const double *a, int nb, std::vector<double> &x) {
                double z[4] = {0.0, 0.0, 0.0, 0.0};
                for (size_t i = 0; i < x.size(); i++) {
                    const double xn = x[i], yn = z[0] + b[0] * xn;
                    for (int m = 0; m < nb - 2; m++)
                        z[m] = z[m + 1] + xn * b[m + 1] - yn * a[m + 1];
                    z[nb - 2] = xn * b[nb - 1] - yn * a[nb - 1];
                    x[i] = yn;
                }
            };
            auto lowpass = [&](double hz, std::vector<double> &x) {     // (efxbus.lowpass: one pole, 0 none)
                if (hz == 0.0)
                    return;
                const double e = exp(-2.0 * M_PI * hz / SR);
                const double b[2] = {1.0 - e, 0.0}, a[2] = {1.0, -e};
                lfilt(b, a, 2, x);
            };
            auto noises = [&](int ear) {
                const unsigned long long seed = 1000ULL * (unsigned long long)(ear + 1);
                std::vector<double> y(n, 0.0), w(n);
                if (radio_amp != 0.0) {
                    nv_npy_noise(0, n, seed + 1, 1, w.data());
                    lfilt(q + 21, q + 24, 3, w);
                    for (long i = 0; i < n; i++)
                        y[i] += radio_amp * w[i] * 4.5;
                }
                if (wp_amp != 0.0) {
                    nv_npy_noise(0, n, seed + 2, 1, w.data());
                    if (q[4] != 0.0) {
                        lfilt(PB, PA, 4, w);
                        for (long i = 0; i < n; i++)
                            w[i] = w[i] * 11.0;
                    }
                    lowpass(q[5], w);
                    for (long i = 0; i < n; i++)
                        y[i] += wp_amp * w[i];
                }
                if (disc_amp != 0.0) {
                    static const double DISC[4][3] = {{6.0, 33.3 / 60.0, 0.15}, {10.0, 45.0 / 60.0, 0.2},
                                                      {20.0, 78.0 / 60.0, 0.5}, {14.0, 0.0, 0.1}};
                    const double *dc = DISC[(int)q[7]];
                    const double rate = dc[0], rev = dc[1], hiss = dc[2];
                    std::vector<double> u(n), s(n), h(n);
                    nv_npy_noise(0, n, seed + 3, 0, u.data());
                    nv_npy_noise(0, n, seed + 4, 1, s.data());
                    nv_npy_noise(0, n, seed + 5, 1, h.data());
                    for (long i = 0; i < n; i++) {
                        const double sg = s[i] > 0.0 ? 1.0 : s[i] < 0.0 ? -1.0 : s[i];        // (np.sign)
                        w[i] = u[i] < rate / SR ? sg * (0.3 + 2.0 * (u[i] * SR / rate)) : 0.0;
                        if (rev != 0.0)                                 // (the tick once a revolution)
                            w[i] = w[i] + (floor((double)i * rev / SR) != floor((double)(i - 1) * rev / SR)
                                           ? 2.5 : 0.0);
                    }
                    const double cb[2] = {1.0, 0.0}, ca[2] = {1.0, -exp(-1.0 / (0.0003 * SR))};
                    lfilt(cb, ca, 2, w);
                    for (long i = 0; i < n; i++)
                        w[i] = 1.5 * w[i] + hiss * h[i];
                    lowpass(q[8], w);
                    for (long i = 0; i < n; i++)
                        y[i] += disc_amp * w[i];
                }
                if (hum_amp != 0.0) {
                    const double hz = q[10] != 0.0 ? 60.0 : 50.0;
                    for (long i = 0; i < n; i++) {
                        const double t = (double)i / SR;
                        double hv = 0.0;
                        for (const auto &hh : HUM)
                            hv += hh[1] * sin(2.0 * M_PI * hh[0] * hz * t);
                        w[i] = hv;
                    }
                    lowpass(q[11], w);
                    for (long i = 0; i < n; i++)
                        y[i] += hum_amp * w[i];
                }
                return y;
            };
            std::vector<double> xe[2];
            for (int ear = 0; ear < 2; ear++) {
                xe[ear].resize(n);
                for (long i = 0; i < n; i++)
                    xe[ear][i] = (double)(*xs[ear])[i];
            }
            if (dt != 0) {                      // THE RADIO OFF ITS STATION: an AM set's band, fading, wandering
                for (int ear = 0; ear < 2; ear++) {
                    lfilt(q + 21, q + 24, 3, xe[ear]);
                    for (long i = 0; i < n; i++) {
                        const double t = (double)i / SR;
                        const double fade = (1.0 - 0.8 * det) * (1.0 + 0.3 * det * sin(2.0 * M_PI * 0.37 * t)
                                                                 * sin(2.0 * M_PI * 0.11 * t + 1.0));
                        xe[ear][i] = xe[ear][i] * fade;
                    }
                }
            }
            // the hold and bits (efxbus.LoFi, no filters), from float32
            const double step = SR / RATE2[k], qq = pow(2.0, -(double)(BITS2[k] - 1));
            std::vector<double> ye[2];
            for (int ear = 0; ear < 2; ear++) {
                ye[ear].resize(n);
                for (long i = 0; i < n; i++) {
                    const long long st = (long long)ceil(floor((double)i / step) * step);
                    ye[ear][i] = (double)(float)(nearbyint((double)(float)xe[ear][st] / qq) * qq);
                }
            }
            if (q[13] != 0.0) {                 // a stereo pair: each ear its own noises
                for (int ear = 0; ear < 2; ear++) {
                    std::vector<double> z = noises(ear);
                    for (long i = 0; i < n; i++)
                        ye[ear][i] = ye[ear][i] + z[i];
                }
            } else {                            // the effect mono, at its Pan
                const double th = (std::max(0, std::min(127, (int)q[14])) - 64) / 63.0 * 0.25 * M_PI + 0.25 * M_PI;
                const double pl = cos(th), pr = sin(th);
                std::vector<double> z = noises(0);
                for (long i = 0; i < n; i++) {
                    const double m = 0.5 * (ye[0][i] + ye[1][i]) + z[i];
                    ye[0][i] = m * pl * sqrt(2.0);
                    ye[1][i] = m * pr * sqrt(2.0);
                }
            }
            for (int ear = 0; ear < 2; ear++) {
                if (fil)
                    lfilt(q + 15, q + 18, 3, ye[ear]);
                ys[ear]->resize(n);
                for (long i = 0; i < n; i++)
                    (*ys[ear])[i] = (float)ye[ear][i];
            }
        } else if (bd.kind == 5) {
            // ENHANCER (efxbus.Enhancer): each ear's top above the one-pole's
            // corner (scipy's lfilter), saturated, its new harmonics mixed back
            const double a = p[0], drive = p[1], mix = p[2];
            for (int ear = 0; ear < 2; ear++) {
                ys[ear]->resize(n);
                double z = 0.0, b0 = 1.0 - a;
                for (long i = 0; i < n; i++) {
                    const double x = (double)(*xs[ear])[i];
                    const double lp = z + b0 * x;
                    z = x * 0.0 - lp * -a;
                    const double hi = x - lp;
                    const double sat = tanh(drive * hi) / drive;
                    (*ys[ear])[i] = (float)(x + mix * sat);
                }
            }
        } else {                            // Compressor: the envelope, its gain above the threshold
            const double t = p[0], rr = p[1], ka = p[2], kr = p[3], mk = p[4];
            y0.resize(n);
            y1.resize(n);
            double e = 0.0;
            for (long i = 0; i < n; i++) {
                double a = fabs((double)x0[i]), b = fabs((double)x1[i]);
                double v = b > a ? b : a;
                double kk = v > e ? ka : kr;
                e = kk * e + (1.0 - kk) * v;
                double db = 20.0 * log10(e > 1e-9 ? e : 1e-9);
                double over = db - t > 0.0 ? db - t : 0.0;
                double g = pow(10.0, -over * (1.0 - 1.0 / rr) / 20.0) * mk;
                y0[i] = (float)((double)x0[i] * g);
                y1[i] = (float)((double)x1[i] * g);
            }
        }
    };
    // the mix, or the send (fpX its level columns): the rest, then each bus's part, then the post
    // --window: each row's last sample, as the kernel stops (streamrender.zend,
    // on the final float32 columns)
    std::vector<long long> zend;
    if (win > 0 && buses.empty()) {
        zend.resize(P);
        for (long long r = 0; r < P; r++) {
            float dl = std::max(0.0f, std::max(fcols[26][r], fcols[27][r]));     // delL, delR
            zend[r] = (long long)lcols[1][r] + (long long)fcols[4][r] + (long long)ceilf(dl) + BLK;
        }
    } else if (win > 0)
        fprintf(stderr, "nvrender: --window: a part's bus (its processors hold no state across windows): whole\n");
    auto render_mix = [&](float *const *fpX, float *oL, float *oR) {
        if (buses.empty() && win > 0) {
            const long CH = (long)E.k[K_CHUNK];
            const long W = (win + CH - 1) / CH * CH;
            std::vector<long long> live;
            for (long w0 = 0; w0 < N; w0 += W) {
                const long wn = std::min(W, N - w0);
                live.clear();
                for (long long r = 0; r < P; r++)
                    if (lcols[0][r] < w0 + wn && zend[r] > w0)
                        live.push_back(r);
                nv_render_win(fn[0], fn[1], fn[2], N, (int)BLK, nblk, P, dp, fpX, lp, ip, Gt.data(), St.data(),
                              BRr.data(), BCr.data(), BLr.empty() ? nullptr : BLr.data(), noRows, sh,
                              (long)E.k[K_CHUNK], E.k[K_XDEC], SR, E.k[K_MASTER], (const float *)dm[2],
                              (const long *)dm[3], (const long *)dm[4], (const long *)dm[5], oL + w0, oR + w0, slo,
                              (const int *)lobe[0], (float *const *)(lobe + 1), LANG.empty() ? nullptr : LANG.data(),
                              lgn, nft ? &mc : nullptr, FCT.empty() ? nullptr : fsrc.data(),
                              FCT.empty() ? nullptr : ftyc.data(), fpar, FCT.empty() ? nullptr : FCT.data(), fgn,
                              nullptr, 1, w0, wn, live.data(), (long long)live.size());
            }
            return;
        }
        if (buses.empty()) {
            nv_render(fn[0], fn[1], fn[2], N, (int)BLK, nblk, P, dp, fpX, lp, ip, Gt.data(), St.data(), BRr.data(),
                      BCr.data(), BLr.empty() ? nullptr : BLr.data(), noRows, sh, (long)E.k[K_CHUNK], E.k[K_XDEC],
                      SR, E.k[K_MASTER], (const float *)dm[2], (const long *)dm[3], (const long *)dm[4],
                      (const long *)dm[5], oL, oR, slo, (const int *)lobe[0], (float *const *)(lobe + 1),
                      LANG.empty() ? nullptr : LANG.data(), lgn, nft ? &mc : nullptr,
                      FCT.empty() ? nullptr : fsrc.data(), FCT.empty() ? nullptr : ftyc.data(), fpar,
                      FCT.empty() ? nullptr : FCT.data(), fgn, nullptr, 1);
            return;
        }
        auto part = [&](const unsigned char *sel, float *pL, float *pR) {
            nv_render(fn[0], fn[1], fn[2], N, (int)BLK, nblk, P, dp, fpX, lp, ip, Gt.data(), St.data(), BRr.data(),
                      BCr.data(), BLr.empty() ? nullptr : BLr.data(), noRows, sh, (long)E.k[K_CHUNK], E.k[K_XDEC],
                      SR, E.k[K_MASTER], (const float *)dm[2], (const long *)dm[3], (const long *)dm[4],
                      (const long *)dm[5], pL, pR, slo, (const int *)lobe[0], (float *const *)(lobe + 1),
                      LANG.empty() ? nullptr : LANG.data(), lgn, nft ? &mc : nullptr,
                      FCT.empty() ? nullptr : fsrc.data(), FCT.empty() ? nullptr : ftyc.data(), fpar,
                      FCT.empty() ? nullptr : FCT.data(), fgn, sel, 0);
        };
        part(rest.data(), oL, oR);
        const double gain = E.k[K_MASTER];
        const float gf = (float)gain;
        for (size_t q = 0; q < buses.size(); q++) {
            std::vector<unsigned char> sel(busrow.size());
            for (size_t r = 0; r < sel.size(); r++)
                sel[r] = busrow[r] == q + 1;
            std::vector<float> bL(N), bR(N);
            part(sel.data(), bL.data(), bR.data());
            std::vector<float> xL(N), xR(N), yL, yR;
            for (long i = 0; i < N; i++) {      // (at the output's scale: L * the master gain, float32)
                xL[i] = bL[i] * gf;
                xR[i] = bR[i] * gf;
            }
            bus_process(buses[q], xL, xR, yL, yR);
            const float dry = (float)buses[q].dry, wet = (float)buses[q].wet;
            // (a part's: its output only inside the spans it is on, its own signal outside)
            std::vector<unsigned char> on(N, buses[q].part ? 0 : 1);
            for (auto &sp : buses[q].spans)
                for (long long i = std::max(0LL, sp.first); i < std::min((long long)N, sp.second); i++)
                    on[i] = 1;
            for (long i = 0; i < N; i++) {
                float wL = (float)((double)yL[i] / gain), wR = (float)((double)yR[i] / gain);
                float mL = on[i] ? dry * bL[i] + wet * wL : bL[i], mR = on[i] ? dry * bR[i] + wet * wR : bR[i];
                oL[i] = oL[i] + mL;
                oR[i] = oR[i] + mR;
            }
        }
        nv_render_post(oL, oR, N, SR, E.k[K_MASTER], 1);
    };
    std::vector<float> L(g_stream ? 0 : N), R(g_stream ? 0 : N);     // (a stream writes as it goes)
    {                                       // THE MASTER VOLUME (_mvol): the mix's and the send's
        int nm = nv_midi_mvol(midi, SR, nullptr, nullptr, 0);
        std::vector<long long> ms(nm > 0 ? nm : 1);
        std::vector<double> mgv(nm > 0 ? nm : 1);
        nv_midi_mvol(midi, SR, ms.data(), mgv.data(), nm);
        nv_render_mvol(ms.data(), mgv.data(), nm);
    }
    // --STREAM: what it cannot reproduce sends the file to the whole render
    if (g_stream_why_only) {
        printf("%s\n", nv_stream_why()[0] ? nv_stream_why() : "streams");
        return 0;
    }
    if (g_stream && nv_stream_why()[0]) {
        fprintf(stderr, "nvrender: --stream: %s: rendered whole\n", nv_stream_why());
        std::vector<char *> av;
        for (int i = 0; i < argc; i++)
            if (strcmp(argv[i], "--stream"))
                av.push_back(argv[i]);
        av.push_back(nullptr);
        execv("/proc/self/exe", av.data());
        fprintf(stderr, "nvrender: --stream: cannot run the whole render\n");
        return 1;
    }
    // PASS B: the notes again, each window rendered once nothing to come can
    // reach it. wt: the send's weight of a row (its channel, onset), NULL the mix
    pack_layout(E.fin.data());
    auto stream_pass = [&](const std::function<float(long long, long long)> *wt, const char *opath,
                           const char *spath) {
        struct Store {
            std::vector<unsigned char> d;   // (row-major, each column in its table type: pack_row)
            std::vector<long long> non, zend;
            std::vector<std::array<float, 5>> lob;      // (each row's lobe: rotor, azimuth, floor, sharpness, 1/mean)
            std::vector<std::array<long long, 16>> key; // (each row's table key; a copy's its source's and its place)
            std::vector<int> dk;                        // (each row's damper track, -1 none, and its weight)
            std::vector<float> dg;
        };
        struct Pass {
            Store st;
            std::vector<Store> reg;                 // (each register channel's, in `order`)
            std::vector<std::vector<std::pair<long long, long long>>> rkey;    // (their (phase, seq))
            long long hz = LLONG_MAX;               // (the register's horizon)
            std::map<long long, const NoteClass *> cab;     // (the cabinets' channels: nv_cabinet_pass's)
            void *les = nullptr;                    // (the rotors: nv_leslie_row)
            const std::map<long long, std::vector<double>> *eq = nullptr;     // (the insertion EQs' channels)
            // THE HALF-PEDAL's TRACKS (onto_tracks, as each banded note lands): the
            // tracks used so far and their table; the note to come; the laws' constants
            void *song = nullptr;
            int jn = 0, ntr = 0;
            long long nblkv = 0;
            double dfull = 0.0, dres = 0.0, dknee = 0.0, dln = 0.0, dbeta = 0.0, dxdec = 0.0;
            std::vector<float> DM;
            std::vector<long> DMO, DMB, DMN;
            Store lescp;                            // (the Leslie's copies, after the table's rows)
            Store gsdst;                            // (the delays' repeats, after the register's: (j, seq))
            void *gsd = nullptr;
            Store mfst;                             // (the MF-104M's repeats, before the delays')
            void *mf = nullptr;
            Store tremst;                           // (the tremolos' sidebands, after the products)
            const std::vector<std::array<double, 4>> *ht = nullptr;
            const std::map<long long, std::vector<double>> *tch = nullptr, *twave = nullptr;
            std::vector<long long> nprod;           // (each amplifier channel's products so far: their keys)
            // THE AMPLIFIERS' (streamrender._amplifier): each channel's rows as the
            // table orders them, its edge walked to, its next start; its products' store
            struct AmpCh {
                std::vector<double> d;
                std::vector<int> dk;
                std::vector<float> dg;
                std::vector<std::array<long long, 4>> key;
                double edge = -INFINITY, next = INFINITY;
                bool walked = false;
            };
            std::vector<AmpCh> amp;
            std::vector<Store> ampst;
            const std::vector<long long> *ach = nullptr;
            const std::vector<double> *adr, *aref, *aimb, *asb;
            const std::vector<std::vector<double>> *ass, *asl;
            double hraw = INFINITY;                 // (the register's horizon, unfloored)
            void amp_take(const double *x, std::array<long long, 4> k, int dkv = -1, float dgv = 0.0f)
            {
                if (!ach || x[10] <= 0.5)
                    return;
                for (size_t q = 0; q < ach->size(); q++)
                    if ((long long)x[6] == (*ach)[q]) {
                        if ((*adr)[q] <= 0.0)
                            return;
                        amp[q].d.insert(amp[q].d.end(), x, x + NCOLS);
                        amp[q].key.push_back(k);
                        amp[q].dk.push_back(dkv);
                        amp[q].dg.push_back(dgv);
                        return;
                    }
            }
            void amp_advance(double H)              // (every segment ending at or before H walked)
            {
                for (size_t q = 0; ach && q < ach->size(); q++) {
                    AmpCh &c = amp[q];
                    const size_t nr = c.key.size();
                    if (!nr) {
                        c.next = INFINITY;
                        continue;
                    }
                    std::vector<size_t> ord(nr);
                    for (size_t r = 0; r < nr; r++)
                        ord[r] = r;
                    std::stable_sort(ord.begin(), ord.end(), [&](size_t u, size_t v) { return c.key[u] < c.key[v]; });
                    std::vector<double> edges;
                    for (size_t r = 0; r < nr; r++) {
                        edges.push_back(c.d[NCOLS * r + 12]);
                        edges.push_back(c.d[NCOLS * r + 13]);
                    }
                    if (c.walked)
                        edges.push_back(c.edge);
                    std::sort(edges.begin(), edges.end());
                    edges.erase(std::unique(edges.begin(), edges.end()), edges.end());
                    edges.erase(std::remove_if(edges.begin(), edges.end(), [&](double e) { return e < c.edge; }),
                                edges.end());
                    double last = c.edge;
                    bool any = false;
                    for (size_t s = 0; s + 1 < edges.size(); s++) {
                        const double a = edges[s], b = edges[s + 1];
                        if (b > H)
                            break;
                        last = b;
                        any = true;
                        if (b - a < SR * 0.01)
                            continue;
                        std::vector<const double *> live;
                        std::vector<size_t> lix;
                        for (size_t r : ord) {
                            const double *x = c.d.data() + NCOLS * r;
                            if (x[12] <= a + 1e-6 && x[13] >= b - 1e-6) {
                                live.push_back(x);
                                lix.push_back(r);
                            }
                        }
                        if (live.size() < 2)
                            continue;
                        double ref = (*aref)[q];
                        const std::vector<double> &ss = (*ass)[q], &sl = (*asl)[q];
                        if (!ss.empty()) {
                            long i = (long)(std::upper_bound(ss.begin(), ss.end(), a) - ss.begin()) - 1;
                            ref = (*asb)[q] * sl[i > 0 ? i : 0];
                        }
                        double *got = nullptr;
                        long si = 0;
                        long ng = nv_amp_segment(live.data(), (long)live.size(), a, b, (*adr)[q], ref, (*aimb)[q], SR,
                                                 &got, &si);
                        for (long g = 0; g < ng; g++)
                            add(ampst[q], got + NCOLS * g, false, {2, (long long)q, nprod[q]++, 0, 0, 0, 0, 0}, false,
                                c.dk[lix[si]], c.dg[lix[si]]);
                        free(got);
                    }
                    if (any) {
                        c.edge = last;
                        c.walked = true;
                    }
                    if (c.walked) {
                        // A ROW ENDING AT THE EDGE IS DONE (streamrender._amplifier): in no
                        // segment to come -- and a channel left with none holds no one
                        // back, or a part falling silent froze the render at its last row
                        std::vector<double> d2;
                        std::vector<std::array<long long, 4>> k2;
                        std::vector<int> dk2;
                        std::vector<float> dg2;
                        for (size_t r = 0; r < nr; r++)
                            if (!(c.d[NCOLS * r + 13] <= last + 1e-6)) {
                                d2.insert(d2.end(), c.d.begin() + NCOLS * r, c.d.begin() + NCOLS * (r + 1));
                                k2.push_back(c.key[r]);
                                dk2.push_back(c.dk[r]);
                                dg2.push_back(c.dg[r]);
                            }
                        c.d.swap(d2);
                        c.key.swap(k2);
                        c.dk.swap(dk2);
                        c.dg.swap(dg2);
                    }
                    c.next = c.key.empty() ? INFINITY : c.walked ? c.edge : (edges.empty() ? INFINITY : edges[0]);
                }
            }
            long long amp_next() const
            {
                double m = INFINITY;
                for (const AmpCh &c : amp)
                    m = std::min(m, c.next);
                return std::isinf(m) ? LLONG_MAX : (long long)floor(m);
            }
            std::function<void(long long)> render_to;
            const int *kind;
            double SR;
            long long N, BLK;
            // the chorus's: each channel's (kind, send, voices, cents) and its copies' store
            const std::vector<long long> *cch = nullptr;
            const std::vector<int> *ckind, *cnc;
            const std::vector<double> *csend, *ccents;
            const std::vector<StreamDev> *cdev = nullptr;
            Store chocp;
            // THE SCANNER's HOLD: a scanner channel's rows, till their note's group is whole
            struct Pend {
                Store *t;
                size_t q;
                std::array<long long, 14> k;
                int dk;
                float dg;
                std::vector<double> x;
            };
            std::vector<Pend> pend;
            const std::vector<ScanCh> *scn = nullptr;
            void *scanh = nullptr;
            Store scanst;                           // (the scanner's copies: after the tremolos')
            void scan_flush(double lim)             // (each group whose onset less delay is before lim)
            {
                std::vector<Pend> go, keep;
                for (Pend &p_ : pend)
                    (p_.x[12] - p_.x[45] < lim ? go : keep).push_back(std::move(p_));
                pend.swap(keep);
                if (go.empty())
                    return;
                std::map<std::pair<size_t, double>, double> top;     // (note_peaks: the group's loudest)
                for (Pend &p_ : go) {
                    const double a = std::max(fabs(p_.x[3]), fabs(p_.x[4]));
                    auto key_ = std::make_pair(p_.q, p_.x[12] - p_.x[45]);
                    auto it = top.find(key_);
                    if (it == top.end() || a > it->second)
                        top[key_] = a;
                }
                for (Pend &p_ : go) {
                    const ScanCh &c = (*scn)[p_.q];
                    std::vector<double> cp((size_t)NCOLS * 80);
                    int nch = 0, nsd = 0;
                    nv_scan_row(scanh, p_.x.data(), c.depth, c.chorus, c.row0, top[std::make_pair(p_.q, p_.x[12] - p_.x[45])],
                                SR, cp.data(), &nch, &nsd);
                    finish(*p_.t, p_.x.data(), p_.k, false, p_.dk, p_.dg);
                    const std::array<long long, 14> &k = p_.k;
                    for (int m = 0; m < nch + nsd; m++)
                        add(scanst, cp.data() + (size_t)NCOLS * m, false,
                            {2, (1LL << 42) + 2 * (long long)p_.q + (m < nch ? 0 : 1), k[0], k[1], k[2], k[3], k[4],
                             k[5], k[6], k[7], k[8], k[9], k[10], m < nch ? 0 : m - nch},
                            false, -1, 0.0f, true, true);
                }
            }
            void add(Store &t, const double *row, bool cast, std::array<long long, 14> k = {}, bool copy = false,
                     int dkv = -1, float dgv = 0.0f, bool notrem = false, bool noscan = false)
            {
                double xb[NCOLS];
                memcpy(xb, row, sizeof xb);
                if (cast)
                    stream_cast(xb, kind);
                double *x = xb;
                // THE TREMOLOS (after the amplifier, before the chorus: nv_tremolo_expand's
                // two passes): a stop's note rows, else the channel's; the sidebands their own
                // rows after the table's -- through the chorus and on, not the tremolo again
                if (!notrem && !copy && (ht || tch)) {
                    const double *c = nullptr;
                    double c4[4];
                    const long long chk = (long long)(int)x[6];
                    long long base = 0;
                    if (ht && !ht->empty() && k[0] == 0)
                        for (const auto &h : *ht)
                            if ((double)k[1] >= h[0] && (double)k[1] < h[1]) {
                                c4[0] = h[2]; c4[1] = h[3]; c4[2] = 0.0; c4[3] = 0.0;
                                c = c4;
                                base = 1LL << 40;
                                break;
                            }
                    if (!c && tch) {
                        auto it = tch->find(chk);
                        if (it != tch->end()) {
                            c = it->second.data();
                            base = 1LL << 41;
                        }
                    }
                    if (c) {
                        const std::vector<double> *H = nullptr;
                        if (twave) {
                            auto w = twave->find(chk);
                            if (w != twave->end())
                                H = &w->second;
                        }
                        const int nh = H ? (int)(H->size() / 3) : 0;
                        std::vector<double> tb((size_t)NCOLS * (H ? 2 * nh : 2));
                        const int nm = nv_tremolo_row(x, c, chk, H ? H->data() : nullptr, nh, SR, tb.data());
                        for (int m = 0; m < nm; m++)
                            add(tremst, tb.data() + (size_t)NCOLS * m, false,
                                {2, base + k[0], k[1], k[2], k[3], (long long)m}, false, dkv, dgv, true);
                    }
                }
                if (!noscan && !copy && scn)        // (THE SCANNER: its channel's rows held)
                    for (size_t q = 0; q < scn->size(); q++)
                        if ((long long)x[6] == (*scn)[q].ch && x[41] < 0) {
                            pend.push_back(Pend{&t, q, k, dkv, dgv, std::vector<double>(x, x + NCOLS)});
                            return;
                        }
                finish(t, x, k, copy, dkv, dgv);
            }
            void finish(Store &t, const double *xin, const std::array<long long, 14> &k, bool copy, int dkv,
                        float dgv)
            {
                t.dk.push_back(dkv);
                t.dg.push_back(dgv);
                double xl[NCOLS];               // (the row's passes in float64, then stored packed)
                memcpy(xl, xin, sizeof xl);
                double *x = xl;
                // THE CHORUS (before the cabinet, as the whole render's passes): the row's
                // copies keyed after the table's rows, its dry share off it -- not a copy's
                if (cch && !copy)
                    for (size_t q = 0; q < cch->size(); q++)
                        if ((long long)x[6] == (*cch)[q] && (*ckind)[q] == 2) {
                            // A CHORUS DEVICE: each tap's passes, keyed (tap * 17 + pass)
                            const StreamDev &D = (*cdev)[q];
                            if (D.kmax > 0) {
                                const int ntv = (int)(D.TV.size() / 8);
                                const int cap = (D.TV.empty() ? (int)D.G[6] : ntv) * 16;
                                std::vector<double> dcp((size_t)NCOLS * cap);
                                std::vector<int> dix(cap);
                                int nm = nv_chorus_dev_row(x, D.G.data(), D.TV.empty() ? nullptr : D.TV.data(), ntv,
                                                           D.share_at(x[12], SR), D.kmax, SR, dcp.data(), dix.data(),
                                                           cap);
                                for (int m = 0; m < nm; m++)
                                    add(chocp, dcp.data() + NCOLS * m, false,
                                        {3, (long long)q, dix[m], k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7], k[8], k[9], k[10]}, true, dkv, dgv);
                            }
                            break;
                        } else if ((long long)x[6] == (*cch)[q]) {
                            double ccp[8 * NCOLS];
                            int cis[8];
                            int nm = nv_chorus_row(x, (*ckind)[q], (*csend)[q], (*cnc)[q], ccents->data() + 8 * q, SR,
                                                   ccp, cis);
                            for (int m = 0; m < nm; m++)
                                add(chocp, ccp + NCOLS * m, false, {3, (long long)q, cis[m], k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7], k[8], k[9], k[10]},
                                    true, dkv, dgv);
                            break;
                        }
                if (eq) {                           // (THE INSERTION EQ: after the chorus, before the cabinet)
                    auto ie = eq->find((long long)x[6]);
                    if (ie != eq->end())
                        eq_row(ie->second, x);
                }
                auto cb = cab.find((long long)x[6]);   // (THE CABINET: EMIT_COLS' mch, nf, aL, aR, aM)
                if (cb != cab.end()) {
                    double g = nv_cab_gain(cb->second, x[11]);
                    x[3] *= g;
                    x[4] *= g;
                    x[5] *= g;
                }
                // THE ROTORS (nv_leslie_row: the whole render's pass, after the cabinet): the
                // row rotated, its lobe kept; its copies after the table, keyed by its place
                std::array<float, 5> lb = {-1.0f, 0.0f, 1.0f, 0.0f, 1.0f};
                double cp[3 * NCOLS];
                float lob[4 * 5];
                int ncp = 0, on = 0;
                if (les) {
                    ncp = nv_leslie_row(les, x, cp, lob, &on);
                    if (on)
                        std::copy(lob, lob + 5, lb.begin());
                }
                t.lob.push_back(lb);
                {                                   // (its table key: a window takes its rows in this order)
                    std::array<long long, 16> kk = {};
                    std::copy(k.begin(), k.end(), kk.begin());
                    t.key.push_back(kk);
                }
                for (int q = 0; q < ncp; q++) {
                    raw(lescp, cp + NCOLS * q);
                    lescp.dk.push_back(dkv);
                    lescp.dg.push_back(dgv);
                    std::array<float, 5> lc;
                    std::copy(lob + 5 * (q + 1), lob + 5 * (q + 2), lc.begin());
                    lescp.lob.push_back(lc);
                    std::array<long long, 16> kk = {};
                    std::copy(k.begin(), k.end(), kk.begin());
                    kk[14] = q;
                    lescp.key.push_back(kk);
                }
                // the kernel's last sample (streamrender.zend, on the final
                // float32 columns)
                float dl = std::max(0.0f, std::max((float)x[37], (float)x[38]));
                t.non.push_back((long long)x[12]);
                t.zend.push_back((long long)x[13] + (long long)(float)x[15] + (long long)ceilf(dl) + BLK);
                const size_t o = t.d.size();
                t.d.resize(o + g_rowB);
                pack_row(x, t.d.data() + o);
            }
            void raw(Store &t, const double *row)
            {
                const size_t o = t.d.size();
                t.d.resize(o + g_rowB);
                pack_row(row, t.d.data() + o);
                const double *x = row;
                float dl = std::max(0.0f, std::max((float)x[37], (float)x[38]));
                t.non.push_back((long long)x[12]);
                t.zend.push_back((long long)x[13] + (long long)(float)x[15] + (long long)ceilf(dl) + BLK);
            }
            static void note(void *c_, const double *at, long long i0, long long i1, double next_on)
            {
                Pass &p = *(Pass *)c_;
                double buf[NCOLS];
                // THE HALF-PEDAL's TRACK, a banded note's: from its own rows (cast), its
                // place among those used once a row of it takes it (onto_tracks)
                const int j = p.jn++;
                int ni = 0, band = 0, tix = -1;
                double land = 0.0, tf0 = 0.0;
                long long r1 = i1;
                std::vector<double> nb;
                if (p.song && nv_stream_note(j, &ni, &band, &land) && band) {
                    r1 = nv_play_own_end(j, i1);
                    if (r1 > i1)
                        r1 = i1;
                    if (r1 > i0) {
                        nb.assign(at, at + NCOLS * (r1 - i0));
                        for (long long r = 0; r < r1 - i0; r++)
                            stream_cast(nb.data() + NCOLS * r, p.kind);
                        std::vector<float> dc(4096);
                        long long b0 = 0;
                        long nd = nv_damp_track(p.song, ni, nb.data(), r1 - i0, land, p.SR, p.BLK, p.nblkv, p.dfull,
                                                p.dres, p.dknee, &b0, &tf0, dc.data(), (long)dc.size());
                        if (nd < 0) {
                            dc.resize(-nd);
                            nd = nv_damp_track(p.song, ni, nb.data(), r1 - i0, land, p.SR, p.BLK, p.nblkv, p.dfull,
                                               p.dres, p.dknee, &b0, &tf0, dc.data(), (long)dc.size());
                        }
                        if (nd > 0) {
                            bool any = false;   // (a row of it not a burst no damper reaches: fast_rows)
                            for (long long r = 0; r < r1 - i0 && !any; r++) {
                                const double *R_ = nb.data() + NCOLS * r;
                                float lr32 = (float)R_[17];
                                bool fast = (float)R_[20] <= 0 && (float)R_[19] <= 0
                                            && (float)(lr32 * (float)p.BLK) > (float)(p.dxdec * p.SR) && R_[39] < 0;
                                any = !fast;
                            }
                            if (any) {
                                tix = p.ntr++;
                                p.DMO.push_back((long)p.DM.size());
                                p.DMB.push_back((long)b0);
                                p.DMN.push_back(nd);
                                p.DM.insert(p.DM.end(), dc.begin(), dc.begin() + nd);
                            }
                        }
                    }
                }
                // THE MF-104M (before anything reads the note's rows: its dry share on
                // them, its repeats after the register's, before the delays')
                std::vector<double> cb(at, at + NCOLS * (i1 > i0 ? i1 - i0 : 0));
                for (long long r = 0; r < i1 - i0; r++)
                    stream_cast(cb.data() + NCOLS * r, p.kind);
                double *mg = nullptr;
                long long ml = 0;
                const long mm = p.mf && i1 > i0 ? nv_mf104_note(p.mf, cb.data(), i0, i1, &mg, &ml) : 0;
                for (long long r = 0; r < i1 - i0; r++) {
                    memcpy(buf, cb.data() + NCOLS * r, sizeof buf);
                    int dkv = -1;
                    float dgv = 0.0f;
                    if (tix >= 0 && i0 + r < r1) {
                        float lr32 = (float)buf[17];
                        bool fast = (float)buf[20] <= 0 && (float)buf[19] <= 0
                                    && (float)(lr32 * (float)p.BLK) > (float)(p.dxdec * p.SR) && buf[39] < 0;
                        if (!fast) {
                            double nf = (double)(float)buf[11];
                            double x = (nf > 1e-6 ? nf : 1e-6) / (tf0 > 1e-6 ? tf0 : 1e-6);
                            dkv = tix;
                            dgv = (float)(p.dln * pow(x, p.dbeta));
                        }
                    }
                    p.amp_take(buf, {0, i0 + r, 0, 0}, dkv, dgv);     // (the amplifier's copy, before the cabinet)
                    p.add(p.st, buf, false, {0, i0 + r, 0, 0, 0, 0, 0, 0}, false, dkv, dgv);
                }
                for (long q = 0; q < mm; q++) {
                    p.amp_take(mg + NCOLS * q, {1, (1LL << 40) - 1, j, q});
                    p.add(p.mfst, mg + NCOLS * q, false, {1, (1LL << 40) - 1, j, q, 0, 0, 0, 0});
                }
                free(mg);
                if (p.gsd && i1 > i0) {             // THE DELAYS' REPEATS (gsd_expand's, this note's)
                    double *g = nullptr;
                    long long gl = 0;
                    long m = nv_gsd_note(p.gsd, j, nv_play_sink_note(), cb.data(), i0, nv_play_own_end(j, i1), i1, &g,
                                         &gl);
                    for (long q = 0; q < m; q++) {
                        p.amp_take(g + NCOLS * q, {1, 1LL << 40, j, q});
                        p.add(p.gsdst, g + NCOLS * q, false, {1, 1LL << 40, j, q, 0, 0, 0, 0});
                    }
                    free(g);
                }
                long long T = std::isnan(next_on) ? p.N : std::min(p.N, (long long)(next_on * p.SR));
                p.scan_flush(std::isnan(next_on) ? INFINITY : (double)T);     // (the scanner's groups closed)
                if (p.ach && !p.ach->empty())       // (_amp_horizon: the next onset, the register's; at the end, all)
                    p.amp_advance(std::isnan(next_on) ? INFINITY : std::min((double)T, p.hraw));
                p.render_to(std::min(std::min(T, p.hz), p.amp_next()));
            }
            static void reg_rows(void *c_, int rank, const double *at, const long long *ph, const long long *sq, long n)
            {
                Pass &p = *(Pass *)c_;
                if ((int)p.reg.size() <= rank) {
                    p.reg.resize(rank + 1);
                    p.rkey.resize(rank + 1);
                }
                for (long r = 0; r < n; r++) {
                    p.amp_take(at + NCOLS * r, {1, (long long)rank, ph[r], sq[r]});
                    p.add(p.reg[rank], at + NCOLS * r, false, {1, (long long)rank, ph[r], sq[r], 0, 0, 0, 0});
                    p.rkey[rank].push_back(std::make_pair(ph[r], sq[r]));
                }
            }
            static void reg_horizon(void *c_, double h)
            {
                Pass &p = *(Pass *)c_;     // (floor(min(T, pending_min)): streamrender's)
                p.hz = std::isinf(h) ? LLONG_MAX : (long long)floor(h);
                p.hraw = h;
            }
        };
        const long CH = (long)E.k[K_CHUNK];
        const char *srows = getenv("TUNING_STREAM_ROWS");
        const long long row_budget = srows && atoll(srows) > 0 ? atoll(srows) : 300000;
        // THE BATCH (streamrender.BATCH, TUNING_STREAM_BATCH): 8 kernel chunks a
        // render; any size renders the same samples on the CPU, a smaller one
        // holds fewer notes' rows at once
        const char *swin = getenv("TUNING_STREAM_BATCH");
        const long W = (swin && atol(swin) > 0 ? atol(swin) : 8) * CH;
        long w0 = 0;
        Pass ps;
        {
            int nc = nv_song_cabs(song, nullptr, nullptr, 0);
            std::vector<long long> cch(nc);
            std::vector<const NoteClass *> cks(nc);
            if (nc)
                nv_song_cabs(song, cch.data(), cks.data(), nc);
            for (int q = 0; q < nc; q++)
                ps.cab[cch[q]] = cks[q];
        }
        ps.kind = E.kind.data();
        ps.ach = &s_ach;                    // (the amplifiers' settings, pass A's)
        ps.adr = &s_adr;
        ps.aref = &s_aref;
        ps.aimb = &s_aimb;
        ps.asb = &s_asb;
        ps.ass = &s_ass;
        ps.asl = &s_asl;
        ps.amp.assign(s_ach.size(), {});
        ps.ampst.assign(s_ach.size(), {});
        ps.nprod.assign(s_ach.size(), 0);
        ps.les = s_les;
        ps.gsd = scan.gsd;
        ps.mf = nv_mf104_new(song, E.kind.data(), SR);  // (pass B's own walk: the replay registers them again)
        ps.eq = efx_eq.empty() ? nullptr : &efx_eq;
        ps.song = song;                     // (the half-pedal's tracks: pass A's notes, prepare's laws)
        ps.nblkv = nblk;
        ps.dfull = E.k[K_FULL];
        ps.dres = E.k[K_RESIDUAL];
        ps.dknee = E.k[K_KNEE];
        ps.dln = E.k[K_LN10_20];
        ps.dbeta = E.k[K_BETA];
        ps.dxdec = E.k[K_XDEC];
        ps.cch = &s_cch;                    // (the choruses' settings)
        ps.ckind = &s_ckind;
        ps.cnc = &s_cnc;
        ps.csend = &s_csend;
        ps.ccents = &s_ccents;
        ps.cdev = &s_cdev;
        ps.ht = s_ht.empty() ? nullptr : &s_ht;
        ps.tch = s_tch.empty() ? nullptr : &s_tch;
        ps.twave = &s_twave;
        if (!s_scn.empty()) {
            ps.scn = &s_scn;
            ps.scanh = nv_scan_new(E.scan.data());
        }
        ps.SR = SR;
        ps.N = N;
        ps.BLK = BLK;
        const int cMch = col("mch");
        // A PART'S BUSES (render_mix's, window by window): each its processor's
        // state, this pass's own (the mix's, the send's)
        // (the mix's set, and the send's when it renders: Python's one pass, both
        // from the same rows -- streamrender._render's procs[ch][0] and [1])
        struct BusSet {
            std::vector<void *> bush;
            std::vector<std::vector<float>> busL, busR;
            std::vector<std::vector<double>> revL, revR, revX;
            std::vector<long long> revN, revB, revO;
            long long busO = 0;
            long wm = 0;                    // (stage 2: mixed and posted up to here)
            // ITS OUTPUT, written as it is final (streamrender's WavOut: write_wav's
            // bytes, a window at a time), held from outO until then
            std::vector<float> outL, outR;
            long long outO = 0, done = 0;
            FILE *wf = nullptr;
        };
        auto make_set = [&](const char *path) {
            BusSet b;
            b.wf = fopen(path, "wb");
            if (b.wf) {                     // (write_wav's header, for the N frames to come)
                uint32_t data = (uint32_t)(N * 2 * 4);
                auto u32 = [&](uint32_t v) { fwrite(&v, 4, 1, b.wf); };
                auto u16 = [&](uint16_t v) { fwrite(&v, 2, 1, b.wf); };
                fwrite("RIFF", 1, 4, b.wf); u32(36 + data); fwrite("WAVE", 1, 4, b.wf);
                fwrite("fmt ", 1, 4, b.wf); u32(16); u16(1); u16(2); u32((uint32_t)SR); u32((uint32_t)SR * 8);
                u16(8); u16(32);
                fwrite("data", 1, 4, b.wf); u32(data);
            }
            b.bush.assign(buses.size(), nullptr);
            for (size_t q = 0; q < buses.size(); q++)
                b.bush[q] = nv_livebus_raw_new(buses[q].kind, buses[q].p, SR);
            // ...each bus's part (stage 1 writes it, stage 2 mixes it), held from
            // b.busO, the first sample stage 2 has yet to mix; a reverb's responses,
            // its mono history (nh - 1 zeros, then the part) held from b.revO, a
            // whole block B of it (the convolution's blocks fall where they did
            // over the whole history, so its sums are the whole render's), its block B
            b.busL.assign(buses.size(), {}); b.busR.assign(buses.size(), {});
            b.revL.assign(buses.size(), {}); b.revR.assign(buses.size(), {}); b.revX.assign(buses.size(), {});
            b.revN.assign(buses.size(), 0); b.revB.assign(buses.size(), 0); b.revO.assign(buses.size(), 0);
            b.busO = 0;
            for (size_t q = 0; q < buses.size(); q++) {
                if (buses[q].kind == 3 || buses[q].kind == 4) {
                    const double *p = buses[q].p;
                    const long long cap = (long long)(10.0 * SR) + 64;
                    b.revL[q].assign(cap, 0.0);
                    b.revR[q].assign(cap, 0.0);
                    long long nh = buses[q].kind == 3
                        ? nv_efx_reverb_ir(SR, (int)p[0], p[1], (int)p[2], p[3], b.revL[q].data(), b.revR[q].data(), cap)
                        : nv_efx_gate_ir(SR, (int)p[0], p[1], p[2], b.revL[q].data(), b.revR[q].data(), cap);
                    b.revN[q] = nh;
                    long long F = 1;
                    while (F < 2 * nh)
                        F <<= 1;
                    b.revB[q] = F - nh + 1;
                    b.revX[q].assign((size_t)(nh - 1), 0.0);
                }
            }
            return b;
        };
        // THE GPU (--gpu: streamrender's gpu=, gpurender.FileRenderer a window at a time)
        static GpuFile *gpuf = nullptr;
        if (g_gpu && !gpuf) {
            char exe[4096];
            ssize_t ln = readlink("/proc/self/exe", exe, sizeof exe - 1);
            std::string dir = ln > 0 ? std::string(exe, ln) : std::string(".");
            dir = dir.substr(0, dir.rfind('/'));
            gpuf = new GpuFile();
            std::string why = gpuf->open(dir, (int)SR);
            if (!why.empty()) {
                fprintf(stderr, "nvrender: --gpu: %s\n", why.c_str());
                exit(1);
            }
            gpuf->bend_levels(BLr.empty() ? nullptr : BLr.data(), (long)nr, (long)nblk + 1);
        }
        BusSet bset[2];
        bset[0] = make_set(opath);
        const int nset = spath ? 2 : 1;
        if (spath)
            bset[1] = make_set(spath);
        for (int q = 0; q < nset; q++)
            if (!bset[q].wf) {
                fprintf(stderr, "nvrender: cannot write %s\n", q ? spath : opath);
                exit(1);
            }
        // a set's output at [s0, s0 + n): its place, held; and out once final
        auto out_at = [&](BusSet &b, long long s0, long long n_) {
            if ((long long)b.outL.size() < s0 + n_ - b.outO) {
                b.outL.resize(s0 + n_ - b.outO, 0.0f);
                b.outR.resize(s0 + n_ - b.outO, 0.0f);
            }
            return std::make_pair(b.outL.data() + (s0 - b.outO), b.outR.data() + (s0 - b.outO));
        };
        auto out_emit = [&](BusSet &b, long long s0, long long n_) {
            std::vector<int32_t> buf(2 * n_);
            for (long long i = 0; i < n_; i++)
                for (int c = 0; c < 2; c++) {
                    double x = c ? (double)b.outR[s0 - b.outO + i] : (double)b.outL[s0 - b.outO + i];
                    x = x < -1.0 ? -1.0 : (x > 1.0 ? 1.0 : x);         // np.clip
                    buf[2 * i + c] = (int32_t)(x * 2147483647.0);    // astype('<i4'): toward zero
                }
            fwrite(buf.data(), 4, buf.size(), b.wf);
            b.done = s0 + n_;
            if (2 * (b.done - b.outO) > (long long)b.outL.size()) {     // (let go once half are out)
                b.outL.erase(b.outL.begin(), b.outL.begin() + (b.done - b.outO));
                b.outR.erase(b.outR.begin(), b.outR.begin() + (b.done - b.outO));
                b.outO = b.done;
            }
        };
        auto stage2 = [&](BusSet &b, long done) {      // (the parts rendered up to done)
            while (b.wm < N && b.wm < done) {
                const long wn2 = std::min((long)W, N - b.wm);
                bool ready = true;
                for (size_t q = 0; q < buses.size() && ready; q++)
                    if (b.revN[q] > 0 && done < N) {
                        const long long t = b.revN[q] - 1 + b.wm + wn2 - 1, B = b.revB[q];
                        const long long need = t / B * B + B - b.revN[q];     // (the last input its blocks read)
                        ready = need < done;
                    }
                if (!ready || b.wm + wn2 > done)
                    return;
                const double gain = E.k[K_MASTER];
                for (size_t q = 0; q < buses.size(); q++) {
                    std::vector<float> yL(wn2), yR(wn2);
                    if (b.revN[q] > 0) {
                        std::vector<double> o(wn2);
                        const long long nh = b.revN[q];
                        const long long xo = b.revO[q], nx = nh - 1 + N - xo;     // (the whole history's length)
                        nv_efx_conv(b.revX[q].data(), nx, b.revL[q].data(), nh, nh - 1 + b.wm - xo, wn2, o.data());
                        for (long i = 0; i < wn2; i++)
                            yL[i] = (float)o[i];
                        nv_efx_conv(b.revX[q].data(), nx, b.revR[q].data(), nh, nh - 1 + b.wm - xo, wn2, o.data());
                        for (long i = 0; i < wn2; i++)
                            yR[i] = (float)o[i];
                    } else {
                        const float gf = (float)gain;
                        std::vector<float> xL(wn2), xR(wn2);
                        for (long i = 0; i < wn2; i++) {
                            xL[i] = b.busL[q][b.wm - b.busO + i] * gf;
                            xR[i] = b.busR[q][b.wm - b.busO + i] * gf;
                        }
                        nv_livebus_raw(b.bush[q], xL.data(), xR.data(), wn2, yL.data(), yR.data());
                    }
                    const float dry = (float)buses[q].dry, wet = (float)buses[q].wet;
                    for (long i = 0; i < wn2; i++) {
                        bool on = !buses[q].part;
                        for (auto &sp : buses[q].spans)
                            on = on || (b.wm + i >= sp.first && b.wm + i < sp.second);
                        const float bl = b.busL[q][b.wm - b.busO + i], br = b.busR[q][b.wm - b.busO + i];
                        float wL = (float)((double)yL[i] / gain), wR = (float)((double)yR[i] / gain);
                        float mL = on ? dry * bl + wet * wL : bl, mR = on ? dry * br + wet * wR : br;
                        float *oL_ = b.outL.data() + (b.wm - b.outO), *oR_ = b.outR.data() + (b.wm - b.outO);
                        oL_[i] = oL_[i] + mL;
                        oR_[i] = oR_[i] + mR;
                    }
                }
                nv_render_post_win(b.outL.data() + (b.wm - b.outO), b.outR.data() + (b.wm - b.outO), b.wm, wn2, SR,
                                   E.k[K_MASTER], 1);
                out_emit(b, b.wm, wn2);
                b.wm += wn2;
                // what no later window reads let go of: the parts before b.wm, and
                // a reverb's whole blocks that end before its next output can
                // reach back (block b0 reaches b0 + B + nh - 2) -- once half are gone
                if (2 * (b.wm - b.busO) > (long long)(b.busL.empty() ? 0 : b.busL[0].size())) {
                    for (size_t q = 0; q < buses.size(); q++) {
                        b.busL[q].erase(b.busL[q].begin(), b.busL[q].begin() + (b.wm - b.busO));
                        b.busR[q].erase(b.busR[q].begin(), b.busR[q].begin() + (b.wm - b.busO));
                    }
                    b.busO = b.wm;
                }
                for (size_t q = 0; q < buses.size(); q++) {
                    const long long B = b.revB[q];
                    if (b.revN[q] <= 0 || b.wm - B < 0)
                        continue;
                    const long long xo = (b.wm - B) / B * B;      // (blocks before it: b0 + B + nh - 2 < nh - 1 + b.wm)
                    if (xo > b.revO[q] && 2 * (xo - b.revO[q]) > (long long)b.revX[q].size()) {
                        b.revX[q].erase(b.revX[q].begin(), b.revX[q].begin() + (xo - b.revO[q]));
                        b.revO[q] = xo;
                    }
                }
            }
        };
        // THE ROW BUDGET (streamrender's ROW_BUDGET, TUNING_STREAM_ROWS): a batch
        // sounding more rows than that renders in halves, each half judged
        // again (_render: its first nw / 2 windows, then the rest), and the
        // next batch begins where the whole one would have -- the same samples,
        // each row's copies for the kernel fewer, and the GPU's windows where
        // FileRenderer's fall. A render adds no rows, so the halves are planned
        // before any is rendered
        auto sounding = [&](long long a, long long b) {
            size_t nl = 0;
            auto from = [&](const Store &g) {
                for (size_t r = 0; r < g.non.size(); r++)
                    nl += g.non[r] < b && g.zend[r] > a;
            };
            from(ps.st);
            for (Store &g : ps.reg)
                from(g);
            from(ps.mfst);
            from(ps.gsdst);
            for (Store &g : ps.ampst)
                from(g);
            from(ps.tremst);
            from(ps.scanst);
            from(ps.chocp);
            from(ps.lescp);
            return nl;
        };
        std::vector<std::pair<long long, long>> spans;      // (the batch's pieces, last first)
        std::function<void(long long, long)> plan = [&](long long wi, long nw) {
            const long long a = wi * CH, b = std::min((long long)N, a + (long long)nw * CH);
            if (b <= a)
                return;
            if (nw > 1 && sounding(a, b) > (size_t)row_budget) {
                plan(wi, nw / 2);
                plan(wi + nw / 2, nw - nw / 2);
                return;
            }
            spans.insert(spans.begin(), std::make_pair(a, (long)(b - a)));
        };
        ps.render_to = [&](long long T) {
            while (!spans.empty() || (w0 < N && (w0 + W <= T || T >= N))) {
                if (spans.empty())
                    plan(w0 / CH, W / CH);
                long wn = spans.back().second;      // (w0, its start)
                spans.pop_back();
                Store &s = ps.st;
                // the window's rows as the whole table orders them: the notes',
                // then each register channel in `order`, its rows by (phase, seq)
                std::vector<const unsigned char *> live;
                std::vector<const std::array<float, 5> *> llob;    // (each live row's lobe)
                std::vector<int> wdk;                       // (...its damper track and weight)
                std::vector<float> wdg;
                auto take = [&](Store &g, size_t r) {
                    live.push_back(g.d.data() + (size_t)g_rowB * r);
                    llob.push_back(&g.lob[r]);
                    wdk.push_back(g.dk[r]);
                    wdg.push_back(g.dg[r]);
                };
                {                                   // (every store's rows, by their table key)
                    std::vector<std::pair<Store *, size_t>> ix;
                    auto from = [&](Store &g) {
                        for (size_t r = 0; r < g.non.size(); r++)
                            if (g.non[r] < w0 + wn && g.zend[r] > w0)
                                ix.push_back(std::make_pair(&g, r));
                    };
                    from(s);
                    for (Store &g : ps.reg)
                        from(g);
                    from(ps.mfst);
                    from(ps.gsdst);
                    for (Store &g : ps.ampst)
                        from(g);
                    from(ps.tremst);
                    from(ps.scanst);
                    from(ps.chocp);
                    std::sort(ix.begin(), ix.end(), [&](const std::pair<Store *, size_t> &u,
                                                        const std::pair<Store *, size_t> &v) {
                        return u.first->key[u.second] < v.first->key[v.second];
                    });
                    for (auto &pr : ix)
                        take(*pr.first, pr.second);
                }
                {                                   // (the Leslie's copies, after: by their source's place)
                    Store &g = ps.lescp;
                    std::vector<size_t> ix;
                    for (size_t r = 0; r < g.non.size(); r++)
                        if (g.non[r] < w0 + wn && g.zend[r] > w0)
                            ix.push_back(r);
                    std::sort(ix.begin(), ix.end(), [&](size_t a, size_t b) { return g.key[a] < g.key[b]; });
                    for (size_t r : ix)
                        take(g, r);
                }
                const long long n = (long long)live.size();
                // the rotors' lobe columns, the window's rows'
                std::vector<int> wlsr;
                std::vector<float> wlb[4];
                float *wlob[4] = {nullptr, nullptr, nullptr, nullptr};
                if (ps.les || !fltch.empty()) {
                    wlsr.resize(n);
                    for (int q = 0; q < 4; q++)
                        wlb[q].resize(n);
                    for (long long k = 0; k < n; k++) {
                        wlsr[k] = (int)(*llob[k])[0];
                        for (int q = 0; q < 4; q++)
                            wlb[q][k] = (*llob[k])[q + 1];
                    }
                    for (int q = 0; q < 4; q++)
                        wlob[q] = wlb[q].data();
                }
                // THE MOVING FILTERS' columns, the window's rows' (filter_prep:
                // EF.columns of their channels; the control table the whole file's)
                std::vector<int> wfsr, wfty;
                std::vector<float> wflp[3], wfmx;
                const float *wfpp[3] = {nullptr, nullptr, nullptr};
                if (!fltch.empty()) {
                    wfsr.assign(n, -1);
                    wfty.assign(n, 0);
                    for (int q = 0; q < 3; q++)
                        wflp[q].assign(n, 0.0f);
                    wfmx.assign(n, 1.0f);
                    for (long long k = 0; k < n; k++) {
                        const long long m = (long long)unpack(live[k], cMch);
                        for (const FltCh &c : fltch)
                            if (c.ch == m) {
                                wfsr[k] = c.row;
                                wfty[k] = c.ty;
                                for (int q = 0; q < 3; q++)
                                    wflp[q][k] = c.p[q];
                                wfmx[k] = c.mx;
                                break;
                            }
                    }
                    for (int q = 0; q < 3; q++)
                        wfpp[q] = wflp[q].data();
                }
                // the window's table, in prepare's final types (as fcol)
                auto tcol = [&](int c) {
                    std::vector<double> v(n);
                    for (long long k = 0; k < n; k++) {
                        double x = unpack(live[k], c);
                        switch (E.fin[c]) {
                        case 1: x = (double)(float)x; break;
                        case 2: x = (double)(long long)x; break;
                        case 3: x = (double)(int32_t)x; break;
                        }
                        v[k] = x;
                    }
                    return v;
                };
                std::vector<double> wd[3];
                for (int q = 0; q < 3; q++)
                    wd[q] = tcol(col(DN[q]));
                std::vector<std::vector<float>> wf(29);
                for (int q = 0; q < 28; q++) {
                    std::vector<double> v = tcol(col(VF[q]));
                    wf[q].assign(v.begin(), v.end());
                }
                std::vector<long> wl[2];
                for (int q = 0; q < 2; q++) {
                    std::vector<double> v = tcol(col(LN[q]));
                    wl[q].assign(v.begin(), v.end());
                }
                std::vector<int> wi[3];
                for (int q = 0; q < 3; q++) {
                    std::vector<double> v = tcol(col(IN[q]));
                    wi[q].assign(v.begin(), v.end());
                }
                // THE MOOGS' columns, the window's rows' (fcol's casts): the tables pass A's
                MoogCols wmc = mc;
                std::vector<int> wfx, wmk;
                std::vector<double> wfm[3];
                if (nft) {
                    std::vector<double> v = tcol(col("fx"));
                    wfx.assign(v.begin(), v.end());
                    v = tcol(col("mk"));
                    wmk.assign(v.begin(), v.end());
                    const char *FMN[3] = {"fmw", "fmp", "fmpR"};
                    for (int q = 0; q < 3; q++)
                        wfm[q] = tcol(col(FMN[q]));
                    wmc.fx = wfx.data();
                    wmc.mk = wmk.data();
                    for (int q = 0; q < 3; q++)
                        wmc.fm[q] = wfm[q].data();
                }
                double *wdp[3] = {wd[0].data(), wd[1].data(), wd[2].data()};
                float *wfp[29];
                for (int q = 0; q < 29; q++)
                    wfp[q] = wf[q].empty() ? nullptr : wf[q].data();
                if (ps.ntr)                         // (the damper's weights: dm[1]'s, the window's rows')
                    wfp[28] = wdg.data();
                long *wlp[2] = {wl[0].data(), wl[1].data()};
                int *wip[4] = {wi[0].data(), wi[1].data(), wi[2].data(), ps.ntr ? wdk.data() : nullptr};
                auto winr = [&](const unsigned char *sel, int post, float *L_, float *R_) {
                    nv_render_win(fn[0], fn[1], fn[2], N, (int)BLK, nblk, n, wdp, wfp, wlp, wip, Gt.data(), St.data(),
                                  BRr.data(), BCr.data(), BLr.empty() ? nullptr : BLr.data(), noRows, sh,
                                  (long)E.k[K_CHUNK], E.k[K_XDEC], SR, E.k[K_MASTER], ps.ntr ? ps.DM.data() : nullptr,
                                  ps.ntr ? ps.DMO.data() : nullptr, ps.ntr ? ps.DMB.data() : nullptr,
                                  ps.ntr ? ps.DMN.data() : nullptr, L_, R_, slo, wlsr.empty() ? nullptr : wlsr.data(),
                                  wlsr.empty() ? nullptr : (float *const *)wlob, LANG.empty() ? nullptr : LANG.data(), lgn,
                                  nft ? &wmc : nullptr, wfsr.empty() ? nullptr : wfsr.data(),
                                  wfsr.empty() ? nullptr : wfty.data(), (const float *const *)wfpp,
                                  wfsr.empty() ? nullptr : FCT.data(), wfsr.empty() ? 0 : fgn, sel, post, w0, wn, nullptr, 0);
                };
                // the window into a set's outputs: the rest, each bus's part kept (stage 1)
                auto emit = [&](BusSet &b) {
                    if (buses.empty()) {
                        auto o = out_at(b, w0, wn);
                        winr(nullptr, 1, o.first, o.second);
                        out_emit(b, w0, wn);
                    } else {
                        // the rest, then each bus's part through its processor, then the post
                        std::vector<unsigned char> wb(n > 0 ? n : 1, 0), sel(n > 0 ? n : 1);
                        for (long long r = 0; r < n; r++) {
                            const long long m = (long long)unpack(live[r], cMch);
                            for (size_t q = 0; q < buses.size(); q++)
                                if (buses[q].part ? m % 256 == buses[q].ch : buses[q].ch == m) {
                                    if (wb[r]) {
                                        fprintf(stderr, "nvrender: refused: a row on two buses (a part's and its tone's)\n");
                                        exit(2);
                                    }
                                    wb[r] = (unsigned char)(q + 1);
                                }
                        }
                        for (long long r = 0; r < n; r++)
                            sel[r] = wb[r] == 0;
                        auto o = out_at(b, w0, wn);
                        winr(sel.data(), 0, o.first, o.second);
                        const float gf = (float)E.k[K_MASTER];
                        for (size_t q = 0; q < buses.size(); q++) {     // STAGE 1: each bus's part, kept
                            for (long long r = 0; r < n; r++)
                                sel[r] = wb[r] == q + 1;
                            b.busL[q].resize(w0 + wn - b.busO, 0.0f);
                            b.busR[q].resize(w0 + wn - b.busO, 0.0f);
                            winr(sel.data(), 0, b.busL[q].data() + (w0 - b.busO), b.busR[q].data() + (w0 - b.busO));
                            if (b.revN[q] > 0) {          // (a reverb's mono history, at the output's scale)
                                b.revX[q].resize(b.revN[q] - 1 + w0 + wn - b.revO[q], 0.0);
                                for (long i = 0; i < wn; i++)
                                    b.revX[q][b.revN[q] - 1 + w0 + i - b.revO[q]] =
                                        0.5 * ((double)(b.busL[q][w0 - b.busO + i] * gf) + (double)(b.busR[q][w0 - b.busO + i] * gf));
                            }
                        }
                    }
                };
                if (gpuf) {
                    // THE WINDOW ON THE GPU: each selection once, the mix and the send
                    // from the same launch (the send weights the kernel's own), into the
                    // sets as the CPU's renders go
                    GfTable gt;
                    gt.P = n;
                    for (int q = 0; q < 3; q++)
                        gt.d[q] = wdp[q];
                    for (int q = 0; q < 29; q++)
                        gt.f[q] = wfp[q];
                    gt.l[0] = wlp[0];
                    gt.l[1] = wlp[1];
                    for (int q = 0; q < 4; q++)
                        gt.i[q] = wip[q];
                    if (nft) {
                        gt.fx = wmc.fx; gt.mk = wmc.mk; gt.FT = wmc.FT; gt.KN = wmc.KN; gt.knk = wmc.knk;
                        gt.kb0 = wmc.kb0; gt.MPI = wmc.MPI; gt.MKI = wmc.MKI; gt.MPC = wmc.MPC; gt.MPR = wmc.MPR;
                        gt.MPK = wmc.MPK;
                        for (int q = 0; q < 3; q++)
                            gt.fm[q] = wmc.fm[q];
                    }
                    if (!wfsr.empty()) {
                        gt.fsr = wfsr.data();
                        gt.fty = wfty.data();
                        for (int q = 0; q < 3; q++)
                            gt.fp[q] = wflp[q].data();
                        gt.fmx = wfmx.data();
                    }
                    if (!wlsr.empty()) {
                        gt.lsr = wlsr.data();
                        for (int q = 0; q < 4; q++)
                            gt.lob[q] = wlob[q];
                    }
                    std::vector<float> sw;
                    if (nset > 1) {
                        sw.resize(n > 0 ? n : 1);
                        for (long long k = 0; k < n; k++)
                            sw[k] = (*wt)((long long)unpack(live[k], cMch), (long long)unpack(live[k], 12));
                    }
                    std::vector<float> o4((size_t)4 * wn);
                    auto g4 = [&](const unsigned char *sel) {
                        if (gpuf->render(gt, sel, w0, wn, nset > 1 ? sw.data() : nullptr, (int)BLK, (int)nblk,
                                         Gt.data(), St.data(), BRr.data(), BCr.data(),
                                         BLr.empty() ? nullptr : BLr.data(), sh, LANG.empty() ? nullptr : LANG.data(),
                                         lgn, wfsr.empty() ? nullptr : FCT.data(), wfsr.empty() ? 0 : fgn,
                                         ps.ntr ? ps.DM.data() : nullptr, ps.ntr ? ps.DMO.data() : nullptr,
                                         ps.ntr ? ps.DMB.data() : nullptr, ps.ntr ? ps.DMN.data() : nullptr, SR,
                                         o4.data()) != 0) {
                            fprintf(stderr, "nvrender: --gpu: the GPU failed at %.3f s\n", w0 / SR);
                            exit(1);
                        }
                    };
                    if (buses.empty()) {
                        g4(nullptr);
                        for (int q = 0; q < nset; q++) {
                            auto o = out_at(bset[q], w0, wn);
                            memcpy(o.first, o4.data() + (size_t)(2 * q) * wn, sizeof(float) * wn);
                            memcpy(o.second, o4.data() + (size_t)(2 * q + 1) * wn, sizeof(float) * wn);
                            nv_render_post_win(o.first, o.second, w0, wn, SR, E.k[K_MASTER], 1);
                            out_emit(bset[q], w0, wn);
                        }
                    } else {
                        std::vector<unsigned char> wb(n > 0 ? n : 1, 0), sel(n > 0 ? n : 1);
                        for (long long r = 0; r < n; r++) {
                            const long long m = (long long)unpack(live[r], cMch);
                            for (size_t q = 0; q < buses.size(); q++)
                                if (buses[q].part ? m % 256 == buses[q].ch : buses[q].ch == m) {
                                    if (wb[r]) {
                                        fprintf(stderr, "nvrender: refused: a row on two buses (a part's and its tone's)\n");
                                        exit(2);
                                    }
                                    wb[r] = (unsigned char)(q + 1);
                                }
                        }
                        for (long long r = 0; r < n; r++)
                            sel[r] = wb[r] == 0;
                        g4(sel.data());
                        for (int q = 0; q < nset; q++) {
                            auto o = out_at(bset[q], w0, wn);
                            memcpy(o.first, o4.data() + (size_t)(2 * q) * wn, sizeof(float) * wn);
                            memcpy(o.second, o4.data() + (size_t)(2 * q + 1) * wn, sizeof(float) * wn);
                        }
                        const float gf = (float)E.k[K_MASTER];
                        for (size_t bq = 0; bq < buses.size(); bq++) {     // STAGE 1: each bus's part, kept
                            for (long long r = 0; r < n; r++)
                                sel[r] = wb[r] == bq + 1;
                            g4(sel.data());
                            for (int q = 0; q < nset; q++) {
                                BusSet &b = bset[q];
                                b.busL[bq].resize(w0 + wn - b.busO, 0.0f);
                                b.busR[bq].resize(w0 + wn - b.busO, 0.0f);
                                memcpy(b.busL[bq].data() + (w0 - b.busO), o4.data() + (size_t)(2 * q) * wn,
                                       sizeof(float) * wn);
                                memcpy(b.busR[bq].data() + (w0 - b.busO), o4.data() + (size_t)(2 * q + 1) * wn,
                                       sizeof(float) * wn);
                                if (b.revN[bq] > 0) {
                                    b.revX[bq].resize(b.revN[bq] - 1 + w0 + wn - b.revO[bq], 0.0);
                                    for (long i = 0; i < wn; i++)
                                        b.revX[bq][b.revN[bq] - 1 + w0 + i - b.revO[bq]] =
                                            0.5 * ((double)(b.busL[bq][w0 - b.busO + i] * gf)
                                                   + (double)(b.busR[bq][w0 - b.busO + i] * gf));
                                }
                            }
                        }
                    }
                } else {
                emit(bset[0]);
                if (nset > 1) {                 // the send: each row's level at its channel's send
                    for (long long k = 0; k < n; k++) {
                        float g = (*wt)((long long)unpack(live[k], cMch), (long long)unpack(live[k], 12));
                        wf[0][k] = wf[0][k] * g;
                        wf[1][k] = wf[1][k] * g;
                    }
                    emit(bset[1]);
                }
                }
                w0 += wn;
                if (!buses.empty())
                    for (int q = 0; q < nset; q++)
                        stage2(bset[q], w0);                     // STAGE 2: the windows every bus can give, in order
                // the rows past the window let go of (each store compacted once half
                // are gone: its rows, lobes and keys -- a register channel's its own keys too)
                auto compact = [&](Store &g, std::vector<std::pair<long long, long long>> *rk) {
                    size_t gd = 0;
                    for (size_t r = 0; r < g.zend.size(); r++)
                        gd += g.zend[r] <= w0;
                    if (!gd || 2 * gd < g.zend.size())
                        return;
                    Store t;
                    std::vector<std::pair<long long, long long>> tk;
                    for (size_t r = 0; r < g.zend.size(); r++)
                        if (g.zend[r] > w0) {
                            t.d.insert(t.d.end(), g.d.begin() + (size_t)g_rowB * r, g.d.begin() + (size_t)g_rowB * (r + 1));
                            t.non.push_back(g.non[r]);
                            t.zend.push_back(g.zend[r]);
                            t.lob.push_back(g.lob[r]);
                            t.dk.push_back(g.dk[r]);
                            t.dg.push_back(g.dg[r]);
                            if (!g.key.empty())
                                t.key.push_back(g.key[r]);
                            if (rk)
                                tk.push_back((*rk)[r]);
                        }
                    g = std::move(t);
                    if (rk)
                        rk->swap(tk);
                };
                compact(s, nullptr);
                for (Store &g : ps.ampst)
                    compact(g, nullptr);
                for (size_t q = 0; q < ps.reg.size(); q++)
                    compact(ps.reg[q], &ps.rkey[q]);
                compact(ps.chocp, nullptr);
                compact(ps.lescp, nullptr);
                compact(ps.gsdst, nullptr);
                compact(ps.mfst, nullptr);
                compact(ps.tremst, nullptr);
                compact(ps.scanst, nullptr);
            }
        };
        StreamSinkDesc pd{&ps, &Pass::note};
        StreamRegDesc prd{&ps, &Pass::reg_rows, &Pass::reg_horizon};
        nv_play_set_sink(&pd);
        nv_play_set_reg_sink(&prd);
        long long got = nv_play_replay(song, K.data(), &t, rows_ ? br.data() : nullptr, rows_ ? 1024 : 0, &rs, qacc,
                                       &az, E.kind.data(), BLK);
        nv_play_set_sink(nullptr);
        nv_play_set_reg_sink(nullptr);
        ps.render_to(N);                    // (a song with no notes: its silence)
        for (int q = 0; q < nset; q++) {
            if (bset[q].done != N) {
                fprintf(stderr, "nvrender: --stream: %lld of %ld frames written\n", bset[q].done, N);
                got = -1;
            }
            fclose(bset[q].wf);
        }
        return got;
    };
    if (!g_stream)                          // (a stream's: one pass with the send, once it is known)
        render_mix(fp, L.data(), R.data());
    if (!g_stream && !write_wav(argv[3], L.data(), R.data(), N, (int)SR)) {
        fprintf(stderr, "nvrender: cannot write %s\n", argv[3]);
        return 1;
    }
    // THE ROOM SIDECAR (blockrender's OUT.room.json; json.dump(..., indent=1))
    std::string base = argv[3];
    size_t dot = base.rfind('.');
    size_t slash = base.rfind('/');
    if (dot != std::string::npos && (slash == std::string::npos || dot > slash))
        base = base.substr(0, dot);
    // THE REVERB SEND (blockrender's _REVERB_CH, send_steps, send_values,
    // send_weights): each mix channel whose part sends a CC91, its first
    // over GM's 40, in the order its first note came; a part whose CC91
    // changes, its steps (onset samples, multiples); what the channels that
    // sound stand at -- one value, and roomtail scales the mix; more, and the
    // bus is rendered: the table again, each row weighted by its channel's
    // send at its onset
    std::vector<std::pair<long long, double>> rsend;
    std::map<long long, std::pair<std::vector<long long>, std::vector<double>>> steps;
    std::set<long long> heard;
    {
        const int cM = col("mch");
        std::set<long long> seen;
        auto part_cc = [&](long long part, std::vector<double> &tt, std::vector<int> &vv) {
            int n = nv_song_ccs(song, part, 91, nullptr, nullptr, 0);
            tt.resize(n > 0 ? n : 0);
            vv.resize(n > 0 ? n : 0);
            if (n > 0)
                nv_song_ccs(song, part, 91, tt.data(), vv.data(), n);
            return n;
        };
        for (long long r = 0; r < P; r++)
            heard.insert((long long)rows[NCOLS * r + cM]);
        if (g_stream)                       // (the stream's table: the scan heard them)
            heard.insert(scan.heard.begin(), scan.heard.end());
        {
            int nn = nv_song_n_notes(song);
            std::vector<int> ord(nn);
            std::vector<double> on_(nn);
            std::vector<long long> ch_(nn);
            std::vector<int> key_(nn);
            for (int i = 0; i < nn; i++) {
                long long c;
                int iv[4];
                double dv[2];
                nv_song_get_note(song, i, &c, iv, dv);
                ord[i] = i;
                on_[i] = dv[0];
                ch_[i] = c;
                key_[i] = iv[0];
            }
            std::stable_sort(ord.begin(), ord.end(), [&](int a, int b) {
                if (on_[a] != on_[b])
                    return on_[a] < on_[b];
                if (ch_[a] != ch_[b])
                    return ch_[a] < ch_[b];
                return key_[a] < key_[b];
            });
            for (int i : ord) {
                long long c = nv_song_mix(song, i);
                std::vector<double> tt;
                std::vector<int> vv;
                int cq = E.cmap[nv_song_kidx(song, i)];
                const NoteClass *nk = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
                const int nfx = note_fx[i];
                if (seen.count(c)) {
                } else if (efx_send.count(c) && (nfx >= 0 || (nfx == -1 && nk && nk->efx_set))) {
                    rsend.emplace_back(c, efx_send[c]);         // (its insertion effect's send: _REVERB_CH.setdefault)
                    seen.insert(c);
                } else if (part_cc(c % 256, tt, vv) > 0) {
                    rsend.emplace_back(c, vv[0] / 40.0);
                    seen.insert(c);
                } else if (nk && nk->rd_set) {
                    rsend.emplace_back(c, nk->reverb_dist);      // (a voice's own distance: the gunshot's)
                    seen.insert(c);
                }
                // ...A PARALLEL TYPE's BRANCH B: its virtual channel the part's
                // send, at the chain's first note (_REVERB_CH[_vc])
                if (nfx >= 0 && fx_first[i] && fxch[(size_t)NV_FXN * nfx + 208] != 0.0 && !seen.count(c + 65536))
                    for (const auto &e : rsend)
                        if (e.first == c) {
                            rsend.emplace_back(c + 65536, e.second);
                            seen.insert(c + 65536);
                            break;
                        }
            }
        }
        for (long long c : heard) {
            long long part = c % 256;
            if (steps.count(part) || efx_parts.count(part))
                continue;                   // (an effect's part: its send, no steps -- _REVERB_STEPS.pop)
            std::vector<double> tt;
            std::vector<int> vv;
            int n = part_cc(part, tt, vv);
            bool moves = false;
            for (int q = 1; q < n; q++)
                moves = moves || vv[q] != vv[0];
            if (!moves)
                continue;
            auto &st = steps[part];
            for (int q = 0; q < n; q++) {
                st.first.push_back((long long)nearbyint(tt[q] * SR));
                st.second.push_back(vv[q] / 40.0);
            }
        }
    }
    auto rs_of = [&](long long c) {
        for (auto &e : rsend)
            if (e.first == c)
                return e.second;
        return 1.0;
    };
    std::set<double> svals;
    if (!rsend.empty())
        for (long long c : heard) {
            auto st = steps.find(c % 256);
            if (st != steps.end())
                svals.insert(st->second.second.begin(), st->second.second.end());
            else
                svals.insert(rs_of(c));
        }
    if (g_stream) {
        // THE STREAM's ONE PASS (streamrender's): the mix, and the send where
        // the channels heard send differently, window by window from the same rows
        const bool send_ = !rsend.empty() && svals.size() > 1;
        std::function<float(long long, long long)> wfn = [&](long long c, long long nr) {
            auto st = steps.find(c % 256);
            double g;
            if (st != steps.end()) {
                const std::vector<long long> &on = st->second.first;
                long i = (long)(std::upper_bound(on.begin(), on.end(), nr) - on.begin()) - 1;
                g = st->second.second[i > 0 ? i : 0];
            } else {
                g = rs_of(c);
            }
            return (float)g;
        };
        const std::string spath = base + ".send.wav";
        if (stream_pass(send_ ? &wfn : nullptr, argv[3], send_ ? spath.c_str() : nullptr) < 0) {
            fprintf(stderr, "nvrender: --stream: the replay failed\n");
            return 1;
        }
    }
    if (!rsend.empty() && svals.size() > 1) {
        // the bus: aL and aR weighted (float32, numpy's) by each row's send
        std::vector<float> wL = fcols[0], wR = fcols[1];
        for (long long r = 0; r < P; r++) {
            long long c = (long long)rows[NCOLS * r + col("mch")];
            auto st = steps.find(c % 256);
            double g;
            if (st != steps.end()) {
                const std::vector<long long> &on = st->second.first;
                long long nr = lcols[0][r];
                long i = (long)(std::upper_bound(on.begin(), on.end(), nr) - on.begin()) - 1;
                g = st->second.second[i > 0 ? i : 0];
            } else {
                g = rs_of(c);
            }
            float gf = (float)g;
            wL[r] = wL[r] * gf;
            wR[r] = wR[r] * gf;
        }
        float *fp2[29];
        for (int q = 0; q < 29; q++)
            fp2[q] = fp[q];
        fp2[0] = wL.data();
        fp2[1] = wR.data();
        std::vector<float> SLb(g_stream ? 0 : N), SRb(g_stream ? 0 : N);
        if (!g_stream)                      // (a stream's: written in its one pass)
            render_mix(fp2, SLb.data(), SRb.data());
        if (!g_stream && !write_wav((base + ".send.wav").c_str(), SLb.data(), SRb.data(), N, (int)SR)) {
            fprintf(stderr, "nvrender: cannot write %s.send.wav\n", base.c_str());
            return 1;
        }
    }
    std::string sendj = "{}";
    if (!rsend.empty()) {
        std::vector<std::pair<long long, double>> sd;
        if (svals.size() == 1)
            for (long long c : heard)
                sd.emplace_back(c, *svals.begin());
        else
            sd = rsend;
        sendj = "{\n";
        for (size_t q = 0; q < sd.size(); q++)
            sendj += "  \"" + std::to_string(sd[q].first) + "\": " + pyrepr(sd[q].second) + (q + 1 < sd.size() ? ",\n" : "\n");
        sendj += " }";
    }
    FILE *jf = fopen((base + ".room.json").c_str(), "w");
    if (jf) {
        fprintf(jf, "{\n \"bands\": [\n");
        for (int i = 0; i < 9; i++)
            fprintf(jf, "  {\n   \"hz\": %s,\n   \"q\": %s,\n   \"energy\": %s\n  }%s\n", pyrepr(out[4 + 3 * i]).c_str(),
                    pyrepr(out[5 + 3 * i]).c_str(), pyrepr(out[6 + 3 * i]).c_str(), i < 8 ? "," : "");
        fprintf(jf, " ],\n \"send\": %s,\n \"room_name\": \"%s\",\n %s\n}", sendj.c_str(), E.room.c_str(),
                gs_tail.c_str());
        fclose(jf);
    }
    // THE SOUND CANVAS'S DISPLAY as text beside the render (blockrender's
    // OUT.display.txt, gsdisplay.timeline's lines) -- where the file writes any
    {
        gsd::Display D;
        std::vector<std::string> lines;
        for (int i = 0; i < nv_midi_display_n(midi); i++) {
            int n = 0;
            double t = 0.0;
            const uint8_t *d = nv_midi_display(midi, i, &n, &t);
            gsd::timeline_add(D, d, (size_t)n, t, lines);
        }
        if (!lines.empty()) {
            FILE *df = fopen((base + ".display.txt").c_str(), "w");
            if (df) {
                for (const std::string &l : lines)
                    fprintf(df, "%s\n", l.c_str());
                fclose(df);
            }
        }
    }
    printf("nvrender: %s: %lld partials, %.1f s\n", argv[2], P, N / SR);
    nv_buf_free(rows);
    for (int q = 0; q < 6; q++)
        if (dm[q])
            nv_buf_free(dm[q]);
    for (int q = 0; q < 5; q++)
        free(lobe[q]);
    nv_song_free(song);
    nv_midi_free(midi);
    return 0;
}
