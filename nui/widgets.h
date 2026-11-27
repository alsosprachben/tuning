// THE CONTROLS DRAWN (kit.js's knob, fader and display field): the gesture
// (kit.h) over each, its look the web kit's -- a 270-degree ring that fills
// (from the top when centred), a fader's slot and cap, an LCD field.
#pragma once
#include <set>

#include <functional>

#include "app.h"

namespace nui {

// (the value over the finger while it drags: the web's bubble)
inline void bubble(App &a, const std::string &s)
{
    if (!a.K.moved || a.K.active == 0)
        return;
    const ImVec2 m = a.K.bubble_at;
    std::string t = shape(s + (a.K.fine() ? "  \xc2\xb7 " + std::string(T("fine")) : ""));
    const float sz = px(a, 21), w = a.font->CalcTextSizeA(sz, FLT_MAX, 0, t.c_str()).x + 24 * a.k,
                h = sz + 16 * a.k;
    const ImVec2 p0(std::floor(m.x - w / 2), std::floor(m.y - 90 * a.k - h));
    ImDrawList *fg = ImGui::GetForegroundDrawList();
    fg->AddCallback(ImGui::GetPlatformIO().DrawCallback_SetSamplerNearest, nullptr);
    fg->AddRectFilled(p0, ImVec2(p0.x + w, p0.y + h), LCD_BG, 6 * a.k);
    fg->AddRect(p0, ImVec2(p0.x + w, p0.y + h), LCD, 6 * a.k, 0, 1.5f * a.k);
    fg->AddText(a.font, sz, ImVec2(p0.x + 12 * a.k, std::floor(p0.y + 8 * a.k)), LCD, t.c_str());
}

// A KNOB: v01 its position (0..1); size its diameter (design px). Returns
// the gesture's flags; v01 moved by the finger
// (a knob, fader or field drawn in a scrolling phone body: never meant to be -- said once, counted)
inline void no_drag_in_body(App &a, const char *id)
{
    if (!a.vbody)
        return;
    static std::set<std::string> said;
    a.drag_in_body++;
    if (said.insert(id).second)
        fprintf(stderr, "nui: DRAG CONTROL IN A SCROLLING BODY: %s\n", id);
}

inline int knob(App &a, const char *id, float cx, float cy, float size, float &v01, const std::string &label,
                const std::string &value, bool centred = false, const std::vector<float> &detents = {}, float label_w = 0,
                bool own = false, bool sheet = true)
{
    no_drag_in_body(a, id);
    const float r = size / 2;
    Range g;
    g.lo = 0;
    g.hi = 1;
    g.detents = detents;
    int f = gesture(a.K, id, P(a, cx - r, cy - r), P(a, cx + r, cy + r + 34), v01, g);
    if (sheet && (f & K_LONG))
        open_sheet(a, id, label, value, v01, 0, 1, 3, T("Position"), centred ? T("The knob's position, 0 to 1 (0.5 the centre).") : T("The knob's position, 0 to 1."));
    {
        double t = v01;
        f |= take_sheet(a, id, t);
        v01 = (float)t;
    }
    const float A0 = -135, A1 = 135, deg = 3.14159265f / 180.0f;
    auto pt = [&](float rr, float d) {
        const float t = (d - 90) * deg;
        return ImVec2(a.org.x + (cx + rr * std::cos(t)) * a.k, a.org.y + (cy + rr * std::sin(t)) * a.k);
    };
    ImDrawList *d = dl();
    const int seg = 48;
    // the track, the fill, the ticks
    d->PathClear();
    for (int i = 0; i <= seg; i++)
        d->PathLineTo(pt(r * 0.86f, A0 + (A1 - A0) * i / seg));
    d->PathStroke(IM_COL32(0x15, 0x17, 0x1a, 255), 0, 4.0f * a.k);
    const float av = A0 + (A1 - A0) * v01, from = centred ? 0 : A0;
    if (std::fabs(av - from) > 0.5f) {
        d->PathClear();
        const float lo = std::min(av, from), hi = std::max(av, from);
        const int n = std::max(2, (int)(seg * (hi - lo) / (A1 - A0)));
        for (int i = 0; i <= n; i++)
            d->PathLineTo(pt(r * 0.86f, lo + (hi - lo) * i / n));
        d->PathStroke(look::alpha(f & K_ACTIVE ? OWN : LCD, 0.22f), 0, 8.0f * a.k);      // (its glow)
        for (int i = 0; i <= n; i++)
            d->PathLineTo(pt(r * 0.86f, lo + (hi - lo) * i / n));
        d->PathStroke(f & K_ACTIVE ? OWN : LCD, 0, 4.0f * a.k);
    }
    for (float t : detents)
        d->AddLine(pt(r * 0.95f, A0 + (A1 - A0) * t), pt(r * 1.02f, A0 + (A1 - A0) * t), SILK_DIM, 1.5f * a.k);
    // the cap and its pointer
    look::knob_cap(a, cx, cy, r * 0.64f, av);
    const auto ls = label.empty() ? std::vector<std::string>{} : label_lines(a, a.bold, 14, label, label_w);
    for (size_t i = 0; i < ls.size(); i++)
        text_c(a, a.bold, 14, cx, cy + r + 4 + i * (a.lh(14) + 2), SILK_DIM, ls[i]);
    text_c(a, a.font, 14, cx, cy + r + 4 + ls.size() * (a.lh(14) + 2), (f & K_ACTIVE) || own ? OWN : LCD, value);
    if (f & K_ACTIVE)
        bubble(a, label + " " + value);
    return f;
}

// A FADER: v in [lo, hi]; its slot from y to y + h (design px)
inline int fader(App &a, const char *id, float cx, float y, float h, float &v, float lo, float hi, float step,
                 const std::vector<float> &detents, const std::string &label, const std::string &value)
{
    no_drag_in_body(a, id);
    Range g;
    g.lo = lo;
    g.hi = hi;
    g.step = step;
    g.travel = h * 1.2f;
    g.detents = detents;
    int f = gesture(a.K, id, P(a, cx - 30, y), P(a, cx + 30, y + h), v, g, 1);
    if (f & K_LONG)
        open_sheet(a, id, label, value, v, lo, hi, step >= 1 ? 0 : step >= 0.1f ? 1 : 2, T("Value"), "");
    {
        double t = v;
        f |= take_sheet(a, id, t);
        v = std::max(lo, std::min(hi, (float)t));
    }
    for (float t : detents) {           // (the detents' marks, printed beside the slot)
        const float ty = y + h - (t - lo) / (hi - lo) * h;
        rect(a, cx - 16, ty - 1, 32, 2, SILK_DIM, 0);
    }
    look::fader_slot(a, cx, y, h);
    const float cy = y + h - (v - lo) / (hi - lo) * h;
    look::fader_cap(a, cx, cy, f & K_ACTIVE, f & K_ACTIVE ? OWN : LCD);
    // (below the cap's reach: at the bottom it hangs 14 past the slot)
    // (its label, then its value under it -- as every knob's)
    text_c(a, a.bold, 14, cx, y + h + 17, SILK_DIM, label);
    text_c(a, a.font, 14, cx, y + h + 19 + a.lh(14), f & K_ACTIVE ? OWN : LCD, value);
    if (f & K_ACTIVE)
        bubble(a, label + " " + value);
    return f;
}

// A DISPLAY FIELD (the LCD's): its label and value; selected, lit. v moves
// by a drag over [lo, hi] in steps of 1 (travel: max(160, 3 per step))
inline int lcd_field(App &a, const char *id, float x, float y, float w, float h, float &v, float lo, float hi,
                     const std::string &label, const std::string &value, bool sel, float big = 21, float unit = 1)
{
    no_drag_in_body(a, id);
    Range g;
    g.lo = lo;
    g.hi = hi;
    g.step = 1;
    g.travel = std::max(160.0f, 3.0f * (hi - lo + 1));
    int f = gesture(a.K, id, P(a, x, y), P(a, x + w, y + h), v, g);
    // (its sheet in the field's own unit: the LEVEL's steps are half dB)
    if (f & K_LONG)
        open_sheet(a, id, label, value, v * unit, lo * unit, hi * unit, unit < 1 ? 1 : 0, T("Value"), "");
    {
        double t = v * unit;
        if (take_sheet(a, id, t) & K_CHANGED) {
            v = std::max(lo, std::min(hi, (float)std::round(t / unit)));
            f |= K_CHANGED;
        }
        if (a.sheet_reset.erase(id))
            f |= K_RESET;
    }
    // (on the display's glass: lit, a block of light glowing at its edges; else its outline, faint)
    if (sel)
        rect(a, x - 2, y - 2, w + 4, h + 4, IM_COL32(0xf0, 0xb1, 0x3a, 0x30), 5.0f);
    rect(a, x, y, w, h, sel ? LCD : IM_COL32(0x33, 0x24, 0x08, 0xb0), 3.0f);
    frame(a, x, y, w, h, f & K_ACTIVE ? OWN : sel ? LCD : IM_COL32(0x6b, 0x4c, 0x14, 0xa0), 3.0f, 1.0f);
    ImFont *lf = a.lcd ? a.lcd : a.font;
    text(a, lf, 14, x + 10 * a.ts + 2, y + 6 * a.ts, sel ? LCD_BG : LCD, label);
    text(a, lf, big, x + 10 * a.ts + 2, y + h - a.lh(big) - 7 * a.ts, sel ? LCD_BG : LCD, value);
    if (f & K_ACTIVE)
        bubble(a, label + " " + value);
    return f;
}

// A SCROLLING LIST: rows of h; a drag scrolls, a still tap picks (its index), the wheel too
inline int scroll_list(App &a, const std::string &id, float x, float y, float w, float hgt, int n, float rh, float &scroll,
                       const std::function<void(int, float)> &row)
{
    struct T {
        bool down = false, moved = false;
        float y0 = 0, s0 = 0;
    };
    static std::map<std::string, T> ts;
    T &t = ts[id];
    const float content = n * rh;
    scroll = std::max(0.0f, std::min(scroll, std::max(0.0f, content - hgt)));
    ImGui::SetCursorScreenPos(P(a, x, y));
    ImGui::InvisibleButton(id.c_str(), ImVec2(w * a.k, hgt * a.k));
    const float my = (ImGui::GetIO().MousePos.y - a.org.y) / a.k;
    if (ImGui::IsItemHovered() && ImGui::GetIO().MouseWheel != 0)
        scroll -= ImGui::GetIO().MouseWheel * 3 * rh;
    if (ImGui::IsItemActivated()) {
        t.down = true;
        t.moved = false;
        t.y0 = my;
        t.s0 = scroll;
    }
    if (ImGui::IsItemActive() && t.down) {
        if (!t.moved && std::fabs(my - t.y0) * a.k > SLOP)
            t.moved = true;
        if (t.moved) {      // (by the finger's motion; what the list's ends stop goes on to a scrolled card)
            const float want = scroll - ImGui::GetIO().MouseDelta.y / a.k;
            scroll = std::max(0.0f, std::min(want, std::max(0.0f, content - hgt)));
            if (a.vcard || a.vbody)
                a.vcard_push += want - scroll;
        }
    }
    int tap = -1;
    if (ImGui::IsItemDeactivated() && t.down) {
        t.down = false;
        if (!t.moved) {
            const int i = (int)std::floor((t.y0 - y + scroll) / rh);
            if (i >= 0 && i < n)
                tap = i;
        }
    }
    dl()->PushClipRect(P(a, x, y), P(a, x + w, y + hgt), true);
    const int i0 = std::max(0, (int)(scroll / rh)), i1 = std::min(n, (int)((scroll + hgt) / rh) + 1);
    for (int i = i0; i < i1; i++)
        row(i, y + i * rh - scroll);
    dl()->PopClipRect();
    if (content > hgt) {
        const float bh = std::max(30.0f, hgt * hgt / content), by = y + (hgt - bh) * scroll / (content - hgt);
        rect(a, x + w - 4, by, 3, bh, SILK_DIM, 1);
    }
    return tap;
}

}  // namespace nui
