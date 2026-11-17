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
#include <string>
#include <vector>

#include "imgui.h"
#include "imgui_internal.h"

#include "../native/host.h"
#include "../native/session.h"
#include "kit.h"

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
    ImFont *font = nullptr, *bold = nullptr;
    std::string ui_dir;                 // (ui/: the fonts, about.json)
    float k = 1.0f;                     // design units (1920x1080) to pixels
    ImVec2 org{0, 0};
    J parts, meters, build;
    int row = 0;
    int field = 0;                      // (the display's field the jog dial turns)
    std::string card = "parts", msg;
    std::string last_meters;
    bool quit = false;
    bool animate = false;               // (a card asks for another frame: a blink, a send still due)
    double quit_armed = -10.0;          // (QUIT's first tap: a second within 3 s quits)
    Kit K;
    Dial jog;
    // AN EDIT HELD a moment over what the engine pushes (the web's keep/overlay):
    // "row:field" -> (value, until)
    std::map<std::string, std::pair<double, double>> hold;
};

// ---- THE ENGINE's CALLS (uiapi's): a request, its answer
inline J call(App &a, const std::string &req)
{
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
inline float px(const App &a, float size)           // (code7's sizes: whole multiples of its 7 pixels)
{
    const float p = size * a.k;
    return std::max(7.0f, 7.0f * std::floor(p / 7.0f + 0.5f));
}
inline ImDrawList *dl() { return ImGui::GetWindowDrawList(); }
inline void text(App &a, ImFont *f, float size, float x, float y, ImU32 col, const std::string &s)
{
    dl()->AddText(f, px(a, size), P(a, x, y), col, s.c_str());
}
inline float text_w(App &a, ImFont *f, float size, const std::string &s)
{
    return f->CalcTextSizeA(px(a, size), FLT_MAX, 0.0f, s.c_str()).x / a.k;
}
inline void text_c(App &a, ImFont *f, float size, float cx, float y, ImU32 col, const std::string &s)
{
    text(a, f, size, cx - text_w(a, f, size, s) / 2, y, col, s);
}
// (a text cut to a width, with an ellipsis)
inline std::string fit(App &a, ImFont *f, float size, const std::string &s, float w)
{
    if (text_w(a, f, size, s) <= w)
        return s;
    std::string t = s;
    while (!t.empty() && text_w(a, f, size, t + "\xe2\x80\xa6") > w) {
        t.pop_back();
        while (!t.empty() && ((unsigned char)t.back() & 0xC0) == 0x80)     // (whole UTF-8 characters)
            t.pop_back();
    }
    return t + "\xe2\x80\xa6";
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
    if (w <= 0 || text_w(a, f, size, s) <= w || s.find(' ') == std::string::npos)
        return {s};
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

// A BUTTON (the web's .hb): acts on release over it, as the touch kit's
inline bool button(App &a, const char *id, float x, float y, float w, float h, const std::string &label, bool on = false,
                   bool enabled = true, float size = 14)
{
    ImGui::SetCursorScreenPos(P(a, x, y));
    ImGui::PushID(id);
    const bool hit = ImGui::InvisibleButton("b", ImVec2(w * a.k, h * a.k)) && enabled;
    const bool held = ImGui::IsItemActive();
    ImGui::PopID();
    rect(a, x, y, w, h, on ? LCD : held ? PANEL_HI : BTN, 8.0f);
    frame(a, x, y, w, h, EDGE, 8.0f, 1.0f);
    text_c(a, a.bold, size, x + w / 2, y + (h - size) / 2, on ? PANEL : enabled ? SILK : SILK_DIM, label);
    return hit;
}

// ---- the formats (ui/app.js's)
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
