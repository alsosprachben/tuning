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
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <string>
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
        o.o["name"] = sess::str(p.name);
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

// a part's knobs on a layer: positions, whose they are, and each in its own words
J synth_of(nv_host *h, int row, int layer)
{
    double pn[NV_MK_N] = {};
    char own[NV_MK_N] = {};
    J o = sess::obj();
    int layers = nv_host_synth_get(h, row, layer, pn, own);
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

double now_s()
{
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

}  // namespace

struct nv_ui_watch {
    int row = 0, layer = 0;
    std::string parts_sent, synth_sent;
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
    } else if (call == "synth") {
        r.o["synth"] = synth_of(h, row, (int)arg_i(q, "layer", w ? w->layer : 0));
    } else if (call == "synth_set" || call == "synth_forget") {
        const int layer = (int)arg_i(q, "layer", w ? w->layer : 0), knob = (int)arg_i(q, "knob", -1);
        if (knob < 0 || knob >= NV_MK_N) {
            ok = false;
            r.o["error"] = sess::str("no knob " + std::to_string(knob));
        } else if (call == "synth_set") {
            nv_host_synth_set(h, row, layer, knob, std::max(-1.0, std::min(1.0, arg_d(q, "v", 0.0))));
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
        J sy = synth_of(h, w->row, w->layer);
        std::string ss;
        put(ss, sy);
        if (ss != w->synth_sent) {
            w->synth_sent = ss;
            r.o["synth"] = sy;
            any = true;
        }
    }
    return any ? out_of(r) : nullptr;
}
