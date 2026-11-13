// hostlive.h -- THE LIVE HOST's internals (host step 2e): nvlive's struct
// nv_host and what it stands on, shared by libnative's host.cpp (open, a
// block) and nvlive.cpp (the --test runner, the devices, the panel) while
// host.h's C API grows over it. The statics both sides read are single
// (inline): the audio thread's busy_since the guard reads, g_stop, g_msgr_blk.
#ifndef NV_HOSTLIVE_H
#define NV_HOSTLIVE_H
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cerrno>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <condition_variable>
#include <functional>
#include <map>
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
#include "session.h"
#include "pycompat.h"

extern "C" {
void *nv_midi_read(const uint8_t *buf, long long len, int *err);
int nv_midi_master(void *p);
int nv_midi_banked(void *p);
int nv_midi_sysex(void *p, int i, uint8_t *out, int cap);
void nv_part_sysex(void *h, const uint8_t *d, int n);
int nv_part_take_reset(void *h);
void nv_part_mts_ref(void *h, int note, double hz);
void nv_tcache_set_gm2(void *h, int on);
void nv_tcache_set_var(void *h, int v);
void nv_live_vars(int nent, const int *nls, const int *ls, const double *trim, const int *gs, const int *gm2,
                  int nslot, const OrganSpec *const *so, const int *soff, const OrganSpec *const *sog,
                  long long kn);
void nv_midi_free(void *p);
double nv_midi_total(void *p);
void nv_midi_map_kits(const int *ids, int n);
void nv_midi_map_kits_play(int on);
int nv_midi_display_n(void *p);
const uint8_t *nv_midi_display(void *p, int i, int *n, double *t);
int nv_midi_n_events(void *p);
void nv_midi_event(void *p, int i, int *iv, double *t);
void *nv_tcache_new(const NoteClass *const *K, const NoteIn *tmpl, const double *freq, const double *trim,
                    const int *kind, const int *fin, double scale, double full_db_s, double residual, double beta,
                    long long blk, double ring_floor, double ring_max, double knee_db, double ln10_20,
                    double xdec_nepers, double SR);
long nv_tcache_warm(void *h, int program, int lo, int hi, int nb, const int *speeds, int nsp);
long nv_tcache_warm_p(void *h, int program, int lo, int hi, int nb, const int *speeds, int nsp, long *done);
void nv_tcache_kits(void *h, const double *f0, const double *seat, const unsigned long long *choke,
                    const int *skind, const double *spar, double oneshot_floor_db);
void nv_part_drums(void *h, int program, const unsigned long long *choke);
void nv_part_program(void *h, int program);
void nv_part_drone_patch(void *h, int pi, void *cache, int nbuckets, int speed);
void nv_part_toggle_stop(void *h, int rank, long long n0);
int nv_part_drawn(void *h, char *out, int cap);
void nv_part_set_drawn(void *h, const char *want, int n);
void nv_part_chanstate(void *h, double *out);
void nv_part_metronome(void *h, int pi, double bpm, int ring);
int nv_part_synth_get(void *h, int pi, int layer, double *pn, char *own);
int nv_part_synth_set(void *h, int pi, int layer, int knob, double v);
void nv_part_synth_forget(void *h, int pi, int layer, int knob);
void nv_part_synth_set_later(void *h, int pi, int layer, int knob, double v);
int nv_part_synth_send(void *h, int pi);
void nv_part_patch_touch(void *h, int pi, int fixed);
void nv_part_drive(void *h, int pi, double v);
void nv_part_drive_later(void *h, int pi, double v);
int nv_part_drive_get(void *h, int pi, double *out);
int nv_part_patch_touch_sensitive(void *h, int pi);
void nv_part_switches(void *h, int ch, int *out);
void nv_part_set_drawn_names(void *h, const char *const *names, int n);
void nv_part_efx(void *h, const double *X, double SR);
void nv_part_place3d(void *h, const double *q);
int nv_part_efx_state(void *h, int *o, int cap, const char **why);
long nv_part_efx_rev(void *h);
void *nv_part_new(void *cache, long long pid, double level_db, int nbuckets, int speed, int damper_pedal,
                int soft_drop, int soft_top, double rate, double retrigger, long cap, double headroom,
                const double *pan_tab, double pan_beta);
void nv_part_event(void *h, int type, int ch, int a, int b);
void nv_part_block(void *h, long long n0, long long blk);
void nv_part_moog_kernel(void *h, void *pcells, void *srows, void *crows);
void nv_part_render(void *h, long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx,
                  void *sd, long long blk, double master_gain);
void nv_part_damper(void *h, double full_db_s, double residual, double knee_db, double beta, double ln10_20);
void nv_part_press_db(void *h, double db);
void nv_moog_tables(const double *t);
void nv_part_messenger(void *h, void (*send)(void *, const uint8_t *, int), void *ctx, double bend);
void nv_part_detune_wheel(void *h, int on);
void nv_part_leslie(void *h, const double *L, int n);
void nv_part_scan(void *h, const double *X, long n);
void nv_part_scan_async(void *h);
void nv_part_amp_async(void *h);
void nv_tcache_leslie(void *h, const double *L, int n);
int nv_tuning_table(const char *name, int ref_note, double ref_hz, double *out, int *have);
int nv_raga_info(const char *spec, double sa_hz, double *out, int *have, int *sa_note, double *sw, int *nsw);
extern "C" const char *nv_raga_system_name(int i);
extern "C" const char *nv_raga_name(int i, int *n, const int **idx);
void nv_tcache_set_raga(void *h, int sa, const double *sw, int nsw);
void nv_part_room(void *h, void *cn, void *cp, void *cf, const float *ir, long n, const float *mir, long m, int frames);
void *nv_room_new(void *cn, void *cp, void *cf, const float *ir, long n, const float *mir, long m, int frames);
void nv_part_room_set(void *h, void *room, long long frames);
void nv_part_conv(void *h, void *cn, void *cp, void *cf);
void nv_part_room_reap(void *h);
long nv_tcache_room_q(void *h, double *out, long cap);
long nv_room_tail_ir(const double *sp, const double *bq, int has_bq, int sr, int seed, double **out);
long nv_room_tail_modes(const double *sp, const double *bq, int has_bq, int sr, double **out, int *nmodes);
long nv_room_tail_device(const double *sp, const double *dv, const double *bq, int has_bq, int sr, double **out,
                         double ts, double dfb);
void nv_room_spec_scale(double *sp, double ts);
void nv_room_tail_free(double *p);
void nv_part_post(void *h, double thresh, double bend_range, double mod_cents);
void nv_part_output(void *h, long long n0, long frames, float *L, float *R, void *sv, void *sx, void *sd,
                  long long blk, double master_gain);
void *nv_rt_new();
void nv_rt_add(void *h, int src, int arg, int dst, int keep, int channel, int latch, int press);
int nv_rt_feed(void *h, int type, int ch, int a, int b, int *out, int cap);
void nv_part_gpu(void *h, void *vb, void *vbd, void *vds, void *vs, void *vz, void *cl, long gpu_min, int nthr);
// the Moog extensions' kernels: synth_voice_moogx, the GPU build's voice_block, voice_damp_set, voice_moogx_set
void nv_part_moogx(void *h, void *smx, void *vbm, void *vmd, void *vmm);
// the maps' own drum sets: their keys' region of K, how many (live.cpp's) and the song's
void nv_tcache_mapk(int base, int n, const int *ids);
// a melodic cache's drum sets' tables, for a note that borrows a kit key's strokes
void nv_tcache_stroke_kits(void *h, const double *f0, const double *seat, const unsigned long long *choke,
                           const int *skind, const double *spar);
void nv_song_mapk_base(int base);
// the Sound Canvas's display now: its text, how long shown, its page's dots
int nv_part_display(void *h, char *text, double *text_age, int *page, unsigned char *rows);
void nv_part_pipeline(void *h, int on);
int nv_part_add_patch(void *h, void *cache, long long pid, double level_db, int nbuckets, int speed, int damper_pedal,
                    int soft_drop, int soft_top, int drums, int program, const unsigned long long *choke, int channel,
                    unsigned excl, int lo, int hi, int transpose);
void nv_part_patch_range(void *h, int i, int channel, unsigned excl, int lo, int hi, int transpose);
void nv_part_patch_level(void *h, int i, double level_db, int muted);
void nv_part_patch_gone(void *h, int i, long long n0);
int nv_part_on_gpu(void *h);
void nv_part_gpu_ms(void *h, double *out);
void nv_part_reg_async(void *h);
void nv_part_reg_choirs(void *h, int nchoir, const long *bridges, double cross, int nbuff, const int *buffs);
void nv_part_reg_keys(void *h, const NoteClass *k);
void nv_part_swap_bank_keys(void *h, const NoteClass *k);
void nv_part_swap_bank(void *h, const StringMode *modes, int M, const double *k6, int top, int pedals, const int *note,
                     int nchoir, const long *cbr, double cross, int nbuff, const int *buffs);
void nv_part_swap(void *h, int pi, void *cache, int program, int drums, int nbuckets, int speed, int damper_pedal,
                int soft_drop, int soft_top, int detune_wheel, const unsigned long long *choke, const int *reg_note);
void nv_part_set(void *h, int what, double v);
void nv_part_stats(void *h, double *out);
void nv_part_panic(void *h, long long n0);
void nv_rt_del(void *h, int i);
long nv_part_govern(void *h, double ms, double budget_ms, long long n);
long nv_part_partials_shed(void *h);
long nv_part_dropped(void *h);
void *nv_cl_new(const char *dir, const int *sizes, char *err, int errlen);
void nv_part_register(void *h, const StringMode *modes, int M, double kappa, double knock, double fall, double fl,
                    int top, double beta, int pedals, double rel, double full_db_s, double residual, double ln10_20,
                    long long blk, const int *reg_note);
}

#include "hostint.h"
using namespace nvh;

// A MESSENGER's OUTPUT (live.open_messenger): what the audio thread queues,
// written to the raw MIDI device by a thread of its own -- or, in --test,
// logged with the block it was sent in (g_msgr_blk)
inline std::atomic<long long> g_msgr_blk{0};
struct MsgrOut {
    int fd = -1;
    FILE *log = nullptr;
    std::mutex mu;
    std::condition_variable cv;
    std::vector<uint8_t> q;
    static void send(void *ctx, const uint8_t *b, int n)
    {
        MsgrOut *o = (MsgrOut *)ctx;
        if (o->log) {
            fprintf(o->log, "%lld", g_msgr_blk.load());
            for (int i = 0; i < n; i++)
                fprintf(o->log, " %d", b[i]);
            fprintf(o->log, "\n");
            return;
        }
        {
            std::lock_guard<std::mutex> lk(o->mu);
            o->q.insert(o->q.end(), b, b + n);
        }
        o->cv.notify_one();
    }
    void start()
    {
        std::thread([this] {
            for (;;) {
                std::vector<uint8_t> w;
                {
                    std::unique_lock<std::mutex> lk(mu);
                    cv.wait(lk, [this] { return !q.empty(); });
                    w.swap(q);
                }
                size_t off = 0;
                while (off < w.size()) {
                    ssize_t r = ::write(fd, w.data() + off, w.size() - off);
                    if (r <= 0)
                        break;              // (a message lost: never the audio thread's wait)
                    off += (size_t)r;
                }
            }
        }).detach();
    }
};

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

inline std::atomic<bool> g_stop(false);
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
inline std::atomic<long> tid(0);
inline std::atomic<long long> busy_since(0);    // steady_clock ns at the running block's start, 0 between
inline std::atomic<bool> promoted(false);
inline std::atomic<int> dropped(0);

inline long long now_ns()
{
    return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

inline void demote()
{
    if (!promoted.exchange(false))
        return;
    sched_param p{};
    p.sched_priority = 0;
    sched_setscheduler((pid_t)tid.load(), SCHED_OTHER | RESET_ON_FORK, &p);
    dropped++;
}

inline void on_xcpu(int) { demote(); }

// rtsched.rtkit_promote: busctl, naming the pid, so it works from any process
inline std::string rtkit(long pid, long t, int prio)
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
inline std::string promote(int prio)
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
inline void on_signal(int) { g_stop = true; }

struct Midi {
    int type, ch, a, b;
    std::vector<uint8_t> x;     // an exclusive's bytes, between F0 and F7 (type 6)
};

// raw MIDI bytes from a device file: running status; note-on at velocity 0 a
// note-off; channel aftertouch type 3, a key's polytouch 7; an exclusive (F0 .. F7) type 6, its
// bytes; realtime and the other system messages skipped
struct MidiParse {
    int status = 0, need = 0, got = 0;
    uint8_t d[2];
    bool insx = false;                                  // inside an exclusive
    std::vector<uint8_t> sx;
    // n bytes, each message made given to push (a Midi)
    template <class F> void feed(const uint8_t *buf, long n, F &&push)
    {
        for (long i = 0; i < n; i++) {
            uint8_t c = buf[i];
            if (c >= 0xF8)
                continue;                               // realtime: clock, sensing
            if (c == 0xF7 && insx) {                    // its end: to the part
                insx = false;
                push(Midi{6, -1, 0, 0, sx});
                continue;
            }
            if (c >= 0x80) {
                insx = c == 0xF0;                       // (any other status ends one, cut short: dropped)
                sx.clear();
                status = c < 0xF0 ? c : 0;
                int hi = c & 0xF0;
                need = (hi == 0xC0 || hi == 0xD0) ? 1 : 2;
                got = 0;
                continue;
            }
            if (!status) {
                if (insx && sx.size() < 65536)
                    sx.push_back(c);                    // inside an exclusive
                continue;
            }
            d[got++] = c;
            if (got < need)
                continue;
            got = 0;
            int hi = status & 0xF0, ch = status & 0x0F;
            Midi m{-1, ch, d[0], need > 1 ? d[1] : 0, {}};
            if (hi == 0x90 && d[1] > 0)
                m.type = 0;
            else if (hi == 0x80 || hi == 0x90)
                m.type = 1;
            else if (hi == 0xB0)
                m.type = 2;
            else if (hi == 0xD0)
                m.type = 3;
            else if (hi == 0xA0)
                m.type = 7;                             // a key's polytouch (a the key, b the value)
            else if (hi == 0xE0) {
                m.type = 4;                             // the pitch wheel, -8192..8191
                m.a = ((d[1] << 7) | d[0]) - 8192;
            } else if (hi == 0xC0)
                m.type = 5;                             // a program change
            if (m.type >= 0)
                push(std::move(m));
        }
    }
};

// THE RAW MIDI DEVICES THERE ARE NOW (live.input_names): (path, name) -- the
// name ALSA gives /proc/asound/cardC/midiD's first line ("USB Midi")
inline std::vector<std::pair<std::string, std::string>> midi_devices()
{
    std::vector<std::pair<std::string, std::string>> ds;
    for (int c = 0; c < 32; c++)
        for (int d = 0; d < 4; d++) {
            char p[64], q[64];
            snprintf(p, sizeof p, "/dev/snd/midiC%dD%d", c, d);
            if (access(p, R_OK) != 0)
                continue;
            snprintf(q, sizeof q, "/proc/asound/card%d/midi%d", c, d);
            std::string nm;
            if (FILE *f = fopen(q, "r")) {
                char ln[256];
                if (fgets(ln, sizeof ln, f))
                    nm = ln;
                fclose(f);
            }
            while (!nm.empty() && (nm.back() == '\n' || nm.back() == ' '))
                nm.pop_back();
            ds.push_back(std::make_pair(std::string(p), nm.empty() ? std::string(p + 9) : nm));
        }
    return ds;
}

// THE INPUTS OPEN (live.midi_inputs: several, merged): the devices wanted
// (path, name) -- the panel's I changes them, gen counts the changes -- and
// those the reader has open now
struct MidiIns {
    std::mutex mu;
    std::vector<std::pair<std::string, std::string>> want, open;
    std::atomic<int> gen{0};
    std::string err;                            // (the last that would not open, or went away)
    void set(const std::vector<std::pair<std::string, std::string>> &w)
    {
        std::lock_guard<std::mutex> lk(mu);
        want = w;
        gen++;
    }
};

// ...read on one thread: each wanted device opened (non-blocking), each read
// in turn through its own parser (running status is a device's own), a
// device that goes away closed and dropped
inline void midi_reader_ins(MidiIns *ins, std::mutex *mu, std::vector<Midi> *q)
{
    struct In {
        int fd;
        std::string name;
        MidiParse mp;
    };
    std::map<std::string, In> open;
    int seen = -1;
    uint8_t buf[256];
    auto publish = [&]() {
        std::vector<std::pair<std::string, std::string>> o;
        for (auto &kv : open)
            o.push_back(std::make_pair(kv.first, kv.second.name));
        std::lock_guard<std::mutex> lk(ins->mu);
        ins->open = o;
    };
    while (!g_stop) {
        if (ins->gen.load() != seen) {
            std::vector<std::pair<std::string, std::string>> w;
            {
                std::lock_guard<std::mutex> lk(ins->mu);
                w = ins->want;
                seen = ins->gen.load();
            }
            for (auto it = open.begin(); it != open.end();) {
                bool keep = false;
                for (auto &x : w)
                    keep = keep || x.first == it->first;
                if (keep) {
                    ++it;
                } else {
                    ::close(it->second.fd);
                    it = open.erase(it);
                }
            }
            for (auto &x : w)
                if (!open.count(x.first)) {
                    int f = ::open(x.first.c_str(), O_RDONLY | O_NONBLOCK);
                    if (f >= 0) {
                        In in;
                        in.fd = f;
                        in.name = x.second;
                        open.emplace(x.first, std::move(in));
                    } else {
                        std::lock_guard<std::mutex> lk(ins->mu);
                        ins->err = x.second + ": " + strerror(errno);
                    }
                }
            publish();
        }
        bool any = false;
        for (auto it = open.begin(); it != open.end();) {
            ssize_t n = read(it->second.fd, buf, sizeof buf);
            if (n > 0) {
                any = true;
                it->second.mp.feed(buf, (long)n, [&](Midi &&m) {
                    std::lock_guard<std::mutex> lk(*mu);
                    q->push_back(std::move(m));
                });
                ++it;
            } else if (n < 0 && errno != EAGAIN && errno != EINTR) {
                {                                       // (unplugged: gone, and no longer wanted)
                    std::lock_guard<std::mutex> lk(ins->mu);
                    ins->err = it->second.name + " went away";
                    const std::string path = it->first;
                    ins->want.erase(std::remove_if(ins->want.begin(), ins->want.end(),
                                                   [&](const std::pair<std::string, std::string> &x) {
                                                       return x.first == path;
                                                   }),
                                    ins->want.end());
                }
                ::close(it->second.fd);
                it = open.erase(it);
                publish();
            } else {
                ++it;
            }
        }
        if (!any)
            usleep(1000);
    }
    for (auto &kv : open)
        ::close(kv.second.fd);
}

inline void midi_reader(int fd, std::mutex *mu, std::vector<Midi> *q)
{
    MidiParse mp;
    uint8_t buf[256];
    while (!g_stop) {
        ssize_t n = read(fd, buf, sizeof buf);
        if (n <= 0) {
            usleep(1000);
            continue;
        }
        mp.feed(buf, (long)n, [&](Midi &&m) {
            std::lock_guard<std::mutex> lk(*mu);
            q->push_back(std::move(m));
        });
    }
}

inline std::string opt(int argc, char **argv, const char *name, const char *def)
{
    std::string p = std::string("--") + name + "=";
    for (int i = 1; i < argc; i++)
        if (!strncmp(argv[i], p.c_str(), p.size()))
            return argv[i] + p.size();
    return def;
}

// THE LIVE HOST (host step 2a): main()'s locals its members, its body
// run() -- behaviour unchanged; the split into open, render and the
// devices follows
struct nv_host {
    struct PartAt {
        int pi, channel;
        bool drums;
        int program, sid, posted;
        int var = 0, posted_var = 0;            // its variation (live.Patch.variation), 0 the capital tone
        // the last asked for and not yet swapped in (-1 none): a program
        // change is against it, not against what sounds -- else a pick back
        // to the sounding patch while another builds is dropped, and the
        // build lands over it
        int want = -1, want_var = 0;
        bool want_dr = false;
        // ITS PLACE ON THE KEYBOARD (livetui's PARTS columns), the host's copy
        // of the patch's: the channel bits it leaves out (a drum set beside
        // it: 10's), its keys, transpose, level, mute; taken away (its index
        // kept); its part id (the slab's keys)
        unsigned excl = 0;
        int lo = 0, hi = 127, tr = 0;
        double level = 0.0;
        bool muted = false, gone = false;
        long long pid = 1;
        int fixed = -1;                         // its fixed touch (live's part.fixed_touch: -1 the patch's way)
        double drive = -1.0;                    // an organ's drive knob (live's Part.drive: <0 the voice's)
        bool is(int prog, bool dr, int v) const
        {
            return want >= 0 ? want == prog && want_dr == dr && want_var == v
                             : program == prog && drums == dr && var == v;
        }
    };
    void ask(size_t i, int prog, bool dr, int v)
    {
        if (!pats[i].is(prog, dr, v))
            pats[i].drive = -1.0;               // (a new program: its drive the voice's, as the slab's swap has it)
        pats[i].want = prog;
        pats[i].want_dr = dr;
        pats[i].want_var = v;
        reqs.push_back(Req{i, prog, dr, v});
    }
    // a request done (swapped in, or not native): the part wants nothing more
    // if it was the last asked
    void answered(size_t i, int prog, bool dr, int v)
    {
        PartAt &pa = pats[i];
        if (pa.want == prog && pa.want_dr == dr && pa.want_var == v)
            pa.want = -1;
    }
    struct Req {
        size_t i;
        int prog;
        bool dr;
        int var = 0;
    };
    Export E;
    double SR;
    int program;
    bool drums;
    std::function<const int *(int prog, int var)> prec;
    const int * pp;
    std::string tname;
    int raga_sa;
    int raga_nsw;
    double raga_sw[12];
    std::string east;
    std::vector<std::vector<double>> ptab;
    std::vector<int> psa;
    std::vector<int> pnsw;
    std::vector<std::array<double, 12>> psw;
    std::function<const double *(int prog, bool dr)> tune_for;
    std::string tl_;
    std::function<void(void *c, int prog, bool dr)> raga_for;
    std::vector<char> retuned;
    std::function<void(int p)> retune;
    std::vector<int> kmap;
    std::vector<const NoteClass *> K;
    NoteIn t;
    void * cache;
    int bank;
    long built;
    long slots;
    void * part;
    bool nodrums;
    int split;
    int bank0;
    std::vector<PartAt> pats;
    std::map<int, void *> caches;
    bool dry;
    void * conv_cn;
    void * conv_cp;
    void * conv_cf;
    bool noreg;
    bool anyreg;
    bool reg_on;
    void * fn[3];
    double master;
    std::string gopt;
    bool pipe;
    std::string routes_file;
    void * router;
    std::string pks;
    std::array<int, 7> pedal_route;
    std::function<void(int type, int ch, int a, int b)> event;
    std::mutex cmu;
    std::map<int, int> bmsb;
    std::map<int, int> blsb;
    bool rxbank;
    const char * tmap_;
    std::atomic<int> default_map{0};        // THE STANDARD (live.std_map): the map CC32 0 reads in -- global 13
    std::function<void(int type, int ch, int a, int b)> latch;
    std::function<bool(const uint8_t *x, int n)> sys_reset;
    std::function<int(int p, int v)> var_entry_of;
    std::function<const NoteClass *(int prog, int var)> cls60;
    std::function<void *(int prog, const NoteClass *k)> build_drone;
    std::function<void(int pi, int prog, bool dr, int var)> attach_drone;
    std::function<void *(int prog, bool dr, int var)> build;
    // percussion_map.kit_in_map: the drum set a program selects in map mp --
    // the map's own (a drum program 128 + j) where it has one, else the
    // program; and a drum set's name, a map's own included
    int kit_in_map(int prog, int mp) const;
    std::string kit_name(int prog) const;
    std::atomic<int> shown_program;
    std::atomic<int> shown_var;
    std::atomic<int> last_ctl_code;
    std::atomic<long long> last_ctl_ns;
    std::function<void(size_t i, int prog, bool dr, int var, void *c)> swap;
    std::vector<Req> reqs;
    bool told_old;
    std::function<void(int ch, int prog)> asked;
    std::function<void()> reset_asked;
    std::function<void()> landed;
    std::function<int(std::vector<Req> &rq)> settle;
    std::string room_now;
    std::vector<void *> cache_grave;
    std::function<int(double *bq)> room_band_q;
    // (tl: a GS reverb's tail -- gain, time scale, delay feedback < 0 none --
    // NULL the room's plain one: live.room_irs's tail)
    std::function<void *(const Export::RoomData &rd, const double *bq, int has, const double *tl)> room_tail;
    std::function<bool(const std::string &name, const double *tl, void **tail,
                       const std::function<void(size_t, int, bool, int, void *)> &give)> room_switch;
    // A SEQUENCER's GS REVERB (live._gs_reverb): its macro the room, its level,
    // time and delay feedback the tail -- over the panel's room (user_room)
    // until a GS reset, or the panel moved; room_tl the tail in use. A request
    // from a block's events (gs_want) is the builder's when playing, the next
    // block's in step (nvlive --test, as live's check does it)
    std::map<int, int> gs_rev;
    std::string user_room;
    double room_tl[3] = {1.0, 1.0, -1.0};
    bool room_tl_on = false;
    bool gs_want = false;
    std::string gs_want_room;
    double gs_want_tl[3] = {1.0, 1.0, -1.0};
    bool gs_want_tl_on = false;
    std::function<void(int kind, int value)> gs_reverb;
    // THE TUNER, switched while playing (livetui's TUNER column): the table
    // made again, every patch let go and the parts' built again in it on the
    // builder (as a room); notes sounding keep the tuning they were struck in
    std::function<bool(const std::string &name, const std::function<void(size_t, int, bool, int, void *)> &give)> tuner_switch;
    std::string tuner_req, tuner_now, tuner_asked;   // (asked: the panel's, for the session)
    std::atomic<bool> retune_bank{false};             // (the free strings' bank too, at the next swap)
    void set_tuner(const std::string &name);
    // THE EASTERN TUNING, switched while playing (livetui's E: live.set_eastern):
    // the parts whose voice is an Indian instrument built again in it -- or
    // back in their own tuner, the spec empty -- on the builder; the rest
    // untouched; notes sounding keep the tuning they were struck in
    std::function<bool(const std::string &spec, const std::function<void(size_t, int, bool, int, void *)> &give)> east_switch;
    std::string east_req, east_now, east_asked;      // (east_now: the builder's, under bmu)
    bool east_req_set = false;
    void set_eastern(const std::string &spec);
    bool east_part(int prog, bool drums);             // does this voice play the Eastern tuning now
    // THE SCENE (live.scene_from): each channel's captured controls as they
    // reached the part (the audio thread's), an event put past the routes
    std::map<std::pair<int, int>, int> chanlatch;
    void engine_event(int type, int ch, int a, int b);
    // THE PARTS (livetui's PARTS pane): read by the panel under parts_mu, changed
    // by posts (between two blocks); a part added built on the builder first
    // (add_req -> add_done), then added between two blocks
    std::mutex parts_mu;
    struct PartSpec {
        int program = 0, var = 0;
        bool drums = false;
        int channel = -1;
        unsigned excl = 0;
        int lo = 0, hi = 127, tr = 0;
        double level = 0.0;
        bool muted = false;
        bool metro = false;                 // (the metronome's own drum part: no row, no key)
        std::map<int, double> syn[2];       // (its knobs, layers A and B: a session's or preset's)
        int fixed = -1;                     // (its fixed touch)
        double drive = -1.0;                // (an organ's drive knob: <0 the voice's)
    };
    std::vector<PartSpec> add_req;
    std::vector<std::pair<PartSpec, void *>> add_done;
    long long next_pid = 10;
    std::vector<panel::PartRow> part_rows();
    void part_set(size_t row, int channel, int lo, int hi, int tr, double level, bool muted);
    void part_add(const PartSpec &sp);
    void part_added(const PartSpec &sp, void *c);
    bool part_layer(size_t row);
    bool part_split(size_t row, std::string &why);
    bool part_delete(size_t row, std::string &why);
    void pick_row(size_t row, int sp);
    void part_touch(size_t row, int fixed);         // (livetui.toggle_touch: 1 fixed, 0 velocity)
    void part_drive(size_t row, double v);          // (an organ's drive knob, live.set_drive: <0 the voice's)
    int drive_state(size_t row, double *out);       // (nv_part_drive_get's: 1 an organ's, 0 not, -1 unread)
    void messenger_reading(bool on);                // (livetui's M: every part reads a Messenger's chart)
    // THE ON-SCREEN CONTROLS (live's screen_controls; the session's "controls"):
    // the panel's, one sent past the routes (every channel, or its own)
    std::vector<panel::ScreenControl> screen_controls;
    void control_send(int key, int value, int channel);
    // A MOOG PART's KNOBS (livetui's synth pane): a part's panel on a layer
    // read between two blocks (its layers; 0 not a Moog), one turned, one put
    // back to the patch's, the whole sent to a Messenger
    int synth_state(size_t row, int layer, double *pn, char *own);   // (-1: not read, and never was)
    struct SynthRead {
        int n = 0;
        double pn[42];
        char own[42];
    };
    std::map<size_t, SynthRead> synth_cache;        // (row x 2 + layer: the last read -- what a quit saves)
    std::mutex synth_mu;
    void synth_set(size_t row, int layer, int knob, double v);
    void synth_forget(size_t row, int layer, int knob);
    int synth_send(size_t row);
    // THE MESSENGER (live's): one set from the panel (--messenger-out; "" none),
    // its knobs read on every part (--messenger), the chart's firmware
    std::string msgr_out;
    bool msgr_reads = false, msgr_pre107 = false;
    std::vector<std::pair<long long, std::string>> room_at;
    bool follow;
    float L[4096];
    float R[4096];
    std::string dev;
    int fd;
    MidiIns ins;                                // (the inputs open: the panel's I)
    std::vector<std::pair<std::string, std::string>> in_list;  // (the I list as last drawn: its rows' devices)
    bool cli_port = false;                      // (--port or --midi named one: the session's not opened over it)
    Alsa A;
    std::string pcmdev;
    unsigned lat;
    int r;
    std::mutex mu;
    std::vector<Midi> q;
    std::thread reader;
    bool rsync;
    bool nort;
    bool nopanel;
    std::mutex pmu;
    std::vector<std::function<void(long long)>> posted;
    panel::Snap snap;
    std::atomic<int> learning;
    std::atomic<int> learnt_ch;
    std::atomic<int> learnt_note;
    std::pair<int, int> swallow;
    long underruns;
    long over;
    long blocks;
    double worst;
    double budget;
    bool govern;
    double master_now;
    std::atomic<bool> rt_on;
    std::mutex bmu;
    std::condition_variable bcv;
    std::vector<Req> breq;
    std::vector<std::pair<Req, void *>> bdone;
    std::string room_req;
    double room_req_tl[3] = {1.0, 1.0, -1.0};   // (its tail: a GS reverb's, room_req_tl_on)
    bool room_req_tl_on = false;
    void * room_ready;
    bool room_ready_go;
    std::atomic<int> room_idx;
    std::vector<std::string> notes;
    std::function<void(const std::string &m)> note;
    std::function<void()> builder_loop;
    std::function<void()> audio;
    std::thread player;
    std::thread builder;
    long long BLK;                          // (the export's block)
    const Export::Reg *rg0;                 // (the start's register)
    int open(int argc, char **argv);        // (-1: opened, else the exit code)
    void start();                           // the workers and the builder, for playing
    // what the panel and a GUI change, between two blocks (live.post)
    void post(std::function<void(long long)> f);
    double gval[14] = {};                   // the globals as they stand (livetui.GLOBALS: the panel's g; 9 mod
                                            // rate, 10-12 the metronome: bpm, ring, level; 13 the standard)
    std::atomic<int> metro_pi{-1};          // the metronome's patch (-1 not built)
    bool metro_building = false;
    void globals_init();
    void set_global(int i, double v);
    // the patches: every program and set, and the variations, which are native
    std::vector<std::string> pnames;
    std::vector<char> pnative, vnative;
    void patches_init();
    void pick(int sp);                      // sp: a program, 128 + a set, 256 + a variation (vpv's)
    void panic();
    std::atomic<bool> builder_busy{false};
    int building();
    // THE BUILD UNDER WAY (the panel's progress): templates done of the
    // total, and what it is (bmu); total 0 none
    long bp_done = 0, bp_total = 0;
    std::string bp_name;
    bool progress(long *done, long *total, std::string *name);
    MidiParse midi_in;                      // (nv_host_midi's)
    std::mutex midi_in_mu;
    long long play_n0 = 0;                  // (nv_host_render's)
    std::vector<float> play_buf;
    // (in step, --test's: the room's tail to install after the block, the
    // programs asked for built in step; asks: a program change heard)
    void render_block(long long n0, float *buf, bool step = false);
    // --record=FILE: what was played, as it was taken -- each event, each
    // swap, and the blocks (time, slots, shed, peak) -- written by its own
    // thread (nvlive's), for a replay through --test
    // THE SESSION (live's session.json, shared with live.py; session.h):
    // read in main before the part is built, its program the part's and its
    // routes the router's; the rest applied once playing (session_apply);
    // written back at quit and every 2 s it changed (session_save)
    sess::J session;
    bool session_on = false;
    int room_asked = -1;                    // a room asked for (set_global 8), until it is the room
    std::string session_path, session_written;
    std::vector<std::array<int, 7>> session_routes;
    bool session_routes_set = false;
    void session_apply();
    void apply_setup(const sess::J &d, bool at_start);   // (a session's at the start; a preset's while playing)
    // SCENES AND PRESETS (live's scenes.json, presets.json, beside the session)
    std::vector<std::string> scene_cached;
    bool scene_inline = false;              // (no blocks to come: --test's end, read here)
    std::vector<std::string> scene_now();
    int scene_recall(const std::vector<std::string> &events);
    std::string presets_path() const, scenes_path() const;
    std::vector<std::string> pending_drawn; // a preset's stops (names), for its organ once it is swapped in
    int pending_drawn_prog = -1;
    std::vector<std::array<int, 7>> routes_replaced;     // (a preset's routes, for the panel's copy)
    sess::J session_state(const std::vector<std::array<int, 7>> &routes);
    bool session_save(const std::vector<std::array<int, 7>> &routes);
    bool recording = false;
    std::mutex rec_mu;
    std::vector<std::string> recq;
    void rec(const char *fmt, ...);
    bool asks = true;
    void *step_room = nullptr;
    bool step_room_go = false;               // (a switch to install: dry's tail is none)
    long step_swaps = 0;
    double last_step_ms = 0.0, last_out_ms = 0.0;    // (the block's events and step; its render)
    int run(int argc, char **argv);
};

#endif
