// THE NATIVE INTERFACE's STATE AND ITS DRAWING (nui.cpp's): the engine's
// state as the pushes bring it, the calls that change it, and the
// primitives every card draws with -- in the 1920x1080 design's units,
// scaled to the window (App::k), code7 at whole multiples of 7 pixels.
#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "imgui.h"
#include "imgui_internal.h"

#include "../native/host.h"
#include "../native/session.h"
#include "kit.h"
#include "shape.h"
#include "i18n.h"

namespace nui {

using J = sess::J;

// THE FRONT PANEL's COLOURS (ui/style.css's tokens)
static const ImU32 PANEL = IM_COL32(0x23, 0x26, 0x2a, 255), PANEL_HI = IM_COL32(0x2e, 0x32, 0x37, 255),
                   EDGE = IM_COL32(0x12, 0x14, 0x17, 255), SILK = IM_COL32(0xc9, 0xcd, 0xc8, 255),
                   SILK_DIM = IM_COL32(0x8a, 0x91, 0x8b, 255), LCD = IM_COL32(0xf0, 0xb1, 0x3a, 255),
                   LCD_BG = IM_COL32(0x2a, 0x1d, 0x06, 255), LCD_DIM = IM_COL32(0x6b, 0x4c, 0x14, 255),
                   LCD_OFF = IM_COL32(0x3a, 0x29, 0x0b, 255), OWN = IM_COL32(0xf0, 0x8a, 0x3c, 255),
                   BAD = IM_COL32(0xe0, 0x53, 0x3c, 255), PAGE = IM_COL32(0x1b, 0x1d, 0x20, 255),
                   KEY_W = IM_COL32(0xd8, 0xda, 0xd4, 255), KEY_B = IM_COL32(0x1a, 0x1c, 0x1f, 255),
                   CAP = IM_COL32(0x3a, 0x3f, 0x45, 255), BTN = IM_COL32(0x26, 0x2a, 0x2e, 255);

struct App {
    nv_host *h = nullptr;
    nv_ui_watch *w = nullptr;
    // THE SCREEN's USABLE RECT, in points (the window's safe area -- clear of
    // a screen's rounded corners and its home indicator, with a margin on
    // iOS): the layout fits here; w 0 the whole window
    float safe_x = 0, safe_y = 0, safe_w = 0, safe_h = 0;
    ImFont *font = nullptr, *bold = nullptr, *lcd = nullptr;     // (lcd: code7 dotted, the display's)
    std::string ui_dir;                 // (ui/: the fonts, about.json)
    // THE FINGERS ON THE GLASS, each by SDL's id: where it is, in window points (the Keys card plays one key a
    // finger; touch_seen once any has touched -- then the mouse SDL makes of a touch is not played as well)
    std::map<unsigned long long, ImVec2> touches;
    bool touch_seen = false;
    std::string lang_pref = "auto";     // (the language asked for: a code, or "auto" -- the system's; i18n().code the one drawn)
    float k = 1.0f;                     // design units to pixels
    ImVec2 org{0, 0};
    // THE LAYOUT: the laptop's (a 1920x1080 canvas) or the iPad's (tab: 1133x744
    // points, its text half the design sizes -- 2x, 3x code7 on its 2x screen)
    bool tab = false;
    // (the PHONE's: a landscape phone's safe area, 832x419 points on a 16 Pro Max --
    //  tab set too (its sizes, the iPad's), its own panel and cards; the cards' menu open)
    bool ph = false, cards_open = false;
    // (a phone card drawn at the iPad's height, scrolled under the panel: its foot the iPad mini's)
    bool vcard = false;
    // (its scroll's hand-offs this frame: what a list or the pad grid inside it could not take
    //  (vcard_push, card units, + down), and a button's press turned into the card's drag)
    float vcard_push = 0;
    bool vcard_grab = false;
    float W = 1920, H = 1080, ts = 1.0f;
    float lh(float size) const;         // (a line of text at size: its height in design units)
    J parts, meters, build;
    int row = 0;
    int field = 0;                      // (the display's field the jog dial turns)
    std::string card = "parts", msg;
    std::string help;                   // (the help viewer's topic while it is open)
    std::string last_meters;
    // (the display's warning of a note played late or by a stand-in: the
    // counts seen, the line and until when it shows)
    long seen_late = -1, seen_stand = -1, seen_lost = -1;
    std::string warn;
    bool warn_red = false;
    double warn_until = 0.0;
    float lab_x0 = 0, lab_x1 = 0;       // (the panel centred labels stay inside, while a card draws one; 0, 0 none)
    bool quit = false;
    bool animate = false;               // (a card asks for another frame: a blink, a send still due)
    double quit_armed = -10.0;          // (QUIT's first tap: a second within 3 s quits)
    Kit K;
    Dial jog;
    // A CONTROL's SHEET (a long-press): its value typed; SET leaves the value
    // for the control to take on its next frame (sheet_set), as a drag would
    struct Sheet {
        bool open = false, can_reset = true;
        std::string key, title, now, label, hint, typed;
        double lo = 0, hi = 1;
        int digits = 3;
    } sheet;
    std::map<std::string, double> sheet_set;
    std::set<std::string> sheet_reset;
    // AN EDIT HELD a moment over what the engine pushes (the web's keep/overlay):
    // "row:field" -> (value, until)
    std::map<std::string, std::pair<double, double>> hold;
};

// ---- THE ENGINE's CALLS (uiapi's): a request, its answer
inline J call(App &a, const std::string &req)
{
    static const char *log = getenv("NUI_LOG_CALLS");     // (the tests': each call holding one of its words -- "a,b" -- to stderr)
    if (log && *log) {
        const std::string l = log;
        for (size_t i = 0, j; i <= l.size(); i = j + 1) {
            j = l.find(',', i);
            if (j == std::string::npos)
                j = l.size();
            if (j > i && req.find(l.substr(i, j - i)) != std::string::npos) {
                fprintf(stderr, "nui: call %s\n", req.c_str());
                break;
            }
        }
    }
    J r;
    if (char *s = nv_ui_call(a.h, a.w, req.c_str())) {
        sess::parse(s, r);
        nv_ui_free(s);
    }
    return r;
}
inline std::string jnum(double v)
{
    char b[48];
    snprintf(b, sizeof b, "%.10g", v);
    return b;
}
inline std::string jstr(const std::string &s)       // (a string as JSON)
{
    return sess::dump(sess::str(s));
}
// (a call's answer may carry the parts: taken)
inline void take_parts(App &a, const J &r)
{
    if (const J *ps = r.get("parts"); ps && ps->is(J::ARR))
        a.parts = *ps;
}

inline const J *part(const App &a, int r)
{
    return a.parts.is(J::ARR) && r >= 0 && r < (int)a.parts.a.size() ? &a.parts.a[(size_t)r] : nullptr;
}
inline int nparts(const App &a) { return a.parts.is(J::ARR) ? (int)a.parts.a.size() : 0; }
inline double num(const J *o, const char *k, double d = 0.0)
{
    const J *x = o ? o->get(k) : nullptr;
    return x ? x->d(d) : d;
}
inline bool flag(const J *o, const char *k)
{
    const J *x = o ? o->get(k) : nullptr;
    return x && x->d(0.0) != 0.0;
}
inline std::string str(const J *o, const char *k)
{
    const J *x = o ? o->get(k) : nullptr;
    return x && x->is(J::STR) ? x->s : std::string();
}

// A PART's VALUE as shown: the finger's, while held; else the engine's
inline double pv(App &a, int r, const char *k, double d = 0.0)
{
    auto it = a.hold.find(std::to_string(r) + ":" + k);
    if (it != a.hold.end()) {
        if (ImGui::GetTime() < it->second.second)
            return it->second.first;
        a.hold.erase(it);
    }
    return num(part(a, r), k, d);
}
inline void keep(App &a, int r, const char *k, double v, double secs = 0.6)
{
    a.hold[std::to_string(r) + ":" + k] = {v, ImGui::GetTime() + secs};
}

// a part's edit (uiapi's part_set), held
inline void part_set(App &a, int r, const char *k, double v)
{
    keep(a, r, k, v);
    call(a, "{\"call\":\"part_set\",\"row\":" + std::to_string(r) + ",\"" + k + "\":" + jnum(v) + "}");
}
// ...a controller on its channel (uiapi's part_cc: pan, the sends), held
inline void part_cc(App &a, int r, int cc, const char *k, int v)
{
    keep(a, r, k, v);
    call(a, "{\"call\":\"part_cc\",\"row\":" + std::to_string(r) + ",\"cc\":" + std::to_string(cc) + ",\"v\":" +
                std::to_string(v) + "}");
}
inline void select(App &a, int r)
{
    if (r < 0 || r >= nparts(a))
        return;
    a.row = r;
    call(a, "{\"call\":\"select\",\"row\":" + std::to_string(r) + ",\"layer\":0}");
}

// ---- THE DRAWING, in design units
inline ImVec2 P(const App &a, float x, float y)
{
    return ImVec2(std::floor(a.org.x + x * a.k), std::floor(a.org.y + y * a.k));
}
// THE CARD's FOOT (its last row's bottom): the iPad layout's follows the
// screen's height -- 728 on an iPad mini's 744, lower on a squarer iPad's
// (the design 1133 wide, as tall as the screen's shape makes it) -- the
// laptop's 1056
// A CARD's PAGE KEYS (the iPad's and the phone's): the iPad's from x0, w wide; the phone's
// at the card's right, narrower (its heading's notes give way to them)
inline float page_kx(const App &a, int n, int pg, float x0, float w = 190)
{
    return a.ph ? 818 - n * (a.ph && n > 2 ? 130 : 160) + 4 + pg * (n > 2 ? 130 : 160) : x0 + pg * (w + 6);
}
inline float page_kw(const App &a, int n, float w = 190) { return a.ph ? (n > 2 ? 126 : 156) : w; }
inline float card_y1(const App &a) { return a.vcard ? 728.0f : a.ph ? a.H - 12.0f : a.tab ? a.H - 16.0f : a.H - 24.0f; }
inline float px(const App &a, float size)           // (code7's sizes: whole multiples of its 7 device pixels)
{
    // (in points for ImGui; snapped where the screen's pixels are: 7, 14, 21 ... device px,
    // so 3.5, 7, 10.5 ... points on a 2x Retina screen)
    const float fb = std::max(1.0f, ImGui::GetIO().DisplayFramebufferScale.x);
    const float p = size * a.ts * a.k * fb;
    // (down, never up: a size between two -- the iPad's 21 px drawn at half, 10.5 -- takes the
    //  smaller, so it stays inside the box laid out for it rather than spilling over)
    return std::max(7.0f, 7.0f * std::floor(p / 7.0f + 0.01f)) / fb;
}
inline ImDrawList *dl() { return ImGui::GetWindowDrawList(); }
inline float App::lh(float size) const { return px(*this, size) / k; }
// (drawn and measured SHAPED, shape.h: composed, joined, in its visual order)
inline float text_w(App &a, ImFont *f, float size, const std::string &s)
{
    return f->CalcTextSizeA(px(a, size), FLT_MAX, 0.0f, shape(s).c_str()).x / a.k;
}

// ---- THE TEXT AUDIT (NUI_TEXT_AUDIT=FILE, for the tour's checks): each
// frame's texts, the boxes they belong in (cards' plates and pockets,
// buttons) and every text fit() cut; at a scripted shot, written out as
// CUT (an ellipsis), OVERLAP (two texts on each other) and SPILL (a text
// past the edge of the box it is centred in)
struct Audit {
    struct Box {
        float x0, y0, x1, y1;
        std::string s;
    };
    bool on = false;
    std::vector<Box> texts, boxes;
    std::set<std::string> cuts;
};
inline Audit &audit()
{
    static Audit A;
    static bool init = false;
    if (!init) {
        init = true;
        A.on = getenv("NUI_TEXT_AUDIT") != nullptr;
    }
    return A;
}
inline void audit_box(const App &a, float x, float y, float w, float h)
{
    Audit &A = audit();
    if (A.on)
        A.boxes.push_back({x, y, x + w, y + h, ""});
}
inline void audit_text(App &a, ImFont *f, float size, float x, float y, const std::string &s)
{
    Audit &A = audit();
    if (!A.on || s.empty())
        return;
    const float w = text_w(a, f, size, s), h = a.lh(size);
    // (only what shows: a text the clip hides, or cuts at a scrolling list's edge, is not a fault)
    const ImVec2 c0 = dl()->GetClipRectMin(), c1 = dl()->GetClipRectMax();
    const ImVec2 p0 = P(a, x, y), p1 = P(a, x + w, y + h);
    if (p0.x < c0.x - 1 || p0.y < c0.y - 1 || p1.x > c1.x + 1 || p1.y > c1.y + 1)
        return;
    A.texts.push_back({x, y, x + w, y + h, s});
}
inline void text(App &a, ImFont *f, float size, float x, float y, ImU32 col, const std::string &s)
{
    audit_text(a, f, size, x, y, s);
    dl()->AddText(f, px(a, size), P(a, x, y), col, shape(s).c_str());
}
// (a centred text kept inside the panel being drawn, where a card says which: App::lab_x0..lab_x1)
inline void text_c(App &a, ImFont *f, float size, float cx, float y, ImU32 col, const std::string &s)
{
    const float w = text_w(a, f, size, s);
    float x = cx - w / 2;
    if (a.lab_x1 > a.lab_x0) {
        x = std::min(x, a.lab_x1 - w);
        x = std::max(x, a.lab_x0);
    }
    text(a, f, size, x, y, col, s);
}
// (a text cut to a width, with an ellipsis)
inline std::string fit(App &a, ImFont *f, float size, const std::string &s, float w)
{
    if (text_w(a, f, size, s) <= w)
        return s;
    if (audit().on)
        audit().cuts.insert(s);
    std::string t = s;
    while (!t.empty() && text_w(a, f, size, t + "\xe2\x80\xa6") > w) {
        t.pop_back();
        while (!t.empty() && ((unsigned char)t.back() & 0xC0) == 0x80)     // (whole UTF-8 characters)
            t.pop_back();
    }
    return t + "\xe2\x80\xa6";
}
// WORDS WRAPPED to a width (design px): its lines
inline std::vector<std::string> wrap(App &a, ImFont *f, float size, const std::string &s, float w)
{
    std::vector<std::string> lines;
    std::string line, word;
    auto flush_word = [&]() {
        if (word.empty())
            return;
        // (a word wider than the line by itself: broken after a hyphen or slash, else where it fills the line)
        while (text_w(a, f, size, word) > w && word.size() > 1) {
            size_t cut = word.find_first_of("-/");
            if (cut == std::string::npos || text_w(a, f, size, word.substr(0, cut + 1)) > w) {
                cut = 1;
                while (cut + 1 < word.size() && text_w(a, f, size, word.substr(0, cut + 1) + "-") <= w)
                    cut++;
                if (!line.empty())
                    lines.push_back(line);
                lines.push_back(word.substr(0, cut) + "-");
                line.clear();
                word = word.substr(cut);
                continue;
            }
            if (!line.empty())
                lines.push_back(line);
            lines.push_back(word.substr(0, cut + 1));
            line.clear();
            word = word.substr(cut + 1);
        }
        const std::string t = line.empty() ? word : line + " " + word;
        if (!line.empty() && text_w(a, f, size, t) > w) {
            lines.push_back(line);
            line = word;
        } else
            line = t;
        word.clear();
    };
    for (char c : s) {
        if (c == ' ' || c == '\n') {
            flush_word();
            if (c == '\n') {
                lines.push_back(line);
                line.clear();
            }
        } else
            word += c;
    }
    flush_word();
    if (!line.empty())
        lines.push_back(line);
    return lines;
}

// WORDS WRAPPED to at most n lines: more than n is a cut, which the audit records
inline std::vector<std::string> wrap_max(App &a, ImFont *f, float size, const std::string &s, float w, size_t n)
{
    auto ls = wrap(a, f, size, s, w);
    if (ls.size() > n) {
        ls.resize(n);
        ls.back() = fit(a, f, size, ls.back() + " " + s, w);    // (fit() records it)
    }
    return ls;
}
inline void rect(App &a, float x, float y, float w, float h, ImU32 col, float r = 6.0f)
{
    dl()->AddRectFilled(P(a, x, y), P(a, x + w, y + h), col, r * a.k);
}
inline void frame(App &a, float x, float y, float w, float h, ImU32 col, float r = 6.0f, float t = 1.5f)
{
    dl()->AddRect(P(a, x, y), P(a, x + w, y + h), col, r * a.k, 0, t * a.k);
}

// A LABEL's LINES: wrapped at its spaces where wider than w (at most two)
inline std::vector<std::string> label_lines(App &a, ImFont *f, float size, const std::string &s, float w)
{
    if (w <= 0 || text_w(a, f, size, s) <= w)
        return {s};
    if (s.find(' ') == std::string::npos) {     // (one word: split after a hyphen or slash, else whole -- kept in its panel)
        const size_t at = s.find_first_of("-/");
        if (at == std::string::npos || at + 1 >= s.size())
            return {s};
        return {s.substr(0, at + 1), s.substr(at + 1)};
    }
    // (the split nearest the middle that fits, else the middle's)
    size_t best = std::string::npos;
    float bestd = 1e9f;
    for (size_t i = 0; i < s.size(); i++)
        if (s[i] == ' ') {
            const float d = std::fabs((float)i - s.size() / 2.0f);
            if (d < bestd) {
                bestd = d;
                best = i;
            }
        }
    return {s.substr(0, best), s.substr(best + 1)};
}
inline void label_c(App &a, ImFont *f, float size, float cx, float y, ImU32 col, const std::string &s, float w)
{
    const auto ls = label_lines(a, f, size, s, w);
    for (size_t i = 0; i < ls.size(); i++)
        text_c(a, f, size, cx, y + i * (size + 2), col, ls[i]);
}


// THE LANGUAGE drawn: the one asked for (a.lang_pref), or for "auto" the
// system's first that has a table (lang_system(), nui.cpp's: SDL's preferred
// locales), else English
std::string lang_system();
inline void lang_apply(App &a)
{
    std::string c = a.lang_pref == "auto" ? lang_system() : a.lang_pref;
    if (!lang_known(c) || !i18n_load(a.ui_dir, c))
        i18n_load(a.ui_dir, "en");
}
// (a press that has become a drag along the screen -- a scroll, not a tap: a finger's
//  wobble stays a tap; vertical only, so a knob's turn or a slide across is not one)
inline bool drag_is_scroll(const App &a)
{
    const ImVec2 d = ImGui::GetMouseDragDelta(0, 0.0f);
    return std::fabs(d.y) / a.k > 12 && std::fabs(d.y) > 1.5f * std::fabs(d.x);
}

// (a tap's item on a scrolled card -- the phone's -- dragged: the drag is the card's
//  scroll, the item let go unpressed; called just after the item)
inline void tap_yields(App &a)
{
    if (a.vcard && ImGui::IsItemActive() && drag_is_scroll(a)) {
        ImGui::ClearActiveID();
        a.vcard_grab = true;
    }
}

}  // namespace nui
// (the hardware's look: after the primitives above, which it draws with; every
// file includes app.h first, so this is where look.h is first read)
#include "look.h"
namespace nui {

// A BUTTON (the web's .hb): a key cap, lit when on; acts on release over it, as the touch kit's
inline bool button(App &a, const char *id, float x, float y, float w, float h, const std::string &label, bool on = false,
                   bool enabled = true, float size = 14)
{
    ImGui::SetCursorScreenPos(P(a, x, y));
    ImGui::PushID(id);
    const bool hit = ImGui::InvisibleButton("b", ImVec2(w * a.k, h * a.k)) && enabled;
    tap_yields(a);
    const bool held = ImGui::IsItemActive();
    ImGui::PopID();
    const bool press = held && enabled;
    audit_box(a, x, y, w, h);
    if (on)
        look::lit_cap(a, x, y, w, h, press);
    else
        look::key_cap(a, x, y, w, h, press, enabled);
    // (a label wider than its cap -- a language's longer word -- a size smaller, never under 14)
    while (size > 14 && text_w(a, a.bold, size, label) > w - 8 && px(a, size - 7) < px(a, size))
        size -= 7;
    const float ty = y + (press ? look::cap_sink(h) : 0.0f) + (h - a.lh(size)) / 2 - 1;
    text_c(a, a.bold, size, x + w / 2, ty, on ? IM_COL32(0x26, 0x18, 0x02, 255) : enabled ? SILK : SILK_DIM, label);
    return hit;
}

// a control's sheet opened: its value in its own units, lo..hi
inline void open_sheet(App &a, const std::string &key, const std::string &title, const std::string &now, double value,
                       double lo, double hi, int digits, const std::string &label, const std::string &hint, bool can_reset = true)
{
    App::Sheet &s = a.sheet;
    s.open = true;
    s.key = key;
    s.title = title;
    s.now = now;
    s.lo = lo;
    s.hi = hi;
    s.digits = digits;
    s.label = label;
    s.hint = hint;
    s.can_reset = can_reset;
    char b[48];
    snprintf(b, sizeof b, "%.*f", digits, value);
    s.typed = b;
}
// ...and what it left for the control: true (v set) if SET, flags K_RESET if BACK
inline int take_sheet(App &a, const std::string &key, double &v)
{
    int f = 0;
    if (auto it = a.sheet_set.find(key); it != a.sheet_set.end()) {
        v = it->second;
        a.sheet_set.erase(it);
        f |= K_CHANGED;
    }
    if (a.sheet_reset.erase(key))
        f |= K_RESET;
    return f;
}

// A HEADING (a card's name, a region's) and its ? opening the help at key:
// where the words after it may start
inline float heading(App &a, float x, float y, const std::string &t, const std::string &key)
{
    text(a, a.bold, 14, x, y, SILK, t);
    const float qx = x + text_w(a, a.bold, 14, t) + 8, r = 10;
    ImGui::SetCursorScreenPos(P(a, qx - 6, y - 8));
    ImGui::PushID(("q" + key).c_str());
    if (ImGui::InvisibleButton("q", ImVec2((2 * r + 12) * a.k, (2 * r + 12) * a.k)))
        a.help = "@" + key;             // (opened by the frame: help_open)
    tap_yields(a);
    const bool held = ImGui::IsItemActive();
    ImGui::PopID();
    dl()->AddCircle(P(a, qx + r, y + 7), r * a.k, held ? LCD : SILK_DIM, 20, 1.5f * a.k);
    text_c(a, a.bold, 14, qx + r, y, held ? LCD : SILK_DIM, "?");
    return qx + 2 * r + 12;
}

// ---- the formats (the retired web interface's)
inline std::string pad2(int n)
{
    char b[16];
    snprintf(b, sizeof b, "%02d", n);
    return b;
}
inline std::string db_text(double v)
{
    char b[32];
    snprintf(b, sizeof b, "%s%.1f", v > 0 ? "+" : "", v);
    return b;
}
inline std::string pan_text(int v) { return v < 64 ? "L" + std::to_string(64 - v) : v > 64 ? "R" + std::to_string(v - 64) : "C"; }
inline std::string signed_text(int v) { return (v > 0 ? "+" : "") + std::to_string(v); }
inline std::string note_name(int n)
{
    static const char *N[12] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
    return std::string(N[((n % 12) + 12) % 12]) + std::to_string(n / 12 - 1);
}
inline bool is_black(int k)
{
    const int c = k % 12;
    return c == 1 || c == 3 || c == 6 || c == 8 || c == 10;
}

}  // namespace nui
