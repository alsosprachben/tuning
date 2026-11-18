// THE LOOK OF THE HARDWARE: the front panel as a thing -- a brushed
// graphite plate, keys that stand on it and sink when pressed, a display
// recessed behind glass whose dots glow, a machined aluminium dial. ONE
// LIGHT, from above and a little to the left: whatever stands up is lit on
// its top edge and throws a shadow down; whatever is sunk in is shadowed
// inside its top edge and lit on its bottom lip.
//
// All of it is ImGui's own shapes with their vertices shaded (no shader of
// ours, so Metal draws it as OpenGL does), and one small texture in the
// font atlas: the plate's grain. Drawn only when a frame is (nui.cpp redraws
// on a change), so the look costs nothing at rest.
#pragma once

#include <cmath>
#include <cstdint>

#include "app.h"

namespace nui {

namespace look {

inline ImU32 mix(ImU32 a, ImU32 b, float t)
{
    t = t < 0 ? 0 : t > 1 ? 1 : t;
    auto ch = [&](int s) {
        const float x = (float)((a >> s) & 255), y = (float)((b >> s) & 255);
        return (ImU32)std::lround(x + (y - x) * t) << s;
    };
    return ch(0) | ch(8) | ch(16) | ch(24);
}
inline ImU32 alpha(ImU32 c, float a) { return (c & 0x00FFFFFFu) | ((ImU32)std::lround(255 * (a < 0 ? 0 : a > 1 ? 1 : a)) << 24); }
inline ImU32 grey(float v, float a = 1.0f)
{
    const int g = (int)std::lround(255 * (v < 0 ? 0 : v > 1 ? 1 : v));
    return IM_COL32(g, g, g, (int)std::lround(255 * a));
}

// the vertices drawn since i0 recoloured by f(position) -> RGB, their alpha kept (the AA fringe's)
template <class F> inline void shade(ImDrawList *d, int i0, F &&f)
{
    for (int i = i0; i < d->VtxBuffer.Size; i++) {
        ImDrawVert &v = d->VtxBuffer[i];
        v.col = (f(v.pos) & 0x00FFFFFFu) | (v.col & 0xFF000000u);
    }
}
// ...by a vertical gradient, top to bottom
inline void shade_v(ImDrawList *d, int i0, float y0, float y1, ImU32 top, ImU32 bot)
{
    shade(d, i0, [&](ImVec2 p) { return mix(top, bot, (p.y - y0) / std::max(1.0f, y1 - y0)); });
}

// ---- THE PLATE's GRAIN: brushed along x, in the atlas (white; its alpha the grain)
struct Grain {
    ImFontAtlasRectId id = ImFontAtlasRectId_Invalid;
    int w = 256, h = 128;
};
inline Grain &grain_tex()
{
    static Grain g;
    if (g.id != ImFontAtlasRectId_Invalid)
        return g;
    ImFontAtlas *at = ImGui::GetIO().Fonts;
    g.id = at->AddCustomRect(g.w, g.h);
    ImFontAtlasRect r;
    if (g.id == ImFontAtlasRectId_Invalid || !at->GetCustomRect(g.id, &r))
        return g;
    ImTextureData *t = at->TexData;
    uint32_t s = 0x9e3779b9u;
    auto rnd = [&] {                    // (xorshift: the same grain every run)
        s ^= s << 13;
        s ^= s >> 17;
        s ^= s << 5;
        return (s & 0xFFFFFF) / 16777216.0f;
    };
    std::vector<float> row((size_t)g.w);
    for (int y = 0; y < g.h; y++) {
        // a row's streak: its own level, wandering slowly along x (a brush's
        // track), with a fine speck on top; wrapped so the tile repeats
        const float base = rnd();
        float wander = 0;
        for (int x = 0; x < g.w; x++) {
            wander = 0.97f * wander + 0.03f * (rnd() - 0.5f) * 4;
            row[(size_t)x] = base * 0.6f + wander * 0.5f + rnd() * 0.25f;
        }
        for (int x = 0; x < g.w; x++) {
            const float edge = x < 16 ? x / 16.0f : 1.0f;          // (its seam blended into the wrap)
            float v = row[(size_t)x] * edge + row[(size_t)(g.w - 1 - (x < 16 ? 15 - x : 0))] * (1 - edge);
            v = v < 0 ? 0 : v > 1 ? 1 : v;
            unsigned char *p = (unsigned char *)t->GetPixelsAt(r.x + x, r.y + y);
            if (t->BytesPerPixel == 4) {
                p[0] = p[1] = p[2] = 255;
                p[3] = (unsigned char)std::lround(255 * v);
            } else {
                p[0] = (unsigned char)std::lround(255 * v);
            }
        }
    }
    ImFontAtlasTextureBlockQueueUpload(at, t, r.x, r.y, r.w, r.h);
    return g;
}
// the grain over a rectangle (device-pixel tiles: sharp, at any scale), light and dark
inline void grain(App &a, float x, float y, float w, float h, float light = 0.035f, float dark = 0.06f)
{
    Grain &g = grain_tex();
    ImFontAtlasRect r;
    ImFontAtlas *at = ImGui::GetIO().Fonts;
    if (g.id == ImFontAtlasRectId_Invalid || !at->GetCustomRect(g.id, &r))
        return;
    ImDrawList *d = dl();
    const float fb = std::max(1.0f, ImGui::GetIO().DisplayFramebufferScale.x);
    const float tw = g.w / fb, th = g.h / fb;           // (a tile: its texels one to a device pixel)
    const ImVec2 p0 = P(a, x, y), p1 = P(a, x + w, y + h);
    d->PushClipRect(p0, p1, true);
    for (float ty = p0.y; ty < p1.y; ty += th)
        for (float tx = p0.x; tx < p1.x; tx += tw) {
            d->AddImage(at->TexRef, ImVec2(tx, ty), ImVec2(tx + tw, ty + th), r.uv0, r.uv1, grey(1, light));
            // (the dark pass the tile turned over: no light streak sits on its own dark one)
            d->AddImage(at->TexRef, ImVec2(tx, ty), ImVec2(tx + tw, ty + th), ImVec2(r.uv1.x, r.uv1.y),
                        ImVec2(r.uv0.x, r.uv0.y), grey(0, dark));
        }
    d->PopClipRect();
}

// ---- SHADOWS: rounded rings stacked outward, fading (a soft edge without a blur)
inline void shadow(App &a, float x, float y, float w, float h, float r, float spread, float dy, float strength)
{
    ImDrawList *d = dl();
    const int n = std::max(2, (int)std::lround(spread * a.k));
    for (int i = n; i >= 1; i--) {
        const float e = spread * i / n, t = 1.0f - (float)i / (n + 1);
        d->AddRectFilled(P(a, x - e, y - e + dy), P(a, x + w + e, y + h + e + dy), grey(0, strength * t * t / n * 2.2f),
                         (r + e) * a.k);
    }
}

// ---- THE PLATE: brushed graphite, lit from above; its bottom edge throws a shadow onto what is below
inline void plate(App &a, float x, float y, float w, float h)
{
    ImDrawList *d = dl();
    const ImVec2 p0 = P(a, x, y), p1 = P(a, x + w, y + h);
    // (the shadow under its bottom edge, onto the page)
    d->AddRectFilledMultiColor(ImVec2(p0.x, p1.y), ImVec2(p1.x, p1.y + 12 * a.k), grey(0, 0.45f), grey(0, 0.45f),
                               grey(0, 0), grey(0, 0));
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(p0, p1, IM_COL32(255, 255, 255, 255));
    shade_v(d, i0, p0.y, p1.y, IM_COL32(0x31, 0x35, 0x3a, 255), IM_COL32(0x25, 0x28, 0x2c, 255));
    grain(a, x, y, w, h);
    // its bottom edge: a bevel catching the light, then the dark of the edge
    d->AddRectFilled(ImVec2(p0.x, p1.y - 2 * a.k), ImVec2(p1.x, p1.y - 1 * a.k), grey(1, 0.07f));
    d->AddRectFilled(ImVec2(p0.x, p1.y - 1 * a.k), p1, grey(0, 0.6f));
}

// ---- A WELL: a recess in the plate (the display's): shadowed inside its top
// edge, its bottom lip catching the light
inline void well(App &a, float x, float y, float w, float h, float r, ImU32 floor)
{
    ImDrawList *d = dl();
    // (the lip: light on the plate just below the opening, dark just above)
    d->AddRect(P(a, x - 1, y - 1), P(a, x + w + 1, y + h + 1.5f), grey(1, 0.10f), (r + 1) * a.k, 0, 1.2f * a.k);
    d->AddRect(P(a, x - 1, y - 1.5f), P(a, x + w + 1, y + h), grey(0, 0.55f), (r + 1) * a.k, 0, 1.2f * a.k);
    rect(a, x, y, w, h, floor, r);
    // the shadow inside the top edge and the left, falling off
    const ImVec2 p0 = P(a, x, y), p1 = P(a, x + w, y + h);
    d->PushClipRect(p0, p1, true);
    for (int i = 0; i < 6; i++) {
        const float e = (float)i;
        d->AddRect(P(a, x - 6 + e, y - 6 + e + 3), P(a, x + w + 6 - e, y + h + 6 - e + 3), grey(0, 0.10f), (r + 6 - e) * a.k, 0,
                   1.6f * a.k);
    }
    d->PopClipRect();
}

// ---- A KEY: a cap standing on the plate. Pressed, it sinks and its shadow
// goes; lit (on), its LED glows. The label is printed on it.
inline void led(App &a, float cx, float cy, float w, float h, bool on, ImU32 col = LCD)
{
    ImDrawList *d = dl();
    if (on)
        for (int i = 4; i >= 1; i--)        // (its glow on the cap around it)
            d->AddRectFilled(P(a, cx - w / 2 - i * 2.0f, cy - h / 2 - i * 2.0f), P(a, cx + w / 2 + i * 2.0f, cy + h / 2 + i * 2.0f),
                             alpha(col, 0.07f), (h / 2 + i * 2.0f) * a.k);
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, cx - w / 2, cy - h / 2), P(a, cx + w / 2, cy + h / 2), IM_COL32(255, 255, 255, 255), h / 2 * a.k);
    const float y0 = P(a, 0, cy - h / 2).y, y1 = P(a, 0, cy + h / 2).y;
    if (on)
        shade_v(d, i0, y0, y1, mix(col, IM_COL32(255, 255, 255, 255), 0.55f), col);
    else
        shade_v(d, i0, y0, y1, IM_COL32(0x22, 0x18, 0x08, 255), IM_COL32(0x40, 0x2e, 0x10, 255));     // (a dark lens: lit below)
    d->AddRect(P(a, cx - w / 2, cy - h / 2), P(a, cx + w / 2, cy + h / 2), grey(0, 0.6f), h / 2 * a.k, 0, 1.0f * a.k);
}
// (a cap's measures by its height: a small chip's shadow and skirt are small)
inline float cap_r(float h) { return std::min(7.0f, std::max(3.0f, h * 0.18f)); }
inline float cap_sink(float h) { return h >= 30 ? 2.0f : 1.0f; }
inline void key_cap(App &a, float x, float y, float w, float h, bool held, bool enabled)
{
    ImDrawList *d = dl();
    const float r = cap_r(h), sink = held ? cap_sink(h) : 0.0f, sk = h >= 30 ? 3.0f : 2.0f;
    const float sp = std::min(6.0f, h * 0.16f);
    if (!held)
        shadow(a, x, y, w, h, r, sp, sp * 0.5f, 0.55f);
    else
        shadow(a, x, y, w, h, r, sp * 0.35f, 0.5f, 0.5f);
    y += sink;
    // (its sides: the cap's skirt, darker, showing below the face)
    d->AddRectFilled(P(a, x, y + 2), P(a, x + w, y + h), IM_COL32(0x16, 0x18, 0x1b, 255), r * a.k);
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x, y), P(a, x + w, y + h - sk), IM_COL32(255, 255, 255, 255), r * a.k);
    const ImU32 top = held ? IM_COL32(0x33, 0x37, 0x3c, 255) : IM_COL32(0x45, 0x4a, 0x51, 255),
                bot = held ? IM_COL32(0x29, 0x2c, 0x30, 255) : IM_COL32(0x2c, 0x30, 0x35, 255);
    shade_v(d, i0, P(a, 0, y).y, P(a, 0, y + h - sk).y, enabled ? top : mix(top, bot, 0.6f), bot);
    // its face's top edge catching the light
    d->AddLine(P(a, x + r * 0.8f, y + 1), P(a, x + w - r * 0.8f, y + 1), grey(1, held ? 0.06f : 0.16f), 1.2f * a.k);
    d->AddRect(P(a, x, y), P(a, x + w, y + h), grey(0, 0.75f), r * a.k, 0, 1.0f * a.k);
}
// A LIT CAP: a translucent amber cap with its light behind it (a button that
// is on); glowing on the plate around it
inline void lit_cap(App &a, float x, float y, float w, float h, bool held, ImU32 col = LCD)
{
    ImDrawList *d = dl();
    const float r = cap_r(h), sink = held ? cap_sink(h) : 0.0f, sk = h >= 30 ? 3.0f : 2.0f;
    for (int i = 4; i >= 1; i--)        // (its glow)
        d->AddRectFilled(P(a, x - i * 1.6f, y - i * 1.6f), P(a, x + w + i * 1.6f, y + h + i * 1.6f), alpha(col, 0.06f),
                         (r + i * 1.6f) * a.k);
    y += sink;
    d->AddRectFilled(P(a, x, y + 2), P(a, x + w, y + h), mix(col, IM_COL32(0, 0, 0, 255), 0.45f), r * a.k);
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x, y), P(a, x + w, y + h - sk), IM_COL32(255, 255, 255, 255), r * a.k);
    shade_v(d, i0, P(a, 0, y).y, P(a, 0, y + h - sk).y, mix(col, IM_COL32(255, 255, 255, 255), held ? 0.15f : 0.35f),
            mix(col, IM_COL32(0, 0, 0, 255), 0.08f));
    d->AddLine(P(a, x + r * 0.8f, y + 1), P(a, x + w - r * 0.8f, y + 1), grey(1, 0.35f), 1.2f * a.k);
    d->AddRect(P(a, x, y), P(a, x + w, y + h), mix(col, IM_COL32(0, 0, 0, 255), 0.6f), r * a.k, 0, 1.0f * a.k);
}
// the front panel's key: acts on release over it; on lights its LED (led: it has one)
inline bool key(App &a, const char *id, float x, float y, float w, float h, const std::string &label, bool on = false,
                bool enabled = true, float size = 14, bool has_led = true)
{
    ImGui::SetCursorScreenPos(P(a, x, y));
    ImGui::PushID(id);
    const bool hit = ImGui::InvisibleButton("b", ImVec2(w * a.k, h * a.k)) && enabled;
    const bool held = ImGui::IsItemActive() && enabled;
    ImGui::PopID();
    key_cap(a, x, y, w, h, held, enabled);
    const float sink = held ? 2.0f : 0.0f;
    const float lh = a.lh(size);
    if (has_led) {
        const float lw = std::min(26.0f, w * 0.3f), lt = std::max(4.0f, h * 0.09f);
        const float ly = y + sink + std::max(6.0f, (h - lh - lt) / 2 - 3);
        led(a, x + w / 2, ly + lt / 2, lw, lt, on);
        text_c(a, a.bold, size, x + w / 2, std::min(y + sink + h - lh - 6, ly + lt + 4), enabled ? SILK : SILK_DIM, label);
    } else {
        // (the label pressed into the cap: a dark line under it, the face's light above)
        text_c(a, a.bold, size, x + w / 2, y + sink + (h - lh) / 2 + 1, grey(0, 0.5f), label);
        text_c(a, a.bold, size, x + w / 2, y + sink + (h - lh) / 2, enabled ? SILK : SILK_DIM, label);
    }
    return hit;
}

// A CHIP: a small key, lit when on (the cards' choice rows and tiles)
inline void chip(App &a, float x, float y, float w, float h, bool on, bool held = false)
{
    if (on)
        lit_cap(a, x, y, w, h, held);
    else
        key_cap(a, x, y, w, h, held, true);
}

// A LATCHING ROW: a long key that stays in when chosen (a list's item:
// a scene, a MIDI input) -- in, its edge lit amber
inline void latch(App &a, float x, float y, float w, float h, bool on)
{
    key_cap(a, x, y, w, h, on, true);
    if (on)
        dl()->AddRect(P(a, x, y + cap_sink(h)), P(a, x + w, y + h), alpha(LCD, 0.9f), cap_r(h) * a.k, 0, 1.5f * a.k);
}
// A SMALL DISPLAY (a typed value, a search, a name): a window sunk in the
// plate, its dark amber floor; draw its text, then glass() over it
inline void lcd_window(App &a, float x, float y, float w, float h, bool lit = false)
{
    well(a, x, y, w, h, 4, IM_COL32(0x0b, 0x0c, 0x0e, 255));
    ImDrawList *d = dl();
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x + 1, y + 1), P(a, x + w - 1, y + h - 1), IM_COL32(255, 255, 255, 255), 3 * a.k);
    shade_v(d, i0, P(a, 0, y).y, P(a, 0, y + h).y, IM_COL32(0x2e, 0x20, 0x07, 255), IM_COL32(0x1d, 0x14, 0x04, 255));
    if (lit)
        d->AddRect(P(a, x + 1, y + 1), P(a, x + w - 1, y + h - 1), alpha(LCD, 0.6f), 3 * a.k, 0, 1.0f * a.k);
}

// ---- A MODULE: a raised plate of its own (a card's body) -- its shadow on
// the chassis, brushed, its top edge lit and its bottom dark
inline void module(App &a, float x, float y, float w, float h, float r)
{
    ImDrawList *d = dl();
    shadow(a, x, y, w, h, r, 8, 3, 0.6f);
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x, y), P(a, x + w, y + h), IM_COL32(255, 255, 255, 255), r * a.k);
    shade_v(d, i0, P(a, 0, y).y, P(a, 0, y + h).y, IM_COL32(0x2b, 0x2f, 0x34, 255), IM_COL32(0x22, 0x25, 0x29, 255));
    grain(a, x + r * 0.3f, y + r * 0.3f, w - r * 0.6f, h - r * 0.6f, 0.03f, 0.05f);
    d->AddLine(P(a, x + r, y + 1), P(a, x + w - r, y + 1), grey(1, 0.10f), 1.2f * a.k);
    d->AddRect(P(a, x, y), P(a, x + w, y + h), grey(0, 0.7f), r * a.k, 0, 1.0f * a.k);
}
// ---- A TRAY: a pocket milled into a module (a card's region): its floor a
// shade darker, shadowed inside its top edge, its bottom lip lit
inline void tray(App &a, float x, float y, float w, float h, float r)
{
    ImDrawList *d = dl();
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x, y), P(a, x + w, y + h), IM_COL32(255, 255, 255, 255), r * a.k);
    shade_v(d, i0, P(a, 0, y).y, P(a, 0, y + h).y, IM_COL32(0x1a, 0x1d, 0x20, 255), IM_COL32(0x20, 0x23, 0x27, 255));
    const ImVec2 p0 = P(a, x, y), p1 = P(a, x + w, y + h);
    d->PushClipRect(p0, p1, true);
    for (int i = 0; i < 5; i++) {
        const float e = (float)i;
        d->AddRect(P(a, x - 5 + e, y - 5 + e + 2.5f), P(a, x + w + 5 - e, y + h + 5 - e + 2.5f), grey(0, 0.09f),
                   (r + 5 - e) * a.k, 0, 1.4f * a.k);
    }
    d->PopClipRect();
    d->AddLine(P(a, x + r, y + h + 0.5f), P(a, x + w - r, y + h + 0.5f), grey(1, 0.08f), 1.0f * a.k);
    d->AddRect(P(a, x, y), P(a, x + w, y + h), grey(0, 0.5f), r * a.k, 0, 1.0f * a.k);
}

// ---- A SMALL KNOB's CAP: turned aluminium like the dial's, a dark skirt, an
// engraved pointer at deg (0 straight up, clockwise)
inline void knob_cap(App &a, float cx, float cy, float r, float deg_ptr)
{
    ImDrawList *d = dl();
    const ImVec2 c = P(a, cx, cy);
    const float R = r * a.k, deg = 3.14159265f / 180.0f;
    for (int i = 4; i >= 1; i--)
        d->AddCircleFilled(ImVec2(c.x + 1 * a.k, c.y + 2.5f * a.k), R + i * 0.9f * a.k, grey(0, 0.07f), 48);
    {
        const int i0 = d->VtxBuffer.Size;
        d->AddCircleFilled(c, R, IM_COL32(255, 255, 255, 255), 64);
        shade(d, i0, [&](ImVec2 p) {
            const float lit = 0.5f - 0.5f * (p.y - c.y) / R;
            return mix(IM_COL32(0x0e, 0x0f, 0x11, 255), IM_COL32(0x3c, 0x40, 0x46, 255), lit);
        });
    }
    const float Rf = R * 0.78f;
    {
        const int i0 = d->VtxBuffer.Size;
        d->AddCircleFilled(c, Rf, IM_COL32(255, 255, 255, 255), 64);
        const float L = -115 * deg;
        shade(d, i0, [&](ImVec2 p) {
            const float dx = p.x - c.x, dy = p.y - c.y;
            if (dx * dx + dy * dy < 0.0004f * Rf * Rf)
                return grey(0.60f);
            const float t = std::atan2(dy, dx) - L;
            return grey(0.58f + 0.19f * std::cos(2 * t) + 0.05f * std::cos(4 * t) + 0.04f * std::cos(t));
        });
    }
    d->AddCircle(c, Rf, grey(0, 0.45f), 64, 1.0f * a.k);
    const float t = (deg_ptr - 90) * deg;
    d->AddLine(ImVec2(c.x + std::cos(t) * Rf * 0.25f, c.y + std::sin(t) * Rf * 0.25f),
               ImVec2(c.x + std::cos(t) * Rf * 0.92f, c.y + std::sin(t) * Rf * 0.92f), grey(0.08f), std::max(1.5f, 2.2f * a.k));
}

// ---- A FADER: its slot cut through the plate, its cap ridged for the finger
inline void fader_slot(App &a, float cx, float y, float h)
{
    ImDrawList *d = dl();
    d->AddRectFilled(P(a, cx - 4, y), P(a, cx + 4, y + h), IM_COL32(0x08, 0x09, 0x0a, 255), 4 * a.k);
    d->AddRectFilled(P(a, cx - 4, y), P(a, cx + 4, y + 4), grey(0, 0.6f), 4 * a.k);
    d->AddLine(P(a, cx - 3, y + h + 0.5f), P(a, cx + 3, y + h + 0.5f), grey(1, 0.10f), 1.0f * a.k);
}
inline void fader_cap(App &a, float cx, float cy, bool active, ImU32 line)
{
    ImDrawList *d = dl();
    const float x = cx - 24, y = cy - 14, w = 48, h = 28;
    shadow(a, x, y, w, h, 4, 5, 3, 0.6f);
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x, y), P(a, x + w, y + h), IM_COL32(255, 255, 255, 255), 4 * a.k);
    // (its face bowed for the finger: lit above the middle, shadowed below)
    shade(d, i0, [&](ImVec2 p) {
        const float v = (p.y - P(a, 0, y).y) / (h * a.k);
        return mix(active ? IM_COL32(0x40, 0x45, 0x4b, 255) : IM_COL32(0x4c, 0x52, 0x59, 255), IM_COL32(0x22, 0x25, 0x29, 255),
                   std::fabs(v - 0.35f) * 1.6f);
    });
    for (int i = -2; i <= 2; i++) {     // (its ridges)
        if (i == 0)
            continue;
        const float ry = cy + i * 5.0f;
        d->AddLine(P(a, x + 5, ry), P(a, x + w - 5, ry), grey(0, 0.45f), 1.0f * a.k);
        d->AddLine(P(a, x + 5, ry + 1), P(a, x + w - 5, ry + 1), grey(1, 0.08f), 1.0f * a.k);
    }
    d->AddRectFilled(P(a, cx - 18, cy - 1), P(a, cx + 18, cy + 1), line);
    d->AddRect(P(a, x, y), P(a, x + w, y + h), grey(0, 0.75f), 4 * a.k, 0, 1.0f * a.k);
}

// ---- PIANO KEYS: ivory-white with a front lip, black keys standing up from
// them, their front slope catching the light; the fallboard's shadow over the
// tops of all (keybed: once, over the whole row, after the keys)
inline void white_key(App &a, float x, float y, float w, float h, ImU32 base = KEY_W)
{
    ImDrawList *d = dl();
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x, y), P(a, x + w, y + h), IM_COL32(255, 255, 255, 255), 1.5f * a.k);
    shade_v(d, i0, P(a, 0, y).y, P(a, 0, y + h).y, mix(base, IM_COL32(0x9a, 0x9c, 0x96, 255), 0.25f),
            mix(base, IM_COL32(255, 255, 255, 255), 0.25f));
    const float lip = std::max(2.0f, h * 0.06f);
    d->AddRectFilled(P(a, x, y + h - lip), P(a, x + w, y + h), mix(base, IM_COL32(0x60, 0x62, 0x5e, 255), 0.45f), 1.5f * a.k);
}
inline void black_key(App &a, float x, float y, float w, float h, ImU32 base = KEY_B)
{
    ImDrawList *d = dl();
    shadow(a, x, y, w, h, 1.5f, 2.5f, 2.0f, 0.5f);
    d->AddRectFilled(P(a, x, y), P(a, x + w, y + h), base, 1.5f * a.k);
    const float slope = std::max(3.0f, h * 0.13f), side = std::max(1.0f, w * 0.12f);
    // (its top face, lit above; its front slope, lighter)
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x + side, y), P(a, x + w - side, y + h - slope), IM_COL32(255, 255, 255, 255), 1.0f * a.k);
    shade_v(d, i0, P(a, 0, y).y, P(a, 0, y + h - slope).y, mix(base, IM_COL32(0, 0, 0, 255), 0.4f),
            mix(base, IM_COL32(0x60, 0x64, 0x6a, 255), 0.35f));
    d->AddRectFilled(P(a, x + side, y + h - slope), P(a, x + w - side, y + h - 1), mix(base, IM_COL32(0x80, 0x84, 0x8a, 255), 0.45f),
                     1.0f * a.k);
}
inline void keybed(App &a, float x, float y, float w)
{
    dl()->AddRectFilledMultiColor(P(a, x, y), P(a, x + w, y + 7), grey(0, 0.55f), grey(0, 0.55f), grey(0, 0), grey(0, 0));
}

// ---- A SLIDE SWITCH: its track cut into the plate (lit inside when on), a turned thumb
inline void switch_(App &a, float cx, float cy, bool on)
{
    ImDrawList *d = dl();
    const float x = cx - 28, y = cy - 13, w = 56, h = 26;
    d->AddRectFilled(P(a, x, y), P(a, x + w, y + h), on ? mix(LCD, IM_COL32(0, 0, 0, 255), 0.15f) : IM_COL32(0x0a, 0x0b, 0x0c, 255),
                     h / 2 * a.k);
    if (on)
        for (int i = 3; i >= 1; i--)
            d->AddRectFilled(P(a, x - i * 1.5f, y - i * 1.5f), P(a, x + w + i * 1.5f, y + h + i * 1.5f), alpha(LCD, 0.06f),
                             (h / 2 + i * 1.5f) * a.k);
    d->AddRectFilledMultiColor(P(a, x + h / 2, y), P(a, x + w - h / 2, y + 5), grey(0, 0.5f), grey(0, 0.5f), grey(0, 0), grey(0, 0));
    d->AddRect(P(a, x, y), P(a, x + w, y + h), grey(0, 0.7f), h / 2 * a.k, 0, 1.0f * a.k);
    d->AddLine(P(a, x + h / 2, y + h + 0.5f), P(a, x + w - h / 2, y + h + 0.5f), grey(1, 0.10f), 1.0f * a.k);
    knob_cap(a, on ? cx + 14 : cx - 14, cy, 11.5f, on ? 90.0f : -90.0f);
}

// ---- THE DIAL: a machined aluminium cap -- turned, so its sheen is a cone
// that stays with the light as it turns -- a knurled skirt, a finger dimple
inline void dial_cap(App &a, float cx, float cy, float r, float rot_deg)
{
    ImDrawList *d = dl();
    const ImVec2 c = P(a, cx, cy);
    const float R = r * a.k, deg = 3.14159265f / 180.0f;
    // its shadow on the plate, down and a little right
    for (int i = 8; i >= 1; i--)
        d->AddCircleFilled(ImVec2(c.x + 2 * a.k, c.y + 5 * a.k), R + i * 1.4f * a.k, grey(0, 0.05f), 96);
    // THE SKIRT: dark, its knurls turning with the dial
    {
        const int i0 = d->VtxBuffer.Size;
        d->AddCircleFilled(c, R, IM_COL32(255, 255, 255, 255), 128);
        shade(d, i0, [&](ImVec2 p) {
            const float t = std::atan2(p.y - c.y, p.x - c.x), lit = 0.5f - 0.5f * std::sin(t);     // (the top lit)
            return mix(IM_COL32(0x10, 0x11, 0x13, 255), IM_COL32(0x4a, 0x4e, 0x54, 255), lit);
        });
        const int nk = 60;
        for (int i = 0; i < nk; i++) {
            const float t = (i * 360.0f / nk + rot_deg) * deg, lit = 0.5f - 0.5f * std::sin(t);
            d->AddLine(ImVec2(c.x + std::cos(t) * R * 0.86f, c.y + std::sin(t) * R * 0.86f),
                       ImVec2(c.x + std::cos(t) * (R - 0.5f * a.k), c.y + std::sin(t) * (R - 0.5f * a.k)),
                       grey(0, 0.35f + 0.25f * (1 - lit)), 1.2f * a.k);
        }
    }
    // THE FACE: spun aluminium -- light in two opposed fans along the light's
    // line (the turning's grooves), dimmer across it, a bevel round its rim
    const float Rf = R * 0.80f;
    d->AddCircle(c, Rf + 1.0f * a.k, grey(0, 0.6f), 128, 2.0f * a.k);
    {
        const int i0 = d->VtxBuffer.Size;
        d->AddCircleFilled(c, Rf, IM_COL32(255, 255, 255, 255), 192);
        const float L = -115 * deg;     // (the light's bearing: above, a little left)
        shade(d, i0, [&](ImVec2 p) {
            const float dx = p.x - c.x, dy = p.y - c.y;
            const float rr = std::sqrt(dx * dx + dy * dy) / Rf;
            if (rr < 0.02f)
                return grey(0.62f);
            const float t = std::atan2(dy, dx) - L;
            const float v = 0.60f + 0.20f * std::cos(2 * t) + 0.06f * std::cos(4 * t) + 0.04f * std::cos(t);
            return grey(v * (0.97f + 0.03f * rr));
        });
    }
    {                                   // the rim's bevel: lit above, dark below
        const int i0 = d->VtxBuffer.Size;
        d->AddCircle(c, Rf - 1.2f * a.k, IM_COL32(255, 255, 255, 255), 128, 2.0f * a.k);
        shade(d, i0, [&](ImVec2 p) {
            const float lit = 0.5f - 0.5f * (p.y - c.y) / Rf;
            return grey(0.35f + 0.6f * lit);
        });
    }
    // THE DIMPLE: a dish cut in the face -- in shadow at its top, lit at its bottom
    const float t = (rot_deg - 90) * deg, dr = Rf * 0.17f;
    const ImVec2 dc(c.x + std::cos(t) * Rf * 0.62f, c.y + std::sin(t) * Rf * 0.62f);
    {
        const int i0 = d->VtxBuffer.Size;
        d->AddCircleFilled(dc, dr, IM_COL32(255, 255, 255, 255), 48);
        shade(d, i0, [&](ImVec2 p) {
            const float lit = 0.5f + 0.5f * (p.y - dc.y) / dr;
            return grey(0.30f + 0.45f * lit);
        });
        d->AddCircle(dc, dr, grey(0, 0.35f), 48, 1.0f * a.k);
    }
}

// ---- THE DISPLAY's TEXT: code7's dots (the dotted font, a.lcd) with their glow on the glass
inline void lcd_text(App &a, float size, float x, float y, ImU32 col, const std::string &s, bool glow = true)
{
    ImFont *f = a.lcd ? a.lcd : a.font;
    if (glow) {
        const float fb = std::max(1.0f, ImGui::GetIO().DisplayFramebufferScale.x);
        const float o = 1.0f / fb;      // (a device pixel, in points)
        const ImVec2 p = P(a, x, y);
        const float sz = px(a, size);
        static const float OFF[8][2] = {{-1, 0}, {1, 0}, {0, -1}, {0, 1}, {-2, -1}, {2, 1}, {-1, 2}, {1, -2}};
        for (auto &q : OFF)
            dl()->AddText(f, sz, ImVec2(p.x + q[0] * o * 1.5f, p.y + q[1] * o * 1.5f), alpha(col, 0.09f), s.c_str());
    }
    dl()->AddText(f, px(a, size), P(a, x, y), col, s.c_str());
}
inline void lcd_text_c(App &a, float size, float cx, float y, ImU32 col, const std::string &s, bool glow = true)
{
    lcd_text(a, size, cx - text_w(a, a.lcd ? a.lcd : a.font, size, s) / 2, y, col, s, glow);
}

// THE GLASS over the display: its floor a little lighter in the middle, a
// sheen across its top, and the faint pane edge
inline void glass(App &a, float x, float y, float w, float h)
{
    ImDrawList *d = dl();
    const ImVec2 p0 = P(a, x, y), p1 = P(a, x + w, y + h);
    d->AddRectFilledMultiColor(p0, ImVec2(p1.x, p0.y + (p1.y - p0.y) * 0.42f), grey(1, 0.045f), grey(1, 0.03f), grey(1, 0.0f),
                               grey(1, 0.0f));
    // (a reflection's band across the pane, leaning)
    const float bx = x + w * 0.58f;
    d->AddQuadFilled(P(a, bx, y), P(a, bx + w * 0.10f, y), P(a, bx + w * 0.02f, y + h), P(a, bx - w * 0.08f, y + h),
                     grey(1, 0.018f));
    d->AddRect(p0, p1, grey(1, 0.05f), 4 * a.k, 0, 1.0f * a.k);
}

}  // namespace look

}  // namespace nui
