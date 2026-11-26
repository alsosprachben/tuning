// hostsession.cpp -- the host's SESSION, SCENES AND PRESETS (live's
// session.json, scenes.json, presets.json): moved here from nvlive.cpp so
// the library has them -- an app (app/, host.h's nv_host_* calls) saves and
// loads the presets nvlive and live.py do, the same files, the same keys.
// nvlive, the terminal client, links them from the library as before.
#include <dlfcn.h>
#include <unistd.h>
#include "selfexe.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <thread>
#include "hostlive.h"
#include "host.h"

// ---- THE SESSION (session.h): live's session.json, shared with live.py ----

// a live.Route as Route.to_dict writes it, from nv_rt_add's seven; a null
// for one whose destination live has no name for (-99)
static sess::J route_dict(const std::array<int, 7> &a)
{
    static const char *HALF[3] = {"up", "down", "both"};
    sess::J src = sess::arr();
    switch (a[0]) {
    case 0: src.a = {sess::str("cc"), sess::integer(a[1])}; break;
    case 1: src.a = {sess::str("bend"), sess::str(HALF[std::max(0, std::min(2, a[1]))])}; break;
    case 2: src.a = {sess::str("pressure")}; break;
    default: src.a = {sess::str("note"), sess::integer(a[1])}; break;
    }
    if (a[2] == -99)
        return sess::null();
    sess::J d = sess::obj();
    d.o["src"] = src;
    d.o["dst"] = a[2] == -1 ? sess::str("bend") : a[2] == -2 ? sess::str("pressure") : a[2] == -3 ? sess::str("mono")
                                                                                    : sess::integer(a[2]);
    d.o["keep"] = sess::boolean(a[3] != 0);
    d.o["channel"] = a[4] < 0 ? sess::null() : sess::integer(a[4]);
    d.o["latch"] = sess::boolean(a[5] != 0);
    d.o["press"] = sess::boolean(a[6] != 0);
    return d;
}

// ...and back (native.route_args): false for one nvlive cannot take
bool route_args(const sess::J &d, std::array<int, 7> &a)
{
    const sess::J *src = d.get("src"), *dst = d.get("dst");
    if (!src || !src->is(sess::J::ARR) || src->a.empty() || !src->a[0].is(sess::J::STR) || !dst)
        return false;
    const std::string k = src->a[0].s;
    const sess::J *arg = src->a.size() > 1 ? &src->a[1] : nullptr;
    if (k == "cc" && arg)
        a = {0, (int)arg->i(), 0, 0, -1, 0, 1};
    else if (k == "bend")
        a = {1, !arg || arg->s == "up" ? 0 : arg->s == "down" ? 1 : 2, 0, 0, -1, 0, 1};
    else if (k == "pressure")
        a = {2, 0, 0, 0, -1, 0, 1};
    else if (k == "note" && arg)
        a = {3, (int)arg->i(), 0, 0, -1, 0, 1};
    else
        return false;
    a[2] = dst->is(sess::J::STR) ? (dst->s == "bend" ? -1 : dst->s == "pressure" ? -2 : dst->s == "mono" ? -3 : -99)
                                 : (int)dst->i();
    const sess::J *x;
    a[3] = (x = d.get("keep")) && x->d() != 0.0;
    a[4] = (x = d.get("channel")) && x->is(sess::J::NUM) ? (int)x->i() : -1;
    a[5] = (x = d.get("latch")) && x->d() != 0.0;
    a[6] = (x = d.get("press")) ? x->d() != 0.0 : 1;
    return true;
}

// what the session holds that the part takes once playing (live.apply_preset):
// the globals, the room, the insertion effect (efx_recall's messages), the
// organ's drawn stops, and each channel's mix (the scene: recall_scene)
void nv_host::session_apply()
{
    if (session.is(sess::J::OBJ))
        apply_setup(session, true);
}

// ---- SCENES AND PRESETS (live's) ----

// THE CABINET CHOICES by name (patch_map.CAB_CHOICES -- the same order: an
// index is CC83's value: FIXED, a new one at the end), 0 "own", and a session's name's index (-1 none)
static const char *const CAB_NAMES[] = {"own", "direct", "leslie", "hammond", "guitar12", "guitar412", "jc120",
                                        "bass410", "rhodes", "wurlitzer", "spectra", "spectra_chorus"};
static int cab_index(const std::string &s)
{
    for (int i = 0; i < (int)(sizeof CAB_NAMES / sizeof CAB_NAMES[0]); i++)
        if (s == CAB_NAMES[i])
            return i;
    return -1;
}
// ...THE PICKUP CHOICES' NAMES (patch_map.PICKUP_CHOICES; 0 "own"), the same
static const char *const PK_NAMES[] = {"own", "neck", "neck+middle", "middle", "middle+bridge", "bridge", "neck+bridge",
                                       "anti"};
static int pk_index(const std::string &s)
{
    for (int i = 0; i < (int)(sizeof PK_NAMES / sizeof PK_NAMES[0]); i++)
        if (s == PK_NAMES[i])
            return i;
    return -1;
}

// RENAMED RANKS (tonelib.RANK_RENAMES, rank_rename): a preset's or a
// session's old name as the voice with ranks NAMES calls it today -- only
// where the new name is one of its ranks and the old one is not
static std::string rank_rename(const std::string &name, const std::vector<std::string> &names)
{
    static const char *const R[][2] = {{"16", "principal 16"}, {"8", "principal 8"}, {"4", "octave 4"},
                                       {"2", "super octave 2"}, {"2-2/3", "quint 2-2/3"}, {"5-1/3", "quint 5-1/3"},
                                       {"flute", "flute 8"}, {"mixture", "mixture III"}, {"trumpet", "trumpet 8"}};
    auto has = [&](const std::string &n) { return std::find(names.begin(), names.end(), n) != names.end(); };
    for (const auto &r : R)
        if (name == r[0])
            return has(r[1]) && !has(name) ? r[1] : name;
    return name;
}

static std::string beside(const std::string &path, const char *name)
{
    size_t k = path.rfind('/');
    return (k == std::string::npos ? std::string(".") : path.substr(0, k)) + "/" + name;
}
// THE ORGAN a program plays under a GS variation (live._organ_class): the
// variation's entry's where it has one, else the program's; null none
const OrganSpec *nv_host::organ_of(int prog, int var) const
{
    if (prog < 0 || prog > 127)
        return nullptr;
    const int msb = var & 127, mp = var >> 7;
    if (msb && !E.vgs.empty()) {
        const int en = E.vgs[((size_t)(mp >= 1 && mp <= 4 ? mp : 0) * 128 + prog) * 128 + msb];
        if (en > 0 && E.vents[en].pcls >= 0 && E.cls_organ[E.vents[en].pcls] >= 0)
            return &E.organs[E.cls_organ[E.vents[en].pcls]];
    }
    return (size_t)prog < E.prog_organ.size() && E.prog_organ[prog] >= 0 ? &E.organs[E.prog_organ[prog]] : nullptr;
}

// THE MOOG a program plays under a GS variation (live._moog_class): its
// first layer's panel into pn (NV_MK_N), false if it is not one
bool nv_host::moog_pn_of(int prog, int var, double *pn) const
{
    if (prog < 0 || prog > 127)
        return false;
    long long q = 128LL * prog + 60;
    const int msb = var & 127, mp = var >> 7;
    if (msb && !E.vgs.empty()) {
        const int en = E.vgs[((size_t)(mp >= 1 && mp <= 4 ? mp : 0) * 128 + prog) * 128 + msb];
        if (en > 0 && !E.vents[en].ls.empty() && E.vents[en].ls[0][0] >= 0)
            q = NV_K_VAR + 128LL * E.vents[en].ls[0][0] + 60;
    }
    const NoteClass *k = q >= 0 && q < (long long)K.size() ? K[q] : nullptr;
    if (!k || k->moog.n_layer < 1)
        return false;
    for (int i = 0; i < NV_MK_N; i++)
        pn[i] = k->moog.L[0].pn[i];
    return true;
}

std::string nv_host::presets_path() const { return beside(session_path, "presets.json"); }
// (ui/presets_default.json beside the engine's library -- the repository's, the
// iPad app's binary, the Mac bundle's Frameworks -- else beside the program)
std::string nv_host::presets_default_path() const
{
    auto in = [](const std::string &f) {
        const size_t k = f.rfind('/');
        return (k == std::string::npos ? std::string(".") : f.substr(0, k)) + "/ui/presets_default.json";
    };
    Dl_info di;
    if (dladdr((const void *)&nv_host_presets, &di) && di.dli_fname) {
        const std::string p = in(di.dli_fname);
        if (access(p.c_str(), R_OK) == 0)
            return p;
    }
    // (a Mac app's: its Resources, beside its program's folder -- a bundle's Frameworks hold code only)
    const std::string self = nv_self_exe();
    const size_t k = self.rfind('/');
    if (k != std::string::npos) {
        const std::string r = self.substr(0, k) + "/../Resources/ui/presets_default.json";
        if (access(r.c_str(), R_OK) == 0)
            return r;
    }
    return in(self);
}
bool nv_host::presets_read(sess::J &d, std::set<std::string> *defaults, std::set<std::string> *mine) const
{
    d = sess::obj();
    sess::J df, u;
    if (sess::load(presets_default_path(), df) && df.is(sess::J::OBJ))
        for (const auto &kv : df.o) {
            d.o[kv.first] = kv.second;
            if (defaults)
                defaults->insert(kv.first);
        }
    if (!session_path.empty() && sess::load(presets_path(), u) && u.is(sess::J::OBJ))
        for (const auto &kv : u.o) {
            d.o[kv.first] = kv.second;
            if (mine)
                mine->insert(kv.first);
        }
    return !d.o.empty();
}
std::string nv_host::scenes_path() const { return beside(session_path, "scenes.json"); }

static std::string cc_text(int ch, int c, int v)
{
    return "control_change channel=" + std::to_string(ch) + " control=" + std::to_string(c) + " value="
           + std::to_string(std::max(0, std::min(127, v))) + " time=0";
}

// live._rpn_events: an RPN set, then the null RPN
static void rpn_text(std::vector<std::string> &ev, int ch, int lsb, int msb_val, int lsb_val)
{
    ev.push_back(cc_text(ch, 101, 0));
    ev.push_back(cc_text(ch, 100, lsb));
    ev.push_back(cc_text(ch, 6, msb_val));
    if (lsb_val >= 0)
        ev.push_back(cc_text(ch, 38, lsb_val));
    ev.push_back(cc_text(ch, 101, 127));
    ev.push_back(cc_text(ch, 100, 127));
}

// a channel's controller matrix out of the engine (nv_part_cmx): a reset's
// where nothing set it; false where the channel has none
static bool cmx_take(void *part, int ch, nv::Cmx &m)
{
    static thread_local int src[512], col[512], cc[2];
    static thread_local double dep[512];
    const int n = nv_part_cmx(part, ch, src, col, dep, 512, cc);
    m = nv::Cmx();
    if (n < 0)
        return false;
    m.gs.clear();
    for (int i = 0; i < n; i++)
        m.gs.push_back({{src[i], col[i]}, dep[i]});
    m.cc1 = cc[0];
    m.cc2 = cc[1];
    return true;
}

static std::string sysex_text(const std::vector<uint8_t> &d)
{
    std::string t = "sysex data=(";
    for (size_t i = 0; i < d.size(); i++)
        t += (i ? "," : "") + std::to_string(d[i]);
    return t + ") time=0";
}

// THE CONTROLLER MATRIX of channel ch as in effect (live.cmx_state), read
// between two blocks
bool nv_host::cmx_read(int ch, nv::Cmx &m)
{
    struct Got {
        nv::Cmx m;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [this, got, ch](long long) {
        cmx_take(part, ch, got->m);
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return false;
    m = got->m;
    return true;
}

// THE USER DRUM SETS as set (live.udrum_state: the host's copy), read
// between two blocks
bool nv_host::udrum_read(panel::Host::USets &u)
{
    struct Got {
        panel::Host::USets u;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [this, got](long long) {
        got->u = huset;
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return false;
    u = got->u;
    return true;
}

// a user drum set's setting as a sequencer sends it (live.udrum_send: GS 21
// dp rr), into the input -- the host's own path, its template asked
void nv_host::udrum_queue(int s, int key, int code, int v)
{
    const uint8_t a = 0x21, b = (uint8_t)(((s & 1) << 4) | (code & 15)), c = (uint8_t)(key & 127),
                  d = (uint8_t)std::max(0, std::min(127, v));
    std::vector<uint8_t> x{0x41, 0x10, 0x42, 0x12, a, b, c, d, (uint8_t)((128 - (a + b + c + d) % 128) % 128)};
    enqueue(Midi{6, 0, 0, 0, x});
}

// THE SCENE NOW (live.scene_from), in mido's text form: the captured
// controls as they reached the part, then each channel's sound controllers,
// its tuning RPNs and mono, read from the engine between two blocks -- the
// last one taken when the audio is not running. An organ's mod wheel (the
// crescendo: its registration is the part's drawn stops) left out
std::vector<std::string> nv_host::scene_now()
{
    struct Got {
        std::vector<double> st = std::vector<double>(16 * 13, 0.0);
        std::map<std::pair<int, int>, int> latch;
        std::map<int, nv::Cmx> cmx;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [this, got](long long) {
        nv_part_chanstate(part, got->st.data());
        got->latch = chanlatch;
        for (int ch = 0; ch < 16; ch++) {
            nv::Cmx m;
            if (cmx_take(part, ch, m))
                got->cmx[ch] = m;
        }
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return scene_cached;
    const int sp = shown_program;
    const bool cres = sp < 128 && !E.stops[sp].names.empty();
    std::vector<std::string> ev;
    for (const auto &kv : got->latch) {
        const int ch = kv.first.first, c = kv.first.second;
        if (c == 1 && cres && (pats[0].channel < 0 || pats[0].channel == ch))
            continue;
        ev.push_back(cc_text(ch, c, kv.second));
    }
    static const int SND_BY_NAME[8] = {73, 74, 75, 72, 71, 78, 77, 76};    // (attack .. vib_rate: sorted by name)
    for (int ch = 0; ch < 16; ch++) {
        const double *o = got->st.data() + 13 * ch;
        for (int c : SND_BY_NAME)
            if (o[c - 71] != 0.0)
                ev.push_back(cc_text(ch, c, (int)std::nearbyint(o[c - 71] * 64.0 + 64.0)));
        if (o[8] >= 0.0) {
            int msb = (int)o[8], lsb = (int)std::nearbyint((o[8] - msb) * 100.0);
            rpn_text(ev, ch, 0, msb, lsb ? lsb : -1);
        }
        if (o[9] != 0.0) {
            int code = std::max(0, std::min(16383, (int)std::nearbyint(o[9] / 100.0 * 8192.0) + 8192));
            rpn_text(ev, ch, 1, code >> 7, code & 127);
        }
        if (o[10] != 0.0)
            rpn_text(ev, ch, 2, std::max(0, std::min(127, (int)std::nearbyint(o[10]) + 64)), -1);
        if (o[11] >= 0.0) {
            int msb = (int)std::floor(o[11] / 100.0), lsb = (int)std::nearbyint((o[11] - msb * 100.0) / (100.0 / 128.0));
            rpn_text(ev, ch, 5, msb, lsb ? lsb : -1);
        }
        if (o[12] != 0.0)
            ev.push_back(cc_text(ch, 126, 1));
    }
    // THE CONTROLLER MATRIX: each channel's, as the exclusives that set it
    // from a reset's (ctrlmatrix.scene_messages)
    for (const auto &kv : got->cmx)
        for (const auto &d : nv::cmx_scene(kv.first, kv.second))
            ev.push_back(sysex_text(d));
    scene_cached = ev;
    return ev;
}

// A SCENE PUT BACK (live.recall_scene): its events past the routes (they are
// already what the part received), mono changed only where it differs (both
// mode messages carry an All Sounds Off), a channel the scene leaves
// polyphonic put back to poly; an organ's mod wheel never replayed
int nv_host::scene_recall(const std::vector<std::string> &events)
{
    std::vector<std::array<int, 3>> cc;
    std::vector<std::vector<uint8_t>> sx;       // (the controller matrix's exclusives)
    for (const auto &e : events) {
        int ch, c, v;
        if (sscanf(e.c_str(), "control_change channel=%d control=%d value=%d", &ch, &c, &v) == 3)
            cc.push_back({ch & 15, c, v});
        else if (!e.compare(0, 12, "sysex data=(")) {
            std::vector<uint8_t> d;
            const char *p = e.c_str() + 12;
            while (*p && *p != ')') {
                char *end;
                const long b = strtol(p, &end, 10);
                if (end == p)
                    break;
                d.push_back((uint8_t)std::max(0L, std::min(127L, b)));
                p = *end == ',' ? end + 1 : end;
            }
            sx.push_back(d);
        }
    }
    const int sp = shown_program;
    const bool cres = sp < 128 && !E.stops[sp].names.empty();
    const int pch = pats[0].channel;
    post([this, cc, cres, pch, sx](long long) {
        // the scene's exclusives (live.inject's), then a matrix it does not
        // name back to a reset's (ctrlmatrix.undo_messages)
        std::vector<std::vector<uint8_t>> undo;
        for (int ch = 0; ch < 16; ch++) {
            nv::Cmx m;
            if (cmx_take(part, ch, m))
                for (auto &d : nv::cmx_undo(ch, m, sx))
                    undo.push_back(d);
        }
        double st[16 * 13];
        nv_part_chanstate(part, st);
        bool want_mono[16] = {};
        for (const auto &m : cc)
            if (m[1] == 126)
                want_mono[m[0]] = true;
        for (const auto &m : cc) {
            if (m[1] == 1 && cres && (pch < 0 || pch == m[0]))
                continue;
            if (m[1] == 126 || m[1] == 127) {
                if ((m[1] == 126) != (st[13 * m[0] + 12] != 0.0))
                    engine_event(2, m[0], m[1], m[2]);
                continue;
            }
            engine_event(2, m[0], m[1], m[2]);
        }
        for (int ch = 0; ch < 16; ch++)
            if (st[13 * ch + 12] != 0.0 && !want_mono[ch])
                engine_event(2, ch, 127, 0);
        for (const auto &d : sx)                // (after the controls, as the scene lists them)
            nv_part_sysex(part, d.data(), (int)d.size());
        for (const auto &d : undo)
            nv_part_sysex(part, d.data(), (int)d.size());
    });
    int n = (int)sx.size();
    for (const auto &m : cc)
        n += !(m[1] == 1 && cres && (pch < 0 || pch == m[0]));
    return n;
}

// A SETUP TAKEN (live.apply_preset): a session's at the start (the part's
// program already taken, the routes already the router's), or a preset's
// while playing -- then the parts set again (every one but the first and the
// drums nvlive keeps beside it taken away, the first's program asked for,
// the rest added), the routes replaced, the tuner switched; the stops for
// the first part's organ once it is in
void nv_host::apply_setup(const sess::J &setup, bool at_start)
{
    const sess::J *x;
    const sess::J &session = setup;         // (the code below reads it by the session's name)
    if (!at_start) {
        // THE PARTS AWAY: all but the first and the drums kept beside it
        std::vector<size_t> away;
        {
            std::lock_guard<std::mutex> lk(parts_mu);
            for (size_t i = 0; i < pats.size(); i++)
                if (!pats[i].gone && pats[i].pi != 0 && pats[i].pid != 2 && pats[i].pid != 3)
                    away.push_back(i);
        }
        std::string why;
        for (size_t i : away)
            part_delete(i, why);
        // ...THE ROUTES REPLACED (--pedal-key's own kept)
        if ((x = setup.get("routes")) && x->is(sess::J::ARR)) {
            std::vector<std::array<int, 7>> rs;
            for (const sess::J &r : x->a) {
                std::array<int, 7> a;
                if (route_args(r, a))
                    rs.push_back(a);
            }
            const size_t had = E.routes.size() + (pks.empty() ? 0 : 1);
            std::vector<std::array<int, 7>> all = rs;
            if (!pks.empty())
                all.push_back(pedal_route);
            post([this, had, all](long long) {
                for (size_t q = had; q-- > 0;)
                    nv_rt_del(router, (int)q);
                for (const auto &a : all)
                    nv_rt_add(router, a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
            });
            E.routes = rs;
            routes_replaced = all;
        }
        // ...THE EASTERN TUNING (live.apply_preset: before the parts it tunes)
        const sess::J *ea = setup.get("eastern");
        if (ea && (ea->is(sess::J::STR) || ea->is(sess::J::NUL))) {
            std::string want = ea->is(sess::J::STR) ? ea->s : std::string(), cur;
            {
                std::lock_guard<std::mutex> lk(bmu);
                cur = east_req_set ? east_asked : east_now;
            }
            if (want != cur)
                set_eastern(want);
        }
        // ...THE TUNER (the first part's, live's per part; nvlive's one)
        const sess::J *ps = setup.get("parts");
        const sess::J *tn = ps && ps->is(sess::J::ARR) && !ps->a.empty() ? ps->a[0].get("tuner") : nullptr;
        if (tn && tn->is(sess::J::STR) && !tn->s.empty()) {
            std::string cur;
            {
                std::lock_guard<std::mutex> lk(bmu);
                cur = tuner_now;
            }
            if (tn->s != cur)
                set_tuner(tn->s);
        }
    }
    static const char *KEYS[6] = {"master_db", "headroom_db", "thresh", "bend_range", "mod_cents", "press_db"};
    for (int i = 0; i < 6; i++)
        if ((x = session.get(KEYS[i])) && x->is(sess::J::NUM)) {
            double v = std::max(panel::GLOBAL_RANGE[i][0], std::min(panel::GLOBAL_RANGE[i][1], x->d()));
            if (v != gval[i])
                set_global(i, v);
        }
    if ((x = session.get("rubato")) && x->is(sess::J::BOOL))
        rub_wish = x->d() != 0.0;               // (borrowed time: on unless the session turned it off)
    if ((x = session.get("language")) && x->is(sess::J::STR)) {
        std::lock_guard<std::mutex> lk(lang_mu);
        lang = x->s;
    }
    if ((x = session.get("spectra_fast")) && x->is(sess::J::BOOL)) {   // (the Spectra-Tone's rocker, as left)
        const int sf = x->d() != 0.0 ? 1 : 0;
        post([this, sf](long long) { nv_part_set_spectra_fast(part, sf); });
    }
    if ((x = session.get("stand_in_ms")) && x->is(sess::J::NUM) && x->d() != gval[NV_G_STAND_IN])
        set_global(NV_G_STAND_IN, x->d());      // (a held note's stand-in after, ms: 0 none)
    if ((x = session.get("messenger_firmware")) && x->is(sess::J::STR)        // THE MESSENGER's CHART (live's)
        && (x->s == "pre-1.0.7") != msgr_pre107) {
        msgr_pre107 = x->s == "pre-1.0.7";
        const double v = msgr_pre107 ? 1.0 : 0.0;
        post([this, v](long long) { nv_part_set(part, 9, v); });
    }
    if ((x = session.get("controls")) && x->is(sess::J::ARR)) {        // THE ON-SCREEN CONTROLS (live's)
        screen_controls.clear();
        for (const sess::J &c : x->a) {
            const sess::J *k = c.get("key"), *ch = c.get("channel"), *v = c.get("value"), *hk = c.get("hotkey");
            if (!k)
                continue;
            int key;
            if (k->is(sess::J::NUM))
                key = (int)k->i();
            else if (k->is(sess::J::STR) && (k->s == "mono" || k->s == "bend" || k->s == "pressure"))
                key = k->s == "mono" ? -3 : k->s == "bend" ? -1 : -2;
            else
                continue;
            if (!panel::control_label(key))
                continue;                       // (not the catalogue's)
            panel::ScreenControl sc;
            sc.key = key;
            sc.channel = ch && ch->is(sess::J::NUM) ? (int)ch->i() & 15 : -1;
            sc.value = v && v->is(sess::J::NUM) ? (int)v->i() : panel::control_default(key);
            sc.hotkey = hk && hk->is(sess::J::STR) && hk->s.size() == 1 ? (unsigned char)hk->s[0] : 0;
            screen_controls.push_back(sc);
        }
    }
    if ((x = session.get("std_map")) && x->is(sess::J::NUM))           // THE STANDARD (live.std_map)
        set_global(13, x->d());
    if ((x = session.get("mod_rate")) && x->is(sess::J::NUM)) {       // (the host's ninth: live.mod_rate)
        double v = std::max(panel::GLOBAL_RANGE[9][0], std::min(panel::GLOBAL_RANGE[9][1], x->d()));
        if (v != gval[9])
            set_global(9, v);
    }
    // THE MIDI INPUTS (live.saved_inputs): the session's, those plugged in
    // now -- by device name, before any colon (live's "USB Midi:USB Midi MIDI
    // 1" is our "USB Midi") -- unless --port or --midi named one
    if (at_start && !cli_port && (x = session.get("midi_inputs")) && x->is(sess::J::ARR) && !x->a.empty()) {
        auto devname = [](std::string n) {
            n = n.substr(0, n.find(':'));
            while (!n.empty() && n.back() == ' ')
                n.pop_back();
            for (char &ch : n)
                ch = (char)tolower((unsigned char)ch);
            return n;
        };
        std::vector<std::pair<std::string, std::string>> w;
        for (const auto &d : midi_devices())
            for (const auto &j : x->a)
                if (j.is(sess::J::STR) && devname(j.s) == devname(d.second)) {
                    w.push_back(d);
                    break;
                }
        if (!w.empty())
            ins.set(w);
    }
    if ((x = session.get("room")) && x->is(sess::J::STR))
        for (size_t q = 0; q < E.rooms.size(); q++)
            if (E.rooms[q].name == x->s && (int)q != room_idx)
                set_global(8, (double)q);           // (the builder's: every patch built again in it)
    if ((x = session.get("efx")) && x->is(sess::J::OBJ)) {
        auto send = [&](char kind, int a, int b) {
            std::vector<uint8_t> m = panel::efx_message(kind, a, b);
            post([this, m](long long) { nv_part_sysex(part, m.data(), (int)m.size()); });
        };
        const sess::J *t = x->get("type");
        if (t && t->is(sess::J::ARR) && t->a.size() == 2)
            send('t', (int)t->a[0].i(), (int)t->a[1].i());
        for (const char *k : {"p", "send", "ctl"})
            if (const sess::J *l = x->get(k))
                for (const sess::J &kv : l->a)
                    if (kv.is(sess::J::ARR) && kv.a.size() == 2)
                        send(k[0] == 'p' ? 'p' : 's', (int)kv.a[0].i(), (int)kv.a[1].i());
        std::vector<int> want;
        if (const sess::J *l = x->get("parts"))
            for (const sess::J &c : l->a)
                want.push_back((int)c.i());
        for (int ch = 0; ch < 16; ch++)
            send('c', ch, std::find(want.begin(), want.end(), ch) != want.end());
    }
    // THE USER DRUM SETS (live.udrum_recall): each setting sent again
    if ((x = session.get("user_drums")) && x->is(sess::J::ARR))
        for (const sess::J &r : x->a)
            if (r.is(sess::J::ARR) && r.a.size() == 4)
                udrum_queue((int)r.a[0].i(), (int)r.a[1].i(), (int)r.a[2].i(), (int)r.a[3].i());
    // THE PARTS (live.Part.to_dict's): the first's place, level and mute on
    // the part; each after it added -- a drum set on channel 10 the drums
    // nvlive keeps beside the part (its own, not live's: never written back)
    const sess::J *parts = session.get("parts");
    if (parts && parts->is(sess::J::ARR))
        for (size_t k = 0; k < parts->a.size(); k++) {
            const sess::J &pd = parts->a[k];
            if (!pd.is(sess::J::OBJ))
                continue;
            auto num = [&](const char *key, double dflt) {
                const sess::J *v = pd.get(key);
                return v && v->is(sess::J::NUM) ? v->d() : dflt;
            };
            const sess::J *chv = pd.get("channel"), *dv = pd.get("drums"), *mv = pd.get("muted");
            PartSpec sp;
            sp.program = (int)num("program", 0) & 127;
            sp.var = (int)num("bank", 0);
            sp.drums = dv && dv->d() != 0.0;
            sp.channel = chv && chv->is(sess::J::NUM) ? (int)chv->i() & 15 : -1;
            sp.lo = std::max(0, std::min(127, (int)num("lo", 0)));
            sp.hi = std::max(sp.lo, std::min(127, (int)num("hi", 127)));
            sp.tr = std::max(-48, std::min(48, (int)num("transpose", 0)));
            sp.level = std::max(panel::LEVEL_DB_MIN, std::min(panel::LEVEL_DB_MAX, num("level_db", 0.0)));
            sp.muted = mv && mv->d() != 0.0;
            {                                   // its fixed touch (live's part.fixed_touch; absent, the patch's way)
                const sess::J *ft = pd.get("fixed_touch");
                sp.fixed = ft && (ft->is(sess::J::BOOL) || ft->is(sess::J::NUM)) ? (ft->d() != 0.0 ? 1 : 0) : -1;
                const sess::J *ro = pd.get("rotary");   // (its rotary heard: live's Part.rotary, "room" or "mics")
                sp.rot_mode = ro && ro->is(sess::J::STR) ? (ro->s == "mics" ? 1 : ro->s == "room" ? 0 : -1) : -1;
                const sess::J *rs = pd.get("rotary_spread");    // (...degrees; absent, the default)
                sp.rot_sep = rs && rs->is(sess::J::NUM) ? std::max(0.0, std::min(180.0, rs->d())) * M_PI / 180.0 : -1.0;
                const sess::J *cb = pd.get("cabinet");  // (its cabinet, chosen: live's Part.cab by name; absent, none)
                sp.cab = cb && cb->is(sess::J::STR) ? cab_index(cb->s) : -1;
                const sess::J *pu = pd.get("pickup");   // (...its pickup: live's Part.pk by name)
                sp.pk = pu && pu->is(sess::J::STR) ? pk_index(pu->s) : -1;
                if (!sp.drums)
                    sp.var = with_cab(sp.program, sp.var, std::max(0, sp.cab), std::max(0, sp.pk));
                const sess::J *dr = pd.get("drive");    // (an organ's drive knob: live's Part.drive; absent, the voice's)
                sp.drive = dr && dr->is(sess::J::NUM) ? std::max(0.0, dr->d()) : -1.0;
                const sess::J *cm = pd.get("cc_map");   // (a Messenger read on it: nvlive reads one on every part)
                if (cm && cm->is(sess::J::STR) && cm->s == "messenger" && !msgr_reads)
                    messenger_reading(true);
            }
            // ITS KNOBS (live.Part's synth, synth_b): by moog.PANEL's names, in
            // the measured Messenger's units (synth_units 6) -- older ones live
            // converts once on load, which nvlive leaves to it
            {
                const sess::J *su = pd.get("synth_units");
                const int units = su && su->is(sess::J::NUM) ? (int)su->i() : 1;
                bool any = false;
                for (int lay = 0; lay < 2; lay++) {
                    const sess::J *sy = pd.get(lay ? "synth_b" : "synth");
                    if (!sy || !sy->is(sess::J::OBJ))
                        continue;
                    for (const auto &kv : sy->o) {
                        const int mk = panel::mk_index(kv.first.c_str());
                        if (mk >= 0 && (kv.second.is(sess::J::NUM) || kv.second.is(sess::J::BOOL))) {
                            sp.syn[lay][mk] = kv.second.d();
                            any = true;
                        }
                    }
                }
                if (any && units < 6) {
                    fprintf(stderr, "nvlive: part %zu's knobs are in older units (synth_units %d): left as the patch's "
                                    "-- open the session in live.py once to convert them\n", k + 1, units);
                    sp.syn[0].clear();
                    sp.syn[1].clear();
                }
            }
            if (k == 0) {                       // (its knobs, behind its program: posted after its swap)
                for (int lay = 0; lay < 2; lay++)
                    for (const auto &kv : sp.syn[lay]) {
                        const int mk = kv.first, l = lay;
                        const double v = kv.second;
                        post([this, l, mk, v](long long) { nv_part_synth_set_later(part, pats[0].pi, l, mk, v); });
                    }
            }
            if (k == 0) {                       // (at the start its program is the part's already)
                part_set(0, sp.channel, sp.lo, sp.hi, sp.tr, sp.level, sp.muted);
                part_touch(0, sp.fixed);
                part_rotary(0, sp.rot_mode, sp.rot_sep);
                if (at_start) {                 // (its cabinet and pickup: at the start, their own rebuild --
                    {                           //  else after the pick below, which puts them back to its own)
                        std::lock_guard<std::mutex> lk(parts_mu);
                        pats[0].cab = sp.cab;
                        pats[0].pk = sp.pk;
                    }
                    if (sp.cab >= 0 && !sp.drums)
                        set_cabinet(0, sp.cab);
                    if (sp.pk >= 0 && !sp.drums)
                        set_pickup(0, sp.pk);
                }
                if (at_start)                   // (else after the pick's swap, below: a new program clears it)
                    part_drive(0, sp.drive);
                if (!at_start) {
                    int code = (sp.drums ? 128 : 0) + sp.program;
                    for (size_t j = 0; j < E.vpv.size() && sp.var && !sp.drums; j++)
                        if (E.vpv[j][0] == sp.program && E.vpv[j][1] == (sp.var & 4095))
                            code = 256 + (int)j;
                    pick_row(0, code);
                    if (sp.cab >= 0 && !sp.drums)       // (posted after the pick: its program on its way)
                        set_cabinet(0, sp.cab);
                    if (sp.pk >= 0 && !sp.drums)
                        set_pickup(0, sp.pk);
                    if (sp.drive >= 0.0) {      // (its drive knob, behind the swap that brings its program in)
                        const double dv = sp.drive;
                        {
                            std::lock_guard<std::mutex> lk(parts_mu);
                            pats[0].drive = dv;
                        }
                        post([this, dv](long long) { nv_part_drive_later(part, pats[0].pi, dv); });
                    }
                }
                continue;
            }
            size_t beside = pats.size();
            for (size_t i = 0; i < pats.size(); i++)
                if (pats[i].pid == 2 && sp.drums && sp.channel == 9)
                    beside = i;
            if (beside < pats.size()) {
                part_set(beside, 9, sp.lo, sp.hi, sp.tr, sp.level, sp.muted);
                pick_row(beside, 128 + sp.program);
                continue;
            }
            sp.excl = sp.channel < 0 ? pats[0].excl : 0u;
            if (sp.drums)
                sp.var = 0;
            if (const sess::J *dn = sp.drums ? nullptr : pd.get("drawn"))     // (its stops: once its organ is in)
                if (dn->is(sess::J::ARR)) {
                    std::vector<std::string> rk;    // (its ranks' names today: an old name renamed, rank_rename)
                    if (const OrganSpec *og = organ_of(sp.program & 127, sp.var & 4095))
                        for (int r = 0; r < og->n_rank; r++)
                            rk.push_back(og->rank[r].key);
                    for (const sess::J &n : dn->a)
                        if (n.is(sess::J::STR))
                            sp.drawn.push_back(rank_rename(n.s, rk));
                }
            part_add(sp);
        }
    // THE ORGAN's STOPS: drawn as the part's were (parts[0].drawn, by name) --
    // now if the organ is in, else once it is swapped in (pending_drawn)
    if (parts && parts->is(sess::J::ARR) && !parts->a.empty()) {
        const sess::J *dn = parts->a[0].get("drawn"), *pg = parts->a[0].get("program"), *dv = parts->a[0].get("drums");
        const int want_p = pg && pg->is(sess::J::NUM) ? (int)pg->i() & 127 : -1;
        // (its organ's ranks, its VARIATION's where it is one -- the 60's organs are
        //  bank 16's: their tabs, not the Drawbar Organ's, E.stops_for)
        const sess::J *bk = parts->a[0].get("bank");
        const int want_v = bk && bk->is(sess::J::NUM) ? (int)bk->i() & 4095 : 0;
        const auto *wst = want_p >= 0 ? E.stops_for(want_p, want_v) : nullptr;
        if (dn && dn->is(sess::J::ARR) && wst && !(dv && dv->d() != 0.0) && !wst->names.empty()) {
            const auto &names = wst->names;
            std::vector<char> want(names.size(), 0);
            for (size_t ri = 0; ri < names.size(); ri++)
                for (const sess::J &n : dn->a)
                    want[ri] = want[ri] || (n.is(sess::J::STR) && rank_rename(n.s, names) == names[ri]);   // (old names too)
            if (want_p == shown_program)
                post([this, want](long long) { nv_part_set_drawn(part, 0, want.data(), (int)want.size()); });
            // ...and its COUPLER SWITCHES (live's from_dict "couplers"), its organ in
            const sess::J *cj = parts->a[0].get("couplers");
            if (cj && cj->is(sess::J::NUM) && want_p == shown_program) {
                const int cv = (int)cj->i() & 15;
                post([this, cv](long long n0) { nv_part_set_couplers(part, 0, cv, n0); });
            }
            if (!at_start || want_p != shown_program) {
                std::vector<std::string> w;
                for (size_t ri = 0; ri < names.size(); ri++)
                    if (want[ri])
                        w.push_back(names[ri]);
                post([this, w, want_p](long long) {     // (the swap reads it, on this thread)
                    pending_drawn = w;
                    pending_drawn_prog = want_p;
                    pending_drawn_in = false;
                });
            }
        }
    }
    // EACH CHANNEL's MIX (live.recall_scene): past the routes
    if ((x = session.get("chanstate")) && x->is(sess::J::ARR)) {
        std::vector<std::string> ev;
        for (const sess::J &e : x->a)
            if (e.is(sess::J::STR))
                ev.push_back(e.s);
        scene_recall(ev);
    }
}

// the session as it stands: what nvlive owns set, every other key kept
sess::J nv_host::session_state(const std::vector<std::array<int, 7>> &routes)
{
    sess::J j = session.is(sess::J::OBJ) ? session : sess::obj();
    j.o["master_db"] = sess::real(std::round(gval[0] * 100.0) / 100.0);
    static const char *KEYS[6] = {"master_db", "headroom_db", "thresh", "bend_range", "mod_cents", "press_db"};
    for (int i = 1; i < 6; i++)
        j.o[KEYS[i]] = sess::real(gval[i]);
    j.o["mod_rate"] = sess::real(gval[9]);
    rotary_read = {};                           // (its parts' rotary as they stand: a CC82's too)
    rotary_refresh();
    j.o["stand_in_ms"] = sess::real(gval[NV_G_STAND_IN]);
    j.o["rubato"] = sess::boolean(rub_wish.load());
    {
        std::lock_guard<std::mutex> lk(lang_mu);
        if (!lang.empty())
            j.o["language"] = sess::str(lang);
    }
    {                                           // the Spectra-Tone's rocker (live's preset "spectra_fast")
        const int sf = part ? nv_part_spectra_fast(part) : -1;
        if (sf >= 0)
            j.o["spectra_fast"] = sess::boolean(sf != 0);
    }
    j.o["std_map"] = sess::integer(default_map);
    {                                           // the rig's Eastern tuning (live.preset_from's: "" off)
        std::lock_guard<std::mutex> lk(bmu);
        j.o["eastern"] = sess::str(east_req_set ? east_asked : east_now);
    }
    {                                           // the on-screen controls (live's screen_controls, as dicts)
        sess::J cs = sess::arr();
        for (const auto &c : screen_controls) {
            sess::J d = sess::obj();
            d.o["key"] = c.key >= 0 ? sess::integer(c.key) : sess::str(c.key == -3 ? "mono" : c.key == -1 ? "bend" : "pressure");
            d.o["channel"] = c.channel < 0 ? sess::null() : sess::integer(c.channel);
            d.o["value"] = sess::integer(c.value);
            d.o["hotkey"] = c.hotkey ? sess::str(std::string(1, (char)c.hotkey)) : sess::null();
            cs.a.push_back(d);
        }
        j.o["controls"] = cs;
    }
    const int rm = room_asked >= 0 ? (int)room_asked : (int)room_idx;    // (one asked for is the room, building or not)
    if (rm >= 0 && rm < (int)E.rooms.size())
        j.o["room"] = sess::str(E.rooms[rm].name);
    j.o["messenger_firmware"] = sess::str(msgr_pre107 ? "pre-1.0.7" : "1.0.7+");
    {                                           // the Messenger set (live's messenger_port): "none" off
        const std::string w = msgr && msgr->fd.load() >= 0 ? msgr->where() : "";
        j.o["messenger_port"] = !w.empty() ? sess::str(w) : msgr_auto || !msgr_out.empty() ? sess::null() : sess::str("none");
    }
    {                                           // the MIDI inputs open (live's midi_inputs), by name
        sess::J mi = sess::arr();
        std::lock_guard<std::mutex> lk(ins.mu);
        for (auto &d : ins.want)
            mi.a.push_back(sess::str(d.second));
        j.o["midi_inputs"] = mi;
    }
    sess::J ra = sess::arr();
    for (const auto &a : routes) {
        sess::J d = route_dict(a);
        if (d.is(sess::J::OBJ))
            ra.a.push_back(d);
    }
    j.o["routes"] = ra;
    // each channel's mix (live.scene_from)
    {
        sess::J cs = sess::arr();
        for (const auto &e : scene_now())
            cs.a.push_back(sess::str(e));
        j.o["chanstate"] = cs;
    }
    // the insertion effect (live.efx_from), as the audio thread last showed it
    std::vector<int> st;
    {
        std::lock_guard<std::mutex> lk(pmu);
        st = snap.efx;
    }
    panel::EfxView v(st);
    if (v.has) {
        sess::J e = sess::obj(), ps = sess::arr(), sd = sess::arr(), ct = sess::arr(), pa = sess::arr();
        e.o["type"] = sess::arr();
        e.o["type"].a = {sess::integer(v.msb), sess::integer(v.lsb)};
        auto pair = [](int k, int x) {
            sess::J p = sess::arr();
            p.a = {sess::integer(k), sess::integer(x)};
            return p;
        };
        for (int q = 1; q <= 20; q++)
            if (v.p[q] >= 0)
                ps.a.push_back(pair(q, v.p[q]));
        for (int q = 0; q < 3; q++)
            sd.a.push_back(pair(panel::EFX_SEND[q], v.snd[q]));
        for (int q = 0; q < 4; q++)
            ct.a.push_back(pair(panel::EFX_CTL_SRC1 + q, v.ctl[q]));
        std::vector<int> on = v.parts;
        std::sort(on.begin(), on.end());
        for (int c : on)
            pa.a.push_back(sess::integer(c));
        e.o["p"] = ps;
        e.o["send"] = sd;
        e.o["ctl"] = ct;
        e.o["parts"] = pa;
        j.o["efx"] = e;
    }
    // THE USER DRUM SETS (live.udrum_from): [set, key, code, value], every
    // setting made
    {
        panel::Host::USets u;
        if (udrum_read(u)) {
            sess::J ud = sess::arr();
            for (const auto &kv : u)
                for (const auto &cv : kv.second) {
                    sess::J r = sess::arr();
                    r.a = {sess::integer(kv.first.first), sess::integer(kv.first.second), sess::integer(cv.first),
                           sess::integer(cv.second)};
                    ud.a.push_back(r);
                }
            j.o["user_drums"] = ud;
        }
    }
    // THE PARTS (live.Part.to_dict): each one's program, set or variation,
    // its place, level and mute, the first's stops; each one's other keys as
    // they were -- the drums nvlive keeps beside the part not among them
    // (its own: live's rig has none)
    sess::J &parts = j.o["parts"];
    if (!parts.is(sess::J::ARR))
        parts = sess::arr();
    // AN ORGAN's DRAWN STOPS (live's Part.drawn: its ranks' names, sorted), on
    // patch pi playing program prog; none an empty list; as written when the
    // audio does not answer
    auto put_drawn = [this](sess::J &pd, int pi, int prog, int var) {
        sess::J dn = sess::arr();
        const auto *st = prog >= 0 && prog < 128 ? E.stops_for(prog, var & 4095) : nullptr;   // (a variation's own: the 60's organs)
        if (st && !st->names.empty()) {
            const auto &names = st->names;
            std::vector<char> d;
            if (!drawn_of(pi, d))
                return;
            std::vector<std::string> on;
            for (size_t ri = 0; ri < names.size() && ri < d.size(); ri++)
                if (d[ri])
                    on.push_back(names[ri]);
            std::sort(on.begin(), on.end());
            for (auto &n : on)
                dn.a.push_back(sess::str(n));
        }
        pd.o["drawn"] = dn;
    };
    std::vector<PartAt> rows;
    std::vector<size_t> at;                     // (each one's index: its knobs read by it)
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        for (size_t i = 0; i < pats.size(); i++)
            if (!pats[i].gone && pats[i].pid != 2 && pats[i].pid != 3) {
                rows.push_back(pats[i]);
                at.push_back(i);
            }
    }
    parts.a.resize(rows.size());
    for (size_t k = 0; k < rows.size(); k++) {
        sess::J &pd = parts.a[k];
        if (!pd.is(sess::J::OBJ)) {
            pd = sess::obj();
            pd.o["tuner"] = sess::str("gm2");
            pd.o["drawn"] = sess::arr();
        }
        const PartAt &pa = rows[k];
        // (the GS variation alone: a cabinet's or a pickup's choice over bit 12 is saved by name, below -- live's to_dict)
        const int vk = (pa.drums ? 0 : (k == 0 ? (shown_program >= 128 ? 0 : shown_var.load()) : pa.var)) & 4095;
        pd.o["program"] = sess::integer((k == 0 ? shown_program.load() : pa.program) & 127);
        pd.o["drums"] = sess::boolean(k == 0 ? shown_program >= 128 : pa.drums);
        if (vk)
            pd.o["bank"] = sess::integer(vk);
        else
            pd.o.erase("bank");
        pd.o["channel"] = pa.channel < 0 ? sess::null() : sess::integer(pa.channel);
        pd.o["lo"] = sess::integer(pa.lo);
        pd.o["hi"] = sess::integer(pa.hi);
        pd.o["transpose"] = sess::integer(pa.tr);
        pd.o["level_db"] = sess::real(pa.level);
        pd.o["muted"] = sess::boolean(pa.muted);
        if (pa.fixed >= 0)                      // (live writes it only when set)
            pd.o["fixed_touch"] = sess::boolean(pa.fixed != 0);
        else
            pd.o.erase("fixed_touch");
        if (pa.cab >= 0 && pa.cab < (int)(sizeof CAB_NAMES / sizeof CAB_NAMES[0]))     // (its cabinet, chosen: live's likewise, by name)
            pd.o["cabinet"] = sess::str(CAB_NAMES[pa.cab]);
        else
            pd.o.erase("cabinet");
        if (pa.pk >= 0 && pa.pk < (int)(sizeof PK_NAMES / sizeof PK_NAMES[0]))      // (...its pickup, the same)
            pd.o["pickup"] = sess::str(PK_NAMES[pa.pk]);
        else
            pd.o.erase("pickup");
        if (pa.rot_mode >= 0)                   // (its rotary heard, live's likewise: only when set)
            pd.o["rotary"] = sess::str(pa.rot_mode ? "mics" : "room");
        else
            pd.o.erase("rotary");
        if (pa.rot_sep >= 0.0)
            pd.o["rotary_spread"] = sess::real(std::round(pa.rot_sep * 180.0 / M_PI * 1000.0) / 1000.0);
        else
            pd.o.erase("rotary_spread");
        if (pa.drive >= 0.0)                    // (an organ's drive knob, live's likewise)
            pd.o["drive"] = sess::real(pa.drive);
        else
            pd.o.erase("drive");
        if (msgr_reads && k == 0)               // (a Messenger read: the first part's cc_map, live's per part)
            pd.o["cc_map"] = sess::str("messenger");
        else if (!msgr_reads)
            pd.o.erase("cc_map");
        // ITS OWN KNOBS (live's synth, synth_b, synth_units 6), by moog.PANEL's
        // names: a switch as live keeps it (on/off a bool; an octave, a mode,
        // a shape an int), a knob a float -- a value already there kept as written
        bool anyk = false;
        for (int lay = 0; lay < 2; lay++) {
            double pn[42];
            char own[42];
            const char *key = lay ? "synth_b" : "synth";
            const int n = pa.drums ? 0 : synth_state(at[k], lay, pn, own);
            if (n < 0)                          // (never read, and the audio does not answer: as they were)
                continue;
            if (n <= lay) {                     // (not a Moog, or no layer B)
                pd.o.erase(key);
                continue;
            }
            sess::J sy = sess::obj();
            const sess::J *had = pd.get(key);
            for (int q = 0; q < 42; q++) {
                if (!own[q])
                    continue;
                const char *nm = panel::MK_NAMES[q];
                const sess::J *old = had ? had->get(nm) : nullptr;
                if (old && (old->is(sess::J::NUM) || old->is(sess::J::BOOL)) && old->d() == pn[q]) {
                    sy.o[nm] = *old;
                    continue;
                }
                std::string kind;
                for (int i = 0; i < panel::NSYNTH; i++)
                    if (!strcmp(panel::SYNTH_KNOBS[i][1], nm))
                        kind = panel::SYNTH_KNOBS[i][3];
                if (kind == "onoff")
                    sy.o[nm] = sess::boolean(pn[q] != 0.0);
                else if (kind == "foot" || kind == "mode" || kind == "lfoshape" || kind == "lfodest" || kind == "moddest"
                         || kind == "mfrange")
                    sy.o[nm] = sess::integer((long)pn[q]);
                else
                    sy.o[nm] = sess::real(pn[q]);
            }
            if (sy.o.empty()) {
                pd.o.erase(key);
            } else {
                pd.o[key] = sy;
                anyk = true;
            }
        }
        if (k > 0)                              // (the first's below: its program as shown)
            put_drawn(pd, pa.pi, pa.drums ? -1 : pa.program & 127, pa.drums ? 0 : pa.var);
            {                                   // (its coupler switches: live's to_dict "couplers")
                const int cv = pa.drums ? -1 : nv_part_couplers(part, pa.pi);
                if (cv >= 0)
                    pd.o["couplers"] = sess::integer(cv);
                else
                    pd.o.erase("couplers");
            }
        if (anyk)
            pd.o["synth_units"] = sess::integer(6);
        else if (!pd.get("synth") && !pd.get("synth_b"))
            pd.o.erase("synth_units");
    }
    if (parts.a.empty())
        return j;
    sess::J &p0 = parts.a[0];
    const int sp = shown_program, sv = sp >= 128 ? 0 : shown_var.load() & 4095;     // (the GS variation alone)
    p0.o["program"] = sess::integer(sp & 127);
    {                                           // (the tuner it plays: the session's, --tuner's, the panel's)
        std::lock_guard<std::mutex> lk(bmu);
        p0.o["tuner"] = sess::str(!tuner_asked.empty() ? tuner_asked : tuner_now);
    }
    p0.o["drums"] = sess::boolean(sp >= 128);
    if (sv)
        p0.o["bank"] = sess::integer(sv);
    else
        p0.o.erase("bank");
    put_drawn(p0, rows.empty() ? 0 : rows[0].pi, sp < 128 ? sp : -1, sv);
    // A MODULE MODE ON (module.h): what it changes -- the parts, the
    // standard, each channel's mix, the insertion effect, the user drum sets,
    // the room (a sequencer's GS reverb sets it) -- are the module's, not the player's: the setup it set aside is what
    // the session keeps, and what leaving it puts back
    if (module_on.load(std::memory_order_acquire)) {
        std::lock_guard<std::mutex> lk(module_mu);
        if (module_saved.is(sess::J::OBJ))
            for (const char *k : {"parts", "std_map", "chanstate", "efx", "user_drums", "room"}) {
                if (const sess::J *v = module_saved.get(k))
                    j.o[k] = *v;
                else
                    j.o.erase(k);
            }
    }
    return j;
}

// written when it changed (live.save_session: atomically; never raises). The
// first write over a session nvlive did not make keeps it beside, once.
bool nv_host::session_save(const std::vector<std::array<int, 7>> &routes)
{
    if (!session_on)
        return false;
    sess::J j = session_state(routes);
    std::string text = sess::dump(j);
    if (text == session_written)
        return true;
    if (session_written.empty() && access(session_path.c_str(), F_OK) == 0) {
        const std::string bak = session_path + ".before-nvlive";
        if (access(bak.c_str(), F_OK) != 0) {
            sess::J old;
            if (sess::load(session_path, old))
                sess::save(bak, old);
        }
    }
    if (!sess::save(session_path, j))
        return false;
    session_written = text;
    session = j;
    return true;
}


// ---- THE LIBRARY's CALLS (host.h): parts, presets, the session ----

// the routes in force for the library's presets: the last preset's or
// session's (an app has no route editor yet: they pass through unchanged;
// nvlive saves its panel's own)
static std::vector<std::array<int, 7>> lib_routes(nv_host *h)
{
    return !h->routes_replaced.empty() ? h->routes_replaced : h->session_routes;
}

static int copy_out(const std::string &m, char *buf, int cap)
{
    if (buf && cap > 0)
        snprintf(buf, (size_t)cap, "%s", m.c_str());
    return (int)m.size();
}

extern "C" {

int nv_host_parts(nv_host *h, nv_host_partinfo *out, int cap)
{
    const std::vector<panel::PartRow> rows = h->part_rows();
    for (int i = 0; out && i < cap && i < (int)rows.size(); i++) {
        const panel::PartRow &r = rows[(size_t)i];
        nv_host_partinfo &o = out[i];
        o.row = i;
        o.program = r.program;
        o.variation = r.var & 4095;     // (its GS variation: a cabinet choice rides over bit 12, nv_host_cabinet's)
        o.drums = r.drums;
        o.channel = r.channel;
        o.lo = r.lo;
        o.hi = r.hi;
        o.transpose = r.tr;
        o.level_db = r.level;
        o.muted = r.muted;
        o.solo = r.solo;
        o.touch_fixed = r.touch_fixed;
        snprintf(o.name, sizeof o.name, "%s", r.name.c_str());
    }
    return (int)rows.size();
}

// (rows as nv_host_parts lists them; the host's own index behind each)
static bool row_index(nv_host *h, int row, size_t &idx)
{
    const std::vector<panel::PartRow> rows = h->part_rows();
    if (row < 0 || row >= (int)rows.size())
        return false;
    idx = (size_t)rows[(size_t)row].index;
    return true;
}

void nv_host_part_set(nv_host *h, int row, int channel, int lo, int hi, int transpose, double level_db, int muted)
{
    size_t i;
    if (row_index(h, row, i))
        h->part_set(i, channel, lo, hi, transpose, level_db, muted != 0);
}

void nv_host_part_pick(nv_host *h, int row, int pick)
{
    size_t i;
    if (row_index(h, row, i))
        h->pick_row(i, pick);
}

int nv_host_part_layer(nv_host *h, int row)
{
    size_t i;
    return row_index(h, row, i) && h->part_layer(i) ? 0 : -1;
}

int nv_host_part_split(nv_host *h, int row, char *why, int cap)
{
    size_t i;
    std::string w = "no such part";
    if (row_index(h, row, i) && h->part_split(i, w))
        return 0;
    copy_out(w, why, cap);
    return -1;
}

int nv_host_part_delete(nv_host *h, int row, char *why, int cap)
{
    size_t i;
    std::string w = "no such part";
    if (row_index(h, row, i) && h->part_delete(i, w))
        return 0;
    copy_out(w, why, cap);
    return -1;
}

void nv_host_part_solo(nv_host *h, int row)
{
    size_t i;
    if (row_index(h, row, i))
        h->part_solo(i);
}

void nv_host_part_touch(nv_host *h, int row, int fixed)
{
    size_t i;
    if (row_index(h, row, i))
        h->part_touch(i, fixed ? 1 : 0);
}

void nv_host_set_session_path(nv_host *h, const char *path)
{
    h->session_path = path ? path : "";
    h->session_on = path && *path;
}

int nv_host_presets(nv_host *h, char *names, int cap)
{
    sess::J d;
    std::string all;
    if (h->presets_read(d))
        for (const auto &kv : d.o)
            all += (all.empty() ? "" : "\n") + kv.first;
    return copy_out(all, names, cap);
}

int nv_host_preset_save(nv_host *h, const char *name, char *msg, int cap)
{
    if (!name || !*name || h->session_path.empty())
        return copy_out("no name, or no session path (nv_host_set_session_path)", msg, cap), -1;
    sess::J d;
    if (!sess::load(h->presets_path(), d))
        d = sess::obj();
    d.o[name] = h->session_state(lib_routes(h));
    if (!sess::save(h->presets_path(), d))
        return copy_out("could not write " + h->presets_path(), msg, cap), -1;
    copy_out(std::string("saved '") + name + "'", msg, cap);
    return 0;
}

int nv_host_preset_load(nv_host *h, const char *name, char *msg, int cap)
{
    sess::J d;
    const sess::J *p = name && h->presets_read(d) ? d.get(name) : nullptr;
    if (!p || !p->is(sess::J::OBJ))
        return copy_out(std::string("no preset '") + (name ? name : "") + "'", msg, cap), -1;
    h->apply_setup(*p, false);
    copy_out(std::string("loading '") + name + "'", msg, cap);
    return 0;
}

// ---- A PRESET AS A MIDI SETUP MEASURE (live.preset_midi: the same bytes) ----

// a text event's bytes: printable ASCII kept, every other byte '?'
static std::string ascii_text(const std::string &s)
{
    std::string o;
    for (unsigned char c : s)
        o += c >= 32 && c < 127 ? (char)c : '?';
    return o;
}

// a type-0 Standard MIDI File as mido writes one (running status; a sysex
// F0, its length, its data, F7; a meta FF, type, length, data)
struct SmfOut {
    std::vector<uint8_t> d;
    int run = -1;
    long long at = 0;
    void vlq(unsigned long v)
    {
        uint8_t b[5];
        int n = 0;
        b[n++] = v & 0x7F;
        while (v >>= 7)
            b[n++] = 0x80 | (v & 0x7F);
        while (n)
            d.push_back(b[--n]);
    }
    void when(long long t)
    {
        vlq((unsigned long)(t - at));
        at = t;
    }
    void meta(long long t, int type, const std::string &x)
    {
        when(t);
        d.push_back(0xFF);
        d.push_back((uint8_t)type);
        vlq(x.size());
        d.insert(d.end(), x.begin(), x.end());
        run = -1;
    }
    void sysex(long long t, const std::vector<uint8_t> &x)
    {
        when(t);
        d.push_back(0xF0);
        vlq(x.size() + 1);
        d.insert(d.end(), x.begin(), x.end());
        d.push_back(0xF7);
        run = -1;
    }
    void msg(long long t, int status, int a, int b = -1)
    {
        when(t);
        if (status != run)
            d.push_back((uint8_t)status);
        d.push_back((uint8_t)a);
        if (b >= 0)
            d.push_back((uint8_t)b);
        run = status;
    }
};

static std::vector<uint8_t> gs_dt1(int a0, int a1, int a2, int v)
{
    const int sum = a0 + a1 + a2 + v;
    return {0x41, 0x10, 0x42, 0x12, (uint8_t)a0, (uint8_t)a1, (uint8_t)a2, (uint8_t)v, (uint8_t)((128 - sum % 128) % 128)};
}

// (h: the engine whose organs' stops the parts draw -- their stop words; null none)
std::string preset_smf(const sess::J &p, const std::string &name, const nv_host *h)
{
    const long long GAP = 48, END = 1920;      // (live's SETUP_GAP_TICKS, SETUP_END_TICKS)
    SmfOut o;
    o.meta(0, 0x03, ascii_text(name));
    o.meta(0, 0x51, std::string("\x07\xA1\x20", 3));       // set_tempo 500000
    o.sysex(0, {0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41});   // GS Reset
    const long long t = GAP;
    // THE CHANNELS' CONTROLS (the preset's scene): their bank aside
    if (const sess::J *cs = p.get("chanstate"))
        if (cs->is(sess::J::ARR))
            for (const sess::J &e : cs->a) {
                if (!e.is(sess::J::STR))
                    continue;
                int ch, c, v;
                if (sscanf(e.s.c_str(), "control_change channel=%d control=%d value=%d", &ch, &c, &v) == 3) {
                    if (c != 0 && c != 32)
                        o.msg(t, 0xB0 | (ch & 15), c & 127, v & 127);
                } else if (!e.s.compare(0, 12, "sysex data=(")) {
                    std::vector<uint8_t> d;
                    const char *q = e.s.c_str() + 12;
                    while (*q && *q != ')') {
                        char *end;
                        const long b = strtol(q, &end, 10);
                        if (end == q)
                            break;
                        d.push_back((uint8_t)std::max(0L, std::min(127L, b)));
                        q = *end == ',' ? end + 1 : end;
                    }
                    o.sysex(t, d);
                }
            }
    std::vector<const sess::J *> parts;
    if (const sess::J *ps = p.get("parts"))
        if (ps->is(sess::J::ARR))
            for (const sess::J &x : ps->a)
                if (x.is(sess::J::OBJ))
                    parts.push_back(&x);
    auto has = [](const sess::J *x, const char *k) { const sess::J *v = x->get(k); return v && !v->is(sess::J::NUL); };
    auto num = [](const sess::J *x, const char *k, double d) { const sess::J *v = x->get(k); return v ? v->d(d) : d; };
    std::set<int> taken;
    for (const sess::J *x : parts)
        if (has(x, "channel"))
            taken.insert((int)x->get("channel")->i() & 15);
    std::map<int, int> owner;
    for (size_t i = 0; i < parts.size(); i++) {
        const sess::J *x = parts[i];
        const bool drums = num(x, "drums", 0.0) != 0.0;
        int ch = -1;
        if (has(x, "channel"))
            ch = (int)x->get("channel")->i() & 15;
        else if (drums && !owner.count(9) && !taken.count(9))
            ch = 9;
        else
            for (int c = 0; c < 16 && ch < 0; c++)
                if (c != 9 && !taken.count(c) && !owner.count(c))
                    ch = c;
        const int lo = (int)num(x, "lo", 0), hi = (int)num(x, "hi", 127), tr = (int)num(x, "transpose", 0);
        char tx[160];
        if (ch < 0 || owner.count(ch)) {
            if (ch < 0)
                snprintf(tx, sizeof tx, "part %zu: no channel left", i + 1);
            else
                snprintf(tx, sizeof tx, "part %zu: shares channel %d with part %d", i + 1, ch + 1, owner[ch] + 1);
            o.meta(t, 0x01, ascii_text(tx));
            continue;
        }
        owner[ch] = (int)i;
        if (tr)
            snprintf(tx, sizeof tx, "part %zu: channel %d, keys %d-%d, transpose %+d", i + 1, ch + 1, lo, hi, tr);
        else
            snprintf(tx, sizeof tx, "part %zu: channel %d, keys %d-%d", i + 1, ch + 1, lo, hi);
        o.meta(t, 0x01, ascii_text(tx));
        int prog = (int)num(x, "program", 0);
        if (drums != (ch == 9)) {               // (GS's Use For Rhythm Part: channel 10 block 0, 1-9 1-9, 11-16 A-F)
            const int blk = ch == 9 ? 0 : ch < 9 ? ch + 1 : ch;
            o.sysex(t, gs_dt1(0x40, 0x10 | blk, 0x15, drums ? 1 : 0));
        }
        int b0, b32;
        if (drums) {
            b0 = 0;
            b32 = prog >= 128 ? prog / 128 : 0;
            prog %= 128;
        } else {
            const int v = (int)num(x, "bank", 0) & 4095;       // (patch_map.bank_select)
            b0 = v & 0x7F;
            b32 = v >> 7;
        }
        o.msg(t, 0xB0 | ch, 0, b0);
        o.msg(t, 0xB0 | ch, 32, b32);
        o.msg(t, 0xC0 | ch, prog & 127);
        if (!drums) {
            const sess::J *cb = x->get("cabinet"), *pu = x->get("pickup");
            const int cab = cb && cb->is(sess::J::STR) ? cab_index(cb->s) : -1, pk = pu && pu->is(sess::J::STR) ? pk_index(pu->s) : -1;
            if (cab > 0)
                o.msg(t, 0xB0 | ch, 83, cab);
            if (pk > 0)
                o.msg(t, 0xB0 | ch, 85, pk);
            // ...AN ORGAN's STOPS: its drawn ranks as the voice's stop word
            // (live._organ_class: the variation's organ where it has one)
            const sess::J *dn = x->get("drawn");
            const OrganSpec *og = h && dn && dn->is(sess::J::ARR) ? h->organ_of(prog & 127, (int)num(x, "bank", 0) & 4095)
                                                                 : nullptr;
            if (og) {
                std::vector<std::string> names;
                for (int r = 0; r < og->n_rank; r++)
                    names.push_back(og->rank[r].key);
                long long w = 0;
                for (int r = 0; r < og->n_rank; r++)
                    for (const sess::J &nm : dn->a)
                        if (nm.is(sess::J::STR) && rank_rename(nm.s, names) == names[(size_t)r])     // (its old names too)
                            w |= 1LL << r;
                for (int j = 0; j < og->n_wccs; j++)
                    o.msg(t, 0xB0 | ch, og->wccs[j] & 127, (int)((w >> (7 * j)) & 0x7F));
            }
            // ...A MOOG's PANEL (live.preset_midi): CC86's Messenger mode,
            // then the chart's CCs in its order, coarse halves first -- the
            // voice's knobs, the part's own over them (in synth_units 6;
            // older ones left as the voice's, as a session's load leaves them)
            double pn[NV_MK_N];
            if (h && h->moog_pn_of(prog & 127, (int)num(x, "bank", 0) & 4095, pn)) {
                const sess::J *su = x->get("synth_units"), *sy = x->get("synth");
                if (su && su->is(sess::J::NUM) && su->i() >= 6 && sy && sy->is(sess::J::OBJ))
                    for (const auto &kv : sy->o) {
                        const int mk = panel::mk_index(kv.first.c_str());
                        if (mk >= 0 && (kv.second.is(sess::J::NUM) || kv.second.is(sess::J::BOOL)))
                            pn[mk] = kv.second.d();
                    }
                o.msg(t, 0xB0 | ch, 86, 127);
                for (int cc = 0; cc < 128; cc++) {
                    int k, kind, lo;
                    nv_msgr_chart(cc, 0, &k, &kind);
                    if (k < 0 || (k == NV_MK_A_VEL && pn[k] < 0.0))
                        continue;
                    o.msg(t, 0xB0 | ch, cc, nv_msgr_cc_value(kind, pn[k], &lo));
                    if (lo >= 0)
                        o.msg(t, 0xB0 | ch, cc + 32, lo);
                }
            }
        }
        const int vol = num(x, "muted", 0.0) != 0.0 ? 0
                        : (int)std::max(0.0, std::min(127.0, std::nearbyint(127.0 * pow(10.0, num(x, "level_db", 0.0) / 40.0))));
        o.msg(t, 0xB0 | ch, 7, vol);
        if (has(x, "pan"))
            o.msg(t, 0xB0 | ch, 10, std::max(0, std::min(127, (int)x->get("pan")->i())));
    }
    o.meta(END, 0x2F, "");
    std::string f = "MThd";
    const uint8_t hd[10] = {0, 0, 0, 6, 0, 0, 0, 1, 480 >> 8, 480 & 255};
    f.append((const char *)hd, 10);
    f += "MTrk";
    const size_t n = o.d.size();
    const uint8_t ln[4] = {(uint8_t)(n >> 24), (uint8_t)(n >> 16), (uint8_t)(n >> 8), (uint8_t)n};
    f.append((const char *)ln, 4);
    f.append((const char *)o.d.data(), n);
    return f;
}

// A PRESET's SETUP MEASURE written to OUT (live.preset_midi), its organs'
// stops H's (null: none): 0, or -1 (no such preset, or not written)
extern "C" int nv_preset_midi_file(const nv_host *h, const char *presets_path, const char *name, const char *out)
{
    sess::J d;
    // (the player's presets file: the defaults under it; another file as it is)
    const bool ours = h && presets_path && h->presets_path() == presets_path;
    const sess::J *p = presets_path && name && (ours ? h->presets_read(d) : sess::load(presets_path, d)) ? d.get(name) : nullptr;
    if (!p || !p->is(sess::J::OBJ) || !out)
        return -1;
    const std::string f = preset_smf(*p, name, h);
    FILE *fh = fopen(out, "wb");
    if (!fh)
        return -1;
    const bool ok = fwrite(f.data(), 1, f.size(), fh) == f.size();
    return fclose(fh) == 0 && ok ? 0 : -1;
}

int nv_host_session_load(nv_host *h)
{
    sess::J d;
    if (h->session_path.empty() || !sess::load(h->session_path, d) || !d.is(sess::J::OBJ))
        return -1;
    h->session = d;
    h->apply_setup(d, false);
    return 0;
}

int nv_host_session_save(nv_host *h)
{
    return h->session_path.empty() || !h->session_save(lib_routes(h)) ? -1 : 0;
}

// AN ORGAN's STOPS (the export's LSTOP: livetui's stop rows)
int nv_host_stop_names_v(nv_host *h, int program, int variation, char *names, int cap, int labels)
{
    const auto *st = h->E.stops_for(program, variation);
    if (!st)
        return 0;
    const auto &nm = labels && st->labels.size() == st->names.size() ? st->labels : st->names;
    std::string all;
    for (size_t i = 0; i < nm.size(); i++)
        all += (i ? "\n" : "") + nm[i];
    copy_out(all, names, cap);
    return (int)nm.size();
}

int nv_host_stop_names(nv_host *h, int program, char *names, int cap)
{
    return nv_host_stop_names_v(h, program, 0, names, cap, 0);
}

int nv_host_stop_rows_v(nv_host *h, int program, int variation, int *out, int cap)
{
    const auto *stp = h->E.stops_for(program, variation);
    if (!stp)
        return 0;
    const auto &st = *stp;
    std::vector<int> v;
    for (size_t r = 0; r < st.rows.size(); r++) {
        for (size_t i = 0; i < st.rows[r].size(); i++) {
            if (r < st.breaks.size() && std::find(st.breaks[r].begin(), st.breaks[r].end(), (int)i) != st.breaks[r].end())
                v.push_back(-2);
            v.push_back(st.rows[r][i]);
        }
        v.push_back(-1);
    }
    for (int i = 0; out && i < cap && i < (int)v.size(); i++)
        out[i] = v[(size_t)i];
    return (int)v.size();
}

int nv_host_stop_rows(nv_host *h, int program, int *out, int cap)
{
    return nv_host_stop_rows_v(h, program, 0, out, cap);
}

// (the patch behind a row, as nv_host_parts lists them: -1 none)
static int row_pi(nv_host *h, int row)
{
    size_t idx;
    if (!row_index(h, row, idx))
        return -1;
    std::lock_guard<std::mutex> lk(h->parts_mu);
    return idx < h->pats.size() && !h->pats[idx].gone ? h->pats[idx].pi : -1;
}

int nv_host_drawn(nv_host *h, char *out, int cap) { return nv_host_part_drawn(h, 0, out, cap); }

int nv_host_part_drawn(nv_host *h, int row, char *out, int cap)
{
    const int pi = row_pi(h, row);
    std::vector<char> d;
    if (pi < 0 || !h->drawn_of(pi, d))
        return 0;
    for (int i = 0; out && i < cap && i < (int)d.size(); i++)
        out[i] = d[(size_t)i];
    return (int)d.size();
}

void nv_host_toggle_stop(nv_host *h, int rank)
{
    const int pi = row_pi(h, 0);
    if (pi < 0)
        return;
    h->post([h, pi, rank](long long n) {
        if (pi == 0)
            h->pending_drawn_prog = -1;         // (a stop drawn by hand: a preset's no longer)
        nv_part_toggle_stop(h->part, pi, rank, n);
    });
}

void nv_host_part_set_drawn(nv_host *h, int row, const char *want, int n)
{
    const int pi = row_pi(h, row);
    if (pi < 0)
        return;
    std::vector<char> w(want, want + std::max(0, n));
    h->post([h, pi, w](long long) {
        if (pi == 0)
            h->pending_drawn_prog = -1;
        nv_part_set_drawn(h->part, pi, w.data(), (int)w.size());
    });
}

}  // extern "C"

// ---- TUNING (the panel's t and E: livetui's tuners, the Eastern tuning) ----
extern "C" {

int nv_host_tuners(char *out, int cap)
{
    std::string all;
    for (int i = 0; i < panel::NTUNERS; i++)
        all += std::string(i ? "\n" : "") + panel::TUNERS[i][0] + "\t" + panel::TUNERS[i][1];
    return copy_out(all, out, cap);
}

int nv_host_tuner(nv_host *h, char *out, int cap)
{
    std::string t;
    {
        std::lock_guard<std::mutex> lk(h->bmu);
        t = !h->tuner_asked.empty() ? h->tuner_asked : h->tuner_now;
    }
    return copy_out(t, out, cap);
}

void nv_host_set_tuner(nv_host *h, const char *name)
{
    if (name && *name)
        h->set_tuner(name);
}

int nv_host_eastern(nv_host *h, char *out, int cap)
{
    std::string e;
    {
        std::lock_guard<std::mutex> lk(h->bmu);
        e = h->east_req_set ? h->east_asked : h->east_now;
    }
    return copy_out(e, out, cap);
}

void nv_host_set_eastern(nv_host *h, const char *spec) { h->set_eastern(spec ? spec : ""); }

}  // extern "C"

// ---- THE EFFECTS (the panel's x and G: the insertion effect, the system effects) ----
extern "C" {

int nv_host_efx_tables(nv_host *h, char *out, int cap) { return copy_out(h->E.efxu, out, cap); }

int nv_host_efx_state(nv_host *h, nv_host_efx *s)
{
    std::vector<int> o;
    std::string why;
    {
        std::lock_guard<std::mutex> lk(h->pmu);
        o = h->snap.efx;
        why = h->snap.efx_why;
    }
    panel::EfxView v(o);
    s->has = v.has;
    s->msb = v.msb;
    s->lsb = v.lsb;
    for (int q = 0; q < 21; q++)
        s->p[q] = v.p[q];
    for (int q = 0; q < 3; q++)
        s->send[q] = v.snd[q];
    for (int q = 0; q < 4; q++)
        s->ctl[q] = v.ctl[q];
    s->nparts = 0;
    for (int c : v.parts)
        if (s->nparts < 32)
            s->parts[s->nparts++] = c;
    s->status = v.status;
    snprintf(s->why, sizeof s->why, "%s", why.c_str());
    return v.has ? 0 : -1;
}

void nv_host_efx_send(nv_host *h, int kind, int a, int b)
{
    const std::vector<uint8_t> m = panel::efx_message((char)kind, a, b);
    h->post([h, m](long long) { nv_part_sysex(h->part, m.data(), (int)m.size()); });
}

int nv_host_sysfx(nv_host *h, nv_host_sysfx_state *s)
{
    struct Got {
        std::map<int, int> rev, eq;
        int cho[7] = {}, dly[11] = {};
        bool gs = false;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [h, got](long long) {
        got->rev = h->gs_rev;
        got->eq = h->gs_eq;
        got->gs = nv_part_gs_fx(h->part, got->cho, got->dly) != 0;
        got->done = true;
    };
    h->post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return -1;
    static const int TIME[8] = {80, 56, 64, 72, 64, 88, 32, 64};
    auto at = [](const std::map<int, int> &m, int k, int d) {
        auto it = m.find(k);
        return it != m.end() ? it->second : d;
    };
    s->rev_macro = at(got->rev, 0x30, -1);
    s->rev_level = at(got->rev, 0x33, 64);
    s->rev_time = at(got->rev, 0x34, TIME[s->rev_macro >= 0 && s->rev_macro < 8 ? s->rev_macro : 4]);
    s->rev_fb = s->rev_macro == 6 || s->rev_macro == 7 ? at(got->rev, 0x35, s->rev_macro == 6 ? 40 : 32) : -1;
    snprintf(s->room, sizeof s->room, "%s", h->room_now.c_str());
    s->gs = got->gs;
    for (int k = 0; k < 7; k++)
        s->cho[k] = got->cho[k];
    for (int k = 0; k < 11; k++)
        s->dly[k] = got->dly[k];
    for (int k = 0; k < 4; k++)
        s->eq[k] = at(got->eq, k, k % 2 ? 0x40 : 0);
    return 0;
}

void nv_host_sysfx_send(nv_host *h, int hi, int lo, int v)
{
    std::vector<uint8_t> x{0x41, 0x10, 0x42, 0x12, 0x40, (uint8_t)hi, (uint8_t)lo, (uint8_t)std::max(0, std::min(127, v))};
    x.push_back((uint8_t)((128 - (0x40 + hi + lo + x[7]) % 128) % 128));
    h->enqueue(Midi{6, 0, 0, 0, x});
}

int nv_host_synth_knobs(char *out, int cap)
{
    std::string all;
    for (int i = 0; i < panel::NSYNTH; i++) {
        const char **k = panel::SYNTH_KNOBS[i];
        std::string st;
        for (double v : panel::synth_steps(k[3])) {
            char b[24];
            snprintf(b, sizeof b, "%s%g", st.empty() ? "" : ",", v);
            st += b;
        }
        // (then the touch card's: its column, group, generic label, a switch's words -- panel::SYNTH_CARD)
        int at = -1;
        const char *const *c = panel::synth_card(k[1], &at);
        all += std::string(k[0]) + "\t" + std::to_string(panel::mk_index(k[1])) + "\t" + k[2] + "\t" + k[3] + "\t" + st
               + "\t" + (panel::synth_centred(k[3]) ? "1" : "0") + "\t" + (c ? c[1] : "") + "\t" + (c ? c[2] : k[0])
               + "\t" + (c ? c[3] : k[2]) + "\t" + (c ? c[4] : "") + "\t" + std::to_string(at) + "\n";
    }
    return copy_out(all, out, cap);
}

// (a row is a shown part: its place in pats skips the removed ones -- row_index)
int nv_host_synth_get(nv_host *h, int row, int layer, double *pn, char *own)
{
    size_t i;
    return row_index(h, row, i) ? h->synth_state(i, layer, pn, own) : 0;
}
void nv_host_synth_set(nv_host *h, int row, int layer, int knob, double v)
{
    size_t i;
    if (knob >= 0 && knob < NV_MK_N && row_index(h, row, i)) h->synth_set(i, layer, knob, v);
}
void nv_host_synth_forget(nv_host *h, int row, int layer, int knob)
{
    size_t i;
    if (knob >= 0 && knob < NV_MK_N && row_index(h, row, i)) h->synth_forget(i, layer, knob);
}
int nv_host_synth_send(nv_host *h, int row)
{
    size_t i;
    return row_index(h, row, i) ? h->synth_send(i) : 0;
}
int nv_host_synth_fmt(const char *kind, double v, const double *pn, char *out, int cap)
{
    return copy_out(panel::synth_fmt(kind, v, pn), out, cap);
}

int nv_host_messenger_line(nv_host *h, char *out, int cap)
{
    const std::string w = h->msgr && h->msgr->fd.load() >= 0 ? h->msgr->where() : h->msgr_out;
    return copy_out(w.empty() ? std::string(h->msgr_auto ? "-" : "") : w, out, cap);
}
int nv_host_messenger_reads(nv_host *h) { return h->msgr_reads ? 1 : 0; }
void nv_host_set_messenger_reads(nv_host *h, int on)
{
    h->msgr_reads_set = true;               // (the player's: kept over a Messenger's input opening)
    h->messenger_reading(on != 0);
}
int nv_host_messenger_pre107(nv_host *h) { return h->msgr_pre107 ? 1 : 0; }
void nv_host_set_messenger_pre107(nv_host *h, int on)
{
    h->msgr_pre107 = on != 0;
    const double v = on ? 1.0 : 0.0;
    h->post([h, v](long long) { nv_part_set(h->part, 9, v); });
}
// A PART's ROTARY HEARD: out[0] the mode (-1 its own way, 0 room, 1 mics),
// [1] the mics' spread in degrees (<0 the default); 0 no such row
int nv_host_rotary(nv_host *h, int row, double *out)
{
    size_t i;
    if (!row_index(h, row, i))
        return 0;
    h->rotary_refresh();
    std::lock_guard<std::mutex> lk(h->parts_mu);
    if (i >= h->pats.size())
        return 0;
    out[0] = h->pats[i].rot_mode;
    out[1] = h->pats[i].rot_sep < 0.0 ? -1.0 : h->pats[i].rot_sep * 180.0 / M_PI;
    return 1;
}
// A PART's CABINET (live.set_cabinet): *chosen its choice (-1 none: the
// voice's own), *now the one it plays through (0 its own), offer[] the
// choices its voice offers (patch_map.cab_choices) -- how many; -1 no such row
int nv_host_cabinet(nv_host *h, int row, int *chosen, int *now, int *offer, int cap)
{
    size_t i;
    if (!row_index(h, row, i))
        return -1;
    std::lock_guard<std::mutex> lk(h->parts_mu);
    if (i >= h->pats.size())
        return -1;
    const nv_host::PartAt &pa = h->pats[i];
    const int v = pa.want >= 0 ? pa.want_var : pa.var, p = pa.want >= 0 ? pa.want : pa.program;
    const bool dr = pa.want >= 0 ? pa.want_dr : pa.drums;
    *chosen = pa.cab;
    *now = dr ? 0 : (v >> 12) & 15;
    int n = 0;
    for (int c = 1; !dr && c < 16; c++)
        if (((h->with_cab(p, v, c) >> 12) & 15) == c) {
            if (n < cap)
                offer[n] = c;
            n++;
        }
    return n;
}
void nv_host_set_cabinet(nv_host *h, int row, int choice)
{
    size_t i;
    if (row_index(h, row, i))
        h->set_cabinet(i, choice);
}
// A PART's PICKUP (live.set_pickup), as nv_host_cabinet: *chosen (-1 none),
// *now the one it plays through (0 its own), offer[] the PICKUP_CHOICES its
// voice offers (patch_map.pk_choices) -- how many; -1 no such row
int nv_host_pickup(nv_host *h, int row, int *chosen, int *now, int *offer, int cap)
{
    size_t i;
    if (!row_index(h, row, i))
        return -1;
    std::lock_guard<std::mutex> lk(h->parts_mu);
    if (i >= h->pats.size())
        return -1;
    const nv_host::PartAt &pa = h->pats[i];
    const int v = pa.want >= 0 ? pa.want_var : pa.var, p = pa.want >= 0 ? pa.want : pa.program;
    const bool dr = pa.want >= 0 ? pa.want_dr : pa.drums;
    *chosen = pa.pk;
    *now = dr ? 0 : (v >> 16) & 7;
    int n = 0;
    for (int c = 1; !dr && c < 8; c++)
        if (((h->with_cab(p, v, 0, c) >> 16) & 7) == c) {
            if (n < cap)
                offer[n] = c;
            n++;
        }
    return n;
}
void nv_host_set_pickup(nv_host *h, int row, int choice)
{
    size_t i;
    if (row_index(h, row, i))
        h->set_pickup(i, choice);
}

void nv_host_set_rotary(nv_host *h, int row, int mode, double spread_deg)
{
    size_t i;
    if (row_index(h, row, i))
        h->part_rotary(i, mode, spread_deg < 0.0 ? -1.0 : std::min(180.0, spread_deg) * M_PI / 180.0);
}

long nv_host_amp_seq(nv_host *h) { return nv_part_amp_seq(h->part); }
int nv_host_amp(nv_host *h, int row, double *out)
{
    size_t i;
    return row_index(h, row, i) ? h->amp_state(i, out) : 0;
}
int nv_host_drive(nv_host *h, int row, double *out)
{
    size_t i;
    return row_index(h, row, i) ? h->drive_state(i, out) : 0;
}
void nv_host_set_drive(nv_host *h, int row, double v)
{
    size_t i;
    if (row_index(h, row, i)) h->part_drive(i, v);
}

void nv_host_set_couplers(nv_host *h, int row, int v)
{
    size_t i;
    if (row_index(h, row, i)) h->part_couplers(i, v & 15);
}

void nv_host_set_rotor(nv_host *h, int row, int v)
{
    size_t i;
    if (row_index(h, row, i)) h->part_rotor(i, std::max(0, std::min(127, v)));
}

int nv_host_cmx_state(nv_host *h, int channel, nv_host_cmx *out)
{
    nv::Cmx m;
    if (!h->cmx_read(channel < 0 ? 0 : channel, m))
        return -1;
    memset(out, 0, sizeof *out);
    out->cc1 = m.cc1;
    out->cc2 = m.cc2;
    for (int r = 0; r < 6; r++)
        for (int c = 0; c < 11; c++) {
            const double *d = nv::cmx_find(m, r, c);
            out->depth[r][c] = d ? *d : nv::cmx_default(r, c);
        }
    for (const auto &e : nv::cmx_gm2_cells(m))
        if (e.second != 0.0 && out->ngm2 < 32) {
            out->gm2[out->ngm2].cc = e.first.first - 100;
            out->gm2[out->ngm2].dest = e.first.second;
            out->gm2[out->ngm2].depth = e.second;
            out->ngm2++;
        }
    return 0;
}

static void cmx_post(nv_host *h, int channel, const std::function<std::vector<uint8_t>(int)> &msg)
{
    for (int c = channel < 0 ? 0 : channel; c < (channel < 0 ? 16 : channel + 1); c++)
        h->enqueue(Midi{6, 0, 0, 0, msg(c)});
}
void nv_host_cmx_cell(nv_host *h, int channel, int src, int dest, int raw)
{
    if (src < 0 || src > 5 || dest < 0 || dest > 10) return;
    cmx_post(h, channel, [&](int c) { return nv::cmx_cell_message(c, src, dest, raw); });
}
void nv_host_cmx_assign(nv_host *h, int channel, int which, int cc)
{
    if (which != 4 && which != 5) return;
    cmx_post(h, channel, [&](int c) { return nv::cmx_assign_message(c, which, cc); });
}
void nv_host_cmx_range(int dest, int *lo, int *hi)
{
    *lo = dest == 0 ? 0x28 : 0;
    *hi = dest == 0 ? 0x58 : 127;
}
double nv_host_cmx_depth(int dest, int raw) { return nv::cmx_gs_depth(dest, raw); }
int nv_host_cmx_raw(int dest, double depth) { return nv::cmx_gs_raw(dest, depth); }
int nv_host_cmx_printed(int dest, double depth, char *out, int cap) { return copy_out(nv::cmx_printed(dest, depth), out, cap); }
int nv_host_last_ctl(nv_host *h, long long *when_ns)
{
    if (when_ns) *when_ns = h->last_ctl_ns.load();
    return h->last_ctl_code.load();
}
long long nv_host_now_ns(void)
{
    return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

int nv_host_udrum_tables(nv_host *h, char *out, int cap) { return copy_out(h->E.dkey, out, cap); }
int nv_host_udrum_state(nv_host *h, int set, int *out)
{
    panel::Host::USets u;
    if (!h->udrum_read(u))
        return -1;
    for (int i = 0; i < 128 * 16; i++)
        out[i] = -1;
    for (const auto &kv : u)
        if (kv.first.first == set && kv.first.second >= 0 && kv.first.second < 128)
            for (const auto &cv : kv.second)
                if (cv.first >= 0 && cv.first < 16)
                    out[kv.first.second * 16 + cv.first] = cv.second;
    return 0;
}
void nv_host_udrum_send(nv_host *h, int set, int key, int code, int v) { h->udrum_queue(set, key, code, v); }

int nv_host_chan_cc(nv_host *h, int channel, int cc)
{
    const int c = channel < 0 ? 0 : channel & 15;
    if (cc == 10) {                             // (as the part was sent it, before master pan)
        auto pr = h->gs_pan_raw.find(c);
        if (pr != h->gs_pan_raw.end())
            return pr->second;
    }
    return nv_part_chan_cc(h->part, c, cc);
}
void nv_host_chan_cc_send(nv_host *h, int channel, int cc, int v)
{
    v = std::max(0, std::min(127, v));
    for (int c = channel < 0 ? 0 : channel; c < (channel < 0 ? 16 : channel + 1); c++) {
        if (cc == NV_HOST_VSENSE) {             // (GS's 40 1x 1A, as a sequencer sends it)
            const int blk = c == 9 ? 0 : c < 9 ? c + 1 : c;
            std::vector<uint8_t> x{0x41, 0x10, 0x42, 0x12, 0x40, (uint8_t)(0x10 | blk), 0x1A, (uint8_t)v};
            x.push_back((uint8_t)((128 - (0x40 + x[5] + 0x1A + v) % 128) % 128));
            h->enqueue(Midi{6, 0, 0, 0, x});
        } else if (cc >= 0 && cc < 128)
            h->enqueue(Midi{2, c, cc, v, {}});
    }
}

int nv_host_control_kinds(char *out, int cap)
{
    std::string all;
    for (const auto &c : panel::CONTROLS)
        all += std::to_string(c.first) + "\t" + c.second + "\t" + panel::control_kind(c.first) + "\t"
               + std::to_string(panel::control_default(c.first)) + "\n";
    return copy_out(all, out, cap);
}
int nv_host_controls(nv_host *h, nv_host_control *out, int cap)
{
    const auto &cs = h->screen_controls;
    for (int i = 0; out && i < cap && i < (int)cs.size(); i++) {
        const auto &c = cs[(size_t)i];
        int sw[5] = {0, 0, 0, 0, 0};
        if (panel::control_switch(c.key))
            nv_part_switches(h->part, c.channel < 0 ? 0 : c.channel, sw);
        out[i].key = c.key;
        out[i].channel = c.channel;
        out[i].value = c.value;
        out[i].hotkey = c.hotkey;
        out[i].on = c.key == 64 ? sw[0] != 0 : c.key == 66 ? sw[1] != 0 : c.key == 67 ? sw[2] != 0
                  : c.key == 65 ? sw[3] != 0 : c.key == -3 ? sw[4] != 0 : 0;
    }
    return (int)cs.size();
}
int nv_host_control_add(nv_host *h, int key, int channel)
{
    if (!panel::control_label(key))
        return -1;
    h->screen_controls.push_back(panel::ScreenControl{key, channel < 0 ? -1 : channel & 15, panel::control_default(key), 0});
    return (int)h->screen_controls.size() - 1;
}
void nv_host_control_remove(nv_host *h, int index)
{
    if (index >= 0 && index < (int)h->screen_controls.size())
        h->screen_controls.erase(h->screen_controls.begin() + index);
}
void nv_host_control_set(nv_host *h, int index, int v)
{
    if (index < 0 || index >= (int)h->screen_controls.size())
        return;
    panel::ScreenControl &c = h->screen_controls[(size_t)index];
    c.value = panel::control_kind(c.key) == "bend" ? std::max(-8192, std::min(8191, v)) : std::max(0, std::min(127, v));
    h->control_send(c.key, c.value, c.channel);
}
void nv_host_control_hotkey(nv_host *h, int index, int key)
{
    if (index < 0 || index >= (int)h->screen_controls.size())
        return;
    for (auto &o : h->screen_controls)          // (a key is one control's)
        if (key && o.hotkey == key)
            o.hotkey = 0;
    h->screen_controls[(size_t)index].hotkey = key;
}

// THE ROUTES: the library's list (the session's or a preset's), the router
// built again from it -- as a preset's routes replace them (apply_setup)
static void set_routes(nv_host *h, const std::vector<std::array<int, 7>> &rs)
{
    const size_t had = h->E.routes.size() + (h->pks.empty() ? 0 : 1);
    std::vector<std::array<int, 7>> all = rs;
    if (!h->pks.empty())
        all.push_back(h->pedal_route);
    h->post([h, had, all](long long) {
        for (size_t q = had; q-- > 0;)
            nv_rt_del(h->router, (int)q);
        for (const auto &a : all)
            nv_rt_add(h->router, a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
    });
    h->E.routes = rs;
    h->routes_replaced = all;
    h->session_routes = rs;
    h->session_routes_set = true;
}
int nv_host_routes(nv_host *h, int *out7, int cap)
{
    const auto &rs = h->E.routes;
    for (int i = 0; out7 && i < cap && i < (int)rs.size(); i++)
        for (int k = 0; k < 7; k++)
            out7[i * 7 + k] = rs[(size_t)i][(size_t)k];
    return (int)rs.size();
}
int nv_host_route_text(const int *r7, char *out, int cap)
{
    std::array<int, 7> a;
    for (int k = 0; k < 7; k++)
        a[(size_t)k] = r7[k];
    return copy_out(panel::describe(a), out, cap);
}
void nv_host_route_add(nv_host *h, const int *r7)
{
    std::vector<std::array<int, 7>> rs = h->E.routes;
    std::array<int, 7> a;
    for (int k = 0; k < 7; k++)
        a[(size_t)k] = r7[k];
    rs.push_back(a);
    set_routes(h, rs);
}
void nv_host_route_remove(nv_host *h, int index)
{
    std::vector<std::array<int, 7>> rs = h->E.routes;
    if (index < 0 || index >= (int)rs.size())
        return;
    rs.erase(rs.begin() + index);
    set_routes(h, rs);
}
void nv_host_learn_key(nv_host *h, int on)
{
    h->learnt_ch = -1;
    h->learnt_note = -1;
    h->learning = on ? 1 : 0;
}
int nv_host_learnt_key(nv_host *h, int *channel, int *note)
{
    if (h->learning != 2)
        return 0;
    if (channel) *channel = h->learnt_ch;
    if (note) *note = h->learnt_note;
    h->learning = 0;
    return 1;
}

int nv_host_scenes(nv_host *h, char *names, int cap)
{
    std::string all;
    sess::J d;
    if (!h->session_path.empty() && sess::load(h->scenes_path(), d))
        for (const auto &kv : d.o)
            all += (all.empty() ? "" : "\n") + kv.first;
    return copy_out(all, names, cap);
}
int nv_host_scene_save(nv_host *h, const char *name, char *msg, int cap)
{
    if (!name || !*name || h->session_path.empty())
        return copy_out("no name, or no session path (nv_host_set_session_path)", msg, cap), -1;
    const std::vector<std::string> ev = h->scene_now();
    sess::J d;
    if (!sess::load(h->scenes_path(), d))
        d = sess::obj();
    sess::J a = sess::arr();
    for (const auto &e : ev)
        a.a.push_back(sess::str(e));
    d.o[name] = a;
    if (!sess::save(h->scenes_path(), d))
        return copy_out("could not write " + h->scenes_path(), msg, cap), -1;
    copy_out("scene '" + std::string(name) + "': " + std::to_string(ev.size()) + " events", msg, cap);
    return 0;
}
int nv_host_scene_recall(nv_host *h, const char *name, char *msg, int cap)
{
    sess::J d;
    const sess::J *p = name && !h->session_path.empty() && sess::load(h->scenes_path(), d) ? d.get(name) : nullptr;
    if (!p || !p->is(sess::J::ARR))
        return copy_out(std::string("no scene '") + (name ? name : "") + "'", msg, cap), -1;
    std::vector<std::string> ev;
    for (const auto &e : p->a)
        if (e.is(sess::J::STR))
            ev.push_back(e.s);
    copy_out("scene '" + std::string(name) + "': " + std::to_string(h->scene_recall(ev)) + " events", msg, cap);
    return 0;
}

void nv_host_gs_reset(nv_host *h)
{
    std::vector<uint8_t> x{0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41};
    h->enqueue(Midi{6, 0, 0, 0, x});
}

// libnative's own directory (relocate.h): where the library holding this is
const char *nv_native_dir(void)
{
    static std::string dir;
    static bool done = false;
    if (!done) {
        Dl_info di;
        if (dladdr((const void *)&nv_native_dir, &di) && di.dli_fname) {
            char real[4096];
            std::string p = realpath(di.dli_fname, real) ? std::string(real) : std::string(di.dli_fname);
            dir = p.substr(0, p.rfind('/') == std::string::npos ? 0 : p.rfind('/'));
        }
        done = true;
    }
    return dir.c_str();
}

}  // extern "C"
