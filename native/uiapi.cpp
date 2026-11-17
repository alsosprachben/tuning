// uiapi.cpp -- THE TOUCH INTERFACE's CALLS (ui/): one JSON request in, one
// JSON answer out, over the host's own calls (host.h) -- the same ones the
// Mac app makes. Every transport uses it: nvlive --ui's WebSocket server
// (uiserve.h) now; a web view's message handler in the app later.
//
// A request: {"call": "synth_set", "row": 0, "knob": 15, "v": 0.42, "id": 7}
// An answer:  {"id": 7, "ok": true, ...}  (or "ok": false and "error")
//
// A WATCH is one viewer's: the part it has selected, and what it was last
// sent, so nv_ui_poll sends only what changed -- the meters while anything
// sounds, the parts and the selected part's knobs when they move (a
// Messenger's knob turned, a program change from a file).
//
// Never on the audio thread: the host's calls post their work to it.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <map>
#include <memory>
#include <string>
#include <thread>
#include <atomic>
#include <vector>
#include "hostlive.h"
#include "host.h"
#include "nv.h"
#include "session.h"

namespace {

using sess::J;

// compact JSON (session.h's dump is for files: indented)
void put(std::string &o, const J &j)
{
    switch (j.t) {
    case J::NUL: o += "null"; break;
    case J::BOOL: o += j.b ? "true" : "false"; break;
    case J::NUM: o += j.num; break;
    case J::STR: sess::quote(o, j.s); break;
    case J::ARR:
        o += '[';
        for (size_t k = 0; k < j.a.size(); k++) {
            if (k)
                o += ',';
            put(o, j.a[k]);
        }
        o += ']';
        break;
    case J::OBJ: {
        o += '{';
        bool first = true;
        for (const auto &kv : j.o) {
            if (!first)
                o += ',';
            first = false;
            sess::quote(o, kv.first);
            o += ':';
            put(o, kv.second);
        }
        o += '}';
        break;
    }
    }
}

J num(double v)
{
    if (!std::isfinite(v))
        return J();
    // (enough digits for a knob or a level; not a file's exactness)
    char b[32];
    snprintf(b, sizeof b, "%.6g", v);
    J j;
    j.t = J::NUM;
    j.num = b;
    return j;
}

long arg_i(const J &q, const char *k, long d)
{
    const J *v = q.get(k);
    return v ? v->i(d) : d;
}
double arg_d(const J &q, const char *k, double d)
{
    const J *v = q.get(k);
    return v ? v->d(d) : d;
}

// THE KNOB TABLE (nv_host_synth_knobs), parsed once
struct Knob {
    std::string section, label, kind;
    int knob;
    std::vector<double> steps;
    bool centred;
    std::string column, group, generic;     // (the touch card's: panel.h SYNTH_CARD)
    std::vector<std::string> words;         // (a switch's, a step each)
    int at = -1;                            // (its place on the card)
};
const std::vector<Knob> &knobs()
{
    static std::vector<Knob> ks = [] {
        std::vector<Knob> out;
        std::vector<char> buf(32768);
        nv_host_synth_knobs(buf.data(), (int)buf.size());
        const char *p = buf.data();
        while (*p) {
            const char *e = strchr(p, '\n');
            std::string line(p, e ? (size_t)(e - p) : strlen(p));
            std::vector<std::string> f;
            size_t a = 0;
            for (size_t b; (b = line.find('\t', a)) != std::string::npos; a = b + 1)
                f.push_back(line.substr(a, b - a));
            f.push_back(line.substr(a));
            if (f.size() >= 6) {
                Knob k;
                k.section = f[0];
                k.knob = atoi(f[1].c_str());
                k.label = f[2];
                k.kind = f[3];
                for (size_t s = 0, t; s < f[4].size(); s = t + 1) {
                    t = f[4].find(',', s);
                    if (t == std::string::npos)
                        t = f[4].size();
                    k.steps.push_back(atof(f[4].substr(s, t - s).c_str()));
                }
                k.centred = f[5] == "1";
                if (f.size() >= 10) {
                    k.column = f[6];
                    k.group = f[7];
                    k.generic = f[8];
                    for (size_t s = 0, t; !f[9].empty() && s <= f[9].size(); s = t + 1) {
                        t = f[9].find(',', s);
                        if (t == std::string::npos)
                            t = f[9].size();
                        k.words.push_back(f[9].substr(s, t - s));
                    }
                    if (f.size() >= 11)
                        k.at = atoi(f[10].c_str());
                }
                // a switch without its own words: each step in the knob's
                double pn[NV_MK_N] = {};
                for (size_t i = k.words.size(); i < k.steps.size(); i++) {
                    char b[64] = {};
                    nv_host_synth_fmt(k.kind.c_str(), k.steps[i], pn, b, sizeof b);
                    k.words.push_back(b);
                }
                out.push_back(k);
            }
            if (!e)
                break;
            p = e + 1;
        }
        return out;
    }();
    return ks;
}

J knob_table()
{
    J a = sess::arr();
    for (const Knob &k : knobs()) {
        J o = sess::obj();
        o.o["section"] = sess::str(k.section);
        o.o["knob"] = sess::integer(k.knob);
        o.o["label"] = sess::str(k.label);
        o.o["kind"] = sess::str(k.kind);
        J st = sess::arr();
        for (double v : k.steps)
            st.a.push_back(num(v));
        o.o["steps"] = st;
        o.o["centred"] = sess::boolean(k.centred);
        o.o["column"] = sess::str(k.column);
        o.o["group"] = sess::str(k.group);
        o.o["generic"] = sess::str(k.generic.empty() ? k.label : k.generic);
        J wd = sess::arr();
        for (const auto &x : k.words)
            wd.a.push_back(sess::str(x));
        o.o["words"] = wd;
        o.o["at"] = sess::integer(k.at);
        a.a.push_back(o);
    }
    return a;
}

J parts_of(nv_host *h)
{
    int n = nv_host_parts(h, nullptr, 0);
    std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
    n = nv_host_parts(h, ps.data(), n);
    J a = sess::arr();
    for (int i = 0; i < n && i < (int)ps.size(); i++) {
        const nv_host_partinfo &p = ps[(size_t)i];
        J o = sess::obj();
        o.o["row"] = sess::integer(p.row);
        o.o["program"] = sess::integer(p.program);
        o.o["variation"] = sess::integer(p.variation);
        o.o["drums"] = sess::boolean(p.drums != 0);
        o.o["channel"] = sess::integer(p.channel);
        o.o["lo"] = sess::integer(p.lo);
        o.o["hi"] = sess::integer(p.hi);
        o.o["transpose"] = sess::integer(p.transpose);
        o.o["level_db"] = num(p.level_db);
        o.o["muted"] = sess::boolean(p.muted != 0);
        o.o["solo"] = sess::integer(p.solo);
        o.o["touch_fixed"] = sess::boolean(p.touch_fixed != 0);
        o.o["name"] = sess::str(p.name);
        // its channel's pan and sends, as a sequencer set them (an every-channel
        // part reads the first channel's: a change goes to all of them)
        o.o["pan"] = sess::integer(nv_host_chan_cc(h, p.channel, 10));
        o.o["reverb"] = sess::integer(nv_host_chan_cc(h, p.channel, 91));
        o.o["chorus"] = sess::integer(nv_host_chan_cc(h, p.channel, 93));
        o.o["delay"] = sess::integer(nv_host_chan_cc(h, p.channel, 94));
        a.a.push_back(o);
    }
    return a;
}

J patches_of(nv_host *h)
{
    int n = nv_host_patches(h, nullptr, 0);
    std::vector<nv_host_patch> ps((size_t)std::max(0, n));
    n = nv_host_patches(h, ps.data(), n);
    J a = sess::arr();
    for (int i = 0; i < n && i < (int)ps.size(); i++) {
        const nv_host_patch &p = ps[(size_t)i];
        if (!p.native)
            continue;
        J o = sess::obj();
        o.o["program"] = sess::integer(p.program);
        o.o["variation"] = sess::integer(p.variation);
        o.o["drums"] = sess::boolean(p.drums != 0);
        o.o["pick"] = sess::integer(p.pick);
        o.o["name"] = sess::str(p.name);
        a.a.push_back(o);
    }
    return a;
}

// A PART's PEDALS, read between two blocks (the sostenuto's keys are the
// audio thread's): {sustain 0-127, sostenuto, soft}; false when the audio
// did not answer
bool pedals_of(nv_host *h, int channel, int out[3])
{
    struct Got {
        int v[3] = {0, 0, 0};
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    void *part = h->part;
    const int ch = channel < 0 ? 0 : channel & 15;
    auto take = [got, part, ch](long long) {
        int sw[5] = {};
        nv_part_switches(part, ch, sw);
        got->v[0] = nv_part_pedal(part, ch);
        got->v[1] = sw[1];
        got->v[2] = sw[2];
        got->done = true;
    };
    if (h->scene_inline)
        take(0);
    else
        h->post(take);
    for (int i = 0; i < 100 && !got->done; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return false;
    for (int k = 0; k < 3; k++)
        out[k] = got->v[k];
    return true;
}

// THE PIANO CARD's: the part's pedals (its channel's; an every-channel part
// the first's), how far each key's damper rests at the sustain's value (A0
// to C8: 1 on the string, 0 lifted -- the bass's bite later), the keys held
// as the sustain pedal (routes from a key to CC64; pushed into, the dampers
// lowered), and whether the sympathetic strings ring (the first part's)
J piano_of(nv_host *h, int row, int learning)
{
    J o = sess::obj();
    int n = nv_host_parts(h, nullptr, 0);
    std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
    n = nv_host_parts(h, ps.data(), n);
    const bool has = row >= 0 && row < n;
    o.o["row"] = sess::integer(row);
    o.o["part"] = sess::str(has ? ps[(size_t)row].name : "");
    o.o["drums"] = sess::boolean(has && ps[(size_t)row].drums);
    o.o["program"] = sess::integer(has ? ps[(size_t)row].program : -1);
    o.o["variation"] = sess::integer(has ? ps[(size_t)row].variation : 0);
    const int ch = has ? ps[(size_t)row].channel : 0;
    o.o["channel"] = sess::integer(ch);
    int pv[3] = {0, 0, 0};
    o.o["read"] = sess::boolean(has && pedals_of(h, ch, pv));
    o.o["sustain"] = sess::integer(pv[0]);
    o.o["sostenuto"] = sess::boolean(pv[1] != 0);
    o.o["soft"] = sess::boolean(pv[2] != 0);
    J c = sess::arr();
    for (int key = 21; key <= 108; key++)
        c.a.push_back(num(std::round(nv_damper_contact(pv[0], key, 128) * 100.0) / 100.0));
    o.o["contact"] = c;
    J band = sess::arr();                       // (where the dampers leave the strings: A0's, C4's, C8's)
    for (int key : {21, 60, 108}) {
        int lo = 127, hi = 0;
        for (int v = 0; v < 128; v++) {
            const double x = nv_damper_contact(v, key, 128);
            if (x < 0.999 && v < lo) lo = v;
            if (x > 0.001) hi = v;
        }
        J b = sess::arr();
        b.a.push_back(sess::integer(key));
        b.a.push_back(sess::integer(lo));
        b.a.push_back(sess::integer(hi));
        band.a.push_back(b);
    }
    o.o["band"] = band;
    const int nr = nv_host_routes(h, nullptr, 0);
    std::vector<int> rs((size_t)std::max(0, nr) * 7);
    nv_host_routes(h, rs.data(), nr);
    J keys = sess::arr();
    for (int i = 0; i < nr; i++) {
        const int *r = &rs[(size_t)i * 7];
        if (r[0] != 3 || r[2] != 64)
            continue;
        J k = sess::obj();
        k.o["i"] = sess::integer(i);
        k.o["key"] = sess::integer(r[1]);
        k.o["channel"] = sess::integer(r[4]);
        k.o["latch"] = sess::boolean(r[5] != 0);
        k.o["press"] = sess::boolean(r[6] != 0);
        char t[160] = {};
        nv_host_route_text(r, t, sizeof t);
        k.o["text"] = sess::str(t);
        keys.a.push_back(k);
    }
    o.o["keys"] = keys;
    o.o["fixed_key"] = sess::integer(h->pks.empty() ? -1 : atoi(h->pks.c_str()));   // (--pedal-key's: not the session's)
    o.o["learning"] = sess::boolean(learning != 0);
    o.o["strings"] = sess::boolean(h->reg_on);
    return o;
}

// THE DRUM SETS' KEYS (the export's DKEY: "S\tset\tname", "K\tset\tkey\tname"),
// read once: each set's name, and each key's name in it
struct DKeys {
    std::vector<std::pair<int, std::string>> sets;
    std::map<std::pair<int, int>, std::string> keys;
};
const DKeys &dkeys(nv_host *h)
{
    static DKeys d;
    static bool read = false;
    if (read)
        return d;
    read = true;
    const int n = nv_host_udrum_tables(h, nullptr, 0);
    std::vector<char> b((size_t)std::max(0, n) + 1);
    nv_host_udrum_tables(h, b.data(), (int)b.size());
    for (const char *p = b.data(); *p;) {
        const char *e = strchr(p, '\n');
        const std::string line(p, e ? (size_t)(e - p) : strlen(p));
        std::vector<std::string> f;
        for (size_t a = 0;;) {
            const size_t t = line.find('\t', a);
            f.push_back(line.substr(a, t == std::string::npos ? std::string::npos : t - a));
            if (t == std::string::npos)
                break;
            a = t + 1;
        }
        if (f.size() >= 3 && f[0] == "S")
            d.sets.emplace_back(atoi(f[1].c_str()), f[2]);
        else if (f.size() >= 4 && f[0] == "K")
            d.keys[std::make_pair(atoi(f[1].c_str()), atoi(f[2].c_str()))] = f[3];
        if (!e)
            break;
        p = e + 1;
    }
    return d;
}

// THE DRUMS CARD's: the part's kit and its keys by name (a user set's, 64 and
// 65: each key's source set and key, level, pan, received -- -1 not set); the
// sets a user key may take its sound from, once (sets: the first answer's)
J drums_of(nv_host *h, int row, bool with_sets)
{
    J o = sess::obj();
    int n = nv_host_parts(h, nullptr, 0);
    std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
    n = nv_host_parts(h, ps.data(), n);
    const bool has = row >= 0 && row < n;
    const DKeys &dk = dkeys(h);
    o.o["row"] = sess::integer(row);
    o.o["part"] = sess::str(has ? ps[(size_t)row].name : "");
    const bool drums = has && ps[(size_t)row].drums;
    o.o["drums"] = sess::boolean(drums);
    const int kit = drums ? ps[(size_t)row].program : -1;
    o.o["kit"] = sess::integer(kit);
    o.o["channel"] = sess::integer(has ? ps[(size_t)row].channel : 9);
    J keys = sess::arr();
    if (kit == 64 || kit == 65) {               // (a user set: GS 21's settings)
        std::vector<int> st(128 * 16, -1);
        const bool got = nv_host_udrum_state(h, kit - 64, st.data()) == 0;
        o.o["user"] = sess::integer(kit - 64);
        o.o["read"] = sess::boolean(got);
        for (int k = 0; k < 128; k++) {
            const int *u = &st[(size_t)k * 16];
            J e = sess::arr();
            e.a.push_back(sess::integer(k));
            const int ss = u[0x0B] >= 0 ? u[0x0B] : 0, sk = u[0x0C];
            auto it = sk >= 0 ? dk.keys.find(std::make_pair(ss, sk)) : dk.keys.end();
            e.a.push_back(sess::str(it != dk.keys.end() ? it->second : ""));
            for (int c : {0x0B, 0x0C, 0x02, 0x04, 0x08, 0x01})
                e.a.push_back(sess::integer(c == 0x0B && sk >= 0 ? ss : u[c]));
            keys.a.push_back(e);
        }
    } else if (kit >= 0) {
        for (int k = 0; k < 128; k++) {
            auto it = dk.keys.find(std::make_pair(kit, k));
            if (it == dk.keys.end())
                it = dk.keys.find(std::make_pair(0, k));    // (a set the export has no keys for: Standard's)
            if (it == dk.keys.end())
                continue;
            J e = sess::arr();
            e.a.push_back(sess::integer(k));
            e.a.push_back(sess::str(it->second));
            keys.a.push_back(e);
        }
    }
    o.o["keys"] = keys;
    if (with_sets) {
        J sets = sess::arr();
        for (const auto &x : dk.sets) {
            J e = sess::arr();
            e.a.push_back(sess::integer(x.first));
            e.a.push_back(sess::str(x.second));
            J ks = sess::arr();
            for (int k = 0; k < 128; k++) {
                auto it = dk.keys.find(std::make_pair(x.first, k));
                if (it == dk.keys.end())
                    continue;
                J kk = sess::arr();
                kk.a.push_back(sess::integer(k));
                kk.a.push_back(sess::str(it->second));
                ks.a.push_back(kk);
            }
            e.a.push_back(ks);
            sets.a.push_back(e);
        }
        o.o["sets"] = sets;
    }
    return o;
}

// a part's knobs on a layer: positions, whose they are, and each in its own words
J synth_of(nv_host *h, int row, int layer)
{
    double pn[NV_MK_N] = {};
    char own[NV_MK_N] = {};
    J o = sess::obj();
    int layers = nv_host_synth_get(h, row, layer, pn, own);
    if (layers > 0 && layer >= layers)
        layer = 0;                  // (a one-layer patch picked while on B: what was read is A)
    o.o["row"] = sess::integer(row);
    o.o["layer"] = sess::integer(layer);
    o.o["layers"] = sess::integer(layers);
    if (layers > 0) {
        J v = sess::arr(), w = sess::arr(), t = sess::arr();
        for (int k = 0; k < NV_MK_N; k++) {
            v.a.push_back(num(pn[k]));
            w.a.push_back(sess::integer(own[k]));
        }
        for (const Knob &k : knobs()) {
            char b[64] = {};
            if (k.knob >= 0 && k.knob < NV_MK_N)
                nv_host_synth_fmt(k.kind.c_str(), pn[k.knob], pn, b, sizeof b);
            t.a.push_back(sess::str(b));
        }
        o.o["pn"] = v;
        o.o["own"] = w;
        o.o["text"] = t;            // (in the knob table's order)
    }
    return o;
}

J globals_of(nv_host *h)
{
    J g = sess::arr();
    for (int i = 0; i < nv_host_global_count(); i++)
        g.a.push_back(num(nv_host_global(h, i)));
    return g;
}

// THE FAVOURITES (the library's stars): favourites.json beside the session,
// {"favourites": ["d:program.variation", ...]} -- shared by every viewer and the apps
std::string favourites_path(nv_host *h)
{
    const std::string &sp = h->session_path;
    if (sp.empty())
        return "";
    const size_t k = sp.rfind('/');
    return (k == std::string::npos ? std::string() : sp.substr(0, k + 1)) + "favourites.json";
}

// what the builder is doing: the display's line while a patch builds
J build_of(nv_host *h)
{
    J b = sess::obj();
    long done = 0, total = 0;
    char name[96] = {};
    const int n = nv_host_building(h);
    b.o["n"] = sess::integer(n);
    if (n > 0 && nv_host_progress(h, &done, &total, name, sizeof name)) {
        b.o["name"] = sess::str(name);
        b.o["done"] = sess::integer(done);
        b.o["total"] = sess::integer(total);
    }
    return b;
}

// A PART's ORGAN (livetui's stop rows): its program, its ranks' names, the
// panel's rows (each a list of groups, each group's ranks) and what is
// drawn; program -1 when it is not an organ
J stops_of(nv_host *h, int row)
{
    J o = sess::obj();
    int n = nv_host_parts(h, nullptr, 0);
    std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
    n = nv_host_parts(h, ps.data(), n);
    const bool has = row >= 0 && row < n;
    int prog = has && !ps[(size_t)row].drums ? ps[(size_t)row].program : -1;
    std::vector<char> nb(16384);
    const int nr = prog >= 0 ? nv_host_stop_names(h, prog, nb.data(), (int)nb.size()) : 0;
    if (nr <= 0)
        prog = -1;
    o.o["program"] = sess::integer(prog);
    o.o["row"] = sess::integer(row);
    o.o["part"] = sess::str(has ? ps[(size_t)row].name : "");
    J names = sess::arr(), rows = sess::arr(), drawn = sess::arr();
    if (prog >= 0) {
        for (const char *p = nb.data();;) {
            const char *e = strchr(p, '\n');
            names.a.push_back(sess::str(std::string(p, e ? (size_t)(e - p) : strlen(p))));
            if (!e)
                break;
            p = e + 1;
        }
        const int k = nv_host_stop_rows(h, prog, nullptr, 0);
        std::vector<int> v((size_t)std::max(0, k));
        if (k > 0)
            nv_host_stop_rows(h, prog, v.data(), k);
        J line = sess::arr(), grp = sess::arr();
        for (int x : v) {
            if (x >= 0) {
                grp.a.push_back(sess::integer(x));
                continue;
            }
            if (!grp.a.empty())
                line.a.push_back(grp);
            grp = sess::arr();
            if (x == -1) {
                if (!line.a.empty())
                    rows.a.push_back(line);
                line = sess::arr();
            }
        }
        std::vector<char> d((size_t)nr, 0);
        const int got = nv_host_part_drawn(h, row, d.data(), nr);
        for (int i = 0; i < nr; i++)
            drawn.a.push_back(sess::integer(i < got ? d[(size_t)i] : 0));
    }
    o.o["names"] = names;
    o.o["rows"] = rows;
    o.o["drawn"] = drawn;
    return o;
}

// the programs with stops (to put one on a part)
J organs_of(nv_host *h)
{
    J a = sess::arr();
    for (int pg = 0; pg < 128; pg++)
        if (nv_host_stop_names(h, pg, nullptr, 0) > 0)
            a.a.push_back(sess::integer(pg));
    return a;
}

double now_s()
{
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

}  // namespace

struct nv_ui_watch {
    int row = 0, layer = 0;
    std::string parts_sent, synth_sent, build_sent, stops_sent, piano_sent;
    bool piano = false;                 // (its piano card is open: its pedals read each poll)
    bool drums = false;                 // (its drums card is open: the kit, and the keys struck)
    std::string drums_sent;
    int hit_ch = -1;                    // (the channel whose keys it watches, and their counts as last sent)
    unsigned hit_n[128] = {};
    int learning = 0;                   // (a key being learnt as the sustain pedal)
    bool quiet = false;                 // (the last meters sent were silence: none until something sounds)
    long tick = 0;
};

extern "C" nv_ui_watch *nv_ui_watch_new(void) { return new nv_ui_watch(); }
extern "C" void nv_ui_watch_free(nv_ui_watch *w) { delete w; }
extern "C" void nv_ui_free(char *s) { free(s); }

static char *out_of(const J &j)
{
    std::string s;
    put(s, j);
    char *c = (char *)malloc(s.size() + 1);
    memcpy(c, s.c_str(), s.size() + 1);
    return c;
}

extern "C" char *nv_ui_call(nv_host *h, nv_ui_watch *w, const char *req)
{
    J q, r = sess::obj();
    if (!sess::parse(req ? req : "", q) || !q.is(J::OBJ)) {
        r.o["ok"] = sess::boolean(false);
        r.o["error"] = sess::str("not a JSON object");
        return out_of(r);
    }
    if (const J *id = q.get("id"))
        r.o["id"] = *id;
    const J *c = q.get("call");
    const std::string call = c && c->is(J::STR) ? c->s : "";
    const int row = (int)arg_i(q, "row", w ? w->row : 0);
    bool ok = true;
    if (call == "hello") {
        r.o["rate"] = sess::integer(nv_host_rate(h));
        r.o["block"] = sess::integer(nv_host_block(h));
        r.o["globals"] = globals_of(h);
        r.o["knobs"] = knob_table();
        std::vector<char> rb(8192);
        nv_host_rooms(h, rb.data(), (int)rb.size());
        J rooms = sess::arr();
        for (const char *p = rb.data(); *p;) {
            const char *e = strchr(p, '\n');
            rooms.a.push_back(sess::str(std::string(p, e ? (size_t)(e - p) : strlen(p))));
            if (!e)
                break;
            p = e + 1;
        }
        r.o["rooms"] = rooms;
        r.o["room"] = sess::str(nv_host_room(h));
    } else if (call == "parts") {
        r.o["parts"] = parts_of(h);
    } else if (call == "patches") {
        r.o["patches"] = patches_of(h);
    } else if (call == "select") {             // the viewer's part (and layer): the one its knobs follow
        if (w) {
            w->row = row;
            w->layer = (int)arg_i(q, "layer", 0);
            w->synth_sent.clear();
        }
        r.o["synth"] = synth_of(h, row, w ? w->layer : 0);
        r.o["stops"] = stops_of(h, row);
        if (w)
            w->stops_sent.clear();
    } else if (call == "part_pick") {
        nv_host_part_pick(h, row, (int)arg_i(q, "pick", 0));
    } else if (call == "part_set") {
        int n = nv_host_parts(h, nullptr, 0);
        std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
        n = nv_host_parts(h, ps.data(), n);
        if (row < 0 || row >= n) {
            ok = false;
            r.o["error"] = sess::str("no part " + std::to_string(row));
        } else {
            const nv_host_partinfo &p = ps[(size_t)row];
            nv_host_part_set(h, row, (int)arg_i(q, "channel", p.channel), (int)arg_i(q, "lo", p.lo),
                             (int)arg_i(q, "hi", p.hi), (int)arg_i(q, "transpose", p.transpose),
                             arg_d(q, "level_db", p.level_db), (int)arg_i(q, "muted", p.muted));
        }
    } else if (call == "part_solo") {
        nv_host_part_solo(h, row);
    } else if (call == "part_touch") {
        nv_host_part_touch(h, row, (int)arg_i(q, "fixed", 0));
    } else if (call == "part_cc") {            // pan (10) and the sends (91 reverb, 93 chorus, 94 delay)
        const int cc = (int)arg_i(q, "cc", -1);
        int n = nv_host_parts(h, nullptr, 0);
        std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
        n = nv_host_parts(h, ps.data(), n);
        if (row < 0 || row >= n || (cc != 10 && cc != 91 && cc != 93 && cc != 94)) {
            ok = false;
            r.o["error"] = sess::str("no part " + std::to_string(row) + " or cc " + std::to_string(cc));
        } else {
            nv_host_chan_cc_send(h, ps[(size_t)row].channel, cc, (int)arg_i(q, "v", 64));
        }
    } else if (call == "part_layer" || call == "part_split" || call == "part_delete") {
        char why[256] = {};
        const int rc = call == "part_layer"   ? nv_host_part_layer(h, row)
                       : call == "part_split" ? nv_host_part_split(h, row, why, sizeof why)
                                              : nv_host_part_delete(h, row, why, sizeof why);
        if (rc != 0) {
            ok = false;
            r.o["error"] = sess::str(why[0] ? why : "not done");
        }
        r.o["parts"] = parts_of(h);
    } else if (call == "favourites") {
        J f;
        const std::string fp = favourites_path(h);
        const J *l = !fp.empty() && sess::load(fp, f) ? f.get("favourites") : nullptr;
        r.o["favourites"] = l && l->is(J::ARR) ? *l : sess::arr();
        r.o["kept"] = sess::boolean(!fp.empty());
    } else if (call == "favourites_set") {
        const std::string fp = favourites_path(h);
        const J *l = q.get("favourites");
        if (fp.empty() || !l || !l->is(J::ARR)) {
            ok = false;
            r.o["error"] = sess::str(fp.empty() ? "no session to keep them beside" : "no list");
        } else {
            J f = sess::obj();
            f.o["favourites"] = *l;
            if (!sess::save(fp, f)) {
                ok = false;
                r.o["error"] = sess::str("could not write " + fp);
            }
        }
    } else if (call == "synth") {
        r.o["synth"] = synth_of(h, row, (int)arg_i(q, "layer", w ? w->layer : 0));
    } else if (call == "synth_set" || call == "synth_forget") {
        const int layer = (int)arg_i(q, "layer", w ? w->layer : 0), knob = (int)arg_i(q, "knob", -1);
        if (knob < 0 || knob >= NV_MK_N) {
            ok = false;
            r.o["error"] = sess::str("no knob " + std::to_string(knob));
        } else if (call == "synth_set") {
            // (a knob 0..1 -- -1 kept for the amp velocity's "voice"; a switch
            // one of its steps: the octave's feet, a mode's index)
            double v = arg_d(q, "v", 0.0), lo = -1.0, hi = 1.0;
            for (const Knob &k : knobs())
                if (k.knob == knob && !k.steps.empty()) {
                    lo = *std::min_element(k.steps.begin(), k.steps.end());
                    hi = *std::max_element(k.steps.begin(), k.steps.end());
                }
            v = std::max(lo, std::min(hi, v));
            nv_host_synth_set(h, row, layer, knob, v);
            // ...and its new value in the panel's words (the set is posted:
            // the panel as it stood, this knob moved)
            double pn[NV_MK_N] = {};
            char own[NV_MK_N] = {};
            if (nv_host_synth_get(h, row, layer, pn, own) > 0) {
                pn[knob] = v;
                for (const Knob &k : knobs())
                    if (k.knob == knob) {
                        char b[64] = {};
                        nv_host_synth_fmt(k.kind.c_str(), v, pn, b, sizeof b);
                        r.o["text"] = sess::str(b);
                        break;
                    }
            }
        } else {
            nv_host_synth_forget(h, row, layer, knob);
        }
    } else if (call == "global_set") {
        const int i = (int)arg_i(q, "i", -1);
        if (i < 0 || i >= nv_host_global_count()) {
            ok = false;
            r.o["error"] = sess::str("no global " + std::to_string(i));
        } else {
            nv_host_set_global(h, i, arg_d(q, "v", 0.0));
        }
    } else if (call == "stops") {
        r.o["stops"] = stops_of(h, row);
        r.o["organs"] = organs_of(h);
    } else if (call == "stops_set") {          // the whole registration: drawn[rank] 1
        const J *d = q.get("drawn");
        if (!d || !d->is(J::ARR)) {
            ok = false;
            r.o["error"] = sess::str("no drawn list");
        } else {
            std::vector<char> want;
            for (const J &x : d->a)
                want.push_back(x.i(0) != 0);
            nv_host_part_set_drawn(h, row, want.data(), (int)want.size());
        }
    } else if (call == "piano") {              // the card opened (or shut: open false)
        if (w) {
            w->piano = arg_i(q, "open", 1) != 0;
            w->piano_sent.clear();
        }
        r.o["piano"] = piano_of(h, row, w ? w->learning : 0);
    } else if (call == "pedal_set") {          // the part's sustain (64), sostenuto (66), soft (67)
        const int cc = (int)arg_i(q, "cc", -1);
        int n = nv_host_parts(h, nullptr, 0);
        std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
        n = nv_host_parts(h, ps.data(), n);
        if (row < 0 || row >= n || (cc != 64 && cc != 66 && cc != 67)) {
            ok = false;
            r.o["error"] = sess::str("no part " + std::to_string(row) + " or cc " + std::to_string(cc));
        } else {
            nv_host_chan_cc_send(h, ps[(size_t)row].channel, cc, (int)arg_i(q, "v", 0));
        }
    } else if (call == "pedal_key_learn") {    // the next key pressed becomes the sustain pedal
        const int on = (int)arg_i(q, "on", 1);
        nv_host_learn_key(h, on);
        if (w)
            w->learning = on;
    } else if (call == "pedal_key_remove") {
        const int i = (int)arg_i(q, "i", -1);
        const int nr = nv_host_routes(h, nullptr, 0);
        std::vector<int> rs((size_t)std::max(0, nr) * 7);
        nv_host_routes(h, rs.data(), nr);
        if (i < 0 || i >= nr || rs[(size_t)i * 7] != 3 || rs[(size_t)i * 7 + 2] != 64) {
            ok = false;
            r.o["error"] = sess::str("no pedal key " + std::to_string(i));
        } else {
            nv_host_route_remove(h, i);
        }
        if (w)
            w->piano_sent.clear();
    } else if (call == "drums") {              // the card opened (or shut: open false); sets: 1 for the user sets' sources
        if (w) {
            w->drums = arg_i(q, "open", 1) != 0;
            w->drums_sent.clear();
        }
        r.o["drums"] = drums_of(h, row, arg_i(q, "sets", 0) != 0);
    } else if (call == "drum_hit") {           // a pad: key, v (0 its release) on the part's channel
        int n = nv_host_parts(h, nullptr, 0);
        std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
        n = nv_host_parts(h, ps.data(), n);
        const int key = (int)arg_i(q, "key", -1), v = std::max(0, std::min(127, (int)arg_i(q, "v", 0)));
        if (row < 0 || row >= n || key < 0 || key > 127) {
            ok = false;
            r.o["error"] = sess::str("no part " + std::to_string(row) + " or key " + std::to_string(key));
        } else {
            const int ch = ps[(size_t)row].channel < 0 ? 9 : ps[(size_t)row].channel;
            const uint8_t m[3] = {(uint8_t)((v ? 0x90 : 0x80) | ch), (uint8_t)key, (uint8_t)(v ? v : 64)};
            nv_host_midi(h, m, 3);
        }
    } else if (call == "udrum_set") {          // a user set's key: code (GS 21's: 0x0B its source set, 0x0C its key...), v
        const int set = (int)arg_i(q, "set", -1), key = (int)arg_i(q, "key", -1), code = (int)arg_i(q, "code", -1);
        if ((set != 0 && set != 1) || key < 0 || key > 127 || code < 0 || code > 15) {
            ok = false;
            r.o["error"] = sess::str("no user set key");
        } else {
            nv_host_udrum_send(h, set, key, code, (int)arg_i(q, "v", 0));
        }
        if (w)
            w->drums_sent.clear();
    } else if (call == "panic") {
        nv_host_panic(h);
    } else {
        ok = false;
        r.o["error"] = sess::str("no call '" + call + "'");
    }
    r.o["ok"] = sess::boolean(ok);
    return out_of(r);
}

// WHAT CHANGED for this viewer since its last poll (NULL: nothing): the
// meters while anything sounds (a viewer polls ~30 times a second), the
// parts and its part's knobs at a sixth of that
extern "C" char *nv_ui_poll(nv_host *h, nv_ui_watch *w)
{
    if (!w)
        return nullptr;
    J r = sess::obj();
    bool any = false;
    nv_host_snap s;
    nv_host_snapshot(h, &s);
    const double ts = now_s();
    J bars = sess::arr();
    bool loud = s.peak[0] > 1e-5f || s.peak[1] > 1e-5f;
    for (int ch = 0; ch < 16; ch++) {
        double db = -99.0;
        const auto mt = h->meter[(size_t)ch];       // (live.meter: a note's level, and when; the panel's read)
        if (mt.first > 1e-6)
            db = 20.0 * std::log10(mt.first) - 24.0 * (ts - mt.second);       // (falling 24 dB a second)
        db = std::max(-99.0, db);
        loud = loud || db > -60.0;
        bars.a.push_back(num(std::round(db * 10.0) / 10.0));
    }
    if (loud || !w->quiet) {
        J m = sess::obj();
        m.o["peak"] = sess::arr();
        for (int c = 0; c < 2; c++)
            m.o["peak"].a.push_back(num(s.peak[c] > 0.0f ? 20.0 * std::log10(s.peak[c]) : -99.0));
        m.o["bars"] = bars;
        m.o["ms_max"] = num(s.ms_max);
        m.o["ms_mean"] = num(s.ms_mean);
        m.o["budget_ms"] = num(s.budget_ms);
        m.o["voices"] = num(s.eng[0]);
        m.o["gpu"] = sess::boolean(s.eng[4] > 0.5);
        m.o["over"] = sess::integer((long)s.over);
        m.o["underruns"] = sess::integer((long)s.underruns);
        m.o["rt"] = sess::boolean(s.rt != 0);
        m.o["rt_dropped"] = sess::boolean(s.rt_dropped != 0);
        r.o["meters"] = m;
        any = true;
        w->quiet = !loud;
    }
    if (w->tick++ % 6 == 0) {
        std::string ps;
        put(ps, parts_of(h));
        if (ps != w->parts_sent) {
            w->parts_sent = ps;
            J pj;
            sess::parse(ps, pj);
            r.o["parts"] = pj;
            any = true;
        }
        std::string bs;
        put(bs, build_of(h));
        if (bs != w->build_sent) {
            w->build_sent = bs;
            J bj;
            sess::parse(bs, bj);
            r.o["build"] = bj;
            any = true;
        }
        J st = stops_of(h, w->row);
        std::string sts;
        put(sts, st);
        if (sts != w->stops_sent) {
            w->stops_sent = sts;
            r.o["stops"] = st;
            any = true;
        }
        if (w->learning) {                      // (a key learnt: the pedal, pushed into to damp -- --pedal-key's)
            int lch = -1, lnote = -1;
            if (nv_host_learnt_key(h, &lch, &lnote)) {
                const int r7[7] = {3, lnote, 64, 0, -1, 0, 1};
                nv_host_route_add(h, r7);
                w->learning = 0;
            }
        }
        J sy = synth_of(h, w->row, w->layer);
        w->layer = (int)sy.o["layer"].d();      // (back on A once the patch has no B)
        std::string ss;
        put(ss, sy);
        if (ss != w->synth_sent) {
            w->synth_sent = ss;
            r.o["synth"] = sy;
            any = true;
        }
    }
    if (w->drums) {                             // (the keys struck on the part's channel since the last poll)
        int ch = 9;
        {
            int n = nv_host_parts(h, nullptr, 0);
            std::vector<nv_host_partinfo> ps((size_t)std::max(0, n));
            n = nv_host_parts(h, ps.data(), n);
            if (w->row >= 0 && w->row < n && ps[(size_t)w->row].channel >= 0)
                ch = ps[(size_t)w->row].channel;
        }
        J hits = sess::arr();
        for (int k = 0; k < 128; k++) {
            const unsigned c = h->key_hits[(size_t)ch][(size_t)k].load(std::memory_order_relaxed);
            if (ch == w->hit_ch && c != w->hit_n[k]) {
                J e = sess::arr();
                e.a.push_back(sess::integer(k));
                e.a.push_back(sess::integer(h->key_vel[(size_t)ch][(size_t)k]));
                hits.a.push_back(e);
            }
            w->hit_n[k] = c;
        }
        w->hit_ch = ch;
        if (!hits.a.empty()) {
            r.o["hits"] = hits;
            any = true;
        }
        if (w->tick % 6 == 3) {
            J dj = drums_of(h, w->row, false);
            std::string ds;
            put(ds, dj);
            if (ds != w->drums_sent) {
                w->drums_sent = ds;
                r.o["drums"] = dj;
                any = true;
            }
        }
    }
    if (w->piano && w->tick % 2 == 0) {        // (the pedals at 15 a second, while the card is open)
        J pj = piano_of(h, w->row, w->learning);
        std::string pst;
        put(pst, pj);
        if (pst != w->piano_sent) {
            w->piano_sent = pst;
            r.o["piano"] = pj;
            any = true;
        }
    }
    return any ? out_of(r) : nullptr;
}
