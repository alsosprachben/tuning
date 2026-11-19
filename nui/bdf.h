// THE code7 BITMAP FONT, straight from its BDF files (Ben's: ~/repos/code7,
// bundled in ui/fonts): a 6x7 cell (code7w's wide glyphs 12x7), Unicode,
// drawn at whole-number multiples of its 7 pixels -- sharp, no rasterizer,
// a glyph made into the atlas the first time it is drawn (Dear ImGui's font
// loader: ImFontLoader). Sizes asked for round to the nearest multiple of 7.
#pragma once

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

#include "imgui.h"
#include "imgui_internal.h"

namespace nui {

static const unsigned BDF_DOTS = 1;       // (ImFontConfig::FontLoaderFlags: the dotted font)

struct BdfGlyph {
    int w = 0, h = 0, xo = 0, yo = 0, dw = 0;
    std::vector<uint32_t> rows;         // (MSB first: bit 31 the leftmost pixel)
};

struct Bdf {
    int ascent = 6, descent = 1;
    std::unordered_map<uint32_t, int> idx;   // codepoint -> glyph + 1
    std::vector<BdfGlyph> g;
};

// the BDF's glyphs: false if it is not one
inline bool bdf_parse(const std::string &text, Bdf &out)
{
    size_t p = 0;
    auto line = [&](std::string &l) {
        if (p >= text.size())
            return false;
        size_t e = text.find('\n', p);
        if (e == std::string::npos)
            e = text.size();
        l.assign(text, p, e - p);
        if (!l.empty() && l.back() == '\r')
            l.pop_back();
        p = e + 1;
        return true;
    };
    std::string l;
    if (!line(l) || l.rfind("STARTFONT", 0) != 0)
        return false;
    BdfGlyph cur;
    long enc = -1;
    int in_bitmap = -1;
    while (line(l)) {
        if (in_bitmap >= 0) {
            if (l == "ENDCHAR") {
                if (enc >= 0) {
                    out.g.push_back(cur);
                    out.idx[(uint32_t)enc] = (int)out.g.size();
                }
                in_bitmap = -1;
                continue;
            }
            uint32_t v = (uint32_t)strtoul(l.c_str(), nullptr, 16);
            v <<= 32 - 4 * (int)l.size();               // (the row's hex, its leftmost bit to bit 31)
            cur.rows.push_back(v);
            continue;
        }
        if (l.rfind("FONT_ASCENT ", 0) == 0)
            out.ascent = atoi(l.c_str() + 12);
        else if (l.rfind("FONT_DESCENT ", 0) == 0)
            out.descent = atoi(l.c_str() + 13);
        else if (l.rfind("STARTCHAR", 0) == 0) {
            cur = BdfGlyph();
            enc = -1;
        } else if (l.rfind("ENCODING ", 0) == 0)
            enc = atol(l.c_str() + 9);
        else if (l.rfind("DWIDTH ", 0) == 0)
            cur.dw = atoi(l.c_str() + 7);
        else if (l.rfind("BBX ", 0) == 0)
            sscanf(l.c_str() + 4, "%d %d %d %d", &cur.w, &cur.h, &cur.xo, &cur.yo);
        else if (l == "BITMAP")
            in_bitmap = 0;
    }
    return !out.g.empty();
}

// (the whole-number scale for a size in device pixels: 7 px 1, 14 px 2 ...;
// ImGui asks in points at the screen's density -- its framebuffer scale, 2 on
// a Retina screen -- so the bitmap is baked in device pixels and its metrics
// handed back in points)
// (the density: the baked font's, else the screen's framebuffer scale -- ImGui
//  bakes at its config's 1 on a Retina screen, where a 10.5 point size is 21
//  device pixels, and taken as 1 it rounded up to a 2x glyph, 28: a third too big)
inline float bdf_density(const ImFontBaked *baked)
{
    const float fb = ImGui::GetIO().DisplayFramebufferScale.x;
    const float d = baked->RasterizerDensity > 0 ? baked->RasterizerDensity : 1.0f;
    return std::max(d, fb > 0 ? fb : 1.0f);
}
inline int bdf_scale(const Bdf &b, float size)
{
    const int cell = b.ascent + b.descent;
    const int s = (int)(size / cell + 0.5f);
    return s < 1 ? 1 : s;
}

inline bool bdf_src_init(ImFontAtlas *, ImFontConfig *src)
{
    src->FontLoaderData = src->FontData;            // (the Bdf, not owned: the app keeps it)
    return true;
}
inline void bdf_src_destroy(ImFontAtlas *, ImFontConfig *src) { src->FontLoaderData = nullptr; }
inline int bdf_glyph_index(ImFontAtlas *, ImFontConfig *src, ImWchar cp)
{
    const Bdf *b = (const Bdf *)src->FontLoaderData;
    auto it = b->idx.find((uint32_t)cp);
    return it == b->idx.end() ? 0 : it->second;
}
inline bool bdf_contains(ImFontAtlas *, ImFontConfig *src, int glyph_index)
{
    const Bdf *b = (const Bdf *)src->FontLoaderData;
    return glyph_index > 0 && glyph_index <= (int)b->g.size();
}
inline bool bdf_baked_init(ImFontAtlas *, ImFontConfig *src, ImFontBaked *baked, void *)
{
    const Bdf *b = (const Bdf *)src->FontLoaderData;
    if (!src->MergeMode) {
        const float d = bdf_density(baked);
        const int s = bdf_scale(*b, baked->Size * d);
        baked->Ascent = (float)(b->ascent * s) / d;
        baked->Descent = (float)(-b->descent * s) / d;
    }
    return true;
}
inline bool bdf_load_glyph(ImFontAtlas *atlas, ImFontConfig *src, ImFontBaked *baked, void *, int glyph_index,
                           ImFontGlyph *out_glyph, float *out_advance_x)
{
    const Bdf *b = (const Bdf *)src->FontLoaderData;
    if (glyph_index <= 0 || glyph_index > (int)b->g.size())
        return false;
    const BdfGlyph &g = b->g[(size_t)glyph_index - 1];
    const float d = bdf_density(baked);
    const int s = bdf_scale(*b, baked->Size * d);
    if (out_advance_x) {
        *out_advance_x = (float)(g.dw * s) / d;
        return true;
    }
    out_glyph->AdvanceX = (float)(g.dw * s) / d;
    if (g.w <= 0 || g.h <= 0)
        return true;
    const int w = g.w * s, h = g.h * s;
    ImFontAtlasRectId id = ImFontAtlasPackAddRect(atlas, w, h);
    if (id == ImFontAtlasRectId_Invalid)
        return false;
    ImTextureRect *r = ImFontAtlasPackGetRect(atlas, id);
    std::vector<unsigned char> px((size_t)w * h, 0);
    // DOTTED (BDF_DOTS: the display's font): from 4 device pixels a font
    // pixel, each a dot -- a device pixel's gap right and below, from 5 its
    // corners softened -- as a dot-matrix display's are
    const bool dots = (src->FontLoaderFlags & BDF_DOTS) && s >= 4;
    const int ds = dots ? s - 1 : s;
    for (int y = 0; y < g.h && y < (int)g.rows.size(); y++)
        for (int x = 0; x < g.w; x++)
            if (g.rows[(size_t)y] >> (31 - x) & 1u)
                for (int dy = 0; dy < ds; dy++) {
                    unsigned char *row = &px[(size_t)(y * s + dy) * w + (size_t)x * s];
                    memset(row, 255, (size_t)ds);
                    if (dots && s >= 5 && (dy == 0 || dy == ds - 1))
                        row[0] = row[ds - 1] = 150;
                }
    // (the line's top 0, its baseline at the ascent; BDF's yo the glyph's bottom from the baseline)
    const float top = ((float)(b->ascent * s) - (float)((g.yo + g.h) * s)) / d;
    out_glyph->X0 = (float)(g.xo * s) / d;
    out_glyph->Y0 = top;
    out_glyph->X1 = out_glyph->X0 + (float)w / d;
    out_glyph->Y1 = top + (float)h / d;
    out_glyph->Visible = true;
    out_glyph->PackId = id;
    ImFontAtlasBakedSetFontGlyphBitmap(atlas, baked, src, out_glyph, r, px.data(), ImTextureFormat_Alpha8, w);
    return true;
}

inline const ImFontLoader *bdf_loader()
{
    static ImFontLoader L;
    L.Name = "code7-bdf";
    L.FontSrcInit = bdf_src_init;
    L.FontSrcDestroy = bdf_src_destroy;
    L.FontSrcGetGlyphIndexFromCodepoint = bdf_glyph_index;
    L.FontSrcContainsGlyph = bdf_contains;
    L.FontBakedInit = bdf_baked_init;
    L.FontBakedLoadGlyph = bdf_load_glyph;
    return &L;
}

// a font from a parsed BDF (merge: its glyphs added to the font before it)
inline ImFont *bdf_add(ImFontAtlas *atlas, Bdf *b, const char *name, bool merge, unsigned flags = 0)
{
    ImFontConfig cfg;
    cfg.FontLoaderFlags = flags;
    cfg.FontLoader = bdf_loader();
    cfg.FontData = b;
    cfg.FontDataSize = 1;
    cfg.FontDataOwnedByAtlas = false;
    cfg.SizePixels = 21.0f;
    cfg.MergeMode = merge;
    cfg.PixelSnapH = true;
    snprintf(cfg.Name, sizeof cfg.Name, "%s", name);
    return atlas->AddFont(&cfg);
}

}  // namespace nui
