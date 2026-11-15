// hostsession.cpp -- the host's SESSION, SCENES AND PRESETS (live's
// session.json, scenes.json, presets.json): moved here from nvlive.cpp so
// the library has them -- an app (app/, host.h's nv_host_* calls) saves and
// loads the presets nvlive and live.py do, the same files, the same keys.
// nvlive, the terminal client, links them from the library as before.
#include <algorithm>
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

static std::string beside(const std::string &path, const char *name)
{
    size_t k = path.rfind('/');
    return (k == std::string::npos ? std::string(".") : path.substr(0, k)) + "/" + name;
}
std::string nv_host::presets_path() const { return beside(session_path, "presets.json"); }
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
    std::lock_guard<std::mutex> lk(mu);
    q.push_back(Midi{6, 0, 0, 0, x});
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
                if (at_start)                   // (else after the pick's swap, below: a new program clears it)
                    part_drive(0, sp.drive);
                if (!at_start) {
                    int code = (sp.drums ? 128 : 0) + sp.program;
                    for (size_t j = 0; j < E.vpv.size() && sp.var && !sp.drums; j++)
                        if (E.vpv[j][0] == sp.program && E.vpv[j][1] == sp.var)
                            code = 256 + (int)j;
                    pick_row(0, code);
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
            part_add(sp);
        }
    // THE ORGAN's STOPS: drawn as the part's were (parts[0].drawn, by name) --
    // now if the organ is in, else once it is swapped in (pending_drawn)
    if (parts && parts->is(sess::J::ARR) && !parts->a.empty()) {
        const sess::J *dn = parts->a[0].get("drawn"), *pg = parts->a[0].get("program"), *dv = parts->a[0].get("drums");
        const int want_p = pg && pg->is(sess::J::NUM) ? (int)pg->i() & 127 : -1;
        if (dn && dn->is(sess::J::ARR) && want_p >= 0 && !(dv && dv->d() != 0.0) && !E.stops[want_p].names.empty()) {
            const auto &names = E.stops[want_p].names;
            std::vector<char> want(names.size(), 0);
            for (size_t ri = 0; ri < names.size(); ri++)
                for (const sess::J &n : dn->a)
                    want[ri] = want[ri] || (n.is(sess::J::STR) && n.s == names[ri]);
            if (want_p == shown_program)
                post([this, want](long long) { nv_part_set_drawn(part, want.data(), (int)want.size()); });
            if (!at_start || want_p != shown_program) {
                std::vector<std::string> w;
                for (size_t ri = 0; ri < names.size(); ri++)
                    if (want[ri])
                        w.push_back(names[ri]);
                post([this, w, want_p](long long) {     // (the swap reads it, on this thread)
                    pending_drawn = w;
                    pending_drawn_prog = want_p;
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
            pd.o["tuner"] = sess::str("hybrid");
            pd.o["drawn"] = sess::arr();
        }
        const PartAt &pa = rows[k];
        const int vk = pa.drums ? 0 : (k == 0 ? (shown_program >= 128 ? 0 : shown_var.load()) : pa.var);
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
        if (anyk)
            pd.o["synth_units"] = sess::integer(6);
        else if (!pd.get("synth") && !pd.get("synth_b"))
            pd.o.erase("synth_units");
    }
    if (parts.a.empty())
        return j;
    sess::J &p0 = parts.a[0];
    const int sp = shown_program, sv = sp >= 128 ? 0 : shown_var.load();
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
    sess::J dn = sess::arr();
    if (sp < 128 && !E.stops[sp].names.empty()) {
        const auto &names = E.stops[sp].names;
        std::vector<char> d(names.size(), 0);
        nv_part_drawn(part, d.data(), (int)names.size());
        std::vector<std::string> on;
        for (size_t ri = 0; ri < names.size(); ri++)
            if (d[ri])
                on.push_back(names[ri]);
        std::sort(on.begin(), on.end());
        for (auto &n : on)
            dn.a.push_back(sess::str(n));
    }
    p0.o["drawn"] = dn;
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
        o.variation = r.var;
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
    if (sess::load(h->presets_path(), d))
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
    const sess::J *p = name && sess::load(h->presets_path(), d) ? d.get(name) : nullptr;
    if (!p || !p->is(sess::J::OBJ))
        return copy_out(std::string("no preset '") + (name ? name : "") + "'", msg, cap), -1;
    h->apply_setup(*p, false);
    copy_out(std::string("loading '") + name + "'", msg, cap);
    return 0;
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
int nv_host_stop_names(nv_host *h, int program, char *names, int cap)
{
    if (program < 0 || program > 127)
        return 0;
    const auto &st = h->E.stops[program];
    std::string all;
    for (size_t i = 0; i < st.names.size(); i++)
        all += (i ? "\n" : "") + st.names[i];
    copy_out(all, names, cap);
    return (int)st.names.size();
}

int nv_host_stop_rows(nv_host *h, int program, int *out, int cap)
{
    if (program < 0 || program > 127)
        return 0;
    const auto &st = h->E.stops[program];
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

int nv_host_drawn(nv_host *h, char *out, int cap) { return nv_part_drawn(h->part, out, cap); }

void nv_host_toggle_stop(nv_host *h, int rank)
{
    h->post([h, rank](long long n) {
        h->pending_drawn_prog = -1;             // (a stop drawn by hand: a preset's no longer)
        nv_part_toggle_stop(h->part, rank, n);
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
