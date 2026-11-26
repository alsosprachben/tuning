// THE MODULE MODE: the MIDI input read as a sound module reads it -- a
// sequencer or DAW playing a whole file into nvlive, its sixteen channels
// sixteen parts. The same modes as the Files card's, for a stream:
//
//   off       the player's own parts (as before)
//   auto      what the stream says: a GS Reset GS, GM System On GM, the
//             MT-32 family's exclusives the MT-32 (as a module switches)
//   gm        a GM module (GM System On)
//   ours, sc55, sc88, sc88pro, sc8850   GS, its banks in that map
//   cm64      GS: INIT CM-64 (a Sound Canvas's MT-32 setting)
//   mt32, cm64u   a real MT-32 / CM-64: its channels, its exclusives
//             (mt32.h's Unit, message by message, as the file reader runs it)
//
// Turning one on sets the player's setup aside (the session keeps it:
// hostsession's module_saved), gives the engine one part per channel
// (fileplay's file_parts), the map, a reset and the mode's own setup -- read
// from the file reader itself (an empty file in that mode: Init CM-64's
// parts, the MT-32's velocity), so a stream and a file of it sound alike.
// Turning it off puts the setup back as it was.
//
// Included by uiapi.cpp after fileplay.h.
#pragma once
#ifndef N_
#define N_(s) s   // (a text the interface translates where it shows it: nui/i18n.h)
#endif

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "partmux.h"
#include "mt32.h"


namespace module {

using J = sess::J;

static const char *MODES[] = {"off", "auto", "gm", "ours", "sc55", "sc88", "sc88pro", "sc8850", "cm64", "mt32", "cm64u"};

// a message as mt32.h's Unit takes it (the reader's Msg's fields)
struct LMsg {
    long long tick;
    int status, d0, d1;
    int meta;
    std::vector<uint8_t> data;
};

static bool to_msg(const Midi &m, LMsg &o)
{
    o = LMsg{0, 0, m.a & 127, m.b & 127, 0, {}};
    const int ch = m.ch & 15;
    switch (m.type) {
    case 0: o.status = 0x90 | ch; return true;
    case 1: o.status = 0x80 | ch; return true;
    case 2: o.status = 0xB0 | ch; return true;
    case 3: o.status = 0xD0 | ch; return true;
    case 7: o.status = 0xA0 | ch; return true;
    case 5: o.status = 0xC0 | ch; return true;
    case 4: {
        const int v = std::max(0, std::min(16383, m.a + 8192));
        o.status = 0xE0 | ch;
        o.d0 = v & 127;
        o.d1 = v >> 7;
        return true;
    }
    case 6: o.status = 0xF0; o.data = m.x; return true;
    default: return false;
    }
}

static bool to_midi(const LMsg &o, Midi &m)
{
    const int hi = o.status & 0xF0, ch = o.status & 0x0F;
    m = Midi{-1, ch, o.d0, o.d1, {}};
    if (o.status == 0xF0) {
        m.type = 6;
        m.ch = -1;
        m.a = m.b = 0;
        m.x = o.data;
    } else if (hi == 0x90 && o.d1 > 0) {
        m.type = 0;
    } else if (hi == 0x80 || hi == 0x90) {
        m.type = 1;
    } else if (hi == 0xB0) {
        m.type = 2;
    } else if (hi == 0xD0) {
        m.type = 3;
    } else if (hi == 0xA0) {
        m.type = 7;
    } else if (hi == 0xC0) {
        m.type = 5;
    } else if (hi == 0xE0) {
        m.type = 4;
        m.a = ((o.d1 << 7) | o.d0) - 8192;
        m.b = 0;
    }
    return m.type >= 0;
}

static bool gs_reset(const std::vector<uint8_t> &d)
{
    return d.size() >= 7 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && d[4] == 0x40 && d[5] == 0x00 && d[6] == 0x7F;
}
static bool gm_on(const std::vector<uint8_t> &d)
{
    return d.size() >= 4 && d[0] == 0x7E && d[2] == 0x09 && (d[3] == 0x01 || d[3] == 0x03);
}
static bool mt32_excl(const std::vector<uint8_t> &d) { return d.size() >= 3 && d[0] == 0x41 && d[2] == 0x16; }
static int mirror(int v) { return std::max(0, std::min(127, 128 - v)); }    // (a CM-64's pan: Init CM-64's cm64_pan)

struct State {
    std::mutex mu;                      // (mode, eff, unit, stage: the input's thread and the window's)
    std::string mode = "off";           // asked for
    std::string eff;                    // in force ("" GS in the standard; "leaving" on the way out)
    std::string stage;
    std::unique_ptr<mt32::Unit<LMsg>> unit;
    std::thread th;
    std::atomic<bool> busy{false};
    int std_map = 0;                    // (the player's standard, put back at the end)
    ~State()
    {                                   // (a program ending with a change under way: let it finish, not abort)
        if (th.joinable())
            th.join();
    }
};
static State g;

// THE MODE's OWN SETUP, as the file reader gives it: an empty file read in
// that mode -- GM System On; Init CM-64's sixteen parts, the MT-32's velocity
static std::vector<Midi> init_events(const std::string &eff)
{
    static const uint8_t EMPTY[] = {'M', 'T', 'h', 'd', 0, 0, 0, 6, 0, 0, 0, 1, 0x01, 0xE0,
                                    'M', 'T', 'r', 'k', 0, 0, 0, 4, 0, 0xFF, 0x2F, 0};
    std::vector<Midi> out;
    std::vector<uint8_t> b(EMPTY, EMPTY + sizeof EMPTY);
    int err = 0;
    void *m = fileplay::read_mode(b, eff, &err);
    if (!m)
        return out;
    std::vector<uint8_t> x(65536);
    for (int i = 0, ne = nv_midi_n_events(m); i < ne; i++) {
        int iv[4];
        double t;
        nv_midi_event(m, i, iv, &t);
        Midi ev{iv[0], iv[1], iv[2], iv[3], {}};
        if (iv[0] == 6) {
            const int n = nv_midi_sysex(m, iv[2], x.data(), (int)x.size());
            if (n <= 0 || n > (int)x.size())
                continue;
            ev.x.assign(x.begin(), x.begin() + n);
        }
        out.push_back(std::move(ev));
    }
    nv_midi_free(m);
    return out;
}

static bool mt32_family(const std::string &e) { return e == "cm64" || e == "mt32" || e == "cm64u"; }

// the mode in force from here: its map, a reset, its setup (g.mu held)
static void begin(nv_host *h, const std::string &eff)
{
    g.eff = eff;
    const int mp = mt32_family(eff) ? 1 : fileplay::map_of(eff) >= 0 ? fileplay::map_of(eff) : g.std_map;
    nv_host_set_global(h, 13, mp);
    if (eff != "gm") {                  // (a reset to power-on first: GM's own is in its setup, GM System On)
        Midi r{6, -1, 0, 0, {}};
        r.x.assign(fileplay::GS_RESET, fileplay::GS_RESET + sizeof fileplay::GS_RESET);
        h->enqueue(std::move(r));
    }
    for (auto &e : init_events(eff == "" ? "ours" : eff))
        h->enqueue(std::move(e));
    g.unit.reset();
    if (eff == "mt32" || eff == "cm64u")
        g.unit.reset(new mt32::Unit<LMsg>(eff == "cm64u"));
}

// ONE MESSAGE FROM OUTSIDE, as the module in force reads it (the input's
// thread): what it becomes, to OUT (the engine's queue, or the timed queue at
// the message's frame)
template <class Out>
static void feed_to(nv_host *h, Midi &&m, Out &&out)
{
    std::lock_guard<std::mutex> lk(g.mu);
    if (g.eff == "leaving") {
        out(std::move(m));
        return;
    }
    // AUTO: the stream's own word switches it, as a module's reset does
    if (g.mode == "auto" && m.type == 6) {
        std::string want = g.eff;
        if (mt32_excl(m.x))
            want = "mt32";
        else if (gm_on(m.x))
            want = "gm";
        else if (gs_reset(m.x))
            want = "";
        if (want != g.eff) {
            g.stage = want == "mt32" ? "the input sent MT-32 messages: playing as an MT-32"
                    : want == "gm" ? "the input sent GM System On: playing as GM" : "the input sent a GS Reset: playing as GS";
            begin(h, want);
        }
    }
    const std::string &e = g.eff;
    if (e == "cm64") {                  // GS: INIT CM-64 -- a Sound Canvas: the family's exclusives change nothing, pans mirrored
        if (m.type == 6 && mt32_excl(m.x))
            return;
        if (m.type == 2 && m.a == 10)
            m.b = mirror(m.b);
        out(std::move(m));
        return;
    }
    if ((e == "mt32" || e == "cm64u") && g.unit) {
        if (m.type == 6 && !mt32_excl(m.x) && !(m.x.size() >= 3 && m.x[0] == 0x41 && m.x[2] == 0x14))
            return;                     // (the unit reads no GS or GM exclusives)
        LMsg in;
        if (!to_msg(m, in))
            return;
        std::vector<LMsg> heard;
        g.unit->feed(in, heard);
        for (const LMsg &o : heard) {
            Midi mm;
            if (!to_midi(o, mm))
                continue;
            if (mm.type == 2 && mm.a == 10)
                mm.b = mirror(mm.b);    // (its pans the unit's: mirrored, as the CM-64 map's)
            out(std::move(mm));
        }
        return;
    }
    out(std::move(m));
}
static void feed(nv_host *h, Midi &&m)
{
    feed_to(h, std::move(m), [h](Midi &&x) { h->enqueue(std::move(x)); });
}
static void feed_at(nv_host *h, Midi &&m, long long frame)
{
    feed_to(h, std::move(m), [h, frame](Midi &&x) { h->push_timed(std::move(x), frame); });
}

static void say(const std::string &s)
{
    std::lock_guard<std::mutex> lk(g.mu);
    g.stage = s;
}

// ON: the player's setup set aside, a part per channel, the mode begun (a worker's)
static void enter(nv_host *h, const std::string &mode, bool parts)
{
    if (parts) {
        say("setting up sixteen parts, one per channel");
        J st = h->session_state(h->E.routes);
        fileplay::file_parts(h, st);
        h->apply_setup(st, false);
        static const std::atomic<bool> never{false};
        fileplay::wait_built(h, never, 120.0);
    }
    std::lock_guard<std::mutex> lk(g.mu);
    begin(h, mode == "auto" ? "" : mode);
    g.stage = mode == "auto" ? "listening: GS until the input says otherwise" : "ready";
}

// OFF: the notes let go, a reset, the player's setup put back as it was
static void leave(nv_host *h)
{
    {
        std::lock_guard<std::mutex> lk(g.mu);
        g.eff = "leaving";
        g.unit.reset();
        g.stage = N_("putting your setup back");
    }
    h->panic();
    Midi r{6, -1, 0, 0, {}};
    r.x.assign(fileplay::GS_RESET, fileplay::GS_RESET + sizeof fileplay::GS_RESET);
    h->enqueue(std::move(r));
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    // (the session's state while the module is on: the player's setup in it)
    J st = h->session_state(h->E.routes);
    h->apply_setup(st, false);
    {
        std::lock_guard<std::mutex> lk(h->module_mu);
        h->module_on.store(false, std::memory_order_release);
        h->module_saved = J();
    }
    std::lock_guard<std::mutex> lk(g.mu);
    g.mode = "off";
    g.eff.clear();
    g.stage.clear();
}

static void join()
{
    if (g.th.joinable())
        g.th.join();
}

// THE WINDOW's ASK: a mode (off to leave); false (and why) if it cannot now
static bool set(nv_host *h, const std::string &mode, std::string &why)
{
    bool known = false;
    for (const char *m : MODES)
        known = known || mode == m;
    if (!known) {
        why = N_("no such mode");
        return false;
    }
    if (g.busy) {
        why = N_("still changing modes");
        return false;
    }
    join();
    std::string was;
    {
        std::lock_guard<std::mutex> lk(g.mu);
        was = g.mode;
        if (mode == was)
            return true;
        if (mode != "off")
            g.mode = mode;
    }
    if (was == "off") {
        // the player's setup set aside: the session keeps it while the module plays
        J saved = h->session_state(h->E.routes);
        {
            std::lock_guard<std::mutex> lk(h->module_mu);
            h->module_saved = saved;
        }
        {
            std::lock_guard<std::mutex> lk(g.mu);
            g.std_map = (int)lround(nv_host_global(h, 13));
            g.eff = "";
        }
        h->module_feed = feed;
        h->module_feed_at = feed_at;
        h->module_on.store(true, std::memory_order_release);
    }
    g.busy = true;
    g.th = std::thread([h, mode, was]() {
        if (mode == "off")
            leave(h);
        else
            enter(h, mode, was == "off");
        g.busy = false;
    });
    return true;
}

// what the window shows: the mode asked, the one in force, the stage, and
// the unit's report (what it did with the input's exclusives)
static J state()
{
    std::lock_guard<std::mutex> lk(g.mu);
    J o = sess::obj();
    o.o["mode"] = sess::str(g.mode);
    o.o["eff"] = sess::str(g.eff == "" && g.mode != "off" ? "gs" : g.eff);
    o.o["busy"] = sess::boolean(g.busy);
    o.o["stage"] = sess::str(g.stage);
    J rp = sess::arr();
    if (g.unit)
        for (const auto &l : g.unit->R.lines)
            rp.a.push_back(sess::str(l));
    o.o["report"] = rp;
    return o;
}

// OFF NOW, on the caller's thread (the Files card's player takes the parts over)
static void off_now(nv_host *h)
{
    join();
    {
        std::lock_guard<std::mutex> lk(g.mu);
        if (g.mode == "off")
            return;
    }
    g.busy = true;
    leave(h);
    g.busy = false;
}

// (nvlive's exit: a change under way finished; the session already keeps the player's setup)
static void shutdown() { join(); }

}  // namespace module
