// fileplay.h -- THE FILES CARD's engine side (uiapi.cpp's): the folders and
// MIDI files on this machine; a file played LIVE into the engine as a
// sequencer drives a Sound Canvas; and a file RENDERED OFFLINE, as heard (the
// live engine in a process of its own: nvlive --test) or at best quality (the
// file renderer streamed on the GPU, nvrender --stream --gpu, then the
// room's tail, nvroomtail) -- as the Mac app's Render menu does.
//
// THE MODE a file is read in: auto (what the file itself says: a GS Reset,
// GM System On, MT-32 exclusives), gm (bank select off: GM System On before
// the file -- the reader's TUNING_GM), a Sound Canvas map (ours, sc55, sc88,
// sc88pro, sc8850: the map CC32 0 reads its banks in -- live's standard,
// the file renderer's TUNING_MAP), or cm64 (the Sound Canvas's "Init
// CM-64": the MT-32 and CM-32P sets, pans mirrored -- TUNING_CM64).
//
// PLAYED LIVE, a file takes the parts over: one per channel (the drum set
// nvlive keeps beside the first on 10), set as a preset is (apply_setup);
// the sounds its program changes ask for built first, a few at a time, so
// its notes do not fall on a build; then a GS Reset (GM System On for gm)
// and its events, each queued at its time as the keyboard's are. STOP: the
// notes let go, the pedals up.
#pragma once
#include <condition_variable>
#include <dirent.h>
#include <fcntl.h>
#include <mutex>
#include <set>
#include <strings.h>
#include <signal.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include "selfexe.h"

extern "C" {
void nv_midi_free(void *p);
double nv_midi_total(void *p);
int nv_midi_mt32(void *p);
const char *nv_midi_track_name(void *p, int i);
int nv_midi_n_findings(void *p);
const char *nv_midi_finding(void *p, int i);
int nv_midi_muxed(void *p);
int nv_roomtail_main(int argc, char **argv);    // (the room's tail, in this process: nvroomtail.cpp)
int nv_render_main(int argc, char **argv);      // (the file renderer, in this process: nvrender.cpp)
extern "C" void nv_render_progress(double *at_s, double *len_s);
extern "C" int nv_render_pass(void);
void nv_render_stop(void);
const char *nv_render_last(void);
void nv_env_set(const char *const *names, const char *const *values, int n);
const char *nv_midi_mux_line(void *p, int i);
const char *nv_midi_mt32_line(void *p, int i);
}
extern char **environ;

namespace fileplay {

using J = sess::J;

static const char *MODES[] = {"auto", "gm", "ours", "sc55", "sc88", "sc88pro", "sc8850", "cm64", "names", "mt32", "cm64u"};
// (the MT-32 family's: cm64 a Sound Canvas's Init CM-64; mt32 / cm64u the unit
// itself, its exclusives and channels -- mt32.h; all read in the SC-55 map)
static bool mt32_family(const std::string &m) { return m == "cm64" || m == "mt32" || m == "cm64u"; }
// THE MT-32's VELOCITY (the reader's TUNING_MT32_VEL): its 3/4 v + 32, in the
// CM-64 map and orchestra by names; off, the file's velocities as written
static std::atomic<bool> mt32_vel{true};
static int map_of(const std::string &mode)      // (a Sound Canvas map's number; -1 none)
{
    for (int i = 2; i <= 6; i++)
        if (mode == MODES[i])
            return i - 2;
    return -1;
}

// THE FOLDERS (nv_ui_files_dirs, the app's: an iOS app's Documents and
// tmp; here ~/Music and $TMPDIR or /tmp): where the browser starts and the
// renders go, and where a render's working files are kept
static std::string g_music_root, g_tmp_root;
static std::string home();
static bool is_dir(const std::string &p);
static std::string music_root()
{
    if (!g_music_root.empty())
        return g_music_root;
    return is_dir(home() + "/Music") ? home() + "/Music" : home();
}
static std::string tmp_root()
{
    if (!g_tmp_root.empty())
        return g_tmp_root;
    const char *t = getenv("TMPDIR");
    return t && *t ? t : "/tmp";
}
// (no helper programs where the system runs none: iOS)
#if defined(__APPLE__)
#include <TargetConditionals.h>
#endif
#if defined(TARGET_OS_IPHONE) && TARGET_OS_IPHONE
static const bool HELPERS = false;
// (nvlive.cpp's, linked into the app: an as-heard render on a host of its own in
// this process, and its stop -- where helper programs run, nvlive runs as one)
extern "C" int nv_live_render_test(int argc, char **argv);
extern "C" void nv_live_render_stop(void);
#define NV_HEARD_INPROC 1
#else
static const bool HELPERS = true;
#define NV_HEARD_INPROC 0
#endif

static std::string home()
{
    const char *h = getenv("HOME");
    return h && *h ? h : "/tmp";
}

static bool is_dir(const std::string &p)
{
    struct stat st;
    return stat(p.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

static bool slurp(const std::string &path, std::vector<uint8_t> &b)
{
    FILE *f = fopen(path.c_str(), "rb");
    if (!f)
        return false;
    b.clear();
    uint8_t buf[65536];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0)
        b.insert(b.end(), buf, buf + n);
    fclose(f);
    return true;
}

// A FOLDER: its folders, then its MIDI files, by name
static J list_dir(std::string dir)
{
    if (dir.empty() || !is_dir(dir))
        dir = music_root();
    while (dir.size() > 1 && dir.back() == '/')
        dir.pop_back();
    J o = sess::obj(), ents = sess::arr();
    std::vector<std::pair<bool, std::string>> got;
    if (DIR *d = opendir(dir.c_str())) {
        while (dirent *e = readdir(d)) {
            const std::string n = e->d_name;
            if (n.empty() || n[0] == '.')
                continue;
            const std::string full = dir + "/" + n;
            if (is_dir(full)) {
                got.push_back({true, n});
                continue;
            }
            std::string low = n;
            for (char &c : low)
                c = (char)tolower((unsigned char)c);
            auto ends = [&](const char *x) { size_t k = strlen(x); return low.size() > k && low.compare(low.size() - k, k, x) == 0; };
            if (ends(".mid") || ends(".midi") || ends(".kar") || ends(".smf") || ends(".rmi")
                || ends(".mp3") || ends(".wav") || ends(".flac"))           // (audio too: the card's player)
                got.push_back({false, n});
        }
        closedir(d);
    }
    std::sort(got.begin(), got.end(), [](const auto &a, const auto &b) {
        if (a.first != b.first)
            return a.first;
        return strcasecmp(a.second.c_str(), b.second.c_str()) < 0;
    });
    for (const auto &g : got) {
        J e = sess::obj();
        e.o["name"] = sess::str(g.second);
        e.o["dir"] = sess::boolean(g.first);
        {                                   // (an audio file: the player's, not the engine's)
            std::string low = g.second;
            for (char &c : low)
                c = (char)tolower((unsigned char)c);
            const bool au = !g.first && (low.size() > 4 && (low.compare(low.size() - 4, 4, ".mp3") == 0
                                                             || low.compare(low.size() - 4, 4, ".wav") == 0)
                                          || (low.size() > 5 && low.compare(low.size() - 5, 5, ".flac") == 0));
            e.o["audio"] = sess::boolean(au);
        }
        ents.a.push_back(e);
    }
    o.o["dir"] = sess::str(dir);
    const size_t sl = dir.rfind('/');
    o.o["parent"] = sess::str(sl == std::string::npos || dir == "/" ? "" : sl == 0 ? "/" : dir.substr(0, sl));
    o.o["home"] = sess::str(home());
    o.o["music"] = sess::str(music_root());
    o.o["entries"] = ents;
    return o;
}

// THE READER in a mode (its TUNING_GM, TUNING_CM64: read at the parse only)
static std::mutex env_mu;
static void *read_mode(const std::vector<uint8_t> &b, const std::string &mode, int *err)
{
    std::lock_guard<std::mutex> lk(env_mu);
    if (mode == "gm")
        setenv("TUNING_GM", "1", 1);
    if (mode == "cm64")
        setenv("TUNING_CM64", "1", 1);
    if (mode == "names")                // (orchestra by track names: mt32mux's, partmux.h)
        setenv("TUNING_PARTS", "names", 1);
    if (mode == "mt32" || mode == "cm64u")      // (the unit itself: mt32.h)
        setenv("TUNING_MT32", mode == "mt32" ? "mt32" : "cm64", 1);
    if (!mt32_vel)
        setenv("TUNING_MT32_VEL", "0", 1);
    if (mode == "look") {               // (inspect's: an MT-32 exclusive counted, not refused; the file check)
        setenv("TUNING_MT32_SEEN", "1", 1);
        setenv("TUNING_CHECK", "1", 1);
    }
    void *m = nv_midi_read(b.data(), (long long)b.size(), err);
    unsetenv("TUNING_GM");
    unsetenv("TUNING_CM64");
    unsetenv("TUNING_PARTS");
    unsetenv("TUNING_MT32");
    unsetenv("TUNING_MT32_VEL");
    unsetenv("TUNING_MT32_SEEN");
    unsetenv("TUNING_CHECK");
    return m;
}

// WHAT A FILE IS: its length, the channels it plays, its programs, and the
// mode it asks for (auto's: a GS Reset GS, GM System On GM, MT-32 exclusives
// the CM-64 map; none, GS in the Setup card's standard)
struct Info {
    bool ok = false;
    std::string err, detected, why;
    double total = 0.0;
    std::vector<int> chans;
    int programs = 0, sysex = 0;
    std::vector<std::string> findings;  // the file check's (filecheck.h: mt32check's)
    bool muxed = false;                 // every note stamped with its own program
    std::string suggest, suggest_why;   // a mode worth trying (orchestra by names)
    std::vector<std::string> report;    // what a mode did with it (inspect's mode: the mux's, the unit's)
};
static Info inspect(const std::string &path, const std::string &mode = "")
{
    Info I;
    std::vector<uint8_t> b;
    if (!slurp(path, b)) {
        I.err = "cannot read the file";
        return I;
    }
    int err = 0;
    void *m = read_mode(b, "look", &err);
    if (!m) {
        I.err = "the reader refused it (" + std::to_string(err) + ")";
        return I;
    }
    I.ok = true;
    I.total = nv_midi_total(m);
    bool gsr = false, gm = false, mt = false, banked = false;
    std::vector<char> used(16, 0);
    std::set<std::pair<int, int>> progs;
    std::vector<uint8_t> x(65536);
    const int ne = nv_midi_n_events(m);
    for (int i = 0; i < ne; i++) {
        int iv[4];
        double t;
        nv_midi_event(m, i, iv, &t);
        if (iv[0] == 0 && iv[1] >= 0 && iv[1] < 16 && iv[3] > 0)
            used[(size_t)iv[1]] = 1;
        else if (iv[0] == 5)
            progs.insert({iv[1], iv[2]});
        else if (iv[0] == 2 && iv[2] == 0 && iv[3] > 0)
            banked = true;
        else if (iv[0] == 6) {
            I.sysex++;
            const int n = nv_midi_sysex(m, iv[2], x.data(), (int)x.size());
            const uint8_t *d = x.data();
            if (n >= 7 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && d[4] == 0x40 && d[5] == 0x00 && d[6] == 0x7F)
                gsr = true;
            if (n >= 4 && d[0] == 0x7E && d[2] == 0x09 && (d[3] == 0x01 || d[3] == 0x03))
                gm = true;
        }
    }
    // AN MT-32 FILE: its own exclusives (the reader passed them over), or
    // mt32check's tell, a track named 'Master Parameters' (the sequencer's
    // MT-32 setup track; a file with no exclusives of its own)
    const int nmt = nv_midi_mt32(m);
    bool master = false;
    for (int i = 0; const char *nm = nv_midi_track_name(m, i); i++) {
        std::string low(nm);
        for (char &c : low)
            c = (char)tolower((unsigned char)c);
        master = master || low.rfind("master parameters", 0) == 0;
    }
    mt = nmt > 0 || master;
    int fights = 0, named = 0;
    for (int i = 0; const char *f = nv_midi_finding(m, i); i++) {
        I.findings.push_back(f);
        fights += strstr(f, "tracks write controllers") != nullptr || strstr(f, "carries named instrument") != nullptr;
    }
    for (int i = 0; const char *nm = nv_midi_track_name(m, i); i++)
        named += nm[0] != 0;
    I.muxed = nv_midi_muxed(m) == 1;
    nv_midi_free(m);
    // ORCHESTRA BY NAMES worth trying: named parts sharing channels (the
    // check's controller fights, a named part on the drum channel), or more
    // named tracks than channels -- an MT-32 era orchestral file's shape
    if (!I.muxed && (fights > 0 || named > 16) && named >= 4) {
        I.suggest = "names";
        I.suggest_why = fights ? "its named parts share channels" : "it names more parts than there are channels";
    }
    // ...and what the mode asked for would do with it (the mux's parts, the unit's report)
    if (mode == "names" || mode == "mt32" || mode == "cm64u") {
        int e2 = 0;
        if (void *q = read_mode(b, mode, &e2)) {
            for (int i = 0; const char *l = mode == "names" ? nv_midi_mux_line(q, i) : nv_midi_mt32_line(q, i); i++)
                I.report.push_back(l);
            nv_midi_free(q);
        }
    }
    for (int c = 0; c < 16; c++)
        if (used[(size_t)c])
            I.chans.push_back(c);
    I.programs = (int)progs.size();
    if (gsr) {
        I.detected = "gs";
        I.why = "it sends a GS Reset";
    } else if (mt && nmt > 0) {
        I.detected = "mt32";            // (its own exclusives: written for the unit, which reads them)
        I.why = "it sends MT-32 messages, which a real MT-32 reads";
    } else if (mt) {
        I.detected = "cm64";
        I.why = "its 'Master Parameters' track: an MT-32 sequencer's";
    } else if (gm) {
        I.detected = "gm";
        I.why = "it sends GM System On";
    } else {
        I.detected = "gs";
        I.why = banked ? "it selects banks, with no reset" : "it says nothing: plain General MIDI";
    }
    return I;
}

// THE FILE's PARTS: one per channel, as a Sound Canvas's -- the session's
// first part's settings for each (its tuner, its room), program 1, every key;
// 10 the drum set nvlive keeps beside the first, else one of its own
static void file_parts(nv_host *h, J &st)
{
    J *ps = st.get("parts") ? &st.o["parts"] : nullptr;
    J first = ps && ps->is(J::ARR) && !ps->a.empty() ? ps->a[0] : sess::obj();
    for (const char *k : {"synth", "synth_b", "drive", "fixed_touch", "bank", "drawn"})
        first.o.erase(k);
    first.o["drawn"] = sess::arr();
    bool kept_drums = false;
    {
        std::lock_guard<std::mutex> lk(h->parts_mu);
        for (const auto &pa : h->pats)
            kept_drums = kept_drums || (!pa.gone && pa.pid == 2 && pa.drums);
    }
    J a = sess::arr();
    for (int ch = 0; ch < 16; ch++) {
        if (ch == 9 && kept_drums)
            continue;
        J p = first;
        p.o["program"] = sess::integer(0);
        p.o["drums"] = sess::boolean(ch == 9);
        p.o["channel"] = sess::integer(ch);
        p.o["lo"] = sess::integer(0);
        p.o["hi"] = sess::integer(127);
        p.o["transpose"] = sess::integer(0);
        p.o["level_db"] = sess::real(0.0);
        p.o["muted"] = sess::boolean(false);
        a.a.push_back(p);
    }
    st.o["parts"] = a;
}

static const uint8_t GS_RESET[] = {0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41};

static bool wait_built(nv_host *h, const std::atomic<bool> &stop, double secs)
{
    const auto t0 = std::chrono::steady_clock::now();
    std::this_thread::sleep_for(std::chrono::milliseconds(60));
    while (!stop && !g_stop && h->building() > 0) {
        if (std::chrono::steady_clock::now() - t0 > std::chrono::duration<double>(secs))
            return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(40));
    }
    return !stop && !g_stop;
}

// ---- PLAYED LIVE
struct Player {
    std::mutex mu;
    std::thread th;
    std::atomic<bool> stop{false}, busy{false};
    std::string path, name, mode, stage, msg;
    std::atomic<double> pos{0.0};
    double total = 0.0;
    int saved_map = -1;

    J state()
    {
        std::lock_guard<std::mutex> lk(mu);
        J o = sess::obj();
        o.o["busy"] = sess::boolean(busy);
        o.o["path"] = sess::str(path);
        o.o["name"] = sess::str(name);
        o.o["mode"] = sess::str(mode);
        o.o["stage"] = sess::str(stage);
        o.o["msg"] = sess::str(msg);
        o.o["pos"] = sess::real(std::floor(pos.load() * 10.0) / 10.0);
        o.o["total"] = sess::real(total);
        return o;
    }
    void say(const std::string &st)
    {
        std::lock_guard<std::mutex> lk(mu);
        stage = st;
    }

    void halt(nv_host *h)
    {
        stop = true;
        if (th.joinable())
            th.join();
        stop = false;
        (void)h;
    }

    void play(nv_host *h, const std::string &p, std::string md)
    {
        halt(h);
        std::vector<uint8_t> b;
        Info I = inspect(p);
        {
            std::lock_guard<std::mutex> lk(mu);
            path = p;
            name = p.substr(p.rfind('/') + 1);
            msg.clear();
            if (!I.ok || !slurp(p, b)) {
                msg = I.ok ? "cannot read the file" : I.err;
                return;
            }
            if (md == "auto" || md.empty())
                md = I.detected == "gs" ? "" : I.detected;     // ("": GS in the Setup card's standard)
            mode = md.empty() ? "gs" : md;
            total = I.total;
        }
        int err = 0;
        void *m = read_mode(b, md, &err);
        if (!m) {
            std::lock_guard<std::mutex> lk(mu);
            msg = "the reader refused it (" + std::to_string(err) + ")";
            return;
        }
        // its events, copied: (time, the engine's event)
        std::vector<std::pair<double, Midi>> evs;
        std::vector<uint8_t> x(65536);
        const int ne = nv_midi_n_events(m);
        evs.reserve((size_t)ne);
        for (int i = 0; i < ne; i++) {
            int iv[4];
            double t;
            nv_midi_event(m, i, iv, &t);
            Midi ev{iv[0], iv[1], iv[2], iv[3], {}};
            ev.v = nv_midi_event_x(m, i);
            if (iv[0] == 6) {
                const int n = nv_midi_sysex(m, iv[2], x.data(), (int)x.size());
                if (n <= 0 || n > (int)x.size())
                    continue;
                ev.x.assign(x.begin(), x.begin() + n);
            }
            evs.push_back({t, std::move(ev)});
        }
        const unsigned stm = nv_host_stamp_rule(h, m);     // (its stamped channels: a muxed file's)
        // ITS OCTAVES (A5): only those its notes use built, while it plays --
        // not where its programs are read another way (the MT-32 family's
        // tones, an orchestra by its tracks' names): there, every octave
        const bool octs = !mt32_family(md) && md != "names";
        if (octs)
            h->file_octaves(m, false);          // (a part a channel: file_parts)
        nv_midi_free(m);
        busy = true;
        pos = 0.0;
        th = std::thread([this, h, md, stm, octs, evs = std::move(evs)]() mutable {
            run(h, md, stm, evs);
            if (octs)
                h->file_octaves_off();          // (its patches finished whole: live play after it)
        });
    }

    void run(nv_host *h, const std::string &md, unsigned stm, std::vector<std::pair<double, Midi>> &evs)
    {
        // 1: THE PARTS, one per channel
        say("setting up the parts");
        {
            J st = h->session_state(h->E.routes);
            file_parts(h, st);
            h->apply_setup(st, false);
        }
        wait_built(h, stop, 120.0);
        // 2: THE MAP its banks are read in (live's standard), put back at the end
        const int mp = mt32_family(md) ? 1 : map_of(md);
        saved_map = -1;
        if (mp >= 0) {
            saved_map = (int)lround(nv_host_global(h, 13));
            nv_host_set_global(h, 13, mp);
        }
        // 3: ITS SOUNDS BUILT FIRST: each channel's programs (with their banks),
        // a round at a time -- a channel's k-th program in round k
        std::vector<std::vector<std::array<int, 3>>> want(16);
        {
            int msb[16] = {}, lsb[16] = {};
            for (const auto &e : evs) {
                const Midi &v = e.second;
                if (v.ch < 0 || v.ch >= 16)
                    continue;
                if (v.type == 2 && v.a == 0)
                    msb[v.ch] = v.b;
                else if (v.type == 2 && v.a == 32)
                    lsb[v.ch] = v.b;
                else if (v.type == 5) {
                    std::array<int, 3> k{msb[v.ch], lsb[v.ch], v.a};
                    auto &w = want[(size_t)v.ch];
                    if (std::find(w.begin(), w.end(), k) == w.end())
                        w.push_back(k);
                }
            }
        }
        size_t rounds = 0, nprog = 0;
        for (const auto &w : want) {
            rounds = std::max(rounds, w.size());
            nprog += w.size();
        }
        size_t done = 0;
        for (size_t k = 0; k < rounds && !stop && !g_stop; k++) {
            for (int c = 0; c < 16; c++) {
                const auto &w = want[(size_t)c];
                if (k >= w.size())
                    continue;
                h->enqueue(Midi{2, c, 0, w[k][0], {}});
                h->enqueue(Midi{2, c, 32, w[k][1], {}});
                h->enqueue(Midi{5, c, w[k][2], 0, {}});
                done++;
            }
            say("building the file's sounds: " + std::to_string(done) + " of " + std::to_string(nprog));
            wait_built(h, stop, 180.0);
        }
        // 3b: ...AND IN EACH OTHER ROOM IT PLAYS IN (its reverb changes), built
        // ahead: a change of room then a swap at its block, not a rebuild
        if (!stop && !g_stop) {
            say("building the file's sounds in its other rooms");
            h->file_rooms_prebuild();
            wait_built(h, stop, 300.0);
        }
        // 4: A RESET (the file's own mode follows at its start), then its events
        if (!stop && !g_stop) {
            if (md != "gm") {
                Midi r{6, -1, 0, 0, {}};
                r.x.assign(GS_RESET, GS_RESET + sizeof GS_RESET);
                h->enqueue(std::move(r));
            }
            wait_built(h, stop, 60.0);
            std::this_thread::sleep_for(std::chrono::milliseconds(150));
        }
        say("playing");
        // ITS STAMPED CHANNELS: a part's CC7, CC11 and pan stamped before
        // each of its notes set that note's, not the other parts' sounding
        // on the channel (the file render's onset rule), until it stops
        nv_host_stamped(h, stm);
        const auto t0 = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
        for (auto &e : evs) {
            if (stop || g_stop)
                break;
            const auto at = t0 + std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(e.first));
            for (;;) {
                const auto now = std::chrono::steady_clock::now();
                if (now >= at || stop || g_stop)
                    break;
                std::this_thread::sleep_for(std::min<std::chrono::steady_clock::duration>(at - now, std::chrono::milliseconds(20)));
                pos = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            }
            if (stop || g_stop)
                break;
            h->enqueue(std::move(e.second));
            pos = e.first;
        }
        // the tail rings out, unless stopped
        for (int i = 0; i < 30 && !stop && !g_stop; i++) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            pos = std::min(total, std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count());
        }
        // STOPPED: the notes let go, every channel's pedals up and wheel centred
        h->file_report();                       // (its notes missed, its patches' size: the A5 checks)
        h->panic();
        for (int c = 0; c < 16; c++) {
            for (int cc : {64, 66, 67})
                h->enqueue(Midi{2, c, cc, 0, {}});
            h->enqueue(Midi{4, c, 0, 0, {}});
        }
        if (saved_map >= 0)
            nv_host_set_global(h, 13, saved_map);
        nv_host_stamped(h, 0);
        {
            std::lock_guard<std::mutex> lk(mu);
            stage = stop ? "stopped" : "played to the end";
        }
        busy = false;
    }
};

// ---- RENDERED OFFLINE
struct Render {
    std::mutex mu;
    std::thread th;
    std::atomic<bool> busy{false}, stopped{false};
    std::atomic<pid_t> pid{-1};
    std::string kind, name, stage, last, out, msg, ask, ask_why;
    bool whole_ = false;                    // (a best-quality render's: rendered whole, as asked)
    double t0 = 0.0, t1 = 0.0;

    J state()
    {
        std::lock_guard<std::mutex> lk(mu);
        J o = sess::obj();
        o.o["busy"] = sess::boolean(busy);
        o.o["kind"] = sess::str(kind);
        o.o["name"] = sess::str(name);
        // (a best-quality render's passes, numbered: a streamed one reads the song,
        // renders it, adds the room; a whole one renders, adds the room)
        std::string sg = stage;
        if (busy && inproc_on && stage == "rendering, streamed on the GPU")
            sg = nv_render_pass() == 1 ? "1/3 reading the song" : "2/3 rendering, streamed on the GPU";
        else if (stage == "adding the room")
            sg = kind == "best" && whole_ ? "2/2 adding the room" : "3/3 adding the room";
        else if (stage == "rendering whole (the file renderer)")
            sg = "1/2 rendering whole (the file renderer)";
        o.o["stage"] = sess::str(sg);
        o.o["last"] = sess::str(last);
        o.o["out"] = sess::str(out);
        o.o["msg"] = sess::str(msg);
        o.o["ask"] = sess::str(ask);
        o.o["ask_why"] = sess::str(ask_why);
        const double e = (busy ? std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count() : t1) - t0;
        o.o["secs"] = sess::integer(t0 > 0 ? (long long)e : 0);
        double at = 0.0, len = 0.0;         // (the file renderer's place in the song, while it runs)
        if (busy && inproc_on)
            nv_render_progress(&at, &len);
        o.o["at"] = sess::integer((long long)at);
        o.o["len"] = sess::integer(len > 0.0 ? (long long)ceil(len) : 0);
        return o;
    }
    void say(const std::string &st)
    {
        std::lock_guard<std::mutex> lk(mu);
        stage = st;
        last.clear();
    }

    // one step, in its own process group (a STOP kills it whole), capped in
    // memory where systemd can (a step that would take the machine down is
    // stopped instead); its output's last line kept as it comes. Its exit
    // status, or -1 not run, -2 stopped
    int step(const std::vector<std::string> &args, const std::vector<std::string> &env_add)
    {
        std::vector<std::string> av;
        if (access("/usr/bin/systemd-run", X_OK) == 0)
            av = {"/usr/bin/systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=3500M", "--"};
        av.insert(av.end(), args.begin(), args.end());
        std::vector<char *> ap;
        for (auto &s : av)
            ap.push_back(&s[0]);
        ap.push_back(nullptr);
        std::vector<std::string> ev;
        for (char **e = environ; *e; e++) {
            bool over = false;
            for (const auto &a : env_add)
                over = over || strncmp(*e, a.c_str(), a.find('=') + 1) == 0;
            if (!over)
                ev.push_back(*e);
        }
        ev.insert(ev.end(), env_add.begin(), env_add.end());
        std::vector<char *> ep;
        for (auto &s : ev)
            ep.push_back(&s[0]);
        ep.push_back(nullptr);
        int fds[2];
        if (pipe(fds) != 0)                     // (pipe2 is Linux's: closed on exec by hand, as everywhere)
            return -1;
        fcntl(fds[0], F_SETFD, FD_CLOEXEC);
        fcntl(fds[1], F_SETFD, FD_CLOEXEC);
        posix_spawn_file_actions_t fa;
        posix_spawn_file_actions_init(&fa);
        posix_spawn_file_actions_adddup2(&fa, fds[1], 1);
        posix_spawn_file_actions_adddup2(&fa, fds[1], 2);
        posix_spawn_file_actions_addopen(&fa, 0, "/dev/null", O_RDONLY, 0);
        posix_spawnattr_t at;
        posix_spawnattr_init(&at);
        posix_spawnattr_setflags(&at, POSIX_SPAWN_SETPGROUP);
        posix_spawnattr_setpgroup(&at, 0);
        pid_t p = -1;
        const int r = posix_spawn(&p, ap[0], &fa, &at, ap.data(), ep.data());
        posix_spawn_file_actions_destroy(&fa);
        posix_spawnattr_destroy(&at);
        close(fds[1]);
        if (r != 0) {
            close(fds[0]);
            std::lock_guard<std::mutex> lk(mu);
            last = std::string("could not start ") + args[0];
            return -1;
        }
        pid = p;
        std::string line;
        char buf[4096];
        for (ssize_t n; (n = read(fds[0], buf, sizeof buf)) > 0;) {
            for (ssize_t i = 0; i < n; i++) {
                const char c = buf[i];
                if (c == '\n' || c == '\r') {
                    if (!line.empty() && line.find("ld: warning") == std::string::npos) {
                        std::lock_guard<std::mutex> lk(mu);
                        last = line;
                    }
                    line.clear();
                } else if (line.size() < 400) {
                    line += c;
                }
            }
        }
        close(fds[0]);
        int st = 0;
        waitpid(p, &st, 0);
        pid = -1;
        if (stopped)
            return -2;
        return WIFEXITED(st) ? WEXITSTATUS(st) : 128 + (WIFSIGNALED(st) ? WTERMSIG(st) : 0);
    }

    void halt()
    {
        stopped = true;
        const pid_t p = pid;
        if (p > 0)
            kill(-p, SIGTERM);
        if (inproc_on)
            nv_render_stop();
#if NV_HEARD_INPROC
        if (heard_on)                           // (an as-heard render in this process: stopped between blocks)
            nv_live_render_stop();
#endif
        if (th.joinable())
            th.join();
    }

    // THE FILE RENDERER IN THIS PROCESS (nvrender.cpp's nv_render_main: iOS
    // runs no helper programs): ARGS as its command line, ENV (NAME=VALUE) its
    // settings -- this thread's own (nv_env_set), not the process's, which the
    // live engine reads beside it. Its exit code (-2 stopped); its last line kept
    std::atomic<bool> inproc_on{false}, heard_on{false};
    int inproc(const std::vector<std::string> &args, const std::vector<std::string> &env)
    {
        std::vector<std::string> names, values;
        for (const auto &kv : env) {
            const size_t e = kv.find('=');
            names.push_back(kv.substr(0, e));
            values.push_back(e == std::string::npos ? "" : kv.substr(e + 1));
        }
        std::vector<const char *> np, vp;
        for (size_t i = 0; i < names.size(); i++) {
            np.push_back(names[i].c_str());
            vp.push_back(values[i].c_str());
        }
        nv_env_set(np.data(), vp.data(), (int)np.size());
        std::vector<std::string> a(args);
        std::vector<char *> av;
        for (auto &x : a)
            av.push_back(&x[0]);
        av.push_back(nullptr);
        inproc_on = true;
        const int r = stopped ? -2 : nv_render_main((int)a.size(), av.data());
        inproc_on = false;
        nv_env_set(nullptr, nullptr, 0);
        std::lock_guard<std::mutex> lk(mu);
        last = nv_render_last();
        return r;
    }

    void finish(const std::string &m)
    {
        std::lock_guard<std::mutex> lk(mu);
        msg = m;
        t1 = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
        busy = false;
    }

    // kind "heard" (the live engine offline) or "best" (the file renderer
    // streamed on the GPU; whole: not streamed, asked for), into dir
    void start(nv_host *h, const std::string &in, std::string md, const std::string &k, bool whole,
               const std::string &dir, const std::string &file_export)
    {
        if (busy)
            return;
        if (th.joinable())
            th.join();
        Info I = inspect(in);
        if (!I.ok) {
            std::lock_guard<std::mutex> lk(mu);
            msg = I.err;
            return;
        }
        if (md == "auto" || md.empty())
            md = I.detected == "gs" ? "" : I.detected;
        std::string stem = in.substr(in.rfind('/') + 1);
        if (stem.rfind('.') != std::string::npos && stem.rfind('.') > 0)
            stem = stem.substr(0, stem.rfind('.'));
        for (char &c : stem)
            if (!isalnum((unsigned char)c) && c != '-' && c != '_' && c != '.')
                c = '_';
        mkdir(dir.c_str(), 0755);
        // what it is read in: the map, as the live standard or the reader's TUNING_*
        const int mp = mt32_family(md) ? 1 : map_of(md) >= 0 ? map_of(md) : (int)lround(nv_host_global(h, 13));
        std::vector<std::string> env = {"TUNING_MAP=" + std::to_string(mp)};
        if (md == "gm")
            env.push_back("TUNING_GM=1");
        if (md == "cm64")
            env.push_back("TUNING_CM64=1");
        if (md == "names")
            env.push_back("TUNING_PARTS=names");
        if (md == "mt32" || md == "cm64u")
            env.push_back(std::string("TUNING_MT32=") + (md == "mt32" ? "mt32" : "cm64"));
        if (!mt32_vel)
            env.push_back("TUNING_MT32_VEL=0");
        std::string exe = nv_self_exe();
        exe = exe.substr(0, exe.rfind('/') + 1);
        std::string tuner, east;
        {
            std::lock_guard<std::mutex> lk(h->bmu);
            tuner = h->tuner_now;
            east = h->east_now;
        }
        // (the as-heard render's session: this one's, the file's parts in)
        J st = h->session_state(h->E.routes);
        file_parts(h, st);
        st.o["std_map"] = sess::integer(mp);
        std::string sjs;
        put(sjs, st);
        const std::string live_export = h->routes_file.substr(0, h->routes_file.size() - 7);
        {
            std::lock_guard<std::mutex> lk(mu);
            kind = k;
            name = in.substr(in.rfind('/') + 1);
            out = dir + "/" + stem + (k == "heard" ? ".heard.wav" : ".best.wav");
            msg.clear();
            ask.clear();
            ask_why.clear();
            last.clear();
            t0 = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
        }
        busy = true;
        stopped = false;
        th = std::thread([=]() {
            std::string tpl = tmp_root() + "/clavitone-render-XXXXXX";
            const char *td = mkdtemp(&tpl[0]);
            const std::string tmp = td ? td : tmp_root();
            auto clean = [&]() {
                if (!td)
                    return;
                if (DIR *d = opendir(tmp.c_str())) {
                    while (dirent *e = readdir(d))
                        if (e->d_name[0] != '.')
                            unlink((tmp + "/" + e->d_name).c_str());
                    closedir(d);
                }
                rmdir(tmp.c_str());
            };
            std::string o;
            {
                std::lock_guard<std::mutex> lk(mu);
                o = out;
            }
            if (k == "heard" && !HELPERS && !NV_HEARD_INPROC) {
                clean();
                return finish("rendering as heard is not on this device yet: use best quality");
            }
            if (k == "heard") {
                const std::string sp = tmp + "/session.json";
                if (FILE *f = fopen(sp.c_str(), "w")) {
                    fwrite(sjs.data(), 1, sjs.size(), f);
                    fclose(f);
                }
                say("rendering as heard (the live engine, on the CPU)");
                const std::vector<std::string> args = {exe + "nvlive", live_export, "--test", in, o, "--session=" + sp,
                                                       "--programs", "--cpu"};
                int r;
                if (HELPERS || !NV_HEARD_INPROC)
                    r = step(args, env);
#if NV_HEARD_INPROC
                else {                          // (no helper program: a second live engine, in this process)
                    std::vector<std::string> a(args);
                    a.push_back("--messenger-out=none");
                    std::vector<char *> av;
                    for (auto &x : a)
                        av.push_back(&x[0]);
                    av.push_back(nullptr);
                    heard_on = true;
                    r = stopped ? -2 : nv_live_render_test((int)a.size(), av.data());
                    heard_on = false;
                    std::lock_guard<std::mutex> lk(mu);
                    last = r ? "the live engine's render ended " + std::to_string(r) : "";
                }
#endif
                clean();
                std::string l;
                {
                    std::lock_guard<std::mutex> lk(mu);
                    l = last;
                }
                return finish(r == -2 ? "render stopped" : r == 0 ? "rendered" : r == 137 || r == 128 + 9 ? "stopped: not enough memory beside the engine playing" : "the render failed: " + l);
            }
            // BEST: will it stream? (what the stream cannot reproduce yet asks first)
            if (file_export.empty()) {
                clean();
                return finish("no file export: start nvlive with --file-export=PATH (native_export.py's, not --live)");
            }
            const std::string dry = tmp + "/dry.wav";
            std::vector<std::string> common = {"nvrender", file_export, in, dry};     // (in this process: inproc)
            if (!tuner.empty())
                common.push_back("--tuner=" + tuner);
            if (!east.empty())
                common.push_back("--eastern=" + east);
            // (streamed: the render reads the song first and, where it cannot stream,
            // stops saying why (--stream-only: exit 3) -- asked before a whole render,
            // with no pass of its own to find out)
            {
                std::lock_guard<std::mutex> lk(mu);
                whole_ = whole;
            }
            say(whole ? "rendering whole (the file renderer)" : "rendering, streamed on the GPU");
            auto a = common;
            if (!whole) {
                a.push_back("--stream-only");
                a.push_back("--gpu");
            }
            int r = inproc(a, env);
            if (!whole && (r == 3 || r == 2)) {     // (cannot stream: asked; not the engine's file: refused)
                std::string why;
                {
                    std::lock_guard<std::mutex> lk(mu);
                    why = last;
                }
                if (why.rfind("nvrender: ", 0) == 0)
                    why = why.substr(10);
                clean();
                {
                    std::lock_guard<std::mutex> lk(mu);
                    ask = r == 3 ? "whole" : "refused";
                    ask_why = why;
                }
                return finish("");
            }
            if (r != 0) {
                std::string l;
                {
                    std::lock_guard<std::mutex> lk(mu);
                    l = last;
                }
                clean();
                return finish(r == -2 ? "render stopped" : r == 2 ? "best quality refused: " + l
                                                    : r == 137 ? "stopped: not enough memory beside the engine playing"
                                                               : "the render failed: " + l);
            }
            say("adding the room");
            // (in this process, not a helper program: iOS runs none -- nvroomtail's whole is the library's)
            {
                std::vector<std::string> a = {"nvroomtail", dry, o, "--export=" + file_export};
                std::vector<char *> av;
                for (auto &x : a)
                    av.push_back(&x[0]);
                av.push_back(nullptr);
                r = stopped ? -2 : nv_roomtail_main((int)a.size(), av.data());
            }
            clean();
            finish(r == -2 ? "render stopped" : r == 0 ? "rendered" : "the room failed (" + std::to_string(r) + ")");
        });
    }
};

}  // namespace fileplay
