// THE CONTROLS DRAWN (kit.js's knob, fader and display field): the gesture
// (kit.h) over each, its look the web kit's -- a 270-degree ring that fills
// (from the top when centred), a fader's slot and cap, an LCD field.
#pragma once

#include "app.h"

namespace nui {

// (the value over the finger while it drags: the web's bubble)
inline void bubble(App &a, const std::string &s)
{
    if (!a.K.moved || a.K.active == 0)
        return;
    const ImVec2 m = a.K.bubble_at;
    const float sz = px(a, 21), w = a.font->CalcTextSizeA(sz, FLT_MAX, 0, s.c_str()).x + 24 * a.k,
                h = sz + 16 * a.k;
    const ImVec2 p0(std::floor(m.x - w / 2), std::floor(m.y - 90 * a.k - h));
    ImDrawList *fg = ImGui::GetForegroundDrawList();
    fg->AddCallback(ImGui::GetPlatformIO().DrawCallback_SetSamplerNearest, nullptr);
    fg->AddRectFilled(p0, ImVec2(p0.x + w, p0.y + h), LCD_BG, 6 * a.k);
    fg->AddRect(p0, ImVec2(p0.x + w, p0.y + h), LCD, 6 * a.k, 0, 1.5f * a.k);
    std::string t = s + (a.K.fine() ? "  \xc2\xb7 fine" : "");
    fg->AddText(a.font, sz, ImVec2(p0.x + 12 * a.k, std::floor(p0.y + 8 * a.k)), LCD, t.c_str());
}

// A KNOB: v01 its position (0..1); size its diameter (design px). Returns
// the gesture's flags; v01 moved by the finger
inline int knob(App &a, const char *id, float cx, float cy, float size, float &v01, const std::string &label,
                const std::string &value, bool centred = false, const std::vector<float> &detents = {}, float label_w = 0,
                bool own = false)
{
    const float r = size / 2;
    Range g;
    g.lo = 0;
    g.hi = 1;
    g.detents = detents;
    const int f = gesture(a.K, id, P(a, cx - r, cy - r), P(a, cx + r, cy + r + 34), v01, g);
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
        d->PathStroke(f & K_ACTIVE ? OWN : LCD, 0, 4.0f * a.k);
    }
    for (float t : detents)
        d->AddLine(pt(r * 0.95f, A0 + (A1 - A0) * t), pt(r * 1.02f, A0 + (A1 - A0) * t), SILK_DIM, 1.5f * a.k);
    // the cap and its pointer
    const ImVec2 c = P(a, cx, cy);
    d->AddCircleFilled(c, r * 0.64f * a.k, IM_COL32(0x15, 0x17, 0x1a, 255), 40);
    d->AddCircleFilled(c, r * 0.52f * a.k, CAP, 40);
    d->AddLine(c, pt(r * 0.48f, av), SILK, 2.5f * a.k);
    const auto ls = label_lines(a, a.bold, 14, label, label_w);
    for (size_t i = 0; i < ls.size(); i++)
        text_c(a, a.bold, 14, cx, cy + r + 4 + i * 16, SILK_DIM, ls[i]);
    text_c(a, a.font, 14, cx, cy + r + 4 + ls.size() * 16, (f & K_ACTIVE) || own ? OWN : LCD, value);
    if (f & K_ACTIVE)
        bubble(a, label + " " + value);
    return f;
}

// A FADER: v in [lo, hi]; its slot from y to y + h (design px)
inline int fader(App &a, const char *id, float cx, float y, float h, float &v, float lo, float hi, float step,
                 const std::vector<float> &detents, const std::string &label, const std::string &value)
{
    Range g;
    g.lo = lo;
    g.hi = hi;
    g.step = step;
    g.travel = h * 1.2f;
    g.detents = detents;
    const int f = gesture(a.K, id, P(a, cx - 30, y), P(a, cx + 30, y + h), v, g, 1);
    rect(a, cx - 4, y, 8, h, IM_COL32(0x15, 0x17, 0x1a, 255), 4);
    for (float t : detents) {
        const float ty = y + h - (t - lo) / (hi - lo) * h;
        rect(a, cx - 16, ty - 1, 32, 2, SILK_DIM, 0);
    }
    const float cy = y + h - (v - lo) / (hi - lo) * h;
    rect(a, cx - 24, cy - 14, 48, 28, f & K_ACTIVE ? PANEL_HI : CAP, 4);
    frame(a, cx - 24, cy - 14, 48, 28, EDGE, 4, 1);
    rect(a, cx - 18, cy - 1, 36, 2, f & K_ACTIVE ? OWN : LCD, 0);
    text_c(a, a.font, 14, cx, y + h + 10, f & K_ACTIVE ? OWN : LCD, value);
    text_c(a, a.bold, 14, cx, y + h + 26, SILK_DIM, label);
    if (f & K_ACTIVE)
        bubble(a, label + " " + value);
    return f;
}

// A DISPLAY FIELD (the LCD's): its label and value; selected, lit. v moves
// by a drag over [lo, hi] in steps of 1 (travel: max(160, 3 per step))
inline int lcd_field(App &a, const char *id, float x, float y, float w, float h, float &v, float lo, float hi,
                     const std::string &label, const std::string &value, bool sel, float big = 21)
{
    Range g;
    g.lo = lo;
    g.hi = hi;
    g.step = 1;
    g.travel = std::max(160.0f, 3.0f * (hi - lo + 1));
    const int f = gesture(a.K, id, P(a, x, y), P(a, x + w, y + h), v, g);
    rect(a, x, y, w, h, sel ? LCD : IM_COL32(0x33, 0x24, 0x08, 255), 3.0f);
    frame(a, x, y, w, h, f & K_ACTIVE ? OWN : LCD_DIM, 3.0f, 1.0f);
    text(a, a.font, 14, x + 10, y + 6, sel ? LCD_BG : LCD, label);
    text(a, a.font, big, x + 10, y + h - big - 7, sel ? LCD_BG : LCD, value);
    if (f & K_ACTIVE)
        bubble(a, label + " " + value);
    return f;
}

}  // namespace nui
