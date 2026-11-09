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
// The patch picker (p) lists every program, its variations and the drum
// sets; x is the insertion effect (livetui.pick_efx): the part on it or off,
// its type by Roland's families, each parameter as his panel prints it, the
// two controllers and the sends -- each sent as the GS message a file would
// carry.
//
// Not live's: the patch tree, layers and splits, a tone's own effect shown,
// the synth, presets and scenes (one part, its program picked here or by MIDI),
// and the room itself (the voices are packed in the export's room; its tail
// can be turned off).
//
// No curses: ANSI escapes on a raw terminal, so it runs wherever nvlive does.
// The panel runs on its own thread; what it changes it POSTS (Host::post),
// done by the audio thread between two blocks, as live's panel posts.

#ifndef NV_PANEL_H
#define NV_PANEL_H

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <deque>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <termios.h>
#include <thread>
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
    double eng[15] = {};                // nv_part_stats
    // the insertion effect when it last changed (nv_part_efx_state: empty
    // none in the export), its revision and why its chain is refused
    std::vector<int> efx;
    std::string efx_why;
    long efx_rev = -1;
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
    double g[9];
    // ...and THE ROOM (live's global 'room': live.ROOM_NAMES the export
    // carries, g[8] the index of the one now; a step asks the builder for it)
    std::vector<std::string> rooms;
    bool has_gpu = false, has_room = false;
    std::function<void(int, double)> set_global;                  // posted by the panel itself
    std::vector<std::array<int, 7>> routes;                        // the panel's copy (nv_rt_add's seven)
    std::function<void(const std::array<int, 7> &)> add_route;
    std::function<void(int)> del_route;
    std::function<void()> panic;                                   // every note off, now
    // AN ORGAN'S STOPS (live's panel: Patch.stop_rows): its ranks' names, the
    // rows as the panel lays them out (rank indices), which are drawn now,
    // and a stop drawn or put in (posted)
    std::vector<std::string> stop_names;
    std::vector<std::vector<int>> stop_rows;
    std::function<std::vector<char>()> drawn;
    std::function<void(int)> toggle_stop;
    // before each frame: the host brings what it changed itself up to date
    // (a program change from the keyboard: the program, its name, its stops)
    // and says what it has to say ("" nothing)
    std::function<std::string()> refresh;
    // THE PATCH PICKER: each program's name (0-127) and each drum set's (128 +
    // set; "" none), which are native here, whether the part is a drum set
    // now, and a program or set asked for (posted)
    std::vector<std::string> names;
    std::vector<char> native;
    bool kit = false;
    // ...and the variations under the programs (256 + j: program, key, name,
    // native), the part's own now (0 the capital tone)
    std::vector<std::array<int, 2>> vpv;
    std::vector<std::string> vnames;
    std::vector<char> vnative;
    int var = 0;
    std::function<void(int)> pick;
    // THE INSERTION EFFECT's tables (the export's EFXU: gsefx's numbered
    // types, families and each type's parameters), the GS exclusive the
    // panel sends (posted, as a file's), the channel the part listens on (-1
    // all), and the last controller moved (gsefx's source code: CC 1-95,
    // 0x60 aftertouch, 0x61 the wheel; and when, steady_clock ns)
    struct EfxType {
        int num, msb, lsb;
        std::string name;
    };
    struct EfxCat {
        int a, b;
        std::string name;
    };
    struct EfxParam {
        int n;
        std::string name;
        char mark;                      // '+' or '#': moved by that controller; '-' neither
        bool read;                      // the model reads it (gsefx.in_effect has it)
        int fresh;                      // its value in effect where none is set
        std::vector<int> vals;          // the raw values it takes
        std::vector<std::string> shown; // ...each as Roland's panel prints it
    };
    std::vector<EfxType> efx_types;
    std::vector<EfxCat> efx_cats;
    std::map<std::pair<int, int>, std::vector<EfxParam>> efx_params;
    std::function<void(const std::vector<uint8_t> &)> efx_send;
    std::function<std::pair<int, long long>()> last_ctl;
    int channel = -1;
};

// the export's EFXU into the host's tables (native_export.py's lines)
static void efx_tables(Host &H, const std::string &txt)
{
    auto split = [](const std::string &s, char d) {
        std::vector<std::string> f;
        size_t a = 0;
        for (size_t b; (b = s.find(d, a)) != std::string::npos; a = b + 1)
            f.push_back(s.substr(a, b - a));
        f.push_back(s.substr(a));
        return f;
    };
    for (const std::string &ln : split(txt, '\n')) {
        std::vector<std::string> f = split(ln, '\t');
        if (f[0] == "T" && f.size() == 5) {
            H.efx_types.push_back({atoi(f[1].c_str()), atoi(f[2].c_str()), atoi(f[3].c_str()), f[4]});
        } else if (f[0] == "C" && f.size() == 4) {
            H.efx_cats.push_back({atoi(f[1].c_str()), atoi(f[2].c_str()), f[3]});
        } else if (f[0] == "P" && f.size() == 10) {
            Host::EfxParam p{atoi(f[3].c_str()), f[4], f[5].empty() ? '-' : f[5][0], f[6] == "1", atoi(f[7].c_str()),
                             {}, split(f[9], '\x1f')};
            for (const std::string &v : split(f[8], ','))
                p.vals.push_back(atoi(v.c_str()));
            if (p.vals.size() == p.shown.size())
                H.efx_params[std::make_pair(atoi(f[1].c_str()), atoi(f[2].c_str()))].push_back(p);
        }
    }
}

// gsefx's addresses: the sends from the effect, its two controllers
static const int EFX_SEND[3] = {0x17, 0x18, 0x19};
static const int EFX_CTL_SRC1 = 0x1B, EFX_CTL_DEP1 = 0x1C, EFX_CTL_SRC2 = 0x1D, EFX_CTL_DEP2 = 0x1E;
static const int EFX_SRC_CAF = 0x60, EFX_SRC_BEND = 0x61;

// gsefx.message: the GS DT1 exclusive (no F0/F7) for an EFX setting --
// kind 't' type (a msb, b lsb), 'p' parameter (a 1-20, b), 's' a send or
// controller (a its address, b), 'c' a part (a channel, b on)
static std::vector<uint8_t> efx_message(char kind, int a, int b)
{
    std::vector<uint8_t> body;
    if (kind == 't') {
        body = {0x40, 0x03, 0x00, (uint8_t)a, (uint8_t)b};
    } else if (kind == 'p') {
        body = {0x40, 0x03, (uint8_t)(0x02 + a), (uint8_t)b};
    } else if (kind == 's') {
        body = {0x40, 0x03, (uint8_t)a, (uint8_t)b};
    } else {
        int ch = a % 16, blk = ch == 9 ? 0 : ch < 9 ? ch + 1 : ch;
        body = {(uint8_t)(a >= 16 ? 0x50 : 0x40), (uint8_t)(0x40 | blk), 0x22, (uint8_t)(b ? 1 : 0)};
    }
    int sum = 0;
    for (uint8_t x : body)
        sum += x;
    std::vector<uint8_t> m = {0x41, 0x10, 0x42, 0x12};
    m.insert(m.end(), body.begin(), body.end());
    m.push_back((uint8_t)((128 - sum % 128) % 128));
    return m;
}

// the state nv_part_efx_state wrote, read back
struct EfxView {
    bool has = false;
    int msb = 0, lsb = 0, p[21], snd[3] = {40, 0, 0}, ctl[4] = {0, 0x40, 0, 0x40};
    std::vector<int> parts;
    std::map<int, int> cv;
    int status = -1;
    explicit EfxView(const std::vector<int> &o)
    {
        for (int q = 0; q < 21; q++)
            p[q] = -1;
        if (o.size() < 31)
            return;
        has = true;
        msb = o[0];
        lsb = o[1];
        for (int q = 1; q <= 20; q++)
            p[q] = o[1 + q];
        for (int q = 0; q < 3; q++)
            snd[q] = o[22 + q];
        for (int q = 0; q < 4; q++)
            ctl[q] = o[25 + q];
        size_t i = 29, np = (size_t)o[i++];
        for (size_t q = 0; q < np && i < o.size(); q++)
            parts.push_back(o[i++]);
        size_t nc = i < o.size() ? (size_t)o[i++] : 0;
        for (size_t q = 0; q < nc && i + 1 < o.size(); q++, i += 2)
            cv[o[i]] = o[i + 1];
        status = i < o.size() ? o[i] : -1;
    }
};

// THE STOP KEYS, as livetui's on a US layout: row 0 the digits, row 1 the
// same keys shifted; rows 2 and 3 the same after the prefix (backtick: a
// window manager that keeps Alt never lets Alt+digit through)
static const char STOP_DIGITS[] = "123456789", STOP_SHIFTED[] = "!@#$%^&*(";
static const int STOP_PREFIX = '`';

static const int NGLOBALS = 9;
static const char *GLOBAL_NAMES[NGLOBALS] = {"master", "headroom", "limiter", "bend range", "mod depth", "aftertouch",
                                             "gpu", "room tail", "room"};
static const char *GLOBAL_UNITS[NGLOBALS] = {"dB", "dB", "", "st", "cents", "dB", "onoff", "onoff", "room"};
static const double GLOBAL_RANGE[NGLOBALS][3] = {{-60.0, 0.0, 0.5}, {0.0, 24.0, 0.5}, {0.10, 1.00, 0.02},
                                                 {0.0, 24.0, 0.5}, {0.0, 200.0, 5.0}, {0.0, 24.0, 0.5},
                                                 {0.0, 1.0, 1.0}, {0.0, 1.0, 1.0}, {0.0, 0.0, 1.0}};

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

    // one key within ms (-1 none): arrows as 1000+ (up down right left), shift-tab 1004,
    // page up and down 1005-1006, home and end 1007-1008
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
        if (s[1] >= '1' && s[1] <= '8') {           // ESC [ n ~: page up 5, down 6, home 1/7, end 4/8
            unsigned char t;
            if (read(0, &t, 1) != 1 || t != '~')
                return 27;
            return s[1] == '5' ? 1005 : s[1] == '6' ? 1006 : (s[1] == '1' || s[1] == '7') ? 1007
                                                            : (s[1] == '4' || s[1] == '8') ? 1008 : 27;
        }
        switch (s[1]) {
        case 'H': return 1007;
        case 'F': return 1008;
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
    bool stop_bank = false;             // the stop prefix pressed: the next stop key is rows 3-4's
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
        if (!strcmp(GLOBAL_UNITS[i], "room")) {
            int k = (int)v;
            return k >= 0 && k < (int)H.rooms.size() ? H.rooms[k] : "-";
        }
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
        if (H.var && !H.kit)                    // (a variation: its program, its bank)
            snprintf(b, sizeof b, "   %d.%d  %s", H.program, H.var & 127, H.program_name.c_str());
        else
            snprintf(b, sizeof b, "   %s%d  %s", H.kit ? "set " : "", H.program, H.program_name.c_str());
        line(C("value") + b + "\x1b[0m" + C("dim") + "   " + H.tuner + "   room " + H.room
             + (H.reg_modes ? "   register " + std::to_string(H.reg_modes) + " string modes" : "   no register"));
        // the insertion effect: its type, the part on it or not, and why it
        // is not heard where it is refused here (x opens it)
        if (!s.efx.empty()) {
            EfxView v(s.efx);
            std::string nm = efx_name(v.msb, v.lsb), st;
            if (nm != "Thru") {
                st = efx_on(v) ? "   part on it" : "   part not on it";
                if (v.status == -3)
                    st += C("warn") + "   not native live: " + s.efx_why;
                else if (v.status != 0)
                    st += C("warn") + "   not built live";
            }
            line("   " + C("label") + "efx  " + C("value") + nm + "\x1b[0m" + C("dim") + st + C("dim") + "   (x)");
        }
        // the globals
        if (pane == 0 || T.h > 30) {
            rule("GLOBALS", pane == 0, "←→ -+ adjust");
            int half = (NGLOBALS + 1) / 2;
            for (int r = 0; r < half; r++) {
                std::string row;
                for (int c = 0; c < 2; c++) {
                    int i = r + c * half;
                    if (i >= NGLOBALS)
                        continue;
                    bool here = pane == 0 && grow == i;
                    bool na = (i == 6 && !H.has_gpu) || (i == 7 && !H.has_room) || (i == 8 && H.rooms.empty());
                    double lo = GLOBAL_RANGE[i][0], hi = i == 8 ? (double)H.rooms.size() - 1.0 : GLOBAL_RANGE[i][1];
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
        // an organ's stops: drawn in the accent, the rest dim, each with its key
        if (!H.stop_names.empty()) {
            rule("STOPS", false, stop_bank ? "rows 3-4: press a stop key" : "1-9  shift  ` then a key: rows 3-4");
            std::vector<char> dr = H.drawn();
            for (size_t r = 0; r < H.stop_rows.size(); r++) {
                std::string row = "   ";
                for (size_t i = 0; i < H.stop_rows[r].size() && i < 9; i++) {
                    int ri = H.stop_rows[r][i];
                    std::string key = std::string(r >= 2 ? "`" : "") + (r % 2 ? STOP_SHIFTED[i] : STOP_DIGITS[i]);
                    bool on = ri >= 0 && ri < (int)dr.size() && dr[ri];
                    row += (on ? C("accent") + "\x1b[1m" : C("dim")) + key + " "
                           + (ri < (int)H.stop_names.size() ? H.stop_names[ri] : "?") + "\x1b[0m   ";
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
            line("   " + C("dim") + "tab pane  ↑↓ select  ←→ -+ adjust  p patch  x efx  P panic  ? keys  q quit");
        if (help) {
            line("");
            line(C("accent") + "  keys");
            line("   tab / shift-tab   globals -> controls and routes");
            line("   up down (k j)     select a global or a route");
            line("   left right - +    adjust the global (_ + by five)");
            line("   r                 add a route (from, to, how, replace or keep, channel)");
            line("   d                 delete the selected route");
            line("   p                 the patch: every program, its variations, the drum sets; / to search");
            line("   x                 the insertion effect: the part on it, its type, parameters, controllers, sends");
            line("   P                 panic: every note off, now");
            line("   q                 quit (routes added here are kept beside the export)");
        }
        out += "\x1b[J";
        fwrite(out.data(), 1, out.size(), stdout);
        fflush(stdout);
    }

    // -- questions --
    // a menu over the bottom of the screen: the index, or -1 (Esc, q) --
    // opened on start, the rows head marks headings (never chosen), a long
    // one scrolled
    int menu(const std::string &title, const std::vector<std::string> &items, int start = 0,
             const std::vector<char> &head = {})
    {
        const int n = (int)items.size();
        auto is_head = [&](int i) { return i < (int)head.size() && head[i]; };
        auto step = [&](int at, int d) {
            for (int j = at + d; j >= 0 && j < n; j += d)
                if (!is_head(j))
                    return j;
            return at;
        };
        int at = std::max(0, std::min(start, n - 1));
        if (is_head(at))
            at = step(at, 1);
        while (true) {
            T.size();
            int win = std::max(3, T.h - 4), top = std::max(0, std::min(at - win / 2, n - win));
            std::string m = "\x1b[H\x1b[2J " + C("accent") + "\x1b[1m" + title + "\x1b[0m\r\n";
            for (int i = top; i < std::min(n, top + win); i++)
                m += is_head(i) ? C("accent2") + "   " + items[i] + "\x1b[0m\x1b[K\r\n"
                                : std::string(i == at ? C("sel") + " ▸ " : "   ") + items[i] + "\x1b[0m\x1b[K\r\n";
            m += C("dim") + "\r\n   ↑↓ choose  enter take  esc back\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            if (c == 1000 || c == 'k')
                at = step(at, -1);
            else if (c == 1001 || c == 'j')
                at = step(at, 1);
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

    // THE PATCH: one list of every program under its family's heading, then
    // the drum sets -- opened on the part's own, the arrows (page up/down,
    // home/end) through all of it, Enter takes one; "/" searches every
    // program and set by the words typed. A voice not native here is listed
    // dim and cannot be picked.
    void pick_patch()
    {
        static const char *FAM[16] = {"Piano", "Chromatic Percussion", "Organ", "Guitar", "Bass", "Strings",
                                      "Ensemble", "Brass", "Reed", "Pipe", "Synth Lead", "Synth Pad",
                                      "Synth Effects", "Ethnic", "Percussive", "Sound Effects"};
        int here = (H.kit ? 128 : 0) + H.program;
        for (size_t j = 0; j < H.vpv.size() && H.var && !H.kit; j++)
            if (H.vpv[j][0] == H.program && H.vpv[j][1] == H.var)
                here = 256 + (int)j;
        auto nat = [&](int sp) {
            return sp >= 256 ? sp - 256 < (int)H.vnative.size() && H.vnative[sp - 256]
                             : sp >= 0 && sp < (int)H.native.size() && H.native[sp];
        };
        auto label = [&](int sp) {
            char b[200];
            if (sp >= 256) {                    // (a variation: under its program, its bank)
                const auto &pv = H.vpv[sp - 256];
                snprintf(b, sizeof b, "%s     %3d.%-3d  %-28s%s", sp == here ? "● " : "  ", pv[0], pv[1] & 127,
                         H.vnames[sp - 256].c_str(), nat(sp) ? "" : "  (not native)");
            } else {
                snprintf(b, sizeof b, "%s%s%3d  %-28s%s", sp == here ? "● " : "  ", sp >= 128 ? "set " : "",
                         sp & 127, sp < (int)H.names.size() ? H.names[sp].c_str() : "?", nat(sp) ? "" : "  (not native)");
            }
            return std::string(b);
        };
        // the whole list: (sp, or -1 a heading), its text
        std::vector<int> ids0;
        std::vector<std::string> rows0;
        for (int sp = 0; sp < 256; sp++) {
            bool kit = sp >= 128;
            if (kit && !(sp < (int)H.names.size() && !H.names[sp].empty()))
                continue;
            if ((!kit && sp % 8 == 0) || (kit && (ids0.empty() || ids0.back() < 128))) {
                ids0.push_back(-1);
                rows0.push_back(kit ? "── Drum sets" : std::string("── ") + FAM[sp / 8]);
            }
            ids0.push_back(sp);
            rows0.push_back(label(sp));
            for (size_t j = 0; j < H.vpv.size() && !kit; j++)     // (its variations under it)
                if (H.vpv[j][0] == sp) {
                    ids0.push_back(256 + (int)j);
                    rows0.push_back(label(256 + (int)j));
                }
        }
        pick_list("patch", ids0, rows0, here, nat, [&](int id) {
            const std::string what = id >= 256 ? std::to_string(H.vpv[id - 256][0]) + "."
                                                 + std::to_string(H.vpv[id - 256][1] & 127) + " " + H.vnames[id - 256]
                                               : (id >= 128 ? "drum set " : "program ") + std::to_string(id & 127)
                                                 + " " + H.names[id];
            if (!nat(id)) {
                say(what + " is not native here");
                return false;
            }
            if (id != here) {
                H.pick(id);
                say("asked for " + what + " (built if new, then swapped in)");
            }
            return true;
        });
    }

    // A LIST TO PICK FROM (the patch's, the effect types'): rows under
    // headings (id -1), opened on here, the arrows (page up/down, home/end)
    // through it; "/" searches by the words typed; Enter hands the row's id to
    // accept, which closes the list by returning true. A row dim_not says
    // false of is drawn dim.
    void pick_list(const std::string &title, const std::vector<int> &ids0, const std::vector<std::string> &rows0,
                   int here, const std::function<bool(int)> &dim_not, const std::function<bool(int)> &accept)
    {
        int at = 0;
        for (size_t i = 0; i < ids0.size(); i++)
            if (ids0[i] == here)
                at = (int)i;
        std::string query;
        bool searching = false;
        while (true) {
            std::vector<int> ids;
            std::vector<std::string> rows;
            if (query.empty()) {
                ids = ids0;
                rows = rows0;
            } else {
                std::vector<std::string> ws;
                std::string w;
                for (char c : query + " ")
                    if (c == ' ') {
                        if (!w.empty())
                            ws.push_back(w);
                        w.clear();
                    } else {
                        w += (char)tolower((unsigned char)c);
                    }
                for (size_t i = 0; i < ids0.size(); i++) {
                    if (ids0[i] < 0)
                        continue;
                    std::string lo;
                    for (char c : rows0[i])
                        lo += (char)tolower((unsigned char)c);
                    bool ok = true;
                    for (auto &x : ws)
                        ok = ok && lo.find(x) != std::string::npos;
                    if (ok) {
                        ids.push_back(ids0[i]);
                        rows.push_back(rows0[i]);
                    }
                }
            }
            int n = (int)ids.size();
            at = std::max(0, std::min(at, n - 1));
            if (n && ids[at] < 0 && at + 1 < n)
                at++;                           // (never on a heading)
            T.size();
            int win = std::max(3, T.h - 4), top = std::max(0, std::min(at - win / 2, n - win));
            std::string m = "\x1b[H\x1b[2J " + C("accent") + "\x1b[1m" + title + "\x1b[0m" + C("dim") + "   "
                            + std::to_string(at + 1) + "/" + std::to_string(n) + "\x1b[0m\r\n";
            for (int i = top; i < std::min(n, top + win); i++) {
                if (ids[i] < 0) {
                    m += C("accent2") + rows[i] + "\x1b[0m\x1b[K\r\n";
                    continue;
                }
                m += std::string(i == at ? C("sel") + " ▸" : "  ") + (!dim_not(ids[i]) && i != at ? C("dim") : "")
                     + rows[i] + "\x1b[0m\x1b[K\r\n";
            }
            if (!n)
                m += C("dim") + "   (nothing matches)\x1b[0m\r\n";
            if (searching || !query.empty())
                m += C("accent") + "\x1b[1m /" + query + (searching ? "_" : "") + "\x1b[0m" + C("dim") + "   "
                     + std::to_string(n) + " found  esc clears\x1b[0m";
            else
                m += C("dim") + "   ↑↓ pgup pgdn  enter take  / search  esc cancel\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            if (c < 0)
                continue;
            if (searching && c >= 32 && c < 127 && c != '/') {
                query += (char)c;
                at = 0;
                continue;
            }
            if (searching && (c == 127 || c == 8)) {
                if (!query.empty())
                    query.pop_back();
                at = 0;
                continue;
            }
            auto step = [&](int d) {            // d rows, past headings
                int j = std::max(0, std::min(n - 1, at + d));
                while (j > 0 && j < n - 1 && ids[j] < 0)
                    j += d > 0 ? 1 : -1;
                if (ids.size() && ids[j] < 0)
                    j = at;
                at = j;
            };
            if (c == '/') {
                searching = true;
            } else if (c == 1000 || (!searching && c == 'k')) {
                step(-1);
            } else if (c == 1001 || (!searching && c == 'j')) {
                step(1);
            } else if (c == 1005) {
                step(-win);
            } else if (c == 1006) {
                step(win);
            } else if (c == 1007) {
                at = 0;
                step(0);
            } else if (c == 1008) {
                at = n - 1;
            } else if (c == 10 || c == 13) {
                if (n && ids[at] >= 0 && accept(ids[at]))
                    return;
            } else if (c == 27) {
                if (searching || !query.empty()) {
                    query.clear();              // first Esc: the search
                    searching = false;
                    at = 0;
                    for (size_t i = 0; i < ids0.size(); i++)
                        if (ids0[i] == here)
                            at = (int)i;
                } else {
                    return;
                }
            } else if (c == 'q' && !searching) {
                return;
            }
        }
    }

    // ---- THE INSERTION EFFECT (livetui.pick_efx) ----
    std::string efx_name(int msb, int lsb) const
    {
        if (!msb && !lsb)
            return "Thru";
        for (const auto &t : H.efx_types)
            if (t.msb == msb && t.lsb == lsb)
                return t.name;
        char b[32];
        snprintf(b, sizeof b, "type %02X %02X", msb, lsb);
        return b;
    }
    int efx_num(int msb, int lsb) const
    {
        for (const auto &t : H.efx_types)
            if (t.msb == msb && t.lsb == lsb)
                return t.num;
        return 0;
    }
    // the channels the part listens on (livetui.efx_channels)
    std::vector<int> efx_channels() const
    {
        std::vector<int> c;
        for (int ch = 0; ch < 16; ch++)
            if (H.channel < 0 || H.channel == ch)
                c.push_back(ch);
        return c;
    }
    bool efx_on(const EfxView &v) const
    {
        for (int ch : efx_channels())
            if (std::find(v.parts.begin(), v.parts.end(), ch) == v.parts.end())
                return false;
        return true;
    }
    // the raw value a parameter stands at: the one set, else the one in
    // effect, moved by its controller (gsefx.controlled) where it has one
    int efx_value(const EfxView &v, const Host::EfxParam &p) const
    {
        int x = p.n >= 1 && p.n <= 20 && v.p[p.n] >= 0 ? v.p[p.n] : p.fresh;
        if (!p.read || p.mark == '-' || (!v.ctl[0] && !v.ctl[2]))
            return x;
        int which = p.mark == '+' ? 0 : 2, src = v.ctl[which];
        if (!src)
            return x;
        double dep = std::max(-1.0, std::min(1.0, (v.ctl[which + 1] - 0x40) / 63.0));
        auto it = v.cv.find(src);
        double cv = it != v.cv.end() ? it->second : src == EFX_SRC_BEND ? 64 : 0;
        int lo = *std::min_element(p.vals.begin(), p.vals.end()), hi = *std::max_element(p.vals.begin(), p.vals.end());
        double y = std::max((double)lo, std::min((double)hi, x + (hi - lo) * (cv / 127.0) * dep));
        if ((int)p.vals.size() == hi - lo + 1)
            return (int)nearbyint(y);
        int best = p.vals[0];
        for (int r : p.vals)
            if (fabs(r - y) < fabs(best - y))
                best = r;
        return best;
    }
    static std::string efx_printed(const Host::EfxParam &p, int x)
    {
        size_t k = 0;
        for (size_t i = 0; i < p.vals.size(); i++)
            if (abs(p.vals[i] - x) < abs(p.vals[k] - x))
                k = i;
        return p.shown.empty() ? std::to_string(x) : p.shown[k];
    }
    static std::string src_label(int code)
    {
        return !code ? "off" : code <= 95 ? "CC" + std::to_string(code) : code == EFX_SRC_CAF ? "aftertouch" : "bend";
    }
    // a setting sent, then the state seen back (live's _efx_wait: the audio
    // thread applies it as hardware's message, the panel reads it after)
    void efx_send(char kind, int a, int b)
    {
        long rev = s.efx_rev;
        H.efx_send(efx_message(kind, a, b));
        auto t0 = std::chrono::steady_clock::now();
        while (std::chrono::steady_clock::now() - t0 < std::chrono::milliseconds(100)) {
            Snap n = H.take();
            s.efx = n.efx;
            s.efx_why = n.efx_why;
            s.efx_rev = n.efx_rev;
            if (s.efx_rev != rev)
                break;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }

    void pick_efx()
    {
        if (!H.efx_send || s.efx.empty()) {
            say("the export has no insertion effect");
            return;
        }
        int i = 0;
        while (true) {
            EfxView v(s.efx);
            const std::string name = efx_name(v.msb, v.lsb);
            const int num = efx_num(v.msb, v.lsb);
            const bool on = efx_on(v);
            std::vector<std::string> rows;
            std::vector<char> head;
            std::vector<std::array<int, 3>> what;           // (kind, a, b): 0 part, 1 type, 2 param, 3 ctl, 4 send
            char b[160];
            auto add = [&](const std::string &r, int k, int a = 0, int c = 0) {
                rows.push_back(r);
                head.push_back(k < 0);
                what.push_back({k, a, c});
            };
            add(std::string("part on the EFX (") + (H.channel < 0 ? "all channels" : "channel " + std::to_string(H.channel + 1))
                    + "):  " + (on ? "yes" : "no"), 0);
            if (num)
                snprintf(b, sizeof b, "type:  %02d %s", num, name.c_str());
            else
                snprintf(b, sizeof b, "type:  %s", name.c_str());
            add(b, 1);
            auto pit = H.efx_params.find(std::make_pair(v.msb, v.lsb));
            if (name != "Thru" && pit != H.efx_params.end()) {
                const auto &ps = pit->second;
                add("-- parameters", -1);
                for (size_t q = 0; q < ps.size(); q++) {
                    snprintf(b, sizeof b, "%-16.16s %s", ps[q].name.c_str(), efx_printed(ps[q], efx_value(v, ps[q])).c_str());
                    add(b, 2, (int)q);
                }
                add("-- its controllers (a knob the instrument does not use)", -1);
                for (int which = 1; which <= 2; which++) {
                    char mk = which == 1 ? '+' : '#';
                    std::string pname = "-";
                    for (const auto &p : ps)
                        if (p.mark == mk)
                            pname = p.name;
                    int src = v.ctl[which == 1 ? 0 : 2], dep = v.ctl[which == 1 ? 1 : 3];
                    std::string desc = src ? src_label(src) + ", " : "off";
                    if (src) {
                        snprintf(b, sizeof b, "%+d%%", (int)nearbyint(std::max(-1.0, std::min(1.0, (dep - 0x40) / 63.0)) * 100));
                        desc += b;
                    }
                    snprintf(b, sizeof b, "%c %-13.13s %s", mk, pname.c_str(), desc.c_str());
                    add(b, 3, which);
                }
                add("-- sends from the EFX", -1);
                static const char *SN[3] = {"to reverb", "to chorus", "to delay"};
                for (int q = 0; q < 3; q++) {
                    snprintf(b, sizeof b, "%-16s %d", SN[q], v.snd[q]);
                    add(b, 4, q);
                }
            }
            std::string title = "insertion effect";
            if (v.status == -3)
                title += "   (not native live: " + s.efx_why + ")";
            else if (name != "Thru" && v.status != 0)
                title += "   (not built live)";
            int got = menu(title, rows, i, head);
            if (got < 0)
                return;
            i = got;
            const auto &w = what[got];
            if (w[0] == 0) {
                for (int ch : efx_channels())
                    efx_send('c', ch, !on);
            } else if (w[0] == 1) {
                pick_efx_type(v);
            } else if (w[0] == 2) {
                const auto &p = pit->second[w[1]];
                edit_efx(p.name, p.vals, [&](int x) { return efx_printed(p, x); }, efx_value(v, p),
                         [&](int x) { efx_send('p', p.n, x); });
            } else if (w[0] == 3) {
                std::string pname = "-";
                for (const auto &p : pit->second)
                    if (p.mark == (w[1] == 1 ? '+' : '#'))
                        pname = p.name;
                pick_efx_ctl(v, w[1], pname);
            } else if (w[0] == 4) {
                static const char *SN[3] = {"to reverb", "to chorus", "to delay"};
                std::vector<int> all(128);
                for (int x = 0; x < 128; x++)
                    all[x] = x;
                edit_efx(SN[w[1]], all, [](int x) { return std::to_string(x); }, v.snd[w[1]],
                         [&](int x) { efx_send('s', EFX_SEND[w[1]], x); });
            }
        }
    }

    // the type, under Roland's families; "/" searches every type by name
    void pick_efx_type(const EfxView &v)
    {
        std::vector<int> ids{-1, 0};
        std::vector<std::string> rows{"── 00", "  00 Thru"};
        for (const auto &c : H.efx_cats) {
            ids.push_back(-1);
            rows.push_back("── " + c.name);
            for (size_t j = 0; j < H.efx_types.size(); j++) {
                const auto &t = H.efx_types[j];
                if (t.num < c.a || t.num > c.b)
                    continue;
                char b[120];
                snprintf(b, sizeof b, "%s%02d %s   (%s)", t.msb == v.msb && t.lsb == v.lsb ? "● " : "  ", t.num,
                         t.name.c_str(), c.name.c_str());
                ids.push_back(1 + (int)j);
                rows.push_back(b);
            }
        }
        int here = 0;
        for (size_t j = 0; j < H.efx_types.size(); j++)
            if (H.efx_types[j].msb == v.msb && H.efx_types[j].lsb == v.lsb)
                here = 1 + (int)j;
        pick_list("insertion effect type", ids, rows, here, [](int) { return true; }, [&](int id) {
            int msb = id ? H.efx_types[id - 1].msb : 0, lsb = id ? H.efx_types[id - 1].lsb : 0;
            if (msb != v.msb || lsb != v.lsb) {
                efx_send('t', msb, lsb);
                say("EFX: " + efx_name(msb, lsb));
            }
            return true;
        });
    }

    // an effect controller (livetui.pick_efx_ctl): what moves its parameter
    // -- learnt (move the knob, pedal or wheel), or picked -- and how far
    void pick_efx_ctl(const EfxView &v, int which, const std::string &pname)
    {
        const int sa = which == 1 ? EFX_CTL_SRC1 : EFX_CTL_SRC2, da = which == 1 ? EFX_CTL_DEP1 : EFX_CTL_DEP2;
        const int cur = v.ctl[which == 1 ? 0 : 2], dep = v.ctl[which == 1 ? 1 : 3];
        std::vector<std::string> opts{"learn: move a knob, pedal or wheel now", "off"};
        std::vector<int> codes{-1, 0};
        for (int c = 1; c <= 95; c++) {
            opts.push_back("CC" + std::to_string(c));
            codes.push_back(c);
        }
        opts.push_back("aftertouch");
        codes.push_back(EFX_SRC_CAF);
        opts.push_back("bend");
        codes.push_back(EFX_SRC_BEND);
        char b[64];
        snprintf(b, sizeof b, "depth: %+d%%", (int)nearbyint((dep - 64) / 63.0 * 100));
        opts.push_back(b);
        codes.push_back(-2);
        int start = 1;
        for (size_t j = 0; j < codes.size(); j++)
            if (codes[j] == cur)
                start = (int)j;
        int got = menu(pname + " moved by", opts, start);
        if (got < 0)
            return;
        int code = codes[got];
        if (code == -2) {
            std::vector<int> all(128);
            for (int x = 0; x < 128; x++)
                all[x] = x;
            edit_efx("depth", all, [](int x) {
                char t[16];
                snprintf(t, sizeof t, "%+d%%", (int)nearbyint((x - 64) / 63.0 * 100));
                return std::string(t);
            }, dep, [&](int x) { efx_send('s', da, x); });
            return;
        }
        if (code == -1) {                               // learn
            long long t0 = std::chrono::duration_cast<std::chrono::nanoseconds>(
                               std::chrono::steady_clock::now().time_since_epoch()).count();
            std::string m = "\x1b[H\x1b[2J " + C("accent") + "move the knob, pedal or wheel for " + pname + "\x1b[0m"
                            + C("dim") + "   (esc: back)\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            auto until = std::chrono::steady_clock::now() + std::chrono::seconds(8);
            while (code < 0 && std::chrono::steady_clock::now() < until) {
                auto lc = H.last_ctl ? H.last_ctl() : std::make_pair(0, 0LL);
                if (lc.first && lc.second > t0)
                    code = lc.first;
                else if (T.key(50) == 27)
                    return;
            }
            if (code < 0) {
                say("nothing moved");
                return;
            }
        }
        efx_send('s', sa, code);
        if (code && dep == 0x40)
            efx_send('s', da, 0x7F);                    // (a source with no depth does nothing: +100%)
        say(pname + " moved by " + src_label(code));
    }

    // one value (livetui.edit_efx): left/right (page up/down by ten), digits a
    // raw value; each move sent, so it is heard as it goes; Enter keeps it,
    // Esc puts back what it was
    void edit_efx(const std::string &nm, const std::vector<int> &vals, const std::function<std::string(int)> &show,
                  int v0, const std::function<void(int)> &send)
    {
        size_t j = 0;
        for (size_t i = 0; i < vals.size(); i++)
            if (abs(vals[i] - v0) < abs(vals[j] - v0))
                j = i;
        const size_t j0 = j;
        while (true) {
            char b[200];
            snprintf(b, sizeof b, " %s:  %s   (raw %d)", nm.c_str(), show(vals[j]).c_str(), vals[j]);
            std::string m = "\x1b[H\x1b[2J" + C("sel") + "\x1b[1m" + b + "\x1b[0m\r\n\r\n" + C("dim")
                            + "   ←→ -+ step  pgup pgdn ten  digits a raw value  enter keep  esc back\x1b[0m";
            fwrite(m.data(), 1, m.size(), stdout);
            fflush(stdout);
            int c = T.key(1000);
            size_t k = j;
            if (c == 1002 || c == 'l' || c == '+' || c == '=')
                k = std::min(vals.size() - 1, j + 1);
            else if (c == 1003 || c == 'h' || c == '-')
                k = j ? j - 1 : 0;
            else if (c == 1006)
                k = j >= 10 ? j - 10 : 0;
            else if (c == 1005)
                k = std::min(vals.size() - 1, j + 10);
            else if (c >= '0' && c <= '9') {
                std::string got;
                if (prompt(nm + " raw value = " + std::string(1, (char)c), got)) {
                    int x = atoi((std::string(1, (char)c) + got).c_str());
                    for (size_t i = 0; i < vals.size(); i++)
                        if (abs(vals[i] - x) < abs(vals[k] - x))
                            k = i;
                }
            } else if (c == 10 || c == 13) {
                return;
            } else if (c == 27) {
                if (j != j0)
                    send(vals[j0]);
                return;
            }
            if (k != j) {
                j = k;
                send(vals[j]);
            }
        }
    }

    void adjust(int delta, bool big)
    {
        if (pane != 0)
            return;
        int i = grow;
        if ((i == 6 && !H.has_gpu) || (i == 7 && !H.has_room) || (i == 8 && H.rooms.empty())) {
            say(i == 6 ? "gpu: not available (--gpu at start)" : i == 7 ? "room tail: the export has none"
                                                                       : "room: the export carries no rooms");
            return;
        }
        const double hi = i == 8 ? (double)H.rooms.size() - 1.0 : GLOBAL_RANGE[i][1];
        double v = H.g[i] + delta * GLOBAL_RANGE[i][2] * (big && i != 8 ? 5 : 1);
        v = std::max(GLOBAL_RANGE[i][0], std::min(hi, v));
        if (i == 8 && v != H.g[i])
            say("room: " + H.rooms[(int)v] + " -- every patch built again in it, the tail crossfaded");
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
                        grow = std::min(NGLOBALS - 1, grow + 1);
                    else
                        crow = std::min(std::max(0, (int)H.routes.size() - 1), crow + 1);
                } else if (c == 1003 || c == 'h' || c == '-' || c == '_') {
                    adjust(-1, c == '_');
                } else if (c == 1002 || c == 'l' || c == '=' || c == '+') {
                    adjust(1, c == '+');
                } else if (!H.stop_names.empty() && c == STOP_PREFIX) {
                    stop_bank = !stop_bank;
                    say(stop_bank ? "stops: rows 3 and 4 -- press a stop key" : "stops: rows 1 and 2");
                } else if (!H.stop_names.empty() && c > 0 && c < 128
                           && (strchr(STOP_DIGITS, c) || strchr(STOP_SHIFTED, c))) {
                    int row = strchr(STOP_DIGITS, c) ? 0 : 1;
                    int i = (int)((row ? strchr(STOP_SHIFTED, c) - STOP_SHIFTED : strchr(STOP_DIGITS, c) - STOP_DIGITS));
                    if (stop_bank) {
                        row += 2;
                        stop_bank = false;
                    }
                    if (row < (int)H.stop_rows.size() && i < (int)H.stop_rows[row].size()) {
                        int ri = H.stop_rows[row][i];
                        std::vector<char> dr = H.drawn();
                        bool was = ri < (int)dr.size() && dr[ri];
                        H.toggle_stop(ri);
                        say(std::string(was ? "in: " : "drawn: ") + H.stop_names[ri]);
                    }
                } else if (c == 'p' && H.pick) {
                    pick_patch();
                } else if (c == 'x' || c == 'X') {
                    pick_efx();
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
                if (H.refresh) {
                    std::string m = H.refresh();
                    if (!m.empty())
                        say(m);
                }
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
