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
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <tuple>
#include <dlfcn.h>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "pycompat.h"

extern "C" {
void *nv_midi_read(const uint8_t *buf, long long len, int *err);
void nv_midi_map_kits(const int *ids, int n);
void nv_midi_map_kits_play(int on);
void nv_song_mapk_base(int base);
int nv_midi_n_dedit(void *p);
void nv_midi_dedit(void *p, int i, int *iv, double *t);
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
void nv_buf_free(void *p);
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

struct Export {
    std::vector<double> k, freq, trim;
    std::vector<std::vector<unsigned char>> classes;
    std::vector<int> cmap, kind, fin;     // cmap: the programs' keys, then the drum sets'
    std::vector<double> kit_f0, kit_seat;
    std::vector<int> mk_ids, mk_map;            // MKIT: the maps' own drum sets, their keys' classes
    std::vector<unsigned long long> kit_choke;
    std::vector<int> kit_skind;
    std::vector<double> kit_spar;
    std::string room, libs[3];
    std::vector<OrganSpec> organs;        // ORGN: the registered organs' tables
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
        for (int i = 0; ok && i < ncls; i++) {
            E.classes.emplace_back(csz);
            ok = fread(E.classes.back().data(), 1, csz, f) == (size_t)csz;
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
        // ORGN: the registered organs' tables, each class's organ, each program's
        char om[4];
        int norg = 0, osz = 0;
        ok = ok && fread(om, 1, 4, f) == 4 && !memcmp(om, "ORGN", 4) && fread(&norg, 4, 1, f) == 1
             && fread(&osz, 4, 1, f) == 1 && osz == (int)sizeof(OrganSpec);
        if (ok) {
            E.organs.resize(norg);
            E.cls_organ.resize(ncls);
            E.prog_organ.resize(128);
            ok = fread(E.organs.data(), sizeof(OrganSpec), norg, f) == (size_t)norg
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
    for (int i = 4; i < argc; i++) {
        if (!strncmp(argv[i], "--tuner=", 8))
            tname = argv[i] + 8;
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
        if (banked && nc->meend && nks.size() != 1) {     // (a layered one: the meend rows read one slot)
            fprintf(stderr, "nvrender: refused: a layered variation that meends (Python's)\n");
            return 2;
        }
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
            bool var = false;               // (a variation that is no organ)
            for (int pk : uniq[c])
                var = var || (pk >= 128 && ent_organs(pk / 128).empty());
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
                    if (!fams.empty()) {
                        fprintf(stderr, "nvrender: refused: two organs on channel %d\n", c);
                        return 2;
                    }
                    if (var) {
                        fprintf(stderr, "nvrender: refused: an organ and a variation on channel %d\n", c);
                        return 2;
                    }
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
    std::set<int> mch;
    for (int i = 0, n = nv_midi_n_notes(midi); i < n; i++) {
        int iv[5];
        double dv[5];
        nv_midi_note(midi, i, iv, dv);
        std::vector<int> ks = note_ks(i, iv);
        int cq = ks.size() == 1 ? E.cmap[ks[0]] : -1;     // (a layered variation that meends: refused)
        if (!iv[4] && cq >= 0 && ((const NoteClass *)E.classes[cq].data())->meend && wheel.count(iv[0]))
            mch.insert(iv[0]);
    }
    for (int c : mch)
        btun[c & 255] = 0.0;
    // the rows: each channel's gesture first (_prep_bend_rows: brow_of, at
    // br[256 + channel]), then the faders' (_LROW, at br[channel])
    std::vector<int> fch, gch;
    std::vector<double> br(512, -1.0);
    for (int c = 0; c < 256; c++)
        if (!mch.count(c) && nv_bend_gesture(midi, song, E.k[K_BEND_SEMIS], c, 0, (int)BLK, SR, nullptr, nullptr)) {
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
    // has one, as the file's notes come, at its first CC94's position (the
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
        if ((k->scanner & 2) && nv_song_first_cc(song, c, 94, &v)) {
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
        std::vector<int> ks = note_ks(i, iv);
        int cq = ks.size() == 1 ? E.cmap[ks[0]] : -1;
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
        if (k && k->init.kind == 6 && cmx_cut.count(c)) {
            fprintf(stderr, "nvrender: refused: a Moog's knobs under a controller matrix's moving cutoff\n");
            return 2;
        }
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
        const double *X = E.k.data() + K_EFX;
        const int code = msb * 128 + lsb;
        bool built = false;
        for (int q = 0; q < (int)X[0] && q < 128; q++)
            built = built || (int)X[1 + q] == code;
        if (!built)
            return fx_memo[pre] = -1;
        const double *D = nullptr;
        const int NK = (int)X[130], W = (int)X[131], DF = 3 + NK, MK = DF + 20;
        for (int q = 0; q < (int)X[129] && q < NV_EFX_NAT; q++)
            if ((int)X[132 + W * q] == code)
                D = X + 132 + W * q;
        auto refuse = [&](const char *why) {
            fprintf(stderr, "nvrender: refused: the insertion effect's %s (type %02X %02X)\n", why, msb, lsb);
            return fx_memo[pre] = -3;
        };
        if (!D)
            return refuse("type");
        const int kind = (int)D[1];
        const bool bass = D[2] != 0.0;
        // (EFX_KEYS's order)
        enum { kLevel, kDrive, kAmpSw, kLowGain, kHiGain, kCmpAtck, kCmpSus, kCmpLevel, kCmpSw, kODSel, kODDrive,
               kODAmpSw, kODSw, kEQL, kEQMF, kEQMQ, kEQMG, kEQH, kODL, kODH, kCFSel, kCFRate, kCFDepth, kCFFb,
               kCFMix, kDlyTime, kDlyFb, kDlyMix, kEHSens, kTPSw, kAzimuth, kSpeed, kTurn, kClockwise, kAttack,
               kSustain, kPostGain, kType, kPreDly, kTime, kHFDamp, kBalance, kGateTime, kLBal, kPreDly1, kPreDly2,
               kPan1, kPan2, kCoarse1, kFine1, kCoarse2, kFine2, kPan, kPCoarse, kPFine, kFeedback, kWahFil,
               kWahMan, kWahPeak, kWahSw, kRate, kDepth, kPhase, kPreFilter, kCutoff, kPreDlyDev, kDepthDev,
               kPanDev, kChoRate, kChoDepth, kTremRate, kTremSep, kModWave, kModRate, kModDepth, kLowFreq,
               kHiFreq, kM1Freq, kM1Q, kM1Gain, kM2Freq, kM2Q, kM2Gain, kBand1, kBand2, kBand3, kBand4, kBand5,
               kBand6, kBand7, kBand8, kWidth, kDlyTmL, kDlyTmR, kFbMode, kPhaseL, kPhaseR, kDlyTmC, kDlyLevC,
               kDlyLevL, kDlyLevR, kDlyTm1, kDlyTm2, kDlyTm3, kDlyTm4, kDlyLev1, kDlyLev2, kDlyLev3, kDlyLev4,
               kModPhase, kManual, kReso, kMix, kFilType, kSens, kPeak, kPolarity, kStepRate, kDriveSw, kVowel,
               kAccel, kLoFiType, kPostFilter, kThreshold, kRatio, kRelease, kEHMix, kTPSel, kTPModWV, kTPModRT,
               kTPModDep, kAWSw, kAWFilter, kAWPeak, kAWMan, kAWDepth, kAWRate, kPHMix, kPHReso, kPHMan, kPHDepth,
               kPHRate };
        auto has = [&](int key) { return D[3 + key] != 0.0; };
        // ...AND ITS CONTROLLERS' (gsefx.controlled): a + or # parameter at
        // "setting value + value from controller x depth (%)/100" of its
        // whole range, clamped and rounded, where its controller has a source
        const bool marked = ctl[0] != 0 || ctl[2] != 0;
        bool choice = false;
        auto controlled = [&](int n, int v) {
            for (int w = 0; w < 2; w++) {
                if ((int)D[MK + w] != n)
                    continue;
                int src = ctl[2 * w];
                if (!src)
                    continue;
                double dep = std::max(-1.0, std::min(1.0, (ctl[2 * w + 1] - 0x40) / 63.0));
                auto it = cvv.find(src);
                int cv = it != cvv.end() ? it->second : (src == 0x61 ? 64 : 0);
                double lo = D[MK + 2 + 2 * w], hi = D[MK + 3 + 2 * w];
                if (lo < 0.0) {
                    choice = true;              // (a choice of codes: not built here)
                    return v;
                }
                double x = (double)v + (hi - lo) * (cv / 127.0) * dep;
                x = std::max(lo, std::min(hi, x));
                return (int)nearbyint(x);       // (round: half to even)
            }
            return v;
        };
        auto g = [&](int key, int d) {      // the file's, the type's, ours -- and its controller's
            int n = (int)D[3 + key];
            if (!n)
                return d;
            int v = p[n] >= 0 ? p[n] : D[DF + n - 1] >= 0.0 ? (int)D[DF + n - 1] : d;
            if (marked && (n == (int)D[MK] || n == (int)D[MK + 1]))
                v = controlled(n, v);
            return v;
        };
        const double *L = X + 132 + NV_EFX_NAT * W;
        const double *T6 = L + 30 + 66, *AZ = T6 + 128, *T1 = AZ + 128, *T8 = T1 + 128;    // (value tables *6, *13, *1, *8)
        const double *T9 = T8 + 128 + 512;      // (*9, past the pans' places: a pre-filter's cutoff)
        const double *T2 = T8 + 128 + NV_EFX_PANS_TO_DEG + 2 * 5, *T3 = T2 + 128, *T4 = T3 + 128;  // (delay times)
        const double *T12 = T4 + 128, *T14 = T12 + 128;     // (a phaser's Manual, Hz; the Humanizer's Accel)
        auto clamp = [](int v) { return v < 0 ? 0 : v > 127 ? 127 : v; };
        auto od_gain = [&](int v, bool ds) {
            double x = clamp(v) / 127.0, lo = ds ? L[2] : L[0], hi = ds ? L[3] : L[1];
            return pow(10.0, (lo + (hi - lo) * x) / 20.0);
        };
        auto gain_db = [](int v) { return (double)std::max(-12, std::min(12, v - 64)); };
        double r[NV_FXN] = {};
        r[21] = -1.0;
        r[33] = 1.0;                            // (a bus's dry and effect levels: the effect alone)
        r[31] = M_PI;                           // (its chorus's right output's LFO phase: GS_TAPS's)
        auto balance = [&](int v, double *dw) { // (gsefx.balance: "D>xE" up to D=E, past it "D x<E")
            v = clamp(v);
            if (v <= 0x40) {
                dw[0] = 1.0;
                dw[1] = std::min(1.0, 2.0 * v / 127.0);
            } else {
                dw[0] = std::min(1.0, 2.0 * (127 - v) / 127.0);
                dw[1] = 1.0;
            }
        };
        r[0] = g(kLevel, 127) / 127.0;
        const double mk = pow(10.0, L[4] / 20.0);
        if (kind == 4 || kind == 6) {
            // THE PART PLACED IN 3D: its angle the type's Azimuth, and 3D
            // Auto's turning at its Speed (turns a second), clockwise +
            double turn = 0.0;
            if (kind == 6 && g(kTurn, 1))           // (AUTO_TURN, AUTO_CLOCKWISE)
                turn = T6[clamp(g(kSpeed, 25))] * (g(kClockwise, 1) ? 1.0 : -1.0);
            r[22] = 1.0;
            r[23] = AZ[clamp(g(kAzimuth, 62))];
            r[24] = turn;
        } else if (kind == 5) {
            // A PART'S OWN BUS, the Compressor (efxbus.make's 'comp'): its
            // threshold from Sustain, ratio 8, attack from Attack, release
            // 150 ms, its makeup Post Gain's 6 dB steps
            double a = g(kAttack, 72) / 127.0;
            double att = 0.001 + 0.049 * a;
            r[25] = 2.0;
            r[26] = -10.0 - 30.0 * g(kSustain, 100) / 127.0;
            r[27] = 8.0;
            r[28] = exp(-1.0 / std::max(1.0, att * SR));
            r[29] = exp(-1.0 / std::max(1.0, 0.15 * SR));
            r[30] = pow(10.0, 6.0 * g(kPostGain, 0) / 20.0);
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else if (kind >= 11 && kind <= 16) {
            // THE CHORUS TYPES (gsefx._chorus): Space D 11, Stereo Chorus 12,
            // Hexa Chorus 13, Tremolo Chorus 14, 3D Chorus 15, Stereo Flanger
            // 16 -- the pre-delay and rate from Roland's tables (*1, *6), the
            // depth as the system chorus's swing (a flanger's an eighth of the
            // system law's, its feedback the comb's depth); two outputs apart by
            // their Phase, or the Hexa Chorus's six voices spread in delay,
            // depth and pan by its Dev parameters, or the 3D Chorus's two past
            // the speakers; a pre-filter's low pass; Balance its share
            const bool fl = kind == 16;
            const int kr = has(kRate) ? kRate : kChoRate, kd = has(kDepth) ? kDepth : kChoDepth;
            double rate = T6[clamp(g(kr, 8))];
            double swing = (g(kd, 64) + 1) / 3.2 / 1000.0 / 2.0 * (fl ? 1.0 / 8.0 : L[7]);
            double pd = T1[clamp(g(kPreDly, 10))];
            double pre = (std::isnan(pd) ? 0.0 : pd) / 1000.0;
            double lpf = 0.0;
            if (has(kPreFilter) && g(kPreFilter, 0) == 1) {     // (the LPF; its HPF is not built)
                double c = T9[clamp(g(kCutoff, 127))];
                lpf = std::isnan(c) ? 0.0 : c;
            }
            r[14] = 1.0;
            r[15] = pre + swing;
            r[16] = rate;
            r[17] = 2.0 * M_PI * rate * swing;
            r[18] = fl ? std::max(-0.98, std::min(0.98, (g(kFeedback, 104) - 64) * 2.0 / 100.0)) : 0.0;
            r[19] = lpf;
            r[20] = 0.0;
            r[21] = g(kBalance, 64) / 127.0;
            r[31] = has(kPhase) ? (2.0 * g(kPhase, (int)(180.0 / 2.0))) * (M_PI / 180.0)    // (math.radians)
                                : 180.0 * (M_PI / 180.0);                                   // (CHORUS_PHASE_DEG)
            if (kind == 13) {                   // (its voices' Devs: Pan, Pre Dly, Depth; the printed defaults)
                r[87] = 1.0;
                r[88] = clamp(g(kPanDev, 16));
                r[89] = g(kPreDlyDev, 5);
                r[90] = g(kDepthDev, 0x40 + 2);
            } else if (kind == 15) {
                r[87] = 2.0;
            }
            if (kind == 14) {                   // ITS TREMOLO (TREMOLO_CHORUS_DEPTH: half), stereo by Trem Sep
                r[55] = 2.0;
                r[56] = T6[clamp(g(kTremRate, 60))];
                r[57] = 0.5;
                r[58] = g(kTremSep, 96) > 0 ? 1.0 : 0.0;
            }
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else if (kind == 17 || kind == 18) {
            // TREMOLO, AUTO PAN: ROLAND'S DEPTH DIPS THE LEVEL (1 - d .. 1); the
            // tremolo pass swings about its carrier, so the part is taken down
            // to the swing's middle and the swing measured from there -- its
            // wave (WAVES, Mod Wave), Auto Pan's the right ear's opposite
            double d = g(kModDepth, 96) / 127.0;
            double mid = 1.0 - 0.5 * d;
            r[0] *= mid;
            r[55] = 1.0;
            r[56] = T6[clamp(g(kModRate, 60))];
            r[57] = 0.5 * d / mid;
            r[58] = kind == 18 ? 1.0 : 0.0;
            r[59] = std::min(4, g(kModWave, 2));
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else if (kind >= 21 && kind <= 26) {
            // THE DELAY TYPES (gsefx._delay): gsdelay taps (time, level, side,
            // period) -- each time through its own value table (*2, *3, *4),
            // its default the type's, else 0 -- the feedback, HF Damp a low
            // pass; the Stereo and Mod Delay's two loops at their own periods,
            // a phase their tap's sign, Fb Mode the ping-pong; the 3 Tap's
            // centre, left and right, the 3D Delay's past the speakers; the 4
            // Tap's across the field (FOUR_TAP_SIDES: the pans' table's 1, 43,
            // 85, 127); Tm Ctrl's one, at its pan -- a silent tap dropped, the
            // effect at its Balance's share over the dry (DRY_FLOOR)
            auto sec = [&](const double *T, int key) {
                double x = T[clamp(g(key, 0))];
                return (std::isnan(x) ? 0.0 : x) / 1000.0;
            };
            double tp[4][4];
            int nt = 0;
            auto tap = [&](double t, double lv, int sd, double per) {
                tp[nt][0] = t; tp[nt][1] = lv; tp[nt][2] = sd; tp[nt][3] = per;
                nt++;
            };
            if (kind == 21 || kind == 22) {
                double tl = sec(T4, kDlyTmL), tr = sec(T4, kDlyTmR);
                tap(tl, g(kPhaseL, 0) ? -1.0 : 1.0, 0, tl);
                tap(tr, g(kPhaseR, 0) ? -1.0 : 1.0, 1, tr);
            } else if (kind == 23 || kind == 26) {
                const double *T = kind == 23 ? T2 : T4;
                double tc = sec(T, kDlyTmC);
                tap(sec(T, kDlyTmC), g(kDlyLevC, 127) / 127.0, 2, tc);      // (TAP_LEVEL)
                tap(sec(T, kDlyTmL), g(kDlyLevL, 127) / 127.0, kind == 23 ? 0 : 300, tc);
                tap(sec(T, kDlyTmR), g(kDlyLevR, 127) / 127.0, kind == 23 ? 1 : 301, tc);
            } else if (kind == 24) {
                static const int FOUR[4] = {101, 143, 185, 227};
                const int kt[4] = {kDlyTm1, kDlyTm2, kDlyTm3, kDlyTm4}, kl[4] = {kDlyLev1, kDlyLev2, kDlyLev3, kDlyLev4};
                double t1 = sec(T2, kDlyTm1);
                for (int j = 0; j < 4; j++)
                    tap(sec(T2, kt[j]), g(kl[j], 127) / 127.0, FOUR[j], t1);
            } else {
                double t = sec(T3, kDlyTime);
                tap(t, 1.0, g(kPan, 64) != 64 ? 100 + clamp(g(kPan, 64)) : 2, t);
            }
            double hf = T8[clamp(g(kHFDamp, 127))];
            double dw[2];
            balance(g(kBalance, 37), dw);
            const double DRY_FLOOR = 1e-3, dk = std::max(dw[0], DRY_FLOOR);
            r[34] = 2.0;
            r[96] = dw[1] / dk;                 // (level: the effect over the dry)
            r[97] = std::max(-0.98, std::min(0.98, (g(kFeedback, 64) - 64) * 2.0 / 100.0));
            r[98] = std::isnan(hf) ? 0.0 : hf;  // (Bypass: none)
            r[99] = tp[0][3];                   // (tc: the first tap's period, a silent one's too)
            int kept = 0;
            for (int j = 0; j < nt; j++) {
                if (tp[j][1] == 0.0)
                    continue;
                double *T = r + 101 + 5 * kept++;
                T[0] = tp[j][0]; T[1] = tp[j][1]; T[2] = tp[j][2]; T[3] = tp[j][3]; T[4] = 1.0;
            }
            r[100] = kept;
            r[121] = (kind == 21 || kind == 22) && g(kFbMode, 0) ? 1.0 : 0.0;
            if (kind == 22) {                   // (the Mod Delay's LFO: Mod Rate *6, efx_swing, Mod Phase)
                r[122] = T6[clamp(g(kModRate, 12))];
                r[123] = (g(kModDepth, 21) + 1) / 3.2 / 1000.0 / 2.0 * L[7];
                r[124] = (2.0 * g(kModPhase, 45)) * (M_PI / 180.0);
            }
            r[0] *= dk;
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else if (kind >= 27 && kind <= 30) {
            // THE MOVING FILTERS (gsefx._filter, efxfilter): the type and its
            // parameters, and this setting's control (r[128]: 1 a sweep --
            // base Hz, octaves, rate, up (NaN: a phaser, about its base), Sens
            // octaves; 2 a flanger's line -- base s, swing s, rate, step rate;
            // 3 the Humanizer's vowel -- which, its glide)
            const double WAH_HZ0 = 200.0, WAH_HZ1 = 4000.0, WAH_Q0 = 0.7, WAH_Q1 = 12.0;
            auto wah_hz = [&](int v) { return WAH_HZ0 * pow(WAH_HZ1 / WAH_HZ0, clamp(v) / 127.0); };
            auto wah_q = [&](int v) { return WAH_Q0 * pow(WAH_Q1 / WAH_Q0, clamp(v) / 127.0); };
            r[50] = 1.0;
            if (kind == 27) {                   // PHASER: four all-passes about its Manual (PHASER_OCT)
                r[51] = 1.0;
                r[52] = g(kMix, 64) / 127.0;
                r[53] = 0.9 * g(kReso, 16) / 127.0;
                r[134] = 4.0;                   // (PHASER_STAGES)
                r[128] = 1.0;
                r[129] = T12[clamp(g(kManual, 36))];
                r[130] = 2.0 * g(kDepth, 64) / 127.0;
                r[131] = T6[clamp(g(kRate, 16))];
                r[132] = NAN;
                r[133] = 0.0;
            } else if (kind == 28) {            // AUTO WAH: up (or down) from its Manual, and by Sens (AUTOWAH_OCT, _SENS_OCT)
                r[51] = g(kFilType, 1) == 0 ? 2.0 : 3.0;
                r[52] = wah_q(g(kPeak, 62));
                r[53] = 1.0;
                r[128] = 1.0;
                r[129] = wah_hz(g(kManual, 68));
                r[130] = 3.0 * g(kDepth, 72) / 127.0;
                r[131] = T6[clamp(g(kRate, 40))];
                r[132] = g(kPolarity, 1) ? 1.0 : 0.0;
                r[133] = 3.0 * g(kSens, 0) / 127.0;
            } else if (kind == 29) {            // STEP FLANGER: a moving comb, its line stepped at Step Rate
                double pd = T1[clamp(g(kPreDly, 10))];
                r[51] = 4.0;
                r[52] = g(kBalance, 64) / 127.0;
                r[53] = std::max(-0.98, std::min(0.98, (g(kFeedback, 79) - 64) * 2.0 / 100.0));
                r[128] = 2.0;
                r[129] = (std::isnan(pd) ? 0.0 : pd) / 1000.0;
                r[130] = (g(kDepth, 95) + 1) / 3.2 / 1000.0 / 2.0 * (1.0 / 8.0);    // (efx_swing, a flanger's)
                r[131] = T6[clamp(g(kRate, 5))];
                r[132] = T6[clamp(g(kStepRate, 54))];
            } else {                            // HUMANIZER: its vowel's formants, gliding at its Accel; its drive
                double acc = T14[clamp(g(kAccel, 64))];
                if (std::isnan(acc) || acc == 0.0)
                    acc = 8.0;                  // (table_value(14, ...) or 8.0)
                r[51] = 5.0;
                r[52] = 0.15;                   // (VOWEL_FLOOR)
                r[53] = 1.5;
                r[128] = 3.0;
                r[129] = std::min(4, g(kVowel, 0));
                r[130] = 0.5 * pow(0.03, acc / 15.0);
                if (g(kDriveSw, 0)) {
                    r[1] = od_gain(g(kDrive, 48), false);
                    r[0] *= mk;
                }
            }
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else if (kind >= 31 && kind <= 33) {
            // THE BUSES (efxbus.make): LO-FI 1 the tone's Lo-Fi bus (its Type
            // a held rate and bits, its Pre and Post Filter one-pole corners,
            // LOFI_*), dry against effect by Balance; LIMITER the Compressor's
            // (its Threshold, Ratio, Release, Post Gain's 6 dB steps, a 1 ms
            // attack); ENHANCER its own: the top octaves above 2 kHz saturated
            // by Sens and mixed back by Mix
            if (kind == 31) {
                static const double RATE[9] = {32000, 22050, 16000, 12000, 11025, 8000, 6000, 5000, 4000};
                static const int BITS[9] = {14, 12, 11, 10, 9, 8, 7, 6, 5};
                static const double FHZ[6] = {0.0, 8000.0, 6000.0, 4000.0, 2500.0, 1500.0};
                const int k = std::max(1, std::min(9, g(kLoFiType, 5) + 1)) - 1;
                const int pre = std::max(1, std::min(6, g(kPreFilter, 1) + 1)) - 1;
                const int post = std::max(1, std::min(6, g(kPostFilter, 1) + 1)) - 1;
                r[25] = 1.0;
                r[26] = SR / RATE[k];
                r[27] = pow(2.0, -(double)(BITS[k] - 1));
                r[28] = FHZ[pre] != 0.0 ? exp(-2.0 * M_PI * FHZ[pre] / SR) : 0.0;
                r[29] = FHZ[post] != 0.0 ? exp(-2.0 * M_PI * FHZ[post] / SR) : 0.0;
                double dw[2];
                balance(g(kBalance, 127), dw);
                r[32] = dw[0];
                r[33] = dw[1];
            } else if (kind == 32) {
                static const double RATIO[4] = {1.5, 2.0, 4.0, 100.0};
                const double rel = 0.01 * pow(100.0, g(kRelease, 16) / 127.0);
                r[25] = 2.0;
                r[26] = -60.0 * (1.0 - g(kThreshold, 85) / 127.0);
                r[27] = RATIO[std::min(3, g(kRatio, 2))];
                r[28] = exp(-1.0 / std::max(1.0, 0.001 * SR));
                r[29] = exp(-1.0 / std::max(1.0, rel * SR));
                r[30] = pow(10.0, 6.0 * g(kPostGain, 0) / 20.0);
            } else {
                r[25] = 5.0;
                r[26] = exp(-2.0 * M_PI * 2000.0 / SR);         // (ENH_HZ)
                r[27] = 1.0 + 15.0 * g(kSens, 64) / 127.0;
                r[28] = g(kMix, 64) / 127.0;
            }
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else if (kind == 19) {
            // STEREO-EQ: its shelves at their chosen corners, two mids
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[8] = L[13 + clamp(g(kM1Freq, 72)) / 8];
            r[9] = L[8 + std::min(4, g(kM1Q, 1))];
            r[10] = gain_db(g(kM1Gain, 64));
            r[11] = gain_db(g(kHiGain, 64));
            r[60] = std::min(1, g(kLowFreq, 0)) ? 400.0 : 200.0;
            r[61] = std::min(1, g(kHiFreq, 0)) ? 8000.0 : 4000.0;
            r[62] = 1.0;
            r[63] = L[13 + clamp(g(kM2Freq, 56)) / 8];
            r[64] = L[8 + std::min(4, g(kM2Q, 1))];
            r[65] = gain_db(g(kM2Gain, 64));
        } else if (kind == 20) {
            // SPECTRUM: a static filter, eq_gain's mids at SPECTRUM_HZ, no shelves
            static const double SPECTRUM_HZ[8] = {250.0, 500.0, 1000.0, 1250.0, 2000.0, 3150.0, 4000.0, 8000.0};
            r[6] = 1.0;
            r[60] = 400.0;
            r[61] = 4000.0;
            r[62] = 8.0;
            const double q = L[8 + std::min(4, g(kWidth, 2))];
            for (int j = 0; j < 8; j++) {
                r[63 + 3 * j] = SPECTRUM_HZ[j];
                r[64 + 3 * j] = q;
                r[65 + 3 * j] = gain_db(g(kBand1 + j, 64));
            }
        } else if (kind == 9 || kind == 10) {
            // THE PITCH SHIFTERS (gsdelay taps that move each repeat's pitch):
            // 2 Pitch Shifter's two voices at their own pitch, delay and pan,
            // L.Bal between them, no feedback; Fb P.Shifter's one, spiralling
            // by its ratio round its feedback -- the effect at its Balance's
            // share over the dry (DRY_FLOOR), in the GS delay's place, sent whole
            auto pre = [&](int key, int d) {    // (table *1, ms -> s; Bypass 0)
                double v = T1[clamp(g(key, d))];
                return (std::isnan(v) ? 0.0 : v) / 1000.0;
            };
            auto side = [&](int key) { return g(key, 64) != 64 ? 100.0 + clamp(g(key, 64)) : 2.0; };
            auto semis = [&](int co, int fi) {  // (gsefx.semitones)
                return pow(2.0, (co - 0x40) / 12.0 + (fi - 0x40) * 2.0 / 1200.0);
            };
            double dw[2], *T = r + 40;
            int nt;
            double fb;
            if (kind == 9) {
                double lab[2];
                balance(g(kLBal, 64), lab);
                const double t1[5] = {pre(kPreDly1, 0), lab[0], side(kPan1), 1.0, semis(g(kCoarse1, 71), g(kFine1, 62))};
                const double t2[5] = {pre(kPreDly2, 0), lab[1], side(kPan2), 1.0, semis(g(kCoarse2, 59), g(kFine2, 66))};
                std::copy(t1, t1 + 5, T);
                std::copy(t2, t2 + 5, T + 5);
                nt = 2;
                fb = 0.0;
            } else {
                double t = pre(kPreDly, 95);
                const double t1[5] = {t, 1.0, side(kPan), t, semis(g(kPCoarse, 71), g(kPFine, 64))};
                std::copy(t1, t1 + 5, T);
                nt = 1;
                fb = std::max(-0.98, std::min(0.98, (g(kFeedback, 84) - 64) * 2.0 / 100.0));
            }
            balance(g(kBalance, 64), dw);
            const double DRY_FLOOR = 1e-3, dk = std::max(dw[0], DRY_FLOOR);
            r[34] = 1.0;
            r[35] = dw[1] / dk;                 // (level: the effect over the dry)
            r[36] = fb;
            r[37] = 0.0;                        // (no line filter)
            r[38] = std::max(T[0], 1e-3);       // (tc: the first tap's time)
            r[39] = nt;
            r[0] *= dk;
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else if (kind == 7 || kind == 8) {
            // A PART'S OWN BUS, a reverb (efxbus.Reverb, GateReverb: native/efxrev.c's):
            // Reverb's type, pre-delay, Time and HF damp; Gate Reverb's type,
            // pre-delay and gate time (5 ms a step, 5-500 ms); dry against effect by Balance
            r[25] = kind == 7 ? 3.0 : 4.0;
            r[26] = g(kType, 0);
            double pd = T1[clamp(g(kPreDly, kind == 7 ? 112 : 5))];
            r[27] = std::isnan(pd) ? 0.0 : pd;
            if (kind == 7) {
                r[28] = g(kTime, 120);
                r[29] = T8[clamp(g(kHFDamp, 104))];     // (NaN: Bypass, 20 kHz)
            } else {
                r[28] = 5.0 * (std::min(99, g(kGateTime, 12)) + 1);
            }
            balance(g(kBalance, kind == 7 ? 64 : 32), r + 32);
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else if (kind == 1 || kind == 2) {
            r[1] = od_gain(g(kDrive, 48), kind == 2);
            r[0] *= mk;
            if (g(kAmpSw, 1))
                r[2] = 1.0;
            r[6] = 1.0;
            r[7] = gain_db(g(kLowGain, 64));
            r[11] = gain_db(g(kHiGain, 64));
        } else {
            if (has(kCmpSw) && g(kCmpSw, 1)) {
                double sus = g(kCmpSus, 64) / 127.0;
                r[3] = 1.0 / (1.0 + 3.0 * sus);
                r[4] = g(kCmpLevel, 64) / 64.0;
                r[5] = L[5] * g(kCmpAtck, 70) / 127000.0;
            }
            if (has(kODDrive) && g(kODSw, 1)) {
                r[1] = od_gain(g(kODDrive, 48), g(kODSel, 0) != 0);
                r[0] *= mk;
                if (g(kODAmpSw, 1))
                    r[2] = bass ? 2.0 : 1.0;
            }
            if (has(kEQL)) {
                r[6] = 1.0;
                r[7] = gain_db(g(kEQL, 64));
                r[8] = L[13 + clamp(g(kEQMF, 64)) / 8];
                r[9] = L[8 + std::min(4, g(kEQMQ, 1))];
                r[10] = gain_db(g(kEQMG, 64));
                r[11] = gain_db(g(kEQH, 64));
            } else if (has(kODL)) {
                r[6] = 1.0;
                r[7] = gain_db(g(kODL, 64));
                r[11] = gain_db(g(kODH, 64));
            }
            if (has(kCFRate)) {
                // (cf_device: rate2, efx_swing, feedback; a chorus 10 ms, a flanger 1 ms)
                bool fl = g(kCFSel, 0) != 0;
                double rate = 0.05 * (clamp(g(kCFRate, 8)) + 1);
                double swing = (g(kCFDepth, 40) + 1) / 3.2 / 1000.0 / 2.0 * (fl ? 1.0 / 8.0 : L[7]);
                r[14] = 1.0;
                r[15] = (fl ? 0.001 : 0.010) + swing;
                r[16] = rate;
                r[17] = 2.0 * M_PI * rate * swing;
                r[18] = std::max(-0.98, std::min(0.98, (g(kCFFb, 64) - 64) * 2.0 / 100.0));
                r[19] = 0.0;
                r[20] = g(kCFMix, 0) / 127.0;
            }
            // CLEAN GT MULTI 2's AUTO WAH (unprinted: on, up), the RHODES MULTI's
            // PHASER (efxfilter, gsefx._filter: Rate2 their rates)
            auto rate2 = [&](int v) { return 0.05 * (clamp(v) + 1); };
            if (has(kAWMan) && g(kAWSw, 1)) {
                r[50] = 1.0;
                r[51] = g(kAWFilter, 1) == 0 ? 2.0 : 3.0;
                r[52] = 0.7 * pow(12.0 / 0.7, clamp(g(kAWPeak, 40)) / 127.0);     // (wah_q)
                r[53] = 1.0;
                r[128] = 1.0;
                r[129] = 200.0 * pow(4000.0 / 200.0, clamp(g(kAWMan, 55)) / 127.0); // (wah_hz)
                r[130] = 3.0 * g(kAWDepth, 80) / 127.0;
                r[131] = rate2(g(kAWRate, 29));
                r[132] = 1.0;
                r[133] = 0.0;
            } else if (has(kPHMan)) {
                const double *T12 = T8 + 128 + NV_EFX_PANS_TO_DEG + 2 * 5 + 3 * 128;
                r[50] = 1.0;
                r[51] = 1.0;
                r[52] = g(kPHMix, 64) / 127.0;
                r[53] = 0.9 * g(kPHReso, 16) / 127.0;
                r[134] = 4.0;                   // (PHASER_STAGES)
                r[128] = 1.0;
                r[129] = T12[clamp(g(kPHMan, 36))];
                r[130] = 2.0 * g(kPHDepth, 32) / 127.0;
                r[131] = rate2(g(kPHRate, 16));
                r[132] = NAN;
                r[133] = 0.0;
            }
            if (has(kEHSens)) {                 // ...its Enhancer: the part's bus (efxbus.Enhancer)
                r[25] = 5.0;
                r[26] = exp(-2.0 * M_PI * 2000.0 / SR);
                r[27] = 1.0 + 15.0 * g(kEHSens, 64) / 127.0;
                r[28] = g(kEHMix, 64) / 127.0;
            }
            if (has(kTPSw) && g(kTPSw, 1)) {    // ...its Tremolo/Pan (unprinted: on, Trem, the sine): the Tremolo type's
                double d = g(kTPModDep, 64) / 127.0;
                double mid = 1.0 - 0.5 * d;
                r[0] *= mid;
                r[55] = 1.0;
                r[56] = rate2(g(kTPModRT, 60));
                r[57] = 0.5 * d / mid;
                r[58] = g(kTPSel, 0) ? 1.0 : 0.0;
                r[59] = std::min(4, g(kTPModWV, 2));
            }
            if (has(kWahMan) && g(kWahSw, 1)) {
                // GTR MULTI 3's WAH (efxfilter): its pedal held where Wah Man
                // puts it, a band or low pass by Wah Fil, Peak its Q (WAH_HZ, WAH_Q)
                r[50] = 1.0;
                r[51] = g(kWahFil, 1) == 0 ? 2.0 : 3.0;
                r[52] = 0.7 * pow(12.0 / 0.7, clamp(g(kWahPeak, 10)) / 127.0);
                r[53] = 1.0;
                r[54] = 200.0 * pow(4000.0 / 200.0, clamp(g(kWahMan, 60)) / 127.0);
            }
            if (has(kDlyTime)) {
                // THE MULTI's OWN DELAY, as the GS delay's repeats: one tap, 0-635
                // ms (5 ms a step), its feedback 0-127, its mix
                int t = g(kDlyTime, 60), f = g(kDlyFb, 32), x = g(kDlyMix, 0);
                if (x) {
                    r[34] = 1.0;
                    r[35] = x / 127.0;
                    r[36] = f / 128.0;
                    r[37] = 0.0;
                    r[38] = t * 0.005;
                    r[39] = 1.0;
                    const double t1[5] = {t * 0.005, 1.0, 2.0, t * 0.005, 1.0};
                    std::copy(t1, t1 + 5, r + 40);
                }
            }
        }
        if (choice)
            return refuse("controller on a choice");
        r[12] = snd[0];
        r[13] = snd[2];
        int idx = (int)(fxch.size() / NV_FXN);
        fxch.insert(fxch.end(), r, r + NV_FXN);
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
            }
        }
        nv_song_fx(song, (int)(fxch.size() / NV_FXN), fxch.data(), nn, note_fx.data(), fx_first.data(),
                   fx_cab[0], fx_cab[1]);
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
    struct SirRow {
        long long ch;
        std::vector<float> r, l;
        std::vector<double> c;
    };
    std::vector<SirRow> sir;
    const int sbase = (int)(gch.size() + nbr_ + nw + nsr + fch.size() + mrows.size());
    {
        auto pmx = [](double a, double b) { return b > a ? b : a; };    // (Python's max and min)
        auto pmn = [](double a, double b) { return b < a ? b : a; };
        const double A = 0.723, Bc = 0.0908, UK = 0.452, NE = 3.8;     // siren.FIRE
        const double W = (A + Bc) / A, FLOOR = pow(10.0, -60.0 / 20.0);
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
        std::vector<std::pair<long long, int>> order;
        std::map<std::pair<long long, int>, std::vector<std::tuple<double, double, int>>> byk;
        for (int i = 0, n = nv_song_n_notes(song); i < n; i++) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            int q = nv_song_kidx(song, i);
            const NoteClass *k = (q >= 0 && q < (int)K.size()) ? K[q] : nullptr;
            if (!k || k->siren != 1)
                continue;
            auto key = std::make_pair(c, iv[0]);
            if (!byk.count(key))
                order.push_back(key);
            byk[key].push_back(std::make_tuple(dv[0], dv[1], i));
        }
        for (const auto &key : order) {
            auto &ns = byk[key];
            std::stable_sort(ns.begin(), ns.end(), [](const std::tuple<double, double, int> &a,
                                                      const std::tuple<double, double, int> &b) {
                return std::get<0>(a) < std::get<0>(b) || (std::get<0>(a) == std::get<0>(b) && std::get<1>(a) < std::get<1>(b));
            });
            double u = 0.0, tprev = NAN;
            for (size_t j = 0; j < ns.size(); j++) {
                double on = std::get<0>(ns[j]), of = std::get<1>(ns[j]);
                const NoteClass *k = K[nv_song_kidx(song, std::get<2>(ns[j]))];
                if (!std::isnan(tprev) && on > tprev)
                    u *= exp(-Bc * (on - tprev));           // (Rotor.coast)
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
                    double p = tm < drive_end ? 1.0 : 0.0;
                    double l0 = level(u);
                    double rr = mean_over(u, p, bdt);
                    u = step(u, p, bdt);
                    double l1 = level(u);
                    r.push_back(rr);
                    lv.push_back(l0);
                    kb++;
                    if (tb >= drive_end && l1 <= FLOOR) {
                        end = kb * bdt;
                        break;
                    }
                }
                lv.push_back(level(u));
                tprev = pmn(end, cap);
                SirRow row;
                row.ch = key.first;
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
                nv_song_siren(song, key.first, key.second, on, (double)(sbase + (int)sir.size()), tprev);
                sir.push_back(std::move(row));
            }
        }
    }
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
    bool rows_ = !fch.empty() || !gch.empty() || nw || nsr || nbr_ || !mrows.empty() || !sir.empty() || !trows.empty();
    nv_gsd_place_reset();                       // (blockrender's _GSD_PLACE: the render's)
    long long P = nv_prepare(song, K.data(), &t, rows_ ? br.data() : nullptr, rows_ ? 1024 : 0, &rs, &rows,
                             qacc, &az, E.kind.data(),
                             E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK, total,
                             E.k[K_RING_FLOOR], E.k[K_RING_MAX], out, E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR,
                             dm, 1);
    if (P == -3) {
        fprintf(stderr, "nvrender: refused: drones Python's (two drone classes, or phrase breaks, on a channel)\n");
        return 2;
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
    // THE VALVE AMPLIFIERS (_prep_amplifier, tubeamp.expand): each channel's
    // drive its voice's -- times CC1's first (4 x cc/127) where the voice is
    // not on a rotor -- its products appended, before the speaker sees them
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
            aref.push_back(ref);
            aimb.push_back(imb);
            int v;
            if (!rotor && nv_song_first_cc(song, c % 256, 1, &v))     // (the part's: gsefx.part_of)
                drv *= 4.0 * v / 127.0;
            ach.push_back(c);
            adr.push_back(drv);
        }
        if (!ach.empty())
            nv_amp_expand(&rows, &P, dm, (int)ach.size(), ach.data(), adr.data(), aref.data(), aimb.data(), SR);
    }
    // THE CLAVINET's TONE ROCKERS (_prep_clav_rockers): after the valve, before the tremolos
    nv_clav_pass(song, rows, P);
    // THE ORGANS' TREMOLOS (_prep_tremolo, after the render's length is
    // known): a Tremolo stop's on the notes struck with it drawn, then the
    // wheel's on its channels' rows, the stop's sidebands among them
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
                }
            }
        }
        std::vector<char> mask;
        if (which == 0) {
            int nr = nv_song_n_htrem_rows(song, nullptr, 0);
            if (!nr)
                continue;
            std::vector<long long> ab(2 * nr);
            nv_song_n_htrem_rows(song, ab.data(), nr);
            mask.assign(P, 0);
            for (int q = 0; q < nr; q++)
                for (long long r = ab[2 * q]; r < ab[2 * q + 1] && r < P; r++)
                    mask[r] = 1;
        }
        tremolo_expand(&rows, &P, dm, chans, which == 0 ? &mask : nullptr, SR);
    }
    // THE SCANNERS (_prep_scanner, scanner.expand): each channel's partials
    // on their band rows, the chorus's dry share and copies, tier B's copies
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
            if (seen.count(mch))
                continue;
            auto cfi = fx_cfn.find(mch);
            const bool cf = cfi != fx_cfn.end();
            if (cf && rank[i] >= rank[cfi->second]) {
                seen.insert(mch);
                push_cf(mch);
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
        if (!cch.empty())
            nv_chorus_expand(&rows, &P, dm, (int)cch.size(), cch.data(), csend.data(), cnc.data(), ccents.data(),
                             ckind.data(), cgsp.data(), SR);
    }
    // THE INSERTION EFFECTS' EQ (_prep_insertion_eq, gsefx.eq_gain): every
    // row of an effect's mix channel, the valve's products and the copies
    // included, at its frequency -- shelves at 400 Hz and 4 kHz, a peaking
    // mid (the table's float64 still: the cast is the render's last)
    if (!efx_eq.empty()) {
        const int cM = col("mch"), cF = col("nf");
        const int cA[3] = {col("aL"), col("aR"), col("aM")};
        for (long long r = 0; r < P; r++) {
            double *row = rows + NCOLS * r;
            auto it = efx_eq.find((long long)row[cM]);
            if (it == efx_eq.end())
                continue;
            const auto &e = it->second;
            double f = row[cF];
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
            for (int c : cA)
                row[c] = row[c] * g;
        }
    }
    // THE SPEAKER CABINETS (_prep_cabinet, cabinet.expand): every row on a
    // cabinet's channel through its response at the row's frequency, after
    // the amplifier, before the rotors
    nv_cabinet_pass(song, rows, P);
    // THE ROTATING SPEAKERS (_prep_rotating_speaker, leslie.expand): each
    // Leslie channel's half-moon from its CC1s (leslie.zone), on its default
    // speed from 0 where the first is later; the cabinet, the crossover's
    // copies, the Doppler, each rotor row's lobe
    std::vector<long long> lch;
    std::vector<int> lnreq;
    std::vector<double> lreq;
    void *lobe[5] = {nullptr};
    const double *LES = E.les.data();
    for (int k = 0, nl = nv_song_leslie(song, -1, nullptr); k < nl; k++) {
        long long c;
        int kind = nv_song_leslie(song, k, &c);
        int nc = nv_song_ccs(song, c % 256, 1, nullptr, nullptr, 0);     // (the part's CC1: gsefx.part_of)
        std::vector<double> ct(nc);
        std::vector<int> cv(nc);
        nv_song_ccs(song, c % 256, 1, ct.data(), cv.data(), nc);
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
    }
    if (!lch.empty() && nv_leslie_expand(&rows, &P, dm, (int)lch.size(), lch.data(), lnreq.data(), lreq.data(), SR,
                                         LES, lobe, nullptr, nullptr) < 0) {
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
    size_t ng = gch.size(), nr = std::max<size_t>(ng + nbr_ + nw + nsr + fch.size() + mrows.size() + sir.size()
                                                  + trows.size(), 1);
    std::vector<float> BRr(nr * nblk, 1.0f), BLr;
    std::vector<double> BCr(nr * nblk, 0.0);
    for (size_t r = 0; r < ng; r++)
        nv_bend_gesture(midi, song, E.k[K_BEND_SEMIS], gch[r], nblk, (int)BLK, SR, BRr.data() + r * nblk,
                        BCr.data() + r * nblk);
    if (!fch.empty() || nw || nbr_ || !sir.empty() || !trows.empty())
        BLr.assign(nr * (nblk + 1), 1.0f);
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
            for (size_t q = 0; q < sir.size(); q++)     // ...and its sirens' levels, under it
                if (sir[q].ch == fch[r]) {
                    float *bl = BLr.data() + ((size_t)sbase + q) * (nblk + 1);
                    for (long e = 0; e <= nblk; e++)
                        bl[e] = bl[e] * Lf[e];
                }
        }
    }
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
        lgn = nv_leslie_angles((int)lch.size(), lnreq.data(), lreq.data(), N, SR, (int)BLK, LES, nullptr);
        LANG.resize((size_t)2 * lch.size() * lgn);
        nv_leslie_angles((int)lch.size(), lnreq.data(), lreq.data(), N, SR, (int)BLK, LES, LANG.data());
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
                const double *fc = fxch.data() + (size_t)NV_FXN * note_fx[i];
                if (!fx_first[i] || fc[50] == 0.0)
                    continue;
                FxFlt F;
                for (double t : fx_ts) {
                    int pre = fx_prefix(t), cq = fx_on(m % 256, pre) ? fx_chain(pre) : -1;
                    if (cq == -3)
                        return 2;
                    const double *sc = cq >= 0 ? fxch.data() + (size_t)NV_FXN * cq : nullptr;
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
                fch_.push_back(m);
                fk_.push_back(nullptr);
                fpart_.push_back(c);
                ff_.push_back(F);
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
                nfr += !fk_[q] && !ff_[q].ctl.empty() && ff_[q].ctl[0][0] == 3.0 ? 3 : 1;
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
        for (int r = 0; r < nft && (mpon || mkon); r++) {
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
    };
    std::vector<BusDef> buses;
    std::vector<unsigned char> busrow, rest;
    // A PART'S BUS over the file (gsefx.bus_setup, the file's insertion
    // effect): each part a 'part' event names, in order, its processor the
    // first chain with a bus it is on, on wherever its chain has one -- these
    // first (_BUS_CH's order), then the tones' own
    std::vector<std::array<double, 12>> pbus_p;
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
            std::array<double, 12> bp = {};
            for (int q = 0; q < 5; q++)
                bp[q] = first[26 + q];
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
    auto render_mix = [&](float *const *fpX, float *oL, float *oR) {
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
    std::vector<float> L(N), R(N);
    {                                       // THE MASTER VOLUME (_mvol): the mix's and the send's
        int nm = nv_midi_mvol(midi, SR, nullptr, nullptr, 0);
        std::vector<long long> ms(nm > 0 ? nm : 1);
        std::vector<double> mgv(nm > 0 ? nm : 1);
        nv_midi_mvol(midi, SR, ms.data(), mgv.data(), nm);
        nv_render_mvol(ms.data(), mgv.data(), nm);
    }
    render_mix(fp, L.data(), R.data());
    if (!write_wav(argv[3], L.data(), R.data(), N, (int)SR)) {
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
                if (seen.count(c))
                    continue;
                std::vector<double> tt;
                std::vector<int> vv;
                int cq = E.cmap[nv_song_kidx(song, i)];
                const NoteClass *nk = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
                const int nfx = note_fx[i];
                if (efx_send.count(c) && (nfx >= 0 || (nfx == -1 && nk && nk->efx_set))) {
                    rsend.emplace_back(c, efx_send[c]);         // (its insertion effect's send: _REVERB_CH.setdefault)
                    seen.insert(c);
                } else if (part_cc(c % 256, tt, vv) > 0) {
                    rsend.emplace_back(c, vv[0] / 40.0);
                    seen.insert(c);
                } else if (nk && nk->rd_set) {
                    rsend.emplace_back(c, nk->reverb_dist);      // (a voice's own distance: the gunshot's)
                    seen.insert(c);
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
        std::vector<float> SLb(N), SRb(N);
        render_mix(fp2, SLb.data(), SRb.data());
        if (!write_wav((base + ".send.wav").c_str(), SLb.data(), SRb.data(), N, (int)SR)) {
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
