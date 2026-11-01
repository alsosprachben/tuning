// nvrender.cpp -- the native renderer: a General MIDI piano file to the dry
// WAV and room sidecar blockrender writes, with no Python at runtime.
//
//     nvrender EXPORT.nvx IN.mid OUT.wav
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
// Refused (exit 2) -- Python renders them: a file the reader refuses, a note
// no native class plays (drums, other instruments), a pitch wheel or an RPN
// (bend and tuning rows are not ported), a channel's volume or expression
// moving after its first note (its fader row).

#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
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
int nv_midi_gs(void *p);
void nv_midi_note(void *p, int i, int *iv, double *dv);
void nv_midi_cc(void *p, int i, int *iv, double *t);
void nv_midi_song(void *p, void *song, const double *trim);
void *nv_song_new(void);
void nv_song_free(void *s);
void nv_song_tuning(void *s, long long ch, double t, const double *freq);
void nv_song_finish(void *s, double total);
long long nv_prepare(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                     PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind, double scale,
                     double full_db_s, double residual, double beta, long long blk, double total, double ring_floor,
                     double ring_max, double *out, double knee_db, double ln10_20, double xdec_nepers, double SR,
                     void **dm);
int nv_render(void *sv, void *sx, void *sd, long N, int BLK, int nblk, long long P, double *const *d,
              float *const *f, long *const *l, int *const *ii, const float *G, const float *S, const float *BR,
              const double *BC, const float *noRows, const float *sh, long CHUNK, double xdec_nepers, double SR,
              double master_gain, const float *DM, const long *DMO, const long *DMB, const long *DMN, float *L,
              float *R);
void nv_buf_free(void *p);
}

// the export's constants, in native_export.py's order
enum { K_SR, K_BLK, K_CHUNK, K_MASTER, K_RING_FLOOR, K_RING_MAX, K_XDEC, K_REG_SCALE, K_FULL, K_RESIDUAL, K_BETA,
       K_KNEE, K_LN10_20, K_RETRIGGER, K_NYQ_OM, K_SVDC, K_FIXED_TOUCH, K_REFLECT, K_BANDS, K_SH = K_BANDS + 9 };

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

struct Export {
    std::vector<double> k, freq, trim;
    std::vector<std::vector<unsigned char>> classes;
    std::vector<int> cmap, kind, fin;
    std::string room, libs[3];
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
        E.k.resize(nk); E.freq.resize(128); E.trim.resize(512); E.cmap.resize(16384);
        E.kind.resize(NCOLS); E.fin.resize(NCOLS);
        ok = fread(E.k.data(), 8, nk, f) == (size_t)nk && fread(E.freq.data(), 8, 128, f) == 128
             && fread(E.trim.data(), 8, 512, f) == 512;
        for (int i = 0; ok && i < ncls; i++) {
            E.classes.emplace_back(csz);
            ok = fread(E.classes.back().data(), 1, csz, f) == (size_t)csz;
        }
        ok = ok && fread(E.cmap.data(), 4, 16384, f) == 16384 && fread(E.kind.data(), 4, NCOLS, f) == NCOLS
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
    if (argc != 4) {
        fprintf(stderr, "usage: nvrender EXPORT.nvx IN.mid OUT.wav\n");
        return 1;
    }
    Export E;
    if (!read_export(argv[1], E)) {
        fprintf(stderr, "nvrender: cannot read %s (or it is not this build's)\n", argv[1]);
        return 1;
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
    if (nv_midi_n_pws(midi) > 0) {
        fprintf(stderr, "nvrender: refused: a pitch wheel (bend rows are Python's)\n");
        return 2;
    }
    std::vector<double> first(256, INFINITY);
    for (int i = 0, n = nv_midi_n_notes(midi); i < n; i++) {
        int iv[5];
        double dv[5];
        nv_midi_note(midi, i, iv, dv);
        if (dv[0] < first[iv[0] & 255])
            first[iv[0] & 255] = dv[0];
        if (iv[4] || E.cmap[128 * iv[3] + iv[1]] < 0) {
            fprintf(stderr, "nvrender: refused: a note no native voice plays (program %d, key %d%s)\n", iv[3], iv[1],
                    iv[4] ? ", a drum" : "");
            return 2;
        }
    }
    for (int i = 0, n = nv_midi_n_ccs(midi); i < n; i++) {
        int iv[5];
        double t;
        nv_midi_cc(midi, i, iv, &t);
        if (iv[1] == 100 || iv[1] == 101) {
            fprintf(stderr, "nvrender: refused: an RPN (tuning rows are Python's)\n");
            return 2;
        }
        if ((iv[1] == 7 || iv[1] == 11) && t > first[iv[0] & 255]) {
            fprintf(stderr, "nvrender: refused: channel %d's volume moves under its notes (a fader row)\n", iv[0]);
            return 2;
        }
    }
    const double total = nv_midi_total(midi);
    // THE SONG
    void *song = nv_song_new();
    nv_song_tuning(song, -1, 0.0, E.freq.data());
    nv_midi_song(midi, song, E.trim.data() + (nv_midi_gs(midi) ? 256 : 0));
    nv_song_finish(song, total);
    // THE TABLE
    std::vector<const NoteClass *> K(16384, nullptr);
    for (int q = 0; q < 16384; q++)
        if (E.cmap[q] >= 0)
            K[q] = (const NoteClass *)E.classes[E.cmap[q]].data();
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
    long long P = nv_prepare(song, K.data(), &t, nullptr, 0, &rs, &rows, qacc, &az, E.kind.data(),
                             E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK, total,
                             E.k[K_RING_FLOOR], E.k[K_RING_MAX], out, E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR,
                             dm);
    if (P < 0) {
        fprintf(stderr, "nvrender: refused: a note is not the engine's (%lld)\n", P);
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
    float G = 1.0f, S = 1.0f, BRt = 1.0f, noRows[16] = {0}, sh[4];
    double BC = 0.0;
    for (int q = 0; q < 4; q++)
        sh[q] = (float)E.k[K_SH + q];
    std::vector<float> L(N), R(N);
    nv_render(fn[0], fn[1], fn[2], N, (int)BLK, nblk, P, dp, fp, lp, ip, &G, &S, &BRt, &BC, noRows, sh,
              (long)E.k[K_CHUNK], E.k[K_XDEC], SR, E.k[K_MASTER], (const float *)dm[2], (const long *)dm[3],
              (const long *)dm[4], (const long *)dm[5], L.data(), R.data());
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
    FILE *jf = fopen((base + ".room.json").c_str(), "w");
    if (jf) {
        fprintf(jf, "{\n \"bands\": [\n");
        for (int i = 0; i < 9; i++)
            fprintf(jf, "  {\n   \"hz\": %s,\n   \"q\": %s,\n   \"energy\": %s\n  }%s\n", pyrepr(out[4 + 3 * i]).c_str(),
                    pyrepr(out[5 + 3 * i]).c_str(), pyrepr(out[6 + 3 * i]).c_str(), i < 8 ? "," : "");
        fprintf(jf, " ],\n \"send\": {},\n \"room_name\": \"%s\",\n \"tail_gain\": 1.0,\n \"tail_time\": 1.0\n}",
                E.room.c_str());
        fclose(jf);
    }
    printf("nvrender: %s: %lld partials, %.1f s\n", argv[2], P, N / SR);
    nv_buf_free(rows);
    for (int q = 0; q < 6; q++)
        if (dm[q])
            nv_buf_free(dm[q]);
    nv_song_free(song);
    nv_midi_free(midi);
    return 0;
}
