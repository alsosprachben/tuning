// THE LIBRARY CARD (the retired web interface's): every patch the engine plays, by family
// (favourites, all, GM's sixteen, the drum kits, the MT-32's and CM-32P's
// own), or by search -- the words in its number, name and family; a tile's
// tap plays it on the part selected, its star keeps it among the
// favourites. The tiles scroll under a finger (a drag scrolls, a tap
// picks); the search has its own keys (a touch screen has no keyboard),
// and a keyboard's typing reaches it too. Under them, what the patch is
// in a few words (ui/about.json's, from variation_desc.py).
#pragma once

#include <set>

#include "app.h"
#include "widgets.h"

namespace nui {

static const char *FAMILY_NAMES[16] = {N_("Piano"), N_("Chromatic Perc."), N_("Organ"), N_("Guitar"), N_("Bass"), N_("Strings"), N_("Ensemble"),
                                       N_("Brass"), N_("Reed"), N_("Pipe"), N_("Synth Lead"), N_("Synth Pad"), N_("Synth Effects"), N_("Ethnic"),
                                       N_("Percussive"), N_("Sound Effects")};

struct Patch {
    int pick = 0, program = 0, variation = 0;
    bool drums = false;
    std::string name, desc, search;     // (desc: its few words, about.json's; search: its number, name, words and family, lower case)
    std::vector<std::string> stds;      // (the standards it answers to: about.json's std -- GM1, GM2, GS1..GS4, CVT1)
    std::string tag;                    // (...said on its tile: "GS3", "GM2 GS1")
};

// THE STANDARDS' FILTERS (Ben 2026-11-25): a standard shows what a file of it can
// select -- GM1 its own; GM2 GM1's and its own; a Sound Canvas map GM1's and its
// maps' up to it (GS3: GS1, GS2, GS3); CVT1 ours alone
static const char *STD_CHIPS[8] = {"all", "GM1", "GM2", "GS1", "GS2", "GS3", "GS4", "CVT1"};   // i18n-skip (the standards' names)
inline bool std_shows(const std::string &f, const Patch &p)
{
    if (f == "all")
        return true;
    for (const auto &s : p.stds) {
        if (s == f || (s == "GM1" && f != "CVT1"))   // i18n-skip
            return true;
        if (f.rfind("GS", 0) == 0 && s.rfind("GS", 0) == 0 && s <= f)
            return true;
    }
    return false;
}

struct LibUi {
    bool loaded = false, favs_kept = false;
    std::vector<Patch> patches;
    std::set<std::string> favs;
    std::string fam = "all", q, last_q;
    std::string stdf = "all";           // (the standard's filter: STD_CHIPS)
    bool typing = false;                // (the search's keys up)
    float scroll = 0;
    int picking = -1;
    double pick_t = 0;
    // a touch on the tiles: where it began, whether it scrolled
    bool down = false, moved = false;
    ImVec2 p0{0, 0};
    float s0 = 0;
    J about;                            // (ui/about.json)
};
static LibUi g_lib;

inline std::string fav_key(const Patch &p)
{
    return std::string(p.drums ? "1:" : "0:") + std::to_string(p.program) + "." + std::to_string(p.variation);
}
inline std::string fam_of(const Patch &p)
{
    return p.drums ? "drums" : p.variation == 127 ? "mt32" : p.variation == 126 ? "cm32p" : std::to_string(p.program >> 3);
}
inline std::string fam_label(const Patch &p)
{
    // (English: the search's words, kept as they are; translated where drawn)
    return p.drums ? N_("Drum kits") : p.variation == 127 ? "MT-32" : p.variation == 126 ? "CM-64 PCM"   // i18n-skip (a product's name)
                                                                                       : FAMILY_NAMES[(p.program >> 3) & 15];
}
inline std::string lower(std::string s)
{
    for (char &c : s)
        c = (char)tolower((unsigned char)c);
    return s;
}

inline void lib_load(App &a)
{
    LibUi &L = g_lib;
    L.loaded = true;
    sess::load(a.ui_dir + "/about.json", L.about);
    const J *descs = L.about.get("desc");
    const J *stdm = L.about.get("std"), *kstd = L.about.get("kit_std");
    J r = call(a, "{\"call\":\"patches\"}");
    if (const J *ps = r.get("patches"); ps && ps->is(J::ARR))
        for (const J &x : ps->a) {
            Patch p;
            p.pick = (int)num(&x, "pick");
            p.program = (int)num(&x, "program");
            p.variation = (int)num(&x, "variation");
            p.drums = flag(&x, "drums");
            p.name = str(&x, "name");
            if (const J *d = descs && !p.drums ? descs->get(std::to_string(p.program) + "." + std::to_string(p.variation)) : nullptr;
                d && d->is(J::STR))
                p.desc = d->s;
            if (const J *sd = p.drums ? (kstd ? kstd->get(std::to_string(p.program)) : nullptr)
                                      : (stdm ? stdm->get(std::to_string(p.program) + "." + std::to_string(p.variation)) : nullptr);
                sd && sd->is(J::ARR))
                for (const J &e : sd->a)
                    if (e.is(J::STR)) {
                        p.stds.push_back(e.s);
                        p.tag += (p.tag.empty() ? "" : " ") + e.s;
                    }
            char b[16];
            snprintf(b, sizeof b, "%03d ", p.program);
            p.search = lower(b + p.name + " " + p.desc + " " + fam_label(p) + " " + p.tag);
            L.patches.push_back(p);
        }
    J f = call(a, "{\"call\":\"favourites\"}");
    if (const J *fs = f.get("favourites"); fs && fs->is(J::ARR))
        for (const J &x : fs->a)
            if (x.is(J::STR))
                L.favs.insert(x.s);
    L.favs_kept = flag(&f, "kept");
}

// A PART's patch's few words (about.json's desc), for the display and the notes
inline std::string patch_desc(App &a, const J *part)
{
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    const J *d = L.about.get("desc");
    if (!d || !part || flag(part, "drums"))
        return "";
    const J *e = d->get(std::to_string((int)num(part, "program")) + "." + std::to_string((int)num(part, "variation")));
    return e && e->is(J::STR) ? e->s : "";
}

inline bool is_cur(const Patch &p, const J *q)
{
    return q && flag(q, "drums") == p.drums && (int)num(q, "program") == p.program &&
           (p.drums || (int)num(q, "variation") == p.variation);
}

// the patches the family or search shows
inline std::vector<const Patch *> lib_shown()
{
    LibUi &L = g_lib;
    std::vector<const Patch *> out;
    std::vector<std::string> words;
    {
        std::string w;
        for (char c : lower(L.q) + " ")
            if (c == ' ') {
                if (!w.empty())
                    words.push_back(w);
                w.clear();
            } else
                w += c;
    }
    for (const Patch &p : L.patches) {
        if (!std_shows(L.stdf, p))
            continue;
        if (!words.empty()) {
            bool all = true;
            for (const auto &w : words)
                all = all && p.search.find(w) != std::string::npos;
            if (all)
                out.push_back(&p);
        } else if (L.fam == "all" || (L.fam == "fav" ? L.favs.count(fav_key(p)) > 0 : fam_of(p) == L.fam))
            out.push_back(&p);
    }
    return out;
}


// THE ON-SCREEN KEYS (the web's osk): true when DONE
// THE SCREEN's OWN KEYS typing into q (a name's: with - and _); true on DONE
inline bool osk(App &a, std::string &q, float x, float y, float w, bool name = false, const char *done = nullptr)
{
    static const char *ROWS[4] = {"1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"};
    static const char *NROWS[4] = {"1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm_"};
    const char *const *rows = name ? NROWS : ROWS;
    const float kh = a.ph ? 36 : 50, gap = a.ph ? 4 : 6, kw = (w - gap * 9) / 10;   // (the phone's shorter)
    rect(a, x - 10, y - 10, w + 20, 5 * (kh + gap) + 14, IM_COL32(0x17, 0x19, 0x1c, 255), 10);
    for (int r = 0; r < 4; r++) {
        const int n = (int)strlen(rows[r]);
        const float rx = x + (w - (n * kw + (n - 1) * gap)) / 2;
        for (int i = 0; i < n; i++) {
            const std::string k(1, rows[r][i]), id = "osk" + k;
            if (button(a, id.c_str(), rx + i * (kw + gap), y + r * (kh + gap), kw, kh, k, false, true, 21) && q.size() < 40)
                q += k;
        }
    }
    const float ry = y + 4 * (kh + gap), bw = (w - 3 * gap) / 6, ws = a.tab ? 21 : 14;   // (the word keys 3x on the iPad, as its letters)
    if (button(a, "oskclear", x, ry, bw, kh, T("CLEAR"), false, true, ws))
        q.clear();
    if (button(a, "oskspace", x + bw + gap, ry, bw * 3 - gap, kh, T("SPACE"), false, true, ws))
        q += " ";
    if (button(a, "oskback", x + 4 * bw + gap, ry, bw - gap, kh, "\xe2\x86\x90", false, true, ws) && !q.empty()) {
        q.pop_back();
        while (!q.empty() && ((unsigned char)q.back() & 0xC0) == 0x80)
            q.pop_back();
    }
    return button(a, "oskdone", x + 5 * bw + 2 * gap, ry, bw - gap, kh, done ? done : T("DONE"), false, true, ws);   // (done: the caller's, translated)
}
inline bool lib_keys(App &a, float x, float y, float w) { return osk(a, g_lib.q, x, y, w); }

inline void draw_library(App &a)
{
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    const J *cur = part(a, a.row);
    // THE FAMILIES: two columns
    struct Fam {
        std::string id, label;
    };
    std::vector<Fam> fams = {{"fav", std::string("   ") + T("Favourites")}, {"all", T("All")}};   // (the spaces: its star, drawn)
    for (int i = 0; i < 16; i++)
        fams.push_back({std::to_string(i), T(FAMILY_NAMES[i])});
    fams.push_back({"drums", T("Drum kits")});
    fams.push_back({"mt32", "MT-32"});
    fams.push_back({"cm32p", "CM-64 PCM"});   // i18n-skip (a product's name)
    const bool T = a.tab, PH = a.ph;    // (the iPad's: its card from y 210 to card_y1 + 6; the phone's from 106; nui::T below, past it)
    const float FX = PH ? 14 : T ? 20 : 34, FY = PH ? 112 : T ? 218 : 356, fw = PH ? 140 : 196, fh = PH ? 40 : 44, fg = 6,
                Y1 = card_y1(a);
    const bool searching = !L.q.empty();
    float MX;
    if (T) {                            // (the families a column that scrolls, 44-point rows)
        static float fam_scroll = 0;
        const int tap = scroll_list(a, "fams", FX, FY, fw + 8, Y1 - FY, (int)fams.size(), fh + 4, fam_scroll, [&](int i, float y) {
            const bool on = !searching && L.fam == fams[(size_t)i].id;
            look::chip(a, FX, y, fw, fh, on);
            text(a, a.bold, 21, FX + 10, y + (fh - a.lh(21)) / 2, on ? PANEL : SILK, fit(a, a.bold, 21, fams[(size_t)i].label, fw - 20));
            if (fams[(size_t)i].id == "fav")
                look::star(a, FX + 10 + text_w(a, a.bold, 21, "  ") / 2, y + fh / 2, a.lh(21) * 0.55f, on ? PANEL : SILK, true);
        });
        if (tap >= 0) {
            L.fam = fams[(size_t)tap].id;
            L.q.clear();
            L.scroll = 0;
        }
        MX = FX + fw + 20;
    } else {
        for (size_t i = 0; i < fams.size(); i++) {
            const float x = FX + (i % 2) * (fw + fg), y = FY + (i / 2) * (fh + fg);
            const std::string id = "fam" + fams[i].id;
            const bool fon = !searching && L.fam == fams[i].id;
            const bool hit = button(a, id.c_str(), x, y, fw, fh, fams[i].label, fon);
            if (fams[i].id == "fav")            // (its star where the label's spaces are)
                look::star(a, x + fw / 2 - text_w(a, a.bold, 14, fams[i].label) / 2 + text_w(a, a.bold, 14, "  ") / 2,
                           y + fh / 2 - 1, a.lh(14) * 0.55f, fon ? IM_COL32(0x26, 0x18, 0x02, 255) : SILK, true);
            if (hit) {
                L.fam = fams[i].id;
                L.q.clear();
                L.scroll = 0;
            }
        }
        MX = FX + 2 * fw + fg + 24;
    }
    // THE SEARCH and the count
    const float MW = (PH ? 820 : T ? 1105 : 1886) - MX, SY = PH ? 112 : T ? 216 : 350, SH = PH ? 40 : T ? 44 : 46,
                SW = PH ? 250 : T ? 330 : 560;
    look::lcd_window(a, MX, SY, SW, SH, L.typing);
    look::lcd_text(a, 21, MX + 12, SY + (SH - a.lh(21)) / 2, L.q.empty() ? LCD_DIM : LCD,
                   L.q.empty() ? std::string(nui::T("Search patches")) : L.q + (L.typing ? "_" : ""), !L.q.empty());
    look::glass(a, MX, SY, SW, SH);
    ImGui::SetCursorScreenPos(P(a, MX, SY));
    if (ImGui::InvisibleButton("search", ImVec2(SW * a.k, SH * a.k)))
        L.typing = true;
    tap_yields(a);
    if (L.typing) {                     // (a keyboard's typing too, while the keys are up)
        ImGuiIO &io = ImGui::GetIO();
        for (int i = 0; i < io.InputQueueCharacters.Size; i++) {
            const ImWchar c = io.InputQueueCharacters[i];
            if (c >= 32 && c < 127) {
                L.q += (char)c;
                L.scroll = 0;
            }
        }
        if (ImGui::IsKeyPressed(ImGuiKey_Backspace) && !L.q.empty())
            L.q.pop_back();
        if (ImGui::IsKeyPressed(ImGuiKey_Enter) || ImGui::IsKeyPressed(ImGuiKey_Escape))
            L.typing = false;
    }
    if (L.q != L.last_q) {              // (a new search: from the top)
        L.last_q = L.q;
        L.scroll = 0;
    }
    const std::vector<const Patch *> list = lib_shown();
    char info[160];
    snprintf(info, sizeof info, list.size() == 1 ? nui::T("%d patch \xc2\xb7 tap to play on part %02d%s") : nui::T("%d patches \xc2\xb7 tap to play on part %02d%s"),
             (int)list.size(), a.row + 1, L.favs_kept ? "" : nui::T(" \xc2\xb7 (no session: stars are not kept)"));
    const std::string info_ = fit(a, a.font, 14, info, MW - SW - 60);
    text(a, a.font, 14, MX + SW + 16, SY + (PH ? 14 : 16), SILK_DIM, info_);
    heading(a, MX + SW + 16 + text_w(a, a.font, 14, info_) + 4, SY + (PH ? 14 : 16), "", "library");   // (the card's ?)

    // THE STANDARDS: a chip each under the search (what a file of it can select)
    {
        const float CY = SY + SH + (PH ? 6 : 8), CH = PH ? 34 : 40, cg = 6, cw = (MW - 7 * cg) / 8;
        for (int i = 0; i < 8; i++) {
            const std::string id = std::string("std") + STD_CHIPS[i];
            if (button(a, id.c_str(), MX + i * (cw + cg), CY, cw, CH, i ? STD_CHIPS[i] : nui::T("ALL"), L.stdf == STD_CHIPS[i],
                       true, T ? 21 : 14)) {
                L.stdf = STD_CHIPS[i];
                L.scroll = 0;
            }
        }
    }
    // (the patch's words are on its tile and on the display: the grid takes the card)
    const float KH = PH ? 40 : 56;      // (a row of the on-screen keys, with its gap)
    const float TY = PH ? 198 : T ? 322 : 462, TB = L.typing ? Y1 - 5 * KH - 24 : Y1;

    // THE TILES: a grid that scrolls under a finger
    // (three across, a line taller than the names alone: each patch's few words, whole, on two lines under its name)
    const float tw_min = PH ? 300 : T ? 280 : 400, th = T ? 62 : 74, gap = T ? 6 : 8, star = T ? 44 : 52;
    const int cols = std::max(1, (int)((MW + gap) / (tw_min + gap)));
    const float tw = (MW - gap * (cols - 1)) / cols;
    const int rows = ((int)list.size() + cols - 1) / cols;
    const float content = rows * (th + gap), view = TB - TY;
    L.scroll = std::max(0.0f, std::min(L.scroll, std::max(0.0f, content - view)));
    // (the touch: a drag scrolls; a still tap picks the tile, or its star)
    ImGui::SetCursorScreenPos(P(a, MX, TY));
    ImGui::InvisibleButton("tiles", ImVec2(MW * a.k, view * a.k));
    const ImVec2 m = ImGui::GetIO().MousePos;
    const float mx = (m.x - a.org.x) / a.k, my = (m.y - a.org.y) / a.k;
    if (ImGui::IsItemHovered() && ImGui::GetIO().MouseWheel != 0)
        L.scroll -= ImGui::GetIO().MouseWheel * 3 * (th + gap);
    if (ImGui::IsItemActivated()) {
        L.down = true;
        L.moved = false;
        L.p0 = ImVec2(mx, my);
        L.s0 = L.scroll;
    }
    if (ImGui::IsItemActive() && L.down) {
        if (!L.moved && std::fabs(my - L.p0.y) * a.k > SLOP)
            L.moved = true;
        if (L.moved)
            L.scroll = L.s0 - (my - L.p0.y);
    }
    int tap_i = -1;
    bool tap_star = false;
    if (ImGui::IsItemDeactivated() && L.down) {
        L.down = false;
        if (!L.moved) {
            const int c = (int)((L.p0.x - MX) / (tw + gap)), r = (int)((L.p0.y - TY + L.scroll) / (th + gap));
            if (c >= 0 && c < cols && r >= 0 && r * cols + c < (int)list.size()) {
                tap_i = r * cols + c;
                tap_star = L.p0.x > MX + c * (tw + gap) + tw - star;
            }
        }
    }
    dl()->PushClipRect(P(a, MX, TY), P(a, MX + MW, TB), true);
    const int r0 = std::max(0, (int)(L.scroll / (th + gap))), r1 = std::min(rows, (int)((L.scroll + view) / (th + gap)) + 1);
    if (L.picking >= 0 && ImGui::GetTime() - L.pick_t > 15)
        L.picking = -1;
    for (int r = r0; r < r1; r++)
        for (int c = 0; c < cols; c++) {
            const int i = r * cols + c;
            if (i >= (int)list.size())
                break;
            const Patch &p = *list[(size_t)i];
            const float x = MX + c * (tw + gap), y = TY + r * (th + gap) - L.scroll;
            const bool isc = is_cur(p, cur), fav = L.favs.count(fav_key(p)) > 0;
            if (isc && L.picking == p.pick)
                L.picking = -1;
            look::chip(a, x, y, tw, th, isc);
            if (L.picking == p.pick)
                frame(a, x, y, tw, th, OWN, 8, 2.5f);
            // (the number: a kit's, or the program's with its variation smaller, as the web's <i>)
            const ImU32 nc = isc ? LCD_BG : LCD;
            const float h21 = a.lh(21), h14 = a.lh(14);
            float name_x = T ? 10 + text_w(a, a.font, 21, "000") + 8 : 112;
            if (p.drums) {
                text(a, a.font, 14, x + 10, y + (th - h14) / 2, nc, nui::T("KIT"));
                text(a, a.font, 21, x + 14 + text_w(a, a.font, 14, nui::T("KIT")), y + (th - h21) / 2, nc, std::to_string(p.program));
                name_x = std::max(name_x, 18 + text_w(a, a.font, 14, nui::T("KIT")) + text_w(a, a.font, 21, std::to_string(p.program)));
            } else {
                char pn[8];
                snprintf(pn, sizeof pn, "%03d", p.program);
                text(a, a.font, 21, x + 10, y + (th - h21) / 2, nc, pn);
                if (p.variation) {
                    const std::string vs = "." + std::to_string(p.variation);
                    text(a, a.font, 14, x + 10 + text_w(a, a.font, 21, pn), y + (th - h21) / 2 + (h21 - h14), nc, vs);
                    name_x = std::max(name_x, 10 + text_w(a, a.font, 21, pn) + text_w(a, a.font, 14, vs) + 8);
                }
            }
            // (its standards, small, over the star in its column: the name keeps its whole line)
            const float tagw = 0;
            if (!p.tag.empty())
                text_c(a, a.font, 14, x + tw - star / 2, y + 5, isc ? LCD_BG : SILK_DIM, p.tag);
            // (the name; under it, the patch's few words -- "Hammond", "Moog: two saws, ladder")
            const float nw = tw - name_x - star - 4;
            if (p.desc.empty())
                text(a, a.font, 14, x + name_x, y + (th - h14) / 2, isc ? LCD_BG : SILK, fit(a, a.font, 14, p.name, nw - tagw));
            else {
                const auto dl2 = wrap_max(a, a.font, 14, p.desc, nw, 2);
                const size_t n = dl2.size();
                const float y0 = y + (th - (1 + n) * h14 - 2 * n) / 2;
                text(a, a.font, 14, x + name_x, y0, isc ? LCD_BG : SILK, fit(a, a.font, 14, p.name, nw - tagw));
                for (size_t i = 0; i < n; i++)
                    text(a, a.font, 14, x + name_x, y0 + (h14 + 2) * (i + 1), isc ? LCD_BG : SILK_DIM,
                         dl2[i]);
            }
            look::star(a, x + tw - star / 2, y + th / 2 + (p.tag.empty() ? 0 : 5), h21 * 0.5f, fav ? (isc ? LCD_BG : LCD) : (isc ? LCD_DIM : SILK_DIM), fav);
        }
    if (list.empty())
        text(a, a.font, 21, MX, TY + 10, SILK_DIM,
             L.fam == "fav" && !searching ? nui::T("No favourites yet: tap a patch's star to keep it here.") : nui::T("Nothing matches."));
    dl()->PopClipRect();
    // (the scroll's place, at the right)
    if (content > view) {
        const float bh = std::max(30.0f, view * view / content), by = TY + (view - bh) * L.scroll / (content - view);
        rect(a, MX + MW + 6, by, 5, bh, SILK_DIM, 2);
    }
    if (tap_i >= 0) {
        const Patch &p = *list[(size_t)tap_i];
        if (tap_star) {
            const std::string k = fav_key(p);
            if (L.favs.count(k))
                L.favs.erase(k);
            else
                L.favs.insert(k);
            std::string arr;
            for (const auto &f : L.favs)
                arr += (arr.empty() ? "\"" : ",\"") + f + "\"";
            call(a, "{\"call\":\"favourites_set\",\"favourites\":[" + arr + "]}");
        } else {
            L.picking = p.pick;
            L.pick_t = ImGui::GetTime();
            take_parts(a, call(a, "{\"call\":\"part_pick\",\"row\":" + std::to_string(a.row) + ",\"pick\":" +
                                      std::to_string(p.pick) + "}"));
        }
    }
    // THE KEYS, while searching
    if (L.typing && lib_keys(a, MX, Y1 - 5 * KH + 6, MW))
        L.typing = false;
}

}  // namespace nui
