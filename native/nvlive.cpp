// nvlive.cpp -- the native live piano: a MIDI keyboard in, audio out, no
// Python at runtime.
//
//     nvlive EXPORT.nvx [--program=N [--drums]] [--midi=/dev/snd/midiCxDy] [--device=default] [--latency-ms=10]
//                       [--cpu | --gpu[=cl|c]] [--no-pipeline] [--slots=N]
//                       [--drum-set=P | --no-drums] [--split=N [--split-channel=C] [--split-transpose=T]]
//                       [--no-register] [--pedal-key=N] [--press-db=DB] [--gpu[=cl|c]] [--gpu-min=N]
//                       [--no-rt] [--rt-prio=N] [--reg-sync] [--no-governor] [--dry] [--no-panel]
//                       [--tuner=NAME [--a=HZ | --c=HZ]]
//     nvlive EXPORT.nvx --test IN.mid OUT.wav [--program=N] [--seconds=S] [--no-register] [--pedal-key=N]
//                       [--rt] [--reg-async] [--govern]
//
// EXPORT.nvx is examples/native_export.py --live's. At start the part's
// templates are built (live.Patch.warm: every key 21-96 at each velocity
// bucket, natively), then live's callback runs block by block, 128 samples
// at 48 kHz: the block's MIDI applied at its start, the sweep, the reap,
// the render (native/slab.cpp: bit for bit live.Live's on the CPU), out to
// ALSA. MIDI is read raw from the keyboard's device file; ALSA's PCM is
// loaded at run time (libasound.so.2), so nothing needs its headers.
//
// --test: no devices. IN.mid's notes and controllers (native/midi.cpp, in
// message order) each applied at the start of the block its time falls in,
// each block's output (live's callback: the render, the room, the limiter)
// written to OUT.wav as float32 -- what examples/nvlive_check.py compares
// with live.Live fed the same events.
//
// THE REGISTER (the free strings answering, live's _reg_*) when the export
// has the program's (its LREG section), unless --no-register. Playing, its
// jobs are answered on a thread of their own, off the audio thread, and
// placed when ready -- as live's worker process does (--reg-sync: answered
// as they are sent, in the block); --test answers them in step, as the
// checks do, so its output is the same every run.
//
// REAL-TIME when playing (live's rtsched, its default): the audio thread
// SCHED_RR 18, directly or through rtkit, guarded against a runaway block
// (--no-rt or TUNING_RT=0: not). On Ctrl-C it reports its blocks over
// budget and ALSA's underruns.
//
// THE DAMPERS IN BETWEEN (live._damp_block): a pedal value in damper.py's
// band takes a pedalled key down by its level, through synth_voice_damp.
// THE ROUTES (live.Route): the session's, from the export, ahead of the
// part (slab.cpp's Router) -- and --pedal-key=N, MIDI key N as the sustain
// pedal, pushed into to lower the dampers: held, CC64 127; channel
// aftertouch while it is held, 127 - pressure; up, 0.
//
// THE GPU, by default (live's --gpu; --cpu: none): live.GpuRenderer's
// block -- its setup on the CPU (voice_block, from the export's LGPU
// builds), the samples on OpenCL (native/gpu.cpp, gpukernel.cl) -- for a
// block with 100 busy slots or more (--gpu-min; live's GPU_MIN is 1000, set
// for Python's costs). PIPELINED on OpenCL (live's TUNING_GPU_PIPELINE;
// --no-pipeline: not): every block a block late, the CPU's setup of the
// next while the GPU renders this one. --gpu=c runs the samples through the
// C reference (voice_samples) instead, to check the setup without a GPU.
//
// THE SLAB: --slots (65536, live's capacity: a vibraslap's strike is 16524
// rows).
//
// PRESSURE (channel aftertouch): the notes on its channel lifted by the
// export's press_db (tonelib.PRESS_DB; --press-db=DB for Ben's session's) at
// full, as live's Slab.press does a piano (no tilt: effort_tilt 0).
//
// THE GOVERNOR when playing (live's; --no-governor: none): when blocks run
// over 95% of their time (the second smallest of the last four), the
// highest tenth of what sounds is faded out over 5 ms; --test takes
// --govern to time it, its output then the machine's.
//
// THE WHEELS: the pitch wheel over GM's 2 semitones (live._repitch); the mod
// wheel on a honky-tonk picks its detune, and on the other pianos does
// nothing, as live's (a hammered string takes no vibrato).
//
// AFTER THE RENDER, as live's callback: the room's late tail on the send
// (the export's room, live's convolver; --dry: none) and the soft limiter.
// The export takes the session's room, master level, headroom, pressure,
// knee and wheel range, as live starts.
//
// THE RPNs as live reads them: the bend range, fine and coarse tuning (the
// notes sounding moved), the mod range; CC121; sostenuto (CC66).
//
// ALL SOUND OFF, ALL NOTES OFF and the channel modes (CC120, 123, 124-127):
// MONO (126) one voice a channel, handed over to each new key and back to
// the last one held, POLY (127) as many as are played.
//
// PORTAMENTO (CC5, 65, 84) is ignored, as live ignores it on a piano: a
// glide is a voice's mechanism (live._glide), and no piano class has one.
//
// THE PANEL (native/panel.h), playing on a terminal (--no-panel: none, and
// Ctrl-C to stop): live's for this piano -- the globals, the controls and
// routes (added and taken away here, kept beside the export in
// EXPORT.nvx.routes and read back next time), the output's meters, panic.
// The audio runs on its own thread; the panel's changes are done between
// two blocks.

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <functional>
#include <sched.h>
#include <spawn.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <mutex>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

#include "panel.h"
#include "pycompat.h"

extern "C" {
void *nv_midi_read(const uint8_t *buf, long long len, int *err);
void nv_midi_free(void *p);
double nv_midi_total(void *p);
int nv_midi_n_events(void *p);
void nv_midi_event(void *p, int i, int *iv, double *t);
void *nv_tcache_new(const NoteClass *const *K, const NoteIn *tmpl, const double *freq, const double *trim,
                    const int *kind, const int *fin, double scale, double full_db_s, double residual, double beta,
                    long long blk, double ring_floor, double ring_max, double knee_db, double ln10_20,
                    double xdec_nepers, double SR);
long nv_tcache_warm(void *h, int program, int lo, int hi, int nb, const int *speeds, int nsp);
void nv_tcache_kits(void *h, const double *f0, const double *seat, const unsigned long long *choke,
                    const int *skind, const double *spar, double oneshot_floor_db);
void nv_lp_drums(void *h, int program, const unsigned long long *choke);
void nv_lp_program(void *h, int program);
void nv_lp_toggle_stop(void *h, int rank, long long n0);
int nv_lp_drawn(void *h, char *out, int cap);
void *nv_lp_new(void *cache, long long pid, double level_db, int nbuckets, int speed, int damper_pedal,
                int soft_drop, int soft_top, double rate, double retrigger, long cap, double headroom,
                const double *pan_tab, double pan_beta);
void nv_lp_event(void *h, int type, int ch, int a, int b);
void nv_lp_block(void *h, long long n0, long long blk);
void nv_lp_render(void *h, long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx,
                  void *sd, long long blk, double master_gain);
void nv_lp_damper(void *h, double full_db_s, double residual, double knee_db, double beta, double ln10_20);
void nv_lp_press_db(void *h, double db);
void nv_lp_detune_wheel(void *h, int on);
void nv_lp_leslie(void *h, const double *L, int n);
void nv_lp_scan(void *h, const double *X, long n);
void nv_lp_scan_async(void *h);
void nv_lp_amp_async(void *h);
void nv_tcache_leslie(void *h, const double *L, int n);
int nv_tuning_table(const char *name, int ref_note, double ref_hz, double *out, int *have);
void nv_lp_room(void *h, void *cn, void *cp, void *cf, const float *ir, long n, const float *mir, long m, int frames);
void nv_lp_post(void *h, double thresh, double bend_range, double mod_cents);
void nv_lp_output(void *h, long long n0, long frames, float *L, float *R, void *sv, void *sx, void *sd,
                  long long blk, double master_gain);
void *nv_rt_new();
void nv_rt_add(void *h, int src, int arg, int dst, int keep, int channel, int latch, int press);
int nv_rt_feed(void *h, int type, int ch, int a, int b, int *out, int cap);
void nv_lp_gpu(void *h, void *vb, void *vbd, void *vds, void *vs, void *vz, void *cl, long gpu_min, int nthr);
void nv_lp_pipeline(void *h, int on);
int nv_lp_add_patch(void *h, void *cache, long long pid, double level_db, int nbuckets, int speed, int damper_pedal,
                    int soft_drop, int soft_top, int drums, int program, const unsigned long long *choke, int channel,
                    unsigned excl, int lo, int hi, int transpose);
void nv_lp_patch_range(void *h, int i, int channel, unsigned excl, int lo, int hi, int transpose);
int nv_lp_on_gpu(void *h);
void nv_lp_gpu_ms(void *h, double *out);
void nv_lp_reg_async(void *h);
void nv_lp_set(void *h, int what, double v);
void nv_lp_stats(void *h, double *out);
void nv_lp_panic(void *h, long long n0);
void nv_rt_del(void *h, int i);
long nv_lp_govern(void *h, double ms, double budget_ms, long long n);
long nv_lp_partials_shed(void *h);
void *nv_cl_new(const char *dir, const int *sizes, char *err, int errlen);
void nv_lp_register(void *h, const StringMode *modes, int M, double kappa, double knock, double fall, double fl,
                    int top, double beta, int pedals, double rel, double full_db_s, double residual, double ln10_20,
                    long long blk, const int *reg_note);
}

// the export's constants (native_export.py's order)
enum { K_SR, K_BLK, K_CHUNK, K_MASTER, K_RING_FLOOR, K_RING_MAX, K_XDEC, K_REG_SCALE, K_FULL, K_RESIDUAL, K_BETA,
       K_KNEE, K_LN10_20, K_RETRIGGER, K_NYQ_OM, K_SVDC, K_FIXED_TOUCH, K_REFLECT, K_BANDS, K_SH = K_BANDS + 9,
       K_PRESS_DB = K_SH + 4, K_THRESH, K_BEND_RANGE };

struct Export {
    std::vector<double> k, freq, trim, pan;
    std::vector<std::vector<unsigned char>> classes;
    std::vector<int> cmap, kind, fin;     // cmap: the programs' keys, then the drum sets'
    std::vector<double> kit_f0, kit_seat;
    std::vector<unsigned long long> kit_choke;
    std::vector<int> kit_skind;
    std::vector<double> kit_spar;
    std::string room, libs[3];
    std::vector<OrganSpec> organs;        // ORGN: the registered organs' tables
    struct Stops {
        std::vector<std::string> names;
        std::vector<std::vector<int>> rows;
    } stops[128];                         // LSTOP: an organ program's ranks and the panel's stop rows
    std::vector<int> cls_organ, prog_organ;   // each class's organ, each program's (-1 none, -2 not the engine's)
    std::vector<double> les;              // LESL: the rotating speaker's constants
    std::string lobe_lib;                 // ...and synth_voice_lobe's library
    std::vector<double> scan;             // SCAN: the scanner's constants and tables
    double beta = 0.0, headroom = 1.0;
    int part[128][10];
    bool live = false;
    // LREG: each program's free strings (live's register), M 0 for none
    struct Reg {
        int M = 0;
        std::vector<StringMode> modes;
        double d[9];            // kappa knock fall floor beta rel full_db_s residual ln10_20
        int i[3];               // damper_top, dampers, block
        int note[128];
        std::vector<unsigned char> cinit, csnap;    // nv_strings' VoiceInit and VoiceSnap: the bank at another tuner
    } reg[128];
    // LGPU: live's GPU renderer -- its setup's builds, gpukernel.cl's directory, GPU_MIN (and at 64 frames or fewer)
    std::string gpu_lib, gpu_damp_lib, gpu_dir;
    int gpu_min[2] = {1000, 2000};
    bool gpu = false;
    // LROOM: live's convolver, the room's late tail (n stereo samples) and its modes' (m; 0 none)
    std::string conv_lib;
    std::vector<float> ir, mir;
    bool has_room = false;
    // LROUTE: the session's routes, nv_rt_add's seven each
    std::vector<std::array<int, 7>> routes;
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
        } else {
            fseek(f, pos, SEEK_SET);
        }
        char lv[4];
        if (ok && fread(lv, 1, 4, f) == 4 && !memcmp(lv, "LIVE", 4)) {
            E.pan.resize(384);
            double bh[2];
            E.live = fread(E.pan.data(), 8, 384, f) == 384 && fread(bh, 8, 2, f) == 2
                     && fread(E.part, 4, 1280, f) == 1280;
            E.beta = bh[0];
            E.headroom = bh[1];
            if (E.live && fread(lv, 1, 4, f) == 4 && !memcmp(lv, "LREG", 4)) {
                for (int p = 0; p < 128 && ok; p++) {
                    Export::Reg &r = E.reg[p];
                    ok = fread(&r.M, 4, 1, f) == 1;
                    if (ok && r.M > 0) {
                        r.modes.resize(r.M);
                        ok = fread(r.modes.data(), sizeof(StringMode), r.M, f) == (size_t)r.M
                             && fread(r.d, 8, 9, f) == 9 && fread(r.i, 4, 3, f) == 3 && fread(r.note, 4, 128, f) == 128;
                        for (std::vector<unsigned char> *v : {&r.cinit, &r.csnap}) {
                            int n = 0;
                            ok = ok && fread(&n, 4, 1, f) == 1;
                            if (ok) {
                                v->resize(n);
                                ok = fread(v->data(), 1, n, f) == (size_t)n;
                            }
                        }
                    }
                }
                if (ok && fread(lv, 1, 4, f) == 4 && !memcmp(lv, "LGPU", 4)) {
                    std::string *gs[3] = {&E.gpu_lib, &E.gpu_damp_lib, &E.gpu_dir};
                    bool g = true;
                    for (int i = 0; g && i < 3; i++) {
                        int n;
                        g = fread(&n, 4, 1, f) == 1;
                        if (g) {
                            gs[i]->resize(n);
                            g = fread(&(*gs[i])[0], 1, n, f) == (size_t)n;
                        }
                    }
                    E.gpu = g && fread(E.gpu_min, 4, 2, f) == 2;
                }
                char r5[5];
                if (ok && fread(r5, 1, 5, f) == 5 && !memcmp(r5, "LROOM", 5)) {
                    int n = 0;
                    bool g = fread(&n, 4, 1, f) == 1;
                    if (g) {
                        E.conv_lib.resize(n);
                        g = fread(&E.conv_lib[0], 1, n, f) == (size_t)n;
                    }
                    for (std::vector<float> *v : {&E.ir, &E.mir}) {
                        g = g && fread(&n, 4, 1, f) == 1;
                        if (g) {
                            v->resize(2 * (size_t)n);
                            g = fread(v->data(), 4, 2 * (size_t)n, f) == 2 * (size_t)n;
                        }
                    }
                    E.has_room = g;
                }
                char r6[6];
                int nr = 0;
                if (ok && fread(r6, 1, 6, f) == 6 && !memcmp(r6, "LROUTE", 6) && fread(&nr, 4, 1, f) == 1)
                    for (int q = 0; q < nr; q++) {
                        std::array<int, 7> a;
                        if (fread(a.data(), 4, 7, f) != 7)
                            break;
                        E.routes.push_back(a);
                    }
                // LSTOP: each organ program's ranks' names and the panel's stop rows
                char s5[5];
                int no = 0;
                if (ok && fread(s5, 1, 5, f) == 5 && !memcmp(s5, "LSTOP", 5) && fread(&no, 4, 1, f) == 1)
                    for (int q = 0; q < no; q++) {
                        int pg = 0, nr = 0, nrow = 0;
                        if (fread(&pg, 4, 1, f) != 1 || fread(&nr, 4, 1, f) != 1 || pg < 0 || pg > 127)
                            break;
                        auto &so = E.stops[pg];
                        for (int i = 0; i < nr; i++) {
                            int len = 0;
                            if (fread(&len, 4, 1, f) != 1)
                                break;
                            std::string nm(len, ' ');
                            if (len && fread(&nm[0], 1, len, f) != (size_t)len)
                                break;
                            so.names.push_back(nm);
                        }
                        if (fread(&nrow, 4, 1, f) != 1)
                            break;
                        for (int r = 0; r < nrow; r++) {
                            int n = 0;
                            if (fread(&n, 4, 1, f) != 1)
                                break;
                            std::vector<int> row(n);
                            if (n && fread(row.data(), 4, n, f) != (size_t)n)
                                break;
                            so.rows.push_back(row);
                        }
                    }
            }
        }
    }
    fclose(f);
    return ok;
}

// ALSA's PCM, loaded at run time: the five calls a blocking writer needs
struct Alsa {
    void *h = nullptr, *pcm = nullptr;
    int (*open)(void **, const char *, int, int);
    int (*set_params)(void *, int, int, unsigned, unsigned, int, unsigned);
    long (*writei)(void *, const void *, unsigned long);
    int (*recover)(void *, int, int);
    int (*close)(void *);
    const char *(*strerror)(int);

    bool load()
    {
        h = dlopen("libasound.so.2", RTLD_NOW);
        if (!h)
            return false;
        open = (int (*)(void **, const char *, int, int))dlsym(h, "snd_pcm_open");
        set_params = (int (*)(void *, int, int, unsigned, unsigned, int, unsigned))dlsym(h, "snd_pcm_set_params");
        writei = (long (*)(void *, const void *, unsigned long))dlsym(h, "snd_pcm_writei");
        recover = (int (*)(void *, int, int))dlsym(h, "snd_pcm_recover");
        close = (int (*)(void *))dlsym(h, "snd_pcm_close");
        strerror = (const char *(*)(int))dlsym(h, "snd_strerror");
        return open && set_params && writei && recover && close && strerror;
    }
};

static std::atomic<bool> g_stop(false);
extern "C" char **environ;

// REAL-TIME, as live's rtsched.RtSched sets it by default (not pinned): the
// audio thread SCHED_RR at PRIO, under PipeWire's 20 -- directly when this
// user may, else through rtkit (the desktop's real-time broker, no sudo),
// which insists on RLIMIT_RTTIME: SIGXCPU at the soft limit, SIGKILL at the
// hard. THE GUARD: a thread waking every GUARD_MS that, finding a block
// running past STUCK_MS, puts the audio thread back on the desktop's
// scheduler -- a runaway block costs real-time, never the session; SIGXCPU
// does the same. rtkit's grants reset on fork, so the threads the audio
// thread starts (the GPU setup's OpenMP team) are not real-time; the
// register's worker is started before it is promoted, and is not either.
namespace rt {
const int PRIO = 18;                            // rtsched.PRIO
const long RTTIME_SOFT_US = 100000, RTTIME_HARD_US = 200000;
const int GUARD_MS = 25, STUCK_MS = 60;
const int RESET_ON_FORK = 0x40000000;           // SCHED_RESET_ON_FORK
static std::atomic<long> tid(0);
static std::atomic<long long> busy_since(0);    // steady_clock ns at the running block's start, 0 between
static std::atomic<bool> promoted(false);
static std::atomic<int> dropped(0);

static long long now_ns()
{
    return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

static void demote()
{
    if (!promoted.exchange(false))
        return;
    sched_param p{};
    p.sched_priority = 0;
    sched_setscheduler((pid_t)tid.load(), SCHED_OTHER | RESET_ON_FORK, &p);
    dropped++;
}

static void on_xcpu(int) { demote(); }

// rtsched.rtkit_promote: busctl, naming the pid, so it works from any process
static std::string rtkit(long pid, long t, int prio)
{
    std::string a[] = {"busctl", "--system", "call", "org.freedesktop.RealtimeKit1",
                       "/org/freedesktop/RealtimeKit1", "org.freedesktop.RealtimeKit1",
                       "MakeThreadRealtimeWithPID", "ttu", std::to_string(pid), std::to_string(t),
                       std::to_string(prio)};
    std::vector<char *> argv;
    for (std::string &x : a)
        argv.push_back(&x[0]);
    argv.push_back(nullptr);
    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_addopen(&fa, 1, "/dev/null", O_WRONLY, 0);
    posix_spawn_file_actions_addopen(&fa, 2, "/dev/null", O_WRONLY, 0);
    pid_t c;
    int r = posix_spawnp(&c, "busctl", &fa, nullptr, argv.data(), environ);
    posix_spawn_file_actions_destroy(&fa);
    if (r != 0)
        return "no busctl";
    int st = 0;
    waitpid(c, &st, 0);
    return WIFEXITED(st) && WEXITSTATUS(st) == 0 ? "" : "rtkit refused";
}

// the calling thread real-time; "" or why not
static std::string promote(int prio)
{
    tid = (long)syscall(SYS_gettid);
    rlimit rl{(rlim_t)RTTIME_SOFT_US, (rlim_t)RTTIME_HARD_US};
    setrlimit(RLIMIT_RTTIME, &rl);
    signal(SIGXCPU, on_xcpu);
    sched_param p{};
    p.sched_priority = prio;
    std::string why;
    if (sched_setscheduler(0, SCHED_RR | RESET_ON_FORK, &p) != 0) {
        why = rtkit((long)getpid(), tid.load(), prio);
        if (!why.empty())
            return why;
    }
    promoted = true;
    std::thread([] {
        while (!g_stop) {
            std::this_thread::sleep_for(std::chrono::milliseconds(GUARD_MS));
            long long b = busy_since.load();
            if (b && promoted.load() && now_ns() - b > (long long)STUCK_MS * 1000000)
                demote();
        }
    }).detach();
    return "";
}
}  // namespace rt
static void on_signal(int) { g_stop = true; }

struct Midi {
    int type, ch, a, b;
};

// raw MIDI bytes from a device file: running status; note-on at velocity 0 a
// note-off; channel aftertouch type 3; realtime and system messages skipped
static void midi_reader(int fd, std::mutex *mu, std::vector<Midi> *q)
{
    int status = 0, need = 0, got = 0;
    uint8_t d[2];
    uint8_t buf[256];
    while (!g_stop) {
        ssize_t n = read(fd, buf, sizeof buf);
        if (n <= 0) {
            usleep(1000);
            continue;
        }
        for (ssize_t i = 0; i < n; i++) {
            uint8_t c = buf[i];
            if (c >= 0xF8)
                continue;                               // realtime: clock, sensing
            if (c >= 0x80) {
                status = c < 0xF0 ? c : 0;
                int hi = c & 0xF0;
                need = (hi == 0xC0 || hi == 0xD0) ? 1 : 2;
                got = 0;
                continue;
            }
            if (!status)
                continue;                               // inside a sysex
            d[got++] = c;
            if (got < need)
                continue;
            got = 0;
            int hi = status & 0xF0, ch = status & 0x0F;
            Midi m{-1, ch, d[0], need > 1 ? d[1] : 0};
            if (hi == 0x90 && d[1] > 0)
                m.type = 0;
            else if (hi == 0x80 || hi == 0x90)
                m.type = 1;
            else if (hi == 0xB0)
                m.type = 2;
            else if (hi == 0xD0)
                m.type = 3;
            else if (hi == 0xE0) {
                m.type = 4;                             // the pitch wheel, -8192..8191
                m.a = ((d[1] << 7) | d[0]) - 8192;
            }
            if (m.type >= 0) {
                std::lock_guard<std::mutex> lk(*mu);
                q->push_back(m);
            }
        }
    }
}

static std::string opt(int argc, char **argv, const char *name, const char *def)
{
    std::string p = std::string("--") + name + "=";
    for (int i = 1; i < argc; i++)
        if (!strncmp(argv[i], p.c_str(), p.size()))
            return argv[i] + p.size();
    return def;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: nvlive EXPORT.nvx [--program=N] [--midi=DEV] [--device=PCM] [--latency-ms=10]\n"
                        "       nvlive EXPORT.nvx --test IN.mid OUT.wav [--program=N] [--seconds=S]\n");
        return 1;
    }
    Export E;
    if (!read_export(argv[1], E) || !E.live) {
        fprintf(stderr, "nvlive: %s is not a live export of this build (native_export.py --live)\n", argv[1]);
        return 1;
    }
    // each class's organ, its table here (the export's pointer was the exporter's)
    for (size_t i = 0; i < E.classes.size(); i++)
        ((NoteClass *)E.classes[i].data())->organ = E.cls_organ[i] >= 0 ? &E.organs[E.cls_organ[i]] : nullptr;
    const double SR = E.k[K_SR];
    const long long BLK = (long long)E.k[K_BLK];
    const int program = atoi(opt(argc, argv, "program", "0").c_str());
    // --drums: the part a DRUM PART (live.Patch(program, True)): the program
    // its drum set -- one velocity bucket, no wheel step, no dampers, no una
    // corda, every key (live.DRUM_RANGE), its exclusive classes, no register
    bool drums = false;
    for (int i = 1; i < argc; i++)
        drums = drums || !strcmp(argv[i], "--drums");
    static const int DRUM_PART[10] = {1, 1, 1, -1, -1, -1, -1, 0, 0, 0};
    const int *pp = drums ? DRUM_PART : E.part[program & 127];
    if (!pp[0]) {
        fprintf(stderr, "nvlive: program %d is not a native piano\n", program);
        return 1;
    }
    // THE TUNER (native/tuner.cpp): --tuner=NAME in place of the export's (its
    // --tuner, else live's hybrid) -- any of midilib's, `hybrid@D:466`,
    // `raga:todi@c#` -- at --a=HZ or --c=HZ (tunelib.set_reference); the
    // free strings' bank built again at it (nv_strings, as live_bank does)
    std::string tname = opt(argc, argv, "tuner", "");
    if (!tname.empty()) {
        std::string a = opt(argc, argv, "a", ""), c = opt(argc, argv, "c", "");
        int rn = !a.empty() ? 69 : !c.empty() ? 60 : -1;
        double rh = !a.empty() ? atof(a.c_str()) : !c.empty() ? atof(c.c_str()) : 0.0;
        double F[128];
        int have[128];
        int r = nv_tuning_table(tname.c_str(), rn, rh, F, have);
        if (r) {
            fprintf(stderr, "nvlive: tuner %s: %s\n", tname.c_str(),
                    r == -1 ? "no such tuner" : r == -2 ? "no such key" : r == -3 ? "a bad pitch"
                    : r == -4 ? "@KEY or :A4 on a tuner with no table to move" : "a bad raga spec");
            return 1;
        }
        for (int n = 0; n < 128; n++)
            E.freq[n] = have[n] ? F[n] : 0.0;
        Export::Reg &rr = E.reg[program & 127];
        if (rr.M > 0 && !rr.cinit.empty()) {
            int cap = 88 * 4 * 130;
            std::vector<StringMode> modes(cap), tmp(cap);
            int M = nv_strings((const VoiceInit *)rr.cinit.data(), (const VoiceSnap *)rr.csnap.data(), E.freq.data(),
                               0.0, 1.0, SR, modes.data(), tmp.data(), cap);
            if (M > 0) {
                modes.resize(M);
                rr.modes.swap(modes);
                rr.M = M;
            }
        }
        fprintf(stderr, "nvlive: tuned %s%s\n", tname.c_str(), rn >= 0 ? (rn == 69 ? " at a=" + a : " at c=" + c).c_str() : "");
    }
    // THE PART'S TEMPLATES (live.Patch.warm), built here
    std::vector<const NoteClass *> K(2 * NV_K_DRUMS, nullptr);
    for (int q = 0; q < 2 * NV_K_DRUMS; q++)
        if (E.cmap[q] >= 0) {
            const NoteClass *k = (const NoteClass *)E.classes[E.cmap[q]].data();
            K[q] = k;
        }
    NoteIn t;
    memset(&t, 0, sizeof t);
    t.sr = SR; t.retrigger_fade = E.k[K_RETRIGGER]; t.nyq_om = E.k[K_NYQ_OM];
    t.sv[1] = 1.0; t.sound_vib_depth_cents = E.k[K_SVDC]; t.gl[1] = 0.05; t.fx = -1.0;
    for (int i = 0; i < 9; i++)
        t.room_bands[i] = E.k[K_BANDS + i];
    t.reflect = E.k[K_REFLECT] != 0.0;
    t.fixed_touch = 1;                          // live builds its templates at fixed touch
    void *cache = nv_tcache_new(K.data(), &t, E.freq.data(), E.trim.data(), E.kind.data(), E.fin.data(),
                                E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK, E.k[K_RING_FLOOR],
                                E.k[K_RING_MAX], E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR);
    if (drums)
        nv_tcache_kits(cache, E.kit_f0.data(), E.kit_seat.data(), E.kit_choke.data(), E.kit_skind.data(),
                       E.kit_spar.data(), 100.0);       // (live.ONESHOT_FLOOR_DB)
    if (!E.les.empty())                         // a rotary voice's templates through its cabinet
        nv_tcache_leslie(cache, E.les.data(), (int)E.les.size());
    int speeds[3] = {pp[3], pp[4], pp[5]};
    long built = drums ? nv_tcache_warm(cache, program, 0, 127, 1, speeds, 1)
                       : nv_tcache_warm(cache, program, 21, 96, pp[1], speeds, pp[2]);
    fprintf(stderr, "nvlive: %s %d, %ld templates\n", drums ? "drum set" : "program", program, built);
    // THE SLAB'S SLOTS (--slots: live's capacity, 65536 -- a vibraslap's
    // strike is 16524 rows)
    long slots = atol(opt(argc, argv, "slots", "65536").c_str());
    void *part = nv_lp_new(cache, 1, 0.0, pp[1], pp[6], pp[7], pp[8], pp[9], SR, E.k[K_RETRIGGER], slots,
                           E.headroom, E.pan.data(), E.beta);
    if (!E.les.empty())                         // the room's Leslie: its rotors, on chorale
        nv_lp_leslie(part, E.les.data(), (int)E.les.size());
    if (!E.scan.empty())                        // the Hammond's scanner: its circuit's tables
        nv_lp_scan(part, E.scan.data(), (long)E.scan.size());
    if (drums)
        nv_lp_drums(part, program, E.kit_choke.data());
    else
        nv_lp_program(part, program);
    // THE DRUMS BESIDE THE PIANO (live's Parts on one slab): a drum set
    // (--drum-set=P, Standard's 0) on channel 10, the piano on every other
    // (--no-drums: the piano alone); and --split=N, on the keyboard's channel
    // (--split-channel, 1), its keys under N the drum set's, moved by
    // --split-transpose=T (the hand drums, 60-87, from a low split)
    bool nodrums = drums;
    for (int i = 1; i < argc; i++)
        nodrums = nodrums || !strcmp(argv[i], "--no-drums");
    int split = atoi(opt(argc, argv, "split", "0").c_str());
    if (!drums && (!nodrums || split > 0)) {
        int dset = atoi(opt(argc, argv, "drum-set", "0").c_str()) & 127;
        void *dcache = nv_tcache_new(K.data(), &t, E.freq.data(), E.trim.data(), E.kind.data(), E.fin.data(),
                                     E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK,
                                     E.k[K_RING_FLOOR], E.k[K_RING_MAX], E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR);
        nv_tcache_kits(dcache, E.kit_f0.data(), E.kit_seat.data(), E.kit_choke.data(), E.kit_skind.data(),
                       E.kit_spar.data(), 100.0);
        int nsp[1] = {-1};
        long dbuilt = nv_tcache_warm(dcache, dset, 0, 127, 1, nsp, 1);      // (live.DRUM_RANGE)
        if (!nodrums) {
            nv_lp_patch_range(part, 0, -1, 1u << 9, 0, 127, 0);
            nv_lp_add_patch(part, dcache, 2, 0.0, 1, -1, 0, 0, 0, 1, dset, E.kit_choke.data(), 9, 0u, 0, 127, 0);
            fprintf(stderr, "nvlive: drum set %d on channel 10 (%ld templates)\n", dset, dbuilt);
        }
        if (split > 0) {
            int sch = atoi(opt(argc, argv, "split-channel", "1").c_str()) - 1;
            int str = atoi(opt(argc, argv, "split-transpose", "0").c_str());
            nv_lp_add_patch(part, dcache, 3, 0.0, 1, -1, 0, 0, 0, 1, dset, E.kit_choke.data(), sch & 15, 0u, 0,
                            split - 1, str);
            fprintf(stderr, "nvlive: drum set %d under key %d on channel %d (transposed %+d)\n", dset, split,
                    (sch & 15) + 1, str);
        }
    }
    nv_lp_detune_wheel(part, pp[6] >= 0);       // the export's speed: a honky-tonk's wheel, else -1
    if (E.k.size() > K_BEND_RANGE)
        nv_lp_post(part, E.k[K_THRESH], E.k[K_BEND_RANGE], 35.0);     // (the mod range: no vibrato on a piano)
    // THE ROOM'S LATE TAIL (the export's: the session's room), through live's
    // convolver -- unless --dry
    bool dry = false;
    for (int i = 1; i < argc; i++)
        dry = dry || !strcmp(argv[i], "--dry");
    if (!dry && E.has_room && !E.ir.empty()) {
        void *ch = dlopen(E.conv_lib.c_str(), RTLD_NOW | RTLD_LOCAL);
        void *cn = ch ? dlsym(ch, "conv_new") : nullptr, *cp = ch ? dlsym(ch, "conv_process") : nullptr;
        void *cf = ch ? dlsym(ch, "conv_free") : nullptr;
        if (cn && cp && cf) {
            nv_lp_room(part, cn, cp, cf, E.ir.data(), (long)E.ir.size() / 2, E.mir.empty() ? nullptr : E.mir.data(),
                       (long)E.mir.size() / 2, (int)BLK);
            fprintf(stderr, "nvlive: the room's tail, %.2f s%s\n", E.ir.size() / 2 / SR,
                    E.mir.empty() ? "" : ", and its modes");
        } else {
            fprintf(stderr, "nvlive: no convolver (%s): dry\n", E.conv_lib.c_str());
        }
    }
    // the free strings (live's register, its worker answering in step)
    const Export::Reg &rg = E.reg[program & 127];
    bool noreg = drums;                         // (a drum has no free strings)
    for (int i = 1; i < argc; i++)
        noreg = noreg || !strcmp(argv[i], "--no-register");
    if (rg.M > 0 && !noreg) {
        nv_lp_register(part, rg.modes.data(), rg.M, rg.d[0], rg.d[1], rg.d[2], rg.d[3], rg.i[0], rg.d[4], rg.i[1],
                       rg.d[5], rg.d[6], rg.d[7], rg.d[8], rg.i[2], rg.note);
        fprintf(stderr, "nvlive: the register: %d string modes\n", rg.M);
    }
    nv_lp_damper(part, E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_KNEE], E.k[K_BETA], E.k[K_LN10_20]);
    nv_lp_press_db(part, atof(opt(argc, argv, "press-db",
                                  std::to_string(E.k.size() > K_PRESS_DB ? E.k[K_PRESS_DB] : 8.0).c_str()).c_str()));
    void *fn[3];
    const char *FN[3] = {"synth_voice", "synth_voice_xdec", "synth_voice_damp"};
    for (int q = 0; q < 3; q++) {
        void *h = dlopen(E.libs[q].c_str(), RTLD_NOW | RTLD_LOCAL);
        fn[q] = h ? dlsym(h, FN[q]) : nullptr;
        if (!fn[q]) {
            fprintf(stderr, "nvlive: no %s in %s\n", FN[q], E.libs[q].c_str());
            return 1;
        }
    }
    const double master = E.k[K_MASTER];
    // THE GPU (live.GpuRenderer), by default (--cpu: none): the setup on the
    // CPU, the samples on OpenCL (--gpu=c: the C reference, voice_samples);
    // a block with fewer than --gpu-min busy slots (live's GPU_MIN) on the
    // CPU. One that cannot be had says why and plays on the CPU, as live
    // does. PIPELINED on OpenCL (--no-pipeline: not), as live's
    // TUNING_GPU_PIPELINE: a block late, the next block's setup while the
    // GPU renders this one
    std::string gopt = "cl";
    bool pipe = true;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--gpu"))
            gopt = "cl";
        if (!strcmp(argv[i], "--cpu"))
            gopt = "";
        if (!strcmp(argv[i], "--no-pipeline"))
            pipe = false;
    }
    gopt = opt(argc, argv, "gpu", gopt.c_str());
    if (!gopt.empty()) {
        std::string why;
        void *gl = E.gpu ? dlopen(E.gpu_lib.c_str(), RTLD_NOW | RTLD_LOCAL) : nullptr;
        void *gd = E.gpu ? dlopen(E.gpu_damp_lib.c_str(), RTLD_NOW | RTLD_LOCAL) : nullptr;
        void *vb = gl ? dlsym(gl, "voice_block") : nullptr, *vs = gl ? dlsym(gl, "voice_samples") : nullptr;
        void *vz = gl ? dlsym(gl, "voice_sizes") : nullptr;
        void *vbd = gd ? dlsym(gd, "voice_block") : nullptr, *vds = gd ? dlsym(gd, "voice_damp_set") : nullptr;
        void *cl = nullptr;
        if (!E.gpu)
            why = "the export has no GPU section (native_export.py --live again)";
        else if (!vb || !vs || !vz || !vbd || !vds)
            why = "no voice_block in " + E.gpu_lib + " / " + E.gpu_damp_lib;
        else if (gopt != "c") {
            int sz[3];
            ((void (*)(int *))vz)(sz);
            char err[512] = "";
            cl = nv_cl_new(E.gpu_dir.c_str(), sz, err, sizeof err);
            if (!cl)
                why = err;
        }
        if (why.empty()) {
            // FROM 100 BUSY SLOTS, not live's GPU_MIN (1000, set against Python's
            // cost of a GPU block): natively a GPU block is ~0.35 ms however
            // many rows it has, and the CPU's took 1.4 ms on average under
            // 1000 (5.7 ms at p99) -- ondine.mid's 60 s, real-time, register
            // off the thread: 489 blocks over 2.67 ms at 1000, none at 100.
            // Each side's own threshold is checked by nvlive_check --gpu-min.
            long gmin = atol(opt(argc, argv, "gpu-min", "100").c_str());
            nv_lp_gpu(part, vb, vbd, vds, vs, vz, cl, gmin, atoi(opt(argc, argv, "gpu-threads", "4").c_str()));
            nv_lp_pipeline(part, cl && pipe);
            fprintf(stderr, "nvlive: the GPU (%s), from %ld busy slots%s\n", cl ? "OpenCL" : "the C reference", gmin,
                    cl && pipe ? ", pipelined" : "");
        } else {
            fprintf(stderr, "nvlive: no GPU (%s): the CPU\n", why.c_str());
        }
    }
    // THE ROUTES ahead of the part (live.Route, Live.on_midi): the session's,
    // from the export, and --pedal-key's -- a key held as the sustain pedal,
    // pushed into (aftertouch) to lower the dampers
    // ...or, once the panel has edited them, the routes kept beside the export
    std::string routes_file = std::string(argv[1]) + ".routes";
    if (FILE *rf = fopen(routes_file.c_str(), "r")) {
        E.routes.clear();
        std::array<int, 7> a;
        while (fscanf(rf, "%d %d %d %d %d %d %d", &a[0], &a[1], &a[2], &a[3], &a[4], &a[5], &a[6]) == 7)
            E.routes.push_back(a);
        fclose(rf);
        fprintf(stderr, "nvlive: the routes kept in %s\n", routes_file.c_str());
    }
    void *router = nv_rt_new();
    for (auto &a : E.routes)
        nv_rt_add(router, a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
    std::string pks = opt(argc, argv, "pedal-key", "");
    std::array<int, 7> pedal_route = {3, atoi(pks.c_str()), 64, 0, -1, 0, 1};
    if (!pks.empty()) {
        nv_rt_add(router, 3, atoi(pks.c_str()), 64, 0, -1, 0, 1);
        fprintf(stderr, "nvlive: key %d is the sustain pedal, pushed into to lower the dampers\n", atoi(pks.c_str()));
    }
    if (!E.routes.empty())
        fprintf(stderr, "nvlive: %zu route(s) from the session\n", E.routes.size());
    auto event = [&](int type, int ch, int a, int b) {
        int out[4 * 16];
        int n = nv_rt_feed(router, type, ch, a, b, out, 16);
        for (int q = 0; q < n; q++)
            nv_lp_event(part, out[4 * q], out[4 * q + 1], out[4 * q + 2], out[4 * q + 3]);
    };
    float L[4096], R[4096];
    // --test: a file's events, block by block, to the dry blocks
    for (int i = 1; i + 2 < argc; i++)
        if (!strcmp(argv[i], "--test")) {
            FILE *mf = fopen(argv[i + 1], "rb");
            if (!mf) {
                fprintf(stderr, "nvlive: cannot read %s\n", argv[i + 1]);
                return 1;
            }
            std::vector<uint8_t> bytes;
            for (int c; (c = fgetc(mf)) != EOF;)
                bytes.push_back((uint8_t)c);
            fclose(mf);
            int err = 0;
            void *m = nv_midi_read(bytes.data(), (long long)bytes.size(), &err);
            if (!m) {
                fprintf(stderr, "nvlive: the reader refused %s (%d)\n", argv[i + 1], err);
                return 2;
            }
            int ne = nv_midi_n_events(m);
            double secs = atof(opt(argc, argv, "seconds", "0").c_str());
            if (secs <= 0)
                secs = nv_midi_total(m) + 3.0;
            long long nb = (long long)(secs * SR) / BLK;
            // timing as played: --reg-async (the register off this thread; the
            // output then varies run to run) and --rt (this thread real-time)
            for (int q = 1; q < argc; q++) {
                if (!strcmp(argv[q], "--reg-async"))
                    nv_lp_reg_async(part);
                if (!strcmp(argv[q], "--rt")) {
                    std::string why = rt::promote(rt::PRIO);
                    fprintf(stderr, "nvlive: %s\n", why.empty() ? "real-time, SCHED_RR 18" : ("not real-time: " + why).c_str());
                }
            }
            bool tgov = false;
            for (int q = 1; q < argc; q++)
                tgov = tgov || !strcmp(argv[q], "--govern");
            std::vector<float> out;
            std::vector<double> ms, msr, mss, msg;      // each block's events, step and render, ms; its render;
                                                        // a GPU block's setup and samples
            std::vector<double> mstep, mcpu;            // the step (events, register, dampers); a CPU block's render
            int e = 0;
            for (long long b = 0; b < nb; b++) {
                auto t0 = std::chrono::steady_clock::now();
                long long n0 = b * BLK;
                while (e < ne) {
                    int iv[4];
                    double et;
                    nv_midi_event(m, e, iv, &et);
                    if ((long long)(et * SR) / BLK > b)
                        break;                          // a later block's
                    event(iv[0], iv[1], iv[2], iv[3]);
                    e++;
                }
                nv_lp_block(part, n0, BLK);
                auto t1 = std::chrono::steady_clock::now();
                nv_lp_output(part, n0, (long)BLK, L, R, fn[0], fn[1], fn[2], BLK, master);
                msr.push_back(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t1).count());
                mstep.push_back(std::chrono::duration<double, std::milli>(t1 - t0).count());
                if (!nv_lp_on_gpu(part))
                    mcpu.push_back(msr.back());
                if (nv_lp_on_gpu(part)) {
                    double g2[2];
                    nv_lp_gpu_ms(part, g2);
                    mss.push_back(g2[0]);
                    msg.push_back(g2[1]);
                }
                ms.push_back(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count());
                if (tgov)
                    nv_lp_govern(part, ms.back(), 1000.0 * BLK / SR, n0 + BLK);
                for (long long k = 0; k < BLK; k++) {
                    out.push_back(L[k]);
                    out.push_back(R[k]);
                }
            }
            // the blocks' times against the block's own length
            if (!ms.empty()) {
                std::vector<double> o = ms;
                std::sort(o.begin(), o.end());
                double sum = 0.0, budget = 1000.0 * BLK / SR;
                long over = 0;
                for (double x : o) {
                    sum += x;
                    over += x > budget;
                }
                fprintf(stderr, "nvlive: blocks %.3f ms mean, %.3f p99, %.3f worst; %ld of %zu over %.2f ms\n",
                        sum / o.size(), o[o.size() * 99 / 100], o.back(), over, o.size(), budget);
                // ...the render's share, and a GPU block's two halves
                auto stat = [&](const char *what, std::vector<double> v) {
                    if (v.empty())
                        return;
                    std::sort(v.begin(), v.end());
                    double t = 0.0;
                    for (double x : v)
                        t += x;
                    fprintf(stderr, "nvlive:   %s %.3f ms mean, %.3f p99, %.3f worst (%zu blocks)\n", what,
                            t / v.size(), v[v.size() * 99 / 100], v.back(), v.size());
                };
                stat("render", msr);
                stat("step", mstep);
                stat("CPU render", mcpu);
                stat("GPU setup", mss);
                stat("GPU samples", msg);
                if (tgov)
                    fprintf(stderr, "nvlive:   the governor shed %ld partials\n", nv_lp_partials_shed(part));
            }
            nv_midi_free(m);
            FILE *wf = fopen(argv[i + 2], "wb");
            if (!wf)
                return 1;
            uint32_t data = (uint32_t)(out.size() * 4);
            auto u32 = [&](uint32_t v) { fwrite(&v, 4, 1, wf); };
            auto u16 = [&](uint16_t v) { fwrite(&v, 2, 1, wf); };
            fwrite("RIFF", 1, 4, wf); u32(36 + data); fwrite("WAVE", 1, 4, wf);
            fwrite("fmt ", 1, 4, wf); u32(16); u16(3); u16(2); u32((uint32_t)SR); u32((uint32_t)SR * 8); u16(8);
            u16(32);
            fwrite("data", 1, 4, wf); u32(data);
            fwrite(out.data(), 4, out.size(), wf);
            fclose(wf);
            fprintf(stderr, "nvlive: %lld blocks -> %s\n", nb, argv[i + 2]);
            return 0;
        }
    // LIVE: the keyboard in, ALSA out
    std::string dev = opt(argc, argv, "midi", "");
    if (dev.empty()) {
        for (int c = 0; c < 8 && dev.empty(); c++)
            for (int d = 0; d < 4 && dev.empty(); d++) {
                char p[64];
                snprintf(p, sizeof p, "/dev/snd/midiC%dD%d", c, d);
                if (access(p, R_OK) == 0)
                    dev = p;
            }
    }
    int fd = dev.empty() ? -1 : ::open(dev.c_str(), O_RDONLY | O_NONBLOCK);
    if (fd < 0) {
        fprintf(stderr, "nvlive: no MIDI input (%s); --midi=/dev/snd/midiCxDy\n", dev.c_str());
        return 1;
    }
    Alsa A;
    if (!A.load()) {
        fprintf(stderr, "nvlive: cannot load libasound.so.2\n");
        return 1;
    }
    std::string pcmdev = opt(argc, argv, "device", "default");
    unsigned lat = (unsigned)(1000 * atof(opt(argc, argv, "latency-ms", "10").c_str()));
    int r = A.open(&A.pcm, pcmdev.c_str(), 0 /* playback */, 0);
    if (r >= 0)
        r = A.set_params(A.pcm, 14 /* FLOAT_LE */, 3 /* RW_INTERLEAVED */, 2, (unsigned)SR, 1, lat);
    if (r < 0) {
        fprintf(stderr, "nvlive: ALSA %s: %s\n", pcmdev.c_str(), A.strerror(r));
        return 1;
    }
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    std::mutex mu;
    std::vector<Midi> q;
    std::thread reader(midi_reader, fd, &mu, &q);
    // the register's jobs on their own thread, off the audio one (--reg-sync: in step)
    bool rsync = false, nort = getenv("TUNING_RT") && !strcmp(getenv("TUNING_RT"), "0"), nopanel = !isatty(1);
    for (int i = 1; i < argc; i++) {
        rsync = rsync || !strcmp(argv[i], "--reg-sync");
        nort = nort || !strcmp(argv[i], "--no-rt");
        nopanel = nopanel || !strcmp(argv[i], "--no-panel");
    }
    if (!rsync)
        nv_lp_reg_async(part);
    nv_lp_scan_async(part);                     // the scanner's data on its own thread, as live's builder
    nv_lp_amp_async(part);                      // ...and the valve's passes, as live's workers
    fprintf(stderr, "nvlive: playing (MIDI %s, audio %s, %u us); %s\n", dev.c_str(), pcmdev.c_str(), lat,
            nopanel ? "Ctrl-C to stop" : "the panel (q to stop)");
    // WHAT THE PANEL POSTS, done between two blocks (live.post); what it
    // reads, handed over after each; and a key it is learning
    std::mutex pmu;
    std::vector<std::function<void(long long)>> posted;
    panel::Snap snap;
    std::atomic<int> learning(0);                   // 1 armed, 2 got one
    std::atomic<int> learnt_ch(-1), learnt_note(-1);
    std::pair<int, int> swallow(-1, -1);            // the learnt key's release (audio thread)
    long underruns = 0, over = 0, blocks = 0;
    double worst = 0.0, budget = 1000.0 * BLK / SR;
    bool govern = true;
    for (int i = 1; i < argc; i++)
        govern = govern && strcmp(argv[i], "--no-governor");
    double master_now = master;
    std::atomic<bool> rt_on(false);
    // THE AUDIO THREAD: real-time (--no-rt, TUNING_RT=0: not), block by block
    auto audio = [&]() {
        if (!nort) {
            int prio = atoi(opt(argc, argv, "rt-prio", std::to_string(rt::PRIO).c_str()).c_str());
            std::string why = rt::promote(prio);
            rt_on = why.empty();
            if (nopanel)
                fprintf(stderr, why.empty() ? "nvlive: real-time, SCHED_RR %d\n" : "nvlive: not real-time (%s)\n",
                        why.empty() ? prio : 0, why.c_str());
        }
        std::vector<float> buf(2 * BLK);
        long long n0 = 0;
        while (!g_stop) {
            long long t0 = rt::now_ns();
            rt::busy_since = t0;
            std::vector<std::function<void(long long)>> todo;
            {
                std::lock_guard<std::mutex> lk(pmu);
                todo.swap(posted);
            }
            for (auto &f : todo)
                f(n0);
            std::vector<Midi> evs;
            {
                std::lock_guard<std::mutex> lk(mu);
                evs.swap(q);
            }
            for (const Midi &m : evs) {
                // LEARNING A KEY (live._learn_take): the next press taken, and
                // neither it nor its release plays
                if (learning == 1 && m.type == 0) {
                    learnt_ch = m.ch;
                    learnt_note = m.a;
                    learning = 2;
                    swallow = std::make_pair(m.ch, m.a);
                    continue;
                }
                if (m.type == 1 && swallow == std::make_pair(m.ch, m.a)) {
                    swallow = std::make_pair(-1, -1);
                    continue;
                }
                event(m.type, m.ch, m.a, m.b);
            }
            nv_lp_block(part, n0, BLK);
            nv_lp_output(part, n0, (long)BLK, L, R, fn[0], fn[1], fn[2], BLK, master_now);
            rt::busy_since = 0;
            double ms = (rt::now_ns() - t0) / 1e6;
            if (govern)
                nv_lp_govern(part, ms, budget, n0 + BLK);
            blocks++;
            over += ms > budget;
            worst = ms > worst ? ms : worst;
            float pk[2] = {0.0f, 0.0f};
            for (long long k = 0; k < BLK; k++) {
                buf[2 * k] = L[k];
                buf[2 * k + 1] = R[k];
                pk[0] = std::max(pk[0], fabsf(L[k]));
                pk[1] = std::max(pk[1], fabsf(R[k]));
            }
            {
                std::lock_guard<std::mutex> lk(pmu);
                snap.n0 = n0;
                snap.blocks = blocks;
                snap.over = over;
                snap.ms_max = std::max(snap.ms_max, ms);
                snap.ms_sum += ms;
                snap.ms_n++;
                snap.peak[0] = std::max(snap.peak[0], pk[0]);
                snap.peak[1] = std::max(snap.peak[1], pk[1]);
                if ((blocks & 7) == 0)
                    nv_lp_stats(part, snap.eng);
                snap.rt = rt_on && !rt::dropped;
                snap.rt_dropped = rt::dropped > 0;
            }
            long w = A.writei(A.pcm, buf.data(), (unsigned long)BLK);
            if (w < 0) {
                underruns += w == -32;                  // -EPIPE: the device ran dry
                // RECOVER AS PORTAUDIO DOES: the device prepared again, half
                // its buffer of silence ahead (a cushion, so one slow block in
                // a thick passage does not run it dry again, block after
                // block), and THIS block written after it rather than lost
                if (A.recover(A.pcm, (int)w, 1) >= 0) {
                    long half = std::max<long>(1, (long)((double)lat * 1e-6 * SR / 2.0 / BLK));
                    std::vector<float> zero(2 * BLK, 0.0f);
                    for (long q = 0; q < half; q++)
                        A.writei(A.pcm, zero.data(), (unsigned long)BLK);
                    A.writei(A.pcm, buf.data(), (unsigned long)BLK);
                }
                std::lock_guard<std::mutex> lk(pmu);
                snap.underruns = underruns;
            }
            n0 += BLK;
        }
    };
    std::thread player(audio);
    if (nopanel) {
        while (!g_stop)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
    } else {
        // THE PANEL, on this thread
        static const char *GM[8] = {"Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano",
                                    "Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2", "Harpsichord",
                                    "Clavi"};
        panel::Host H;
        auto post = [&](std::function<void(long long)> f) {
            std::lock_guard<std::mutex> lk(pmu);
            posted.push_back(std::move(f));
        };
        H.take = [&]() {
            std::lock_guard<std::mutex> lk(pmu);
            panel::Snap s = snap;
            snap.ms_max = snap.ms_sum = 0.0;
            snap.ms_n = 0;
            snap.peak[0] = snap.peak[1] = 0.0f;
            return s;
        };
        H.learn = [&](bool on) {
            learnt_ch = learnt_note = -1;
            learning = on ? 1 : 0;
        };
        H.learnt = [&]() {
            return learning == 2 ? std::make_pair(learnt_ch.load(), learnt_note.load()) : std::make_pair(-1, -1);
        };
        H.rate = SR;
        H.frames = (int)BLK;
        H.budget_ms = budget;
        H.program = program;
        H.program_name = drums ? "GM percussion" : program >= 0 && program < 8 ? GM[program] : "";
        H.port = dev;
        H.room = E.room.empty() ? "-" : E.room;
        H.reg_modes = rg.M > 0 && !noreg ? rg.M : 0;
        double st[15];
        nv_lp_stats(part, st);
        H.has_gpu = st[12] > 0.5;
        H.has_room = st[11] > 0.5;
        H.g[0] = 20.0 * log10(std::max(master, 1e-12));
        H.g[1] = -20.0 * log10(std::max(E.headroom, 1e-12));
        H.g[2] = E.k.size() > K_THRESH ? E.k[K_THRESH] : 0.70;
        H.g[3] = E.k.size() > K_BEND_RANGE ? E.k[K_BEND_RANGE] : 2.0;
        H.g[4] = 35.0;
        H.g[5] = E.k.size() > K_PRESS_DB ? E.k[K_PRESS_DB] : 8.0;
        H.g[6] = H.has_gpu ? 1.0 : 0.0;
        H.g[7] = H.has_room ? 1.0 : 0.0;
        H.set_global = [&](int i, double v) {
            post([&, i, v](long long) {
                switch (i) {
                case 0: master_now = pow(10.0, v / 20.0); break;     // T.master_gain
                case 1: nv_lp_set(part, 0, v); break;
                case 2: nv_lp_set(part, 2, v); break;
                case 3: nv_lp_set(part, 3, v); break;
                case 4: nv_lp_set(part, 4, v); break;
                case 5: nv_lp_set(part, 1, v); break;
                case 6: nv_lp_set(part, 5, v); break;
                case 7: nv_lp_set(part, 6, v); break;
                }
            });
        };
        H.routes = E.routes;
        if (!pks.empty())
            H.routes.push_back(pedal_route);
        H.add_route = [&](const std::array<int, 7> &a) {
            post([&, a](long long) { nv_rt_add(router, a[0], a[1], a[2], a[3], a[4], a[5], a[6]); });
        };
        H.del_route = [&](int i) { post([&, i](long long) { nv_rt_del(router, i); }); };
        H.panic = [&]() { post([&](long long n) { nv_lp_panic(part, n); }); };
        // AN ORGAN'S STOPS (live's panel): its ranks, drawn and put in between two blocks
        if (!drums && program >= 0 && program < 128 && !E.stops[program].names.empty()) {
            H.stop_names = E.stops[program].names;
            H.stop_rows = E.stops[program].rows;
            H.drawn = [&, nr = (int)E.stops[program].names.size()]() {
                std::vector<char> d(nr, 0);
                nv_lp_drawn(part, d.data(), nr);
                return d;
            };
            H.toggle_stop = [&](int ri) { post([&, ri](long long n) { nv_lp_toggle_stop(part, ri, n); }); };
        }
        bool edited = false;
        auto was = H.routes;
        panel::Panel P(H);
        P.run([&]() { return !g_stop.load(); });
        g_stop = true;
        edited = H.routes != was;
        // ROUTES ADDED OR TAKEN AWAY HERE are kept beside the export, and read
        // back the next time (--pedal-key's own not among them)
        if (edited) {
            if (FILE *wf = fopen(routes_file.c_str(), "w")) {
                bool skipped = pks.empty();
                for (auto &a : H.routes) {
                    if (!skipped && a == pedal_route) {
                        skipped = true;
                        continue;
                    }
                    fprintf(wf, "%d %d %d %d %d %d %d\n", a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
                }
                fclose(wf);
                fprintf(stderr, "nvlive: routes kept in %s\n", routes_file.c_str());
            }
        }
    }
    g_stop = true;
    player.join();
    fprintf(stderr, "nvlive: %ld blocks, %ld over %.2f ms (worst %.2f), %ld underruns, %ld partials shed%s\n", blocks,
            over, budget, worst, underruns, nv_lp_partials_shed(part),
            rt::dropped ? ", real-time dropped by the guard" : "");
    reader.join();
    A.close(A.pcm);
    ::close(fd);
    fprintf(stderr, "nvlive: stopped\n");
    return 0;
}
