// THE LIBRARY CARD (ui/app.js's): every patch the engine plays, by family
// (favourites, all, GM's sixteen, the drum kits, the MT-32's and CM-32P's
// own), or by search -- the words in its number, name and family; a tile's
// tap plays it on the part selected, its star keeps it among the
// favourites. The tiles scroll under a finger (a drag scrolls, a tap
// picks); the search has its own keys (a touch screen has no keyboard),
// and a keyboard's typing reaches it too. Under them, what the patch is
// and what it was fitted to (ui/about.json, the coverage notes).
#pragma once

#include <set>

#include "app.h"
#include "widgets.h"

namespace nui {

static const char *FAMILY_NAMES[16] = {"Piano", "Chromatic Perc.", "Organ", "Guitar", "Bass", "Strings", "Ensemble",
                                       "Brass", "Reed", "Pipe", "Synth Lead", "Synth Pad", "Synth Effects", "Ethnic",
                                       "Percussive", "Sound Effects"};

struct Patch {
    int pick = 0, program = 0, variation = 0;
    bool drums = false;
    std::string name, search;           // (search: its number, name and family, lower case)
};

struct LibUi {
    bool loaded = false, favs_kept = false;
    std::vector<Patch> patches;
    std::set<std::string> favs;
    std::string fam = "all", q, last_q;
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
    return p.drums ? "Drum kits" : p.variation == 127 ? "MT-32" : p.variation == 126 ? "CM-64 PCM"
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
    J r = call(a, "{\"call\":\"patches\"}");
    if (const J *ps = r.get("patches"); ps && ps->is(J::ARR))
        for (const J &x : ps->a) {
            Patch p;
            p.pick = (int)num(&x, "pick");
            p.program = (int)num(&x, "program");
            p.variation = (int)num(&x, "variation");
            p.drums = flag(&x, "drums");
            p.name = str(&x, "name");
            char b[16];
            snprintf(b, sizeof b, "%03d ", p.program);
            p.search = lower(b + p.name + " " + fam_label(p));
            L.patches.push_back(p);
        }
    J f = call(a, "{\"call\":\"favourites\"}");
    if (const J *fs = f.get("favourites"); fs && fs->is(J::ARR))
        for (const J &x : fs->a)
            if (x.is(J::STR))
                L.favs.insert(x.s);
    L.favs_kept = flag(&f, "kept");
    sess::load(a.ui_dir + "/about.json", L.about);
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

// WORDS WRAPPED to a width (design px): its lines
inline std::vector<std::string> wrap(App &a, ImFont *f, float size, const std::string &s, float w)
{
    std::vector<std::string> lines;
    std::string line, word;
    auto flush_word = [&]() {
        if (word.empty())
            return;
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

// THE ON-SCREEN KEYS (the web's osk): true when DONE
// THE SCREEN's OWN KEYS typing into q (a name's: with - and _); true on DONE
inline bool osk(App &a, std::string &q, float x, float y, float w, bool name = false, const char *done = "DONE")
{
    static const char *ROWS[4] = {"1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"};
    static const char *NROWS[4] = {"1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm_"};
    const char *const *rows = name ? NROWS : ROWS;
    const float kh = 50, gap = 6, kw = (w - gap * 9) / 10;
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
    if (button(a, "oskclear", x, ry, bw, kh, "CLEAR", false, true, ws))
        q.clear();
    if (button(a, "oskspace", x + bw + gap, ry, bw * 3 - gap, kh, "SPACE", false, true, ws))
        q += " ";
    if (button(a, "oskback", x + 4 * bw + gap, ry, bw - gap, kh, "\xe2\x86\x90", false, true, ws) && !q.empty()) {
        q.pop_back();
        while (!q.empty() && ((unsigned char)q.back() & 0xC0) == 0x80)
            q.pop_back();
    }
    return button(a, "oskdone", x + 5 * bw + 2 * gap, ry, bw - gap, kh, done, false, true, ws);
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
    std::vector<Fam> fams = {{"fav", "\xe2\x98\x85 Favourites"}, {"all", "All"}};
    for (int i = 0; i < 16; i++)
        fams.push_back({std::to_string(i), FAMILY_NAMES[i]});
    fams.push_back({"drums", "Drum kits"});
    fams.push_back({"mt32", "MT-32"});
    fams.push_back({"cm32p", "CM-64 PCM"});
    const bool T = a.tab;               // (the iPad's: its card from y 210 to 734)
    const float FX = T ? 20 : 34, FY = T ? 218 : 356, fw = T ? 196 : 196, fh = 44, fg = 6, Y1 = T ? 728 : 1056;
    const bool searching = !L.q.empty();
    float MX;
    if (T) {                            // (the families a column that scrolls, 44-point rows)
        static float fam_scroll = 0;
        const int tap = scroll_list(a, "fams", FX, FY, fw + 8, Y1 - FY, (int)fams.size(), fh + 4, fam_scroll, [&](int i, float y) {
            const bool on = !searching && L.fam == fams[(size_t)i].id;
            look::chip(a, FX, y, fw, fh, on);
            text(a, a.bold, 21, FX + 10, y + (fh - a.lh(21)) / 2, on ? PANEL : SILK, fit(a, a.bold, 21, fams[(size_t)i].label, fw - 20));
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
            if (button(a, id.c_str(), x, y, fw, fh, fams[i].label, !searching && L.fam == fams[i].id)) {
                L.fam = fams[i].id;
                L.q.clear();
                L.scroll = 0;
            }
        }
        MX = FX + 2 * fw + fg + 24;
    }
    // THE SEARCH and the count
    const float MW = (T ? 1105 : 1886) - MX, SY = T ? 216 : 350, SH = T ? 44 : 46, SW = T ? 330 : 560;
    look::lcd_window(a, MX, SY, SW, SH, L.typing);
    look::lcd_text(a, 21, MX + 12, SY + (SH - a.lh(21)) / 2, L.q.empty() ? LCD_DIM : LCD,
                   L.q.empty() ? std::string("Search patches") : L.q + (L.typing ? "_" : ""), !L.q.empty());
    look::glass(a, MX, SY, SW, SH);
    ImGui::SetCursorScreenPos(P(a, MX, SY));
    if (ImGui::InvisibleButton("search", ImVec2(SW * a.k, SH * a.k)))
        L.typing = true;
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
    snprintf(info, sizeof info, "%d patch%s \xc2\xb7 tap to play on part %02d%s", (int)list.size(),
             list.size() == 1 ? "" : "es", a.row + 1, L.favs_kept ? "" : " \xc2\xb7 (no session: stars are not kept)");
    const std::string info_ = fit(a, a.font, 14, info, MW - SW - 60);
    text(a, a.font, 14, MX + SW + 16, SY + 16, SILK_DIM, info_);
    heading(a, MX + SW + 16 + text_w(a, a.font, 14, info_) + 4, SY + 16, "", "library");   // (the card's ?)

    // THE NOTES on the part's patch (about.json: its rating, what it was fitted to)
    const float aboutH = T ? 86 : 150, TY = T ? 270 : 410, TB = (L.typing ? Y1 - 5 * 56 - 24 : Y1 - aboutH - 10);
    const float LH = a.lh(14) + (T ? 3 : 4);       // (a line of notes)
    const size_t ML = T ? 4 : 6;
    if (!L.typing && cur && !flag(cur, "drums")) {
        const std::string key = std::to_string((int)num(cur, "program")) + "." + std::to_string((int)num(cur, "variation"));
        const J *pr = L.about.get("programs");
        const J *e = pr ? pr->get(key) : nullptr;
        if (e && e->is(J::ARR) && e->a.size() >= 2) {
            const int r = (int)e->a[0].d();
            const J *lv = L.about.get("levels");
            const std::string lvl = lv && lv->is(J::ARR) && r >= 0 && r < (int)lv->a.size() && lv->a[(size_t)r].is(J::STR)
                                        ? lv->a[(size_t)r].s : "";
            const float ay = Y1 - aboutH;
            look::tray(a, MX, ay, MW, aboutH, 8);
            text(a, a.bold, 14, MX + 12, ay + 8, SILK, fit(a, a.bold, 14, str(cur, "name"), MW - 400));
            const std::string rt = std::to_string(r) + " \xc2\xb7 " + lvl;
            text(a, a.font, 14, MX + MW - 12 - text_w(a, a.font, 14, rt), ay + 8, LCD, rt);
            const auto lines = wrap(a, a.font, 14, e->a[1].is(J::STR) ? e->a[1].s : "", MW - 24);
            for (size_t i = 0; i < lines.size() && i < ML; i++)
                text(a, a.font, 14, MX + 12, ay + 12 + LH * (i + 1), SILK_DIM,
                     i + 1 == ML && lines.size() > ML ? fit(a, a.font, 14, lines[i] + " \xe2\x80\xa6", MW - 24) : lines[i]);
        }
    }

    // THE TILES: a grid that scrolls under a finger
    const float tw_min = T ? 200 : 280, th = T ? 48 : 54, gap = T ? 6 : 8, star = T ? 44 : 52;
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
                text(a, a.font, 14, x + 10, y + (th - h14) / 2, nc, "KIT");
                text(a, a.font, 21, x + 14 + text_w(a, a.font, 14, "KIT"), y + (th - h21) / 2, nc, std::to_string(p.program));
                name_x = std::max(name_x, 18 + text_w(a, a.font, 14, "KIT") + text_w(a, a.font, 21, std::to_string(p.program)));
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
            text(a, a.font, 14, x + name_x, y + (th - h14) / 2, isc ? LCD_BG : SILK, fit(a, a.font, 14, p.name, tw - name_x - star - 4));
            text(a, a.font, 21, x + tw - star + (star - text_w(a, a.font, 21, "\xe2\x98\x85")) / 2, y + (th - h21) / 2,
                 fav ? (isc ? LCD_BG : LCD) : (isc ? LCD_DIM : SILK_DIM), "\xe2\x98\x85");
        }
    if (list.empty())
        text(a, a.font, 21, MX, TY + 10, SILK_DIM,
             L.fam == "fav" && !searching ? "No favourites yet: tap a patch's star to keep it here." : "Nothing matches.");
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
    if (L.typing && lib_keys(a, MX, Y1 - 5 * 56 + 6, MW))
        L.typing = false;
}

}  // namespace nui
