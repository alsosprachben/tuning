// panel.h -- nvlive's panel: live's (livetui.py) for the one native piano.
//
// What live's panel has that a native piano has too, laid out and keyed as
// live's: the header (the stream, the MIDI port, the real-time lamp), the
// part, the GLOBALS (master, headroom, limiter, bend range, mod depth,
// aftertouch, the GPU, the room's tail), the CONTROLS & ROUTES (live.Route:
// r adds one through live's own questions -- from, to, how a key holds,
// replace or keep, which channel -- d deletes, a key learnt by pressing it)
// and the OUTPUT at the bottom (the stereo meter with its fall and hold, the
// block's time against its budget, underruns, partials shed and sounding,
// the pedals). Tab moves between the panes, the arrows (or hjkl) select and
// adjust, - and + (_ and + by five) adjust, P is panic, ? the keys, q quits.
//
// Not live's: the patch tree, layers and splits, organ stops, the effect,
// the synth, presets and scenes (one piano, its program fixed at start),
// and the room itself (the voices are packed in the export's room; its tail
// can be turned off).
//
// No curses: ANSI escapes on a raw terminal, so it runs wherever nvlive does.
// The panel runs on its own thread; what it changes it POSTS (Host::post),
// done by the audio thread between two blocks, as live's panel posts.

#ifndef NV_PANEL_H
#define NV_PANEL_H

#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <deque>
#include <functional>
#include <mutex>
#include <string>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <termios.h>
#include <unistd.h>
#include <vector>

namespace panel {

// what the audio thread hands the panel after each block
struct Snap {
    long long n0 = 0;
    long blocks = 0, over = 0, underruns = 0;
    double ms_max = 0.0, ms_sum = 0.0;  // since the panel last looked
    long ms_n = 0;
    float peak[2] = {0.0f, 0.0f};       // since the panel last looked
    double eng[15] = {};                // nv_lp_stats
    bool rt = false, rt_dropped = false;
};

struct Host {
    std::function<Snap()> take;                                    // the latest, peaks and times reset
    std::function<std::pair<int, int>()> learnt;                  // a key pressed since learning was armed
    std::function<void(bool)> learn;                               // arm (or cancel) learning a key
    double rate = 48000.0, budget_ms = 2.67;
    int frames = 128, program = 0, reg_modes = 0;
    std::string port, room, program_name, tuner;
    // the globals: master dB, headroom dB, limiter, bend range, mod depth,
    // aftertouch dB, the GPU (1 on), the room's tail (1 on)
    double g[8];
    bool has_gpu = false, has_room = false;
    std::function<void(int, double)> set_global;                  // posted by the panel itself
    std::vector<std::array<int, 7>> routes;                        // the panel's copy (nv_rt_add's seven)
    std::function<void(const std::array<int, 7> &)> add_route;
    std::function<void(int)> del_route;
    std::function<void()> panic;                                   // every note off, now
};

static const char *GLOBAL_NAMES[8] = {"master", "headroom", "limiter", "bend range", "mod depth", "aftertouch",
                                      "gpu", "room tail"};
static const char *GLOBAL_UNITS[8] = {"dB", "dB", "", "st", "cents", "dB", "onoff", "onoff"};
static const double GLOBAL_RANGE[8][3] = {{-60.0, 0.0, 0.5}, {0.0, 24.0, 0.5}, {0.10, 1.00, 0.02},
                                          {0.0, 24.0, 0.5}, {0.0, 200.0, 5.0}, {0.0, 24.0, 0.5},
                                          {0.0, 1.0, 1.0}, {0.0, 1.0, 1.0}};

// live.CONTROLS: the destinations, in the panel's order, (key, label)
static const std::pair<int, const char *> CONTROLS[] = {
    {64, "sustain"}, {66, "sostenuto"}, {67, "soft"}, {65, "portamento"}, {-3, "mono"}, {1, "mod wheel"},
    {11, "expression"}, {7, "volume"}, {10, "pan"}, {5, "portamento time"}, {93, "chorus"},
    {94, "scanner (V/C)"}, {74, "brightness"}, {71, "resonance"}, {73, "attack"}, {75, "decay"},
    {72, "release"}, {76, "vibrato rate"}, {77, "vibrato depth"}, {78, "vibrato delay"}, {-1, "pitch wheel"},
    {-2, "aftertouch"}};
static const int NCONTROLS = sizeof(CONTROLS) / sizeof(CONTROLS[0]);

static bool control_switch(int key)
{
    return key == 64 || key == 66 || key == 67 || key == 65 || key == -3;
}

static const char *control_label(int key)
{
    for (auto &c : CONTROLS)
        if (c.first == key)
            return c.second;
    return nullptr;
}

// live.key_name: MIDI 60 is C4
static std::string key_name(int n)
{
    static const char *K[12] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
    return std::string(K[((n % 12) + 12) % 12]) + std::to_string(n / 12 - 1);
}

// livetui.parse_note: C1, F#2, Bb3, or 0-127; -1 not a key
static int parse_note(const std::string &s)
{
    if (s.empty())
        return -1;
    if (isdigit((unsigned char)s[0])) {
        int n = atoi(s.c_str());
        return n >= 0 && n <= 127 ? n : -1;
    }
    static const int base[7] = {9, 11, 0, 2, 4, 5, 7};      // A B C D E F G
    char c = (char)toupper((unsigned char)s[0]);
    if (c < 'A' || c > 'G')
        return -1;
    int n = base[c - 'A'];
    size_t i = 1;
    if (i < s.size() && (s[i] == '#' || s[i] == 'b')) {
        n += s[i] == '#' ? 1 : -1;
        i++;
    }
    if (i >= s.size())
        return -1;
    int oct = atoi(s.c_str() + i);
    n += 12 * (oct + 1);
    return n >= 0 && n <= 127 ? n : -1;
}

// live.Route.describe
static std::string describe(const std::array<int, 7> &r)
{
    std::string src;
    if (r[0] == 0) {
        const char *l = control_label(r[1]);
        src = l ? l : "CC" + std::to_string(r[1]);
    } else if (r[0] == 1) {
        src = r[1] == 0 ? "pitch ↑" : r[1] == 1 ? "pitch ↓" : "pitch ↕";
    } else if (r[0] == 2) {
        src = "aftertouch";
    } else {
        src = "key " + key_name(r[1]);
    }
    const char *d = control_label(r[2]);
    std::string dst = d ? d : std::to_string(r[2]);
    std::string how = control_switch(r[2]) ? (r[5] ? "toggle" : "held") : r[0] == 3 ? "velocity" : "scaled";
    return src + " → " + dst + "  " + how + "  " + (r[3] ? "keeps" : "replaces") + "  "
           + (r[4] < 0 ? "all" : "ch" + std::to_string(r[4] + 1));
}

// ---- the terminal ----------------------------------------------------------
struct Term {
    termios old{};
    bool on = false;
    int w = 80, h = 24;

    void enter()
    {
        tcgetattr(0, &old);
        termios t = old;
        t.c_lflag &= ~(ICANON | ECHO);
        t.c_cc[VMIN] = 0;
        t.c_cc[VTIME] = 0;
        tcsetattr(0, TCSANOW, &t);
        fputs("\x1b[?1049h\x1b[?25l", stdout);       // the alternate screen, no cursor
        fflush(stdout);
        on = true;
    }

    void leave()
    {
        if (!on)
            return;
        fputs("\x1b[?25h\x1b[?1049l", stdout);
        fflush(stdout);
        tcsetattr(0, TCSANOW, &old);
        on = false;
    }

    void size()
    {
        winsize ws{};
        if (ioctl(1, TIOCGWINSZ, &ws) == 0 && ws.ws_col > 0) {
            w = ws.ws_col;
            h = ws.ws_row;
        }
    }

    // one key within ms (-1 none): arrows as 1000+ (up down right left), shift-tab 1004
    int key(int ms)
    {
        fd_set f;
        FD_ZERO(&f);
        FD_SET(0, &f);
        timeval tv{ms / 1000, (ms % 1000) * 1000};
        if (select(1, &f, nullptr, nullptr, &tv) <= 0)
            return -1;
        unsigned char c;
        if (read(0, &c, 1) != 1)
            return -1;
        if (c != 27)
            return c;
        unsigned char s[2];
        timeval t2{0, 20000};
        FD_ZERO(&f);
        FD_SET(0, &f);
        if (select(1, &f, nullptr, nullptr, &t2) <= 0 || read(0, &s[0], 1) != 1)
            return 27;
        if (s[0] != '[' && s[0] != 'O')
            return 27;
        if (read(0, &s[1], 1) != 1)
            return 27;
        switch (s[1]) {
        case 'A': return 1000;
        case 'B': return 1001;
        case 'C': return 1002;
        case 'D': return 1003;
        case 'Z': return 1004;
        }
        return 27;
    }
};

// ---- the panel -------------------------------------------------------------
struct Panel {
    Host &H;
    Term T;
    int pane = 0;                       // 0 globals, 1 controls & routes
    int grow = 0, crow = 0;
    bool help = false;
    std::string msg;
    std::chrono::steady_clock::time_point msg_until;
    std::string out;                    // the frame being drawn
    Snap s;
    double lev[2] = {-90.0, -90.0}, hold[2] = {-90.0, -90.0};
    std::chrono::steady_clock::time_point held_at[2];
    std::deque<double> cpu;             // the load, a frame a column
    std::chrono::steady_clock::time_point last;

    explicit Panel(Host &h) : H(h) {}

    void say(const std::string &m, double secs = 3.0)
    {
        msg = m;
        msg_until = std::chrono::steady_clock::now() + std::chrono::milliseconds((long)(secs * 1000));
    }

    // -- drawing --
    std::string C(const char *what) const
    {
        if (!strcmp(what, "accent")) return "\x1b[38;5;45m";
        if (!strcmp(what, "accent2")) return "\x1b[38;5;141m";
        if (!strcmp(what, "dim")) return "\x1b[38;5;244m";
        if (!strcmp(what, "label")) return "\x1b[38;5;250m";
        if (!strcmp(what, "value")) return "\x1b[38;5;255m\x1b[1m";
        if (!strcmp(what, "ok")) return "\x1b[38;5;78m";
        if (!strcmp(what, "warn")) return "\x1b[38;5;214m";
        if (!strcmp(what, "bad")) return "\x1b[38;5;203m";
        if (!strcmp(what, "sel")) return "\x1b[7m";
        return "";
    }

    void line(const std::string &txt) { out += txt + "\x1b[0m\x1b[K\r\n"; }

    void rule(const std::string &name, bool here, const std::string &right = "")
    {
        int n = T.w - 6 - (int)name.size() - (int)right.size();
        std::string bar;
        for (int i = 0; i < std::max(2, n); i++)
            bar += "─";
        line((here ? C("accent") + "\x1b[1m" : C("dim")) + "── " + name + " " + "\x1b[0m" + C("dim") + bar
             + " " + right);
    }

    static std::string bar(double frac, int width)
    {
        frac = std::max(0.0, std::min(1.0, frac));
        int full = (int)(frac * width * 8 + 0.5);
        static const char *P[8] = {"", "▏", "▎", "▍", "▌", "▋", "▊", "▉"};
        std::string b;
        for (int i = 0; i < width; i++) {
            int k = full - 8 * i;
            b += k >= 8 ? "█" : k > 0 ? P[k] : "·";
        }
        return b;
    }

    std::string fmt_global(int i) const
    {
        char b[32];
        double v = H.g[i];
        if (!strcmp(GLOBAL_UNITS[i], "onoff"))
            return v >= 0.5 ? "on" : "off";
        if (i == 2)
            snprintf(b, sizeof b, "%.2f", v);
        else if (i == 4)
            snprintf(b, sizeof b, "%.0f %s", v, GLOBAL_UNITS[i]);
        else
            snprintf(b, sizeof b, "%.1f %s", v, GLOBAL_UNITS[i]);
        return b;
    }

    void draw()
    {
        T.size();
        out = "\x1b[H";
        char b[256];
        // the header
        snprintf(b, sizeof b, "%.0f kHz · %d frames · %.1f ms", H.rate / 1000.0, H.frames, H.budget_ms);
        std::string lamp = s.rt ? C("ok") + "● RT18" : s.rt_dropped ? C("bad") + "● rt dropped"
                                                                          : C("dim") + "● rt off";
        line(" " + C("accent") + "\x1b[1m◆ tuning native\x1b[0m  " + C("dim") + b + "   " + H.port + "   " + lamp);
        // the part
        rule("PART", false);
        snprintf(b, sizeof b, "   %d  %s", H.program, H.program_name.c_str());
        line(C("value") + b + "\x1b[0m" + C("dim") + "   " + H.tuner + "   room " + H.room
             + (H.reg_modes ? "   register " + std::to_string(H.reg_modes) + " string modes" : "   no register"));
        // the globals
        if (pane == 0 || T.h > 30) {
            rule("GLOBALS", pane == 0, "←→ -+ adjust");
            int half = 4;
            for (int r = 0; r < half; r++) {
                std::string row;
                for (int c = 0; c < 2; c++) {
                    int i = r + c * half;
                    bool here = pane == 0 && grow == i;
                    bool na = (i == 6 && !H.has_gpu) || (i == 7 && !H.has_room);
                    double lo = GLOBAL_RANGE[i][0], hi = GLOBAL_RANGE[i][1];
                    snprintf(b, sizeof b, "%-11s", GLOBAL_NAMES[i]);
                    std::string cell = std::string(here ? C("accent") + " ▸ \x1b[1m" : "   ") + "\x1b[0m"
                                       + (here ? C("accent") + "\x1b[1m" : C("label")) + b + "\x1b[0m";
                    snprintf(b, sizeof b, "%9s ", na ? "-" : fmt_global(i).c_str());
                    cell += C("value") + b + "\x1b[0m" + (here ? C("accent") : C("accent2"))
                            + bar(hi > lo ? (H.g[i] - lo) / (hi - lo) : 0.0, 12) + "\x1b[0m";
                    row += cell + "   ";
                }
                line(row);
            }
        }
        // the routes
        rule("CONTROLS & ROUTES", pane == 1, "r add  d delete");
        if (H.routes.empty())
            line("   " + C("dim") + "no routes -- r adds one (a key as the sustain pedal: from a key, to sustain)");
        for (size_t i = 0; i < H.routes.size(); i++) {
            bool here = pane == 1 && crow == (int)i;
            line(std::string(here ? C("accent") + " ▸ " : "   ") + "\x1b[0m" + (here ? C("value") : C("label"))
                 + describe(H.routes[i]));
        }
        // the output, at the bottom
        rule("OUTPUT", false);
        auto now = std::chrono::steady_clock::now();
        double dt = std::chrono::duration<double>(now - last).count();
        last = now;
        for (int c = 0; c < 2; c++) {
            double db = s.peak[c] > 1e-9 ? 20.0 * log10(s.peak[c]) : -90.0;
            lev[c] = std::max(db, lev[c] - 20.0 * dt);                 // the fall: 20 dB a second
            if (lev[c] >= hold[c] || std::chrono::duration<double>(now - held_at[c]).count() > 1.5) {
                hold[c] = lev[c];                                       // the hold: 1.5 s at the top
                held_at[c] = now;
            }
        }
        for (int c = 0; c < 2; c++) {
            snprintf(b, sizeof b, "%6.1f dB  peak %6.1f", lev[c], hold[c]);
            std::string col = hold[c] > -1.0 ? C("bad") : hold[c] > -6.0 ? C("warn") : C("ok");
            line(std::string("   ") + C("label") + (c ? "R " : "L ") + col + bar((lev[c] + 60.0) / 60.0, 40) + "\x1b[0m "
                 + C("value") + b);
        }
        double mean = s.ms_n ? s.ms_sum / s.ms_n : 0.0;
        cpu.push_back(s.ms_max / H.budget_ms);
        while ((int)cpu.size() > 24)
            cpu.pop_front();
        std::string spark;
        static const char *SP[8] = {"▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"};
        for (double x : cpu)
            spark += SP[std::max(0, std::min(7, (int)(x * 8)))];
        snprintf(b, sizeof b, " %.2f ms (worst %.2f) of %.2f  %s", mean, s.ms_max, H.budget_ms,
                 s.eng[4] > 0.5 ? "GPU" : "CPU");
        line("   " + C("label") + "load " + (s.ms_max > H.budget_ms ? C("bad") : C("accent2")) + spark + "\x1b[0m"
             + C("value") + b);
        snprintf(b, sizeof b, "   over %ld  underruns %ld  shed %.0f  dropped %.0f  partials %.0f  keys %.0f", s.over,
                 s.underruns, s.eng[2], s.eng[3], s.eng[0], s.eng[1]);
        line(C("dim") + b);
        snprintf(b, sizeof b, "   pedal %3.0f %s  sostenuto %s  mono %s  dampers %.0f  bend %+.0f cents", s.eng[7],
                 s.eng[7] >= 127 ? "●" : s.eng[7] > 0 ? "◐" : "○", s.eng[8] > 0.5 ? "●" : "○",
                 s.eng[9] > 0.5 ? "●" : "○", s.eng[10], s.eng[14]);
        line(C("dim") + b);
        // the message, and the keys
        if (now < msg_until)
            line("   " + C("warn") + msg);
        else
            line("   " + C("dim") + "tab pane  ↑↓ select  ←→ -+ adjust  P panic  ? keys  q quit");
        if (help) {
            line("");
            line(C("accent") + "  keys");
            line("   tab / shift-tab   globals -> controls and routes");
            line("   up down (k j)     select a global or a route");
            line("   left right - +    adjust the global (_ + by five)");
            line("   r                 add a route (from, to, how, replace or keep, channel)");
            line("   d                 delete the selected route");
            line("   P                 panic: every note off, now");
            line("   q                 quit (routes added here are kept beside the export)");
        }
        out += "\x1b[J";
        fwrite(out.data(), 1, out.size(), stdout);
        fflush(stdout);
    }

    // -- questions --
    // a menu over the bottom of the screen: the index, or -1 (Esc, q)
    int menu(const std::string &title, const std::vector<std::string> &items)
    {
        int at = 0;
        while (true) {
            std::string m = "\x1b[H\x1b[2J " + C("accent") + "\x1b[1m" + title + "\x1b[0m\r\n";
            for (size_t i = 0; i < items.size(); i++)
                m += std::string((int)i == at ? C("sel") + " ▸ " : "   ") + items[i] + "\x1b[0m\x1b[K\r\n";
            m += C("dim") + "\r\n   ↑↓ choose  enter take  esc back\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            if (c == 1000 || c == 'k')
                at = std::max(0, at - 1);
            else if (c == 1001 || c == 'j')
                at = std::min((int)items.size() - 1, at + 1);
            else if (c == 10 || c == 13)
                return at;
            else if (c == 27 || c == 'q')
                return -1;
        }
    }

    // a line typed: the text, or false (Esc)
    bool prompt(const std::string &label, std::string &got)
    {
        got.clear();
        while (true) {
            std::string m = "\x1b[H\x1b[2J " + C("accent") + label + "\x1b[0m" + got + "\x1b[K";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            if (c == 27)
                return false;
            if (c == 10 || c == 13)
                return true;
            if ((c == 127 || c == 8) && !got.empty())
                got.pop_back();
            else if (c >= 32 && c < 127)
                got += (char)c;
        }
    }

    // a key pressed on the keyboard: (channel, note), or (-1, -1) (Esc)
    std::pair<int, int> learn_key()
    {
        H.learn(true);
        std::string m = "\x1b[H\x1b[2J " + C("accent") + "press the key on the keyboard" + "\x1b[0m" + C("dim")
                        + "   (esc: back)\x1b[0m";
        fwrite(m.data(), 1, m.size(), stdout);
        fflush(stdout);
        while (true) {
            auto got = H.learnt();
            if (got.first >= 0)
                return got;
            if (T.key(50) == 27) {
                H.learn(false);
                return std::make_pair(-1, -1);
            }
        }
    }

    // livetui.add_route, its questions in its order
    void add_route()
    {
        static const char *SOURCES[] = {"mod wheel", "pitch wheel, pushed up", "pitch wheel, pulled down",
                                        "pitch wheel, either way", "aftertouch", "sustain pedal (CC64)",
                                        "expression pedal (CC11)", "another CC, by number", "a key: press it",
                                        "a key: by name (C1, 36)"};
        int i = menu("route FROM", std::vector<std::string>(SOURCES, SOURCES + 10));
        if (i < 0)
            return;
        int src = 0, arg = 0, learned_ch = -1;
        std::string t;
        switch (i) {
        case 0: src = 0; arg = 1; break;
        case 1: src = 1; arg = 0; break;
        case 2: src = 1; arg = 1; break;
        case 3: src = 1; arg = 2; break;
        case 4: src = 2; break;
        case 5: src = 0; arg = 64; break;
        case 6: src = 0; arg = 11; break;
        case 7: {
            if (!prompt("CC number (0-119): ", t))
                return;
            int n = isdigit((unsigned char)(t.empty() ? 'x' : t[0])) ? atoi(t.c_str()) : -1;
            if (n < 0 || n > 119) {
                say("not a controller: " + t);
                return;
            }
            src = 0;
            arg = n;
            break;
        }
        case 8: {
            auto got = learn_key();
            if (got.first < 0)
                return;
            src = 3;
            arg = got.second;
            learned_ch = got.first;
            break;
        }
        default: {
            if (!prompt("key (C1, F#2, or 0-127): ", t))
                return;
            int n = parse_note(t);
            if (n < 0) {
                say("not a key: " + t);
                return;
            }
            src = 3;
            arg = n;
        }
        }
        std::vector<std::string> to;
        for (auto &c : CONTROLS)
            to.push_back(c.second);
        int j = menu("route TO", to);
        if (j < 0)
            return;
        int dst = CONTROLS[j].first;
        if ((src == 0 && arg == dst) || (src == 1 && dst == -1) || (src == 2 && dst == -2)) {
            say("a control routed to itself does nothing");
            return;
        }
        int latch = 0;
        if (src == 3 && control_switch(dst)) {
            int h = menu("the key", {"held while down (a pedal)", "toggle: each press flips it"});
            if (h < 0)
                return;
            latch = h == 1;
        }
        int k = menu("and the original",
                     {"replace it (the source stops doing what it did)", "keep it (the source does both)"});
        if (k < 0)
            return;
        int ch = -1;
        std::string q = learned_ch >= 0
                            ? "listen on channel (blank = " + std::to_string(learned_ch + 1) + ", 'all' = all): "
                            : "listen on channel (1-16, blank = all): ";
        if (!prompt(q, t))
            return;
        if (t.empty())
            ch = learned_ch;
        else if (t != "all") {
            int c = atoi(t.c_str());
            if (c < 1 || c > 16) {
                say("not a channel: " + t);
                return;
            }
            ch = c - 1;
        }
        std::array<int, 7> r = {src, arg, dst, k == 1, ch, latch, 1};
        H.add_route(r);
        H.routes.push_back(r);
        crow = (int)H.routes.size() - 1;
        say("route " + describe(r));
    }

    void adjust(int delta, bool big)
    {
        if (pane != 0)
            return;
        int i = grow;
        if ((i == 6 && !H.has_gpu) || (i == 7 && !H.has_room)) {
            say(i == 6 ? "gpu: not available (--gpu at start)" : "room tail: the export has none");
            return;
        }
        double v = H.g[i] + delta * GLOBAL_RANGE[i][2] * (big ? 5 : 1);
        v = std::max(GLOBAL_RANGE[i][0], std::min(GLOBAL_RANGE[i][1], v));
        if (i == 2)
            v = std::round(v * 100.0) / 100.0;
        H.g[i] = v;
        H.set_global(i, v);
    }

    // the panel until q: drawn ten times a second, between keys
    void run(const std::function<bool()> &going)
    {
        T.enter();
        last = std::chrono::steady_clock::now();
        auto next = last;
        while (going()) {
            int c = T.key(20);
            if (c >= 0) {
                if (help) {
                    help = false;
                } else if (c == 'q') {
                    break;
                } else if (c == '?') {
                    help = true;
                } else if (c == 9) {
                    pane = (pane + 1) % 2;
                } else if (c == 1004) {
                    pane = (pane + 1) % 2;
                } else if (c == 1000 || c == 'k') {
                    if (pane == 0)
                        grow = std::max(0, grow - 1);
                    else
                        crow = std::max(0, crow - 1);
                } else if (c == 1001 || c == 'j') {
                    if (pane == 0)
                        grow = std::min(7, grow + 1);
                    else
                        crow = std::min(std::max(0, (int)H.routes.size() - 1), crow + 1);
                } else if (c == 1003 || c == 'h' || c == '-' || c == '_') {
                    adjust(-1, c == '_');
                } else if (c == 1002 || c == 'l' || c == '=' || c == '+') {
                    adjust(1, c == '+');
                } else if (c == 'P') {
                    H.panic();
                    say("all notes off");
                } else if (pane == 1 && c == 'r') {
                    add_route();
                } else if (pane == 1 && c == 'd' && !H.routes.empty()) {
                    int i = std::min(crow, (int)H.routes.size() - 1);
                    say("removed route " + describe(H.routes[i]));
                    H.del_route(i);
                    H.routes.erase(H.routes.begin() + i);
                    crow = std::max(0, std::min(crow, (int)H.routes.size() - 1));
                }
            }
            auto now = std::chrono::steady_clock::now();
            if (now >= next) {
                s = H.take();
                draw();
                next = now + std::chrono::milliseconds(100);
            }
        }
        T.leave();
    }
};

}  // namespace panel

#endif
