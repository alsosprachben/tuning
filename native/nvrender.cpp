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
#include <dlfcn.h>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "pycompat.h"

extern "C" {
void *nv_midi_read(const uint8_t *buf, long long len, int *err);
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
void nv_midi_note(void *p, int i, int *iv, double *dv);
void nv_midi_cc(void *p, int i, int *iv, double *t);
void nv_midi_song(void *p, void *song, const double *trim);
int nv_midi_note_bsel(void *p, int i);
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
int nv_meend_note(const double *wt, const int *wp, int nw, double on, double off, double nc, const double *sw,
                  int nsw, double rst, double strength, long nblk, int blk, double sr, double *r0, float *BR,
                  double *BC);
int nv_bend_gesture(void *midi, void *song, double bend_range, int ch, long nblk, int blk, double sr, float *BR,
                    double *BC);
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
              const MoogCols *moog);
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
       K_BEND_SEMIS, K_GM_VOL, K_GM_EXPR };

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
        for (int kq : note_ks(i, iv)) {
        int cq = E.cmap[kq];
        if (cq < 0) {
            fprintf(stderr, "nvrender: refused: a note no native voice plays (program %d, key %d%s)\n", iv[3], iv[1],
                    iv[4] ? ", a drum" : banked ? ", a variation" : "");
            return 2;
        }
        const NoteClass *nc = (const NoteClass *)E.classes[cq].data();
        if (banked && nc->meend) {
            fprintf(stderr, "nvrender: refused: a variation that meends (Python's)\n");
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
            if (nv_midi_gs(midi) && mx > 0) {         // (a Sound Canvas file's: its GS chorus device, Python's)
                fprintf(stderr, "nvrender: refused: a GS chorus send (CC93)\n");
                return 2;
            }
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
    nv_song_kits(song, E.kit_f0.data(), E.kit_seat.data());
    nv_song_chokes(song, E.kit_choke.data());
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
    nv_midi_song(midi, song, E.trim.data() + (nv_midi_gs(midi) ? 256 : 0));
    // THE REGISTERED ORGANS (_prep_organ_rows): each melodic channel's, as its
    // programs bring them (ch_progs, uniq_programs), one a family; their stop
    // words' events. A program whose organ the engine does not play: Python's
    std::vector<const OrganSpec *> prog_organ(128, nullptr);
    std::vector<unsigned char> swell(16384, 0);
    for (int p = 0; p < 128; p++)
        if (E.prog_organ[p] >= 0)
            prog_organ[p] = &E.organs[E.prog_organ[p]];
    for (int q = 0; q < 16384; q++)
        if (E.cmap[q] >= 0 && E.cls_organ[E.cmap[q]] >= 0 && E.organs[E.cls_organ[E.cmap[q]]].swells)
            swell[q] = 1;               // (an organ's note: its CC7 its swell, not a fader)
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
            bool var = false;
            for (int pk : uniq[c])
                var = var || pk >= 128;
            for (int pk : uniq[c]) {
                if (pk >= 128)
                    continue;               // (a variation is no organ: variation_tables refuses them)
                const int p = pk;
                if (E.prog_organ[p] == -2) {
                    fprintf(stderr, "nvrender: refused: an organ the engine does not play (program %d)\n", p);
                    return 2;
                }
                const OrganSpec *og = prog_organ[p];
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
    // THE BEND PASSES (native/bend.cpp): each channel's tuning, from its wheel
    // and RPNs, into its notes' f0; a fader moving under its notes, a row --
    // its notes at unity, each riding it (br)
    double btun[256];
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
        int cq = ks.size() == 1 ? E.cmap[ks[0]] : -1;     // (a variation that meends: refused)
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
    bool rows_ = !fch.empty() || !gch.empty() || nw || nsr || nbr_ || !mrows.empty();
    long long P = nv_prepare(song, K.data(), &t, rows_ ? br.data() : nullptr, rows_ ? 1024 : 0, &rs, &rows,
                             qacc, &az, E.kind.data(),
                             E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK, total,
                             E.k[K_RING_FLOOR], E.k[K_RING_MAX], out, E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR,
                             dm, 1);
    if (P == -3) {
        fprintf(stderr, "nvrender: refused: drones Python's (two drone classes, or phrase breaks, on a channel)\n");
        return 2;
    }
    if (P < 0) {
        fprintf(stderr, "nvrender: refused: a note is not the engine's (%lld)\n", P);
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
        if (!nt && !(which == 1 && nv_song_trems(song, nullptr, nullptr, 0)))
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
    // first note's comb (offsets_for), in the order its first note came --
    // before the speaker, which colours the copies too
    {
        std::vector<long long> cch;
        std::vector<double> csend, ccents;
        std::vector<int> cnc;
        std::vector<int> ord(nv_song_n_notes(song));
        for (size_t i = 0; i < ord.size(); i++)
            ord[i] = (int)i;
        auto onset = [&](int i) {
            long long ch;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &ch, iv, dv);
            return dv[0];
        };
        std::stable_sort(ord.begin(), ord.end(), [&](int a, int b) { return onset(a) < onset(b); });
        std::set<long long> seen;
        for (int i : ord) {
            long long ch;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &ch, iv, dv);
            long long mch = nv_song_mix(song, i);
            if (seen.count(mch))
                continue;
            seen.insert(mch);
            int nc = nv_song_ccs(song, mch % 256, 93, nullptr, nullptr, 0);
            if (nc <= 0)
                continue;
            std::vector<double> tt(nc);
            std::vector<int> vv(nc);
            nv_song_ccs(song, mch % 256, 93, tt.data(), vv.data(), nc);
            if (vv[0] <= 0)
                continue;
            int cq = E.cmap[nv_song_kidx(song, i)];
            const NoteClass *nk = cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
            cch.push_back(mch);
            csend.push_back(vv[0] / 127.0);
            cnc.push_back(nk ? nk->n_cho : 0);
            for (int q = 0; q < 8; q++)
                ccents.push_back(nk && q < nk->n_cho ? nk->cho_cents[q] : 0.0);
        }
        if (!cch.empty())
            nv_chorus_expand(&rows, &P, dm, (int)cch.size(), cch.data(), csend.data(), cnc.data(), ccents.data(), SR);
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
    size_t ng = gch.size(), nr = std::max<size_t>(ng + nbr_ + nw + nsr + fch.size() + mrows.size(), 1);
    std::vector<float> BRr(nr * nblk, 1.0f), BLr;
    std::vector<double> BCr(nr * nblk, 0.0);
    for (size_t r = 0; r < ng; r++)
        nv_bend_gesture(midi, song, E.k[K_BEND_SEMIS], gch[r], nblk, (int)BLK, SR, BRr.data() + r * nblk,
                        BCr.data() + r * nblk);
    if (!fch.empty() || nw || nbr_)
        BLr.assign(nr * (nblk + 1), 1.0f);
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
    std::vector<float> L(N), R(N);
    {                                       // THE MASTER VOLUME (_mvol): the mix's and the send's
        int nm = nv_midi_mvol(midi, SR, nullptr, nullptr, 0);
        std::vector<long long> ms(nm > 0 ? nm : 1);
        std::vector<double> mgv(nm > 0 ? nm : 1);
        nv_midi_mvol(midi, SR, ms.data(), mgv.data(), nm);
        nv_render_mvol(ms.data(), mgv.data(), nm);
    }
    nv_render(fn[0], fn[1], fn[2], N, (int)BLK, nblk, P, dp, fp, lp, ip, Gt.data(), St.data(), BRr.data(), BCr.data(),
              BLr.empty() ? nullptr : BLr.data(), noRows, sh,
              (long)E.k[K_CHUNK], E.k[K_XDEC], SR, E.k[K_MASTER], (const float *)dm[2], (const long *)dm[3],
              (const long *)dm[4], (const long *)dm[5], L.data(), R.data(), slo, (const int *)lobe[0],
              (float *const *)(lobe + 1), LANG.empty() ? nullptr : LANG.data(), lgn, nft ? &mc : nullptr);
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
                if (part_cc(c % 256, tt, vv) > 0) {
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
            if (steps.count(part))
                continue;
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
        nv_render(fn[0], fn[1], fn[2], N, (int)BLK, nblk, P, dp, fp2, lp, ip, Gt.data(), St.data(), BRr.data(),
                  BCr.data(), BLr.empty() ? nullptr : BLr.data(), noRows, sh, (long)E.k[K_CHUNK], E.k[K_XDEC], SR,
                  E.k[K_MASTER], (const float *)dm[2], (const long *)dm[3], (const long *)dm[4], (const long *)dm[5],
                  SLb.data(), SRb.data(), slo, (const int *)lobe[0], (float *const *)(lobe + 1),
                  LANG.empty() ? nullptr : LANG.data(), lgn, nft ? &mc : nullptr);
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
        fprintf(jf, " ],\n \"send\": %s,\n \"room_name\": \"%s\",\n \"tail_gain\": 1.0,\n \"tail_time\": 1.0\n}",
                sendj.c_str(), E.room.c_str());
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
