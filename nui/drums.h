// THE DRUMS CARD (ui/app.js's): the selected part's kit as pads, by kind;
// a pad struck harder the higher it is touched, lit as the keyboard or a
// file plays it (the engine's hits). The kits down the side. A user set
// (GS's two): each key takes its sound from a key of any set. Beside the
// pads what the pad last touched is and what it was fitted to.
#pragma once

#include <functional>
#include <regex>

#include "app.h"
#include "library.h"
#include "piano.h"
#include "widgets.h"

namespace nui {

struct DrumKey {
    int key = 0, set = -1, skey = -1;
    std::string name;
};
struct DrumsUi {
    bool open = false;
    J d;                                // (drums_of: row, part, drums, kit, channel, keys, user?)
    std::vector<DrumKey> keys;
    J sets;                             // ([set, name, [[key, name]...]]...: the user sets' sources)
    int sel = -1, touched = -1, browse = -1, kit_was = -2;
    int down_key = -1;                  // (the pad held: released on lift)
    std::map<int, std::pair<double, int>> flash;   // key -> (when, velocity)
    float scroll = 0;
    std::map<std::string, float> list_scroll;
};
static DrumsUi g_drums;

inline void drums_take(App &a, const J &d)
{
    DrumsUi &D = g_drums;
    if ((int)num(&d, "row", -1) != a.row)
        return;
    if (const J *s = d.get("sets"); s && s->is(J::ARR))
        D.sets = *s;
    const int kit = (int)num(&d, "kit", -1);
    if (kit != D.kit_was) {
        D.sel = D.touched = D.browse = -1;
        D.scroll = 0;
        D.kit_was = kit;
    }
    D.d = d;
    D.keys.clear();
    if (const J *ks = d.get("keys"); ks && ks->is(J::ARR))
        for (const J &k : ks->a)
            if (k.is(J::ARR) && k.a.size() >= 2) {
                DrumKey x;
                x.key = (int)k.a[0].d();
                x.name = k.a[1].is(J::STR) ? k.a[1].s : "";
                if (k.a.size() >= 4) {
                    x.set = (int)k.a[2].d();
                    x.skey = (int)k.a[3].d();
                }
                D.keys.push_back(x);
            }
}
inline void drums_card(App &a, bool open)
{
    DrumsUi &D = g_drums;
    if (open == D.open)
        return;
    D.open = open;
    if (open)
        D.sel = -1;
    J r = call(a, std::string("{\"call\":\"drums\",\"open\":") + (open ? "1" : "0") + ",\"sets\":" +
                      (D.sets.is(J::ARR) ? "0" : "1") + "}");
    if (const J *x = r.get("drums"))
        drums_take(a, *x);
}
inline void drums_hits(const J &hits)
{
    for (const J &h : hits.a)
        if (h.is(J::ARR) && h.a.size() >= 2)
            g_drums.flash[(int)h.a[0].d()] = {ImGui::GetTime(), (int)h.a[1].d()};
}

// a pad's kind, from its name
inline std::string drum_kind(const std::string &nm)
{
    static const std::pair<const char *, std::regex> K[] = {
        {"Kicks", std::regex("kick|bass drum|\\bbd\\b", std::regex::icase)},
        {"Snares", std::regex("snare|rim|stick|clap|snap|brush", std::regex::icase)},
        {"Toms", std::regex("\\btom", std::regex::icase)},
        {"Hi-hats", std::regex("hat\\b|hi-?hat|\\bhh\\b", std::regex::icase)},
        {"Cymbals", std::regex("cymbal|crash|ride|splash|china|chinese", std::regex::icase)}};
    for (const auto &k : K)
        if (std::regex_search(nm, k.second))
            return k.first;
    return "Percussion";
}
// what the pad is (about.json: the kit's own notes, else the GM key's)
inline const J *drum_note(const J &about, int kit, int key)
{
    const J *kits = about.get("kits"), *perc = about.get("perc");
    if (!perc)
        return nullptr;
    const std::string ks = std::to_string(key);
    const J *own = kits ? kits->get(std::to_string(kit).c_str()) : nullptr;
    if (own && own->get(ks.c_str()))
        return own->get(ks.c_str());
    if (own)
        if (const J *ko = about.get("kit_only"); ko && ko->is(J::ARR))
            for (const J &x : ko->a)
                if ((int)x.d() == kit)
                    return nullptr;
    return perc->get(ks.c_str());
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
        if (t.moved)
            scroll = std::max(0.0f, std::min(t.s0 - (my - t.y0), std::max(0.0f, content - hgt)));
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

inline void draw_drums(App &a)
{
    DrumsUi &D = g_drums;
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    if ((int)num(&D.d, "row", -1) != a.row) {
        J r = call(a, "{\"call\":\"drums\",\"open\":1,\"sets\":" + std::string(D.sets.is(J::ARR) ? "0" : "1") + "}");
        if (const J *x = r.get("drums"))
            drums_take(a, *x);
    }
    const float X0 = 34, X1 = 1886, Y0 = 394, Y1 = 1056;
    text(a, a.bold, 14, X0, 356, SILK, "DRUMS");
    if (!D.d.is(J::OBJ))
        return;
    const std::string part_name = str(&D.d, "part");
    text(a, a.font, 14, X0 + 76, 357, OWN, "part " + pad2(a.row + 1) + " \xc2\xb7 " + part_name);
    const bool drums = flag(&D.d, "drums"), user = D.d.get("user") != nullptr;
    const int kit = (int)num(&D.d, "kit", -1);
    if (drums) {
        int nk = 0;
        for (const auto &k : D.keys)
            nk += !user || !k.name.empty();
        const int ch = (int)num(&D.d, "channel", -1);
        const std::string info = std::to_string(nk) + " key" + (nk == 1 ? "" : "s") + " \xc2\xb7 channel " +
                                 std::to_string(ch < 0 ? 10 : ch + 1);
        text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), 357, SILK_DIM, info);
    }

    // THE KITS down the side: a tap puts one on the part
    std::vector<const Patch *> kits;
    for (const Patch &p : L.patches)
        if (p.drums)
            kits.push_back(&p);
    const float KW = 250;
    {
        const int tap = scroll_list(a, "kits", X0, Y0, KW, Y1 - Y0, (int)kits.size(), 40, D.list_scroll["kits"], [&](int i, float y) {
            const Patch &p = *kits[(size_t)i];
            const bool cur = p.program == kit && drums;
            const bool pend = L.picking == p.pick;
            rect(a, X0, y, KW - 8, 36, cur ? LCD : IM_COL32(0x1f, 0x22, 0x26, 255), 6);
            if (pend)
                frame(a, X0, y, KW - 8, 36, LCD, 6, 1.5f);
            text(a, a.font, 14, X0 + 8, y + 11, cur ? LCD_BG : LCD, std::to_string(p.program));
            text(a, a.font, 14, X0 + 50, y + 11, cur ? LCD_BG : SILK, fit(a, a.font, 14, p.name, KW - 66));
        });
        if (tap >= 0) {
            L.picking = kits[(size_t)tap]->pick;
            call(a, "{\"call\":\"part_pick\",\"row\":" + std::to_string(a.row) + ",\"pick\":" + std::to_string(L.picking) + "}");
        }
        if (L.picking >= 0 && drums)
            for (const Patch *p : kits)
                if (p->pick == L.picking && p->program == kit)
                    L.picking = -1;
    }

    const float SW = 400, PX0 = X0 + KW + 8, PX1 = X1 - SW - 8, SX = X1 - SW;
    if (!drums) {
        const auto ls = wrap(a, a.font, 21, (part_name.empty() ? std::string("This part") : part_name) +
                                                " is not a drum set. Pick a kit for part " + pad2(a.row + 1) + " from the list.", PX1 - PX0 - 20);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 21, PX0 + 10, Y0 + 10 + i * 28, SILK_DIM, ls[i]);
        return;
    }

    // THE PADS by kind: groups flow along the rows, a group's name over its first pad
    std::vector<const DrumKey *> shown;
    for (const auto &k : D.keys)
        if (!user || (k.key >= 27 && k.key <= 87) || !k.name.empty())
            shown.push_back(&k);
    const bool sfx = std::regex_search(part_name, std::regex("sfx|sound|effect", std::regex::icase));
    static const char *ORDER[] = {"Kicks", "Snares", "Toms", "Hi-hats", "Cymbals", "Percussion", "Sounds", "Not set"};
    std::map<std::string, std::vector<const DrumKey *>> groups;
    for (const DrumKey *k : shown)
        groups[user && k->name.empty() ? "Not set" : sfx ? "Sounds" : drum_kind(k->name)].push_back(k);
    const float pw_min = 112, ph = 62, pg = 6, hh = 24;
    const float PW = PX1 - PX0 - 10;
    const int cols = std::max(1, (int)((PW + pg) / (pw_min + pg)));
    const float pw = (PW - pg * (cols - 1)) / cols;
    struct Pl {
        const DrumKey *k;
        int col, row;
        const char *head;
    };
    std::vector<Pl> pl;
    int r = 0, c = 0;
    for (const char *g : ORDER) {
        auto it = groups.find(g);
        if (it == groups.end())
            continue;
        const int n = (int)it->second.size();
        if (c > 0 && c + std::min(n, cols) > cols) {     // (a group that won't fit the row's rest: a new row)
            r++;
            c = 0;
        } else if (c > 0)
            c++;                                        // (a gap before it)
        for (int i = 0; i < n; i++) {
            if (c >= cols) {
                r++;
                c = 0;
            }
            pl.push_back({it->second[(size_t)i], c, r, i == 0 ? g : nullptr});
            c++;
        }
    }
    // (a row's pads' top: room above for a group's name only where one starts on it)
    std::vector<bool> headed((size_t)r + 1, false);
    for (const Pl &q : pl)
        if (q.head)
            headed[(size_t)q.row] = true;
    std::vector<float> top((size_t)r + 1, 0);
    for (int i = 0; i <= r; i++)
        top[(size_t)i] = (i ? top[(size_t)i - 1] + ph + pg : 0) + (headed[(size_t)i] ? hh : 0);
    const float rowh = ph + pg, content = top[(size_t)r] + ph + pg, view = Y1 - Y0;
    D.scroll = std::max(0.0f, std::min(D.scroll, std::max(0.0f, content - view)));
    {   // (the wheel scrolls; a drag along the edge's bar too)
        const ImVec2 m = ImGui::GetIO().MousePos;
        const float mx = (m.x - a.org.x) / a.k, my = (m.y - a.org.y) / a.k;
        if (mx >= PX0 && mx < PX1 && my >= Y0 && my < Y1 && ImGui::GetIO().MouseWheel != 0)
            D.scroll = std::max(0.0f, std::min(content - view, D.scroll - ImGui::GetIO().MouseWheel * rowh));
    }
    const J &about = L.about;
    const double now = ImGui::GetTime();
    bool flashing = false;
    dl()->PushClipRect(P(a, PX0, Y0), P(a, PX1, Y1), true);
    for (const Pl &q : pl) {
        const float x = PX0 + q.col * (pw + pg), y = Y0 + top[(size_t)q.row] - D.scroll;
        if (q.head)
            text(a, a.bold, 14, x, y - hh + 2, SILK, q.head);
        if (y + ph < Y0 || y > Y1)
            continue;
        const DrumKey &k = *q.k;
        const std::string id = "pad" + std::to_string(k.key);
        ImGui::SetCursorScreenPos(P(a, x, std::max(Y0, y)));
        ImGui::InvisibleButton(id.c_str(), ImVec2(pw * a.k, std::max(1.0f, std::min(y + ph, Y1) - std::max(Y0, y)) * a.k));
        if (ImGui::IsItemActivated()) {     // (down: struck, harder nearer its top)
            const float my = (ImGui::GetIO().MousePos.y - a.org.y) / a.k;
            const int v = std::max(20, std::min(127, (int)std::lround(127 - 100 * (my - y) / ph)));
            call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(a.row) + ",\"key\":" + std::to_string(k.key) +
                        ",\"v\":" + std::to_string(v) + "}");
            D.down_key = k.key;
            if (D.sel != k.key)
                D.browse = -1;
            D.sel = D.touched = k.key;
        }
        if (ImGui::IsItemDeactivated() && D.down_key == k.key) {
            call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(a.row) + ",\"key\":" + std::to_string(k.key) + ",\"v\":0}");
            D.down_key = -1;
        }
        const bool unset = user && k.name.empty(), sel = D.sel == k.key;
        rect(a, x, y, pw, ph, unset ? IM_COL32(0x1f, 0x22, 0x26, 255) : CAP, 9);
        // (lit as it is played: fading over 0.45 s, brighter for a harder hit)
        auto f = D.flash.find(k.key);
        if (f != D.flash.end()) {
            const double t = (now - f->second.first) / 0.45;
            if (t < 1) {
                const float al = (float)((1 - t) * (0.35 + 0.65 * f->second.second / 127.0));
                rect(a, x, y, pw, ph, IM_COL32(0xf0, 0xb1, 0x3a, (int)(al * 200)), 9);
                flashing = true;
            }
        }
        frame(a, x, y, pw, ph, sel ? LCD : EDGE, 9, sel ? 2.0f : 1.0f);
        const std::string kn = note_name_sharp(k.key);
        text(a, a.font, 14, x + 8, y + 7, LCD, kn);
        text(a, a.font, 14, x + 14 + text_w(a, a.font, 14, kn), y + 7, LCD_DIM, std::to_string(k.key));
        const auto ls = label_lines(a, a.font, 14, k.name.empty() ? "\xe2\x80\x94" : k.name, pw - 14);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, x + 8, y + 26 + i * 16, unset ? SILK_DIM : SILK, fit(a, a.font, 14, ls[i], pw - 14));
    }
    dl()->PopClipRect();
    if (content > view) {
        const float bh = std::max(30.0f, view * view / content), by = Y0 + (view - bh) * D.scroll / (content - view);
        ImGui::SetCursorScreenPos(P(a, PX1 - 14, Y0));
        ImGui::InvisibleButton("padbar", ImVec2(16 * a.k, view * a.k));
        if (ImGui::IsItemActive())
            D.scroll = std::max(0.0f, std::min(content - view, D.scroll + ImGui::GetIO().MouseDelta.y / a.k * content / view));
        rect(a, PX1 - 6, by, 4, bh, SILK_DIM, 2);
    }
    if (flashing)
        a.animate = true;
    for (auto it = D.flash.begin(); it != D.flash.end();)
        it = now - it->second.first > 0.5 ? D.flash.erase(it) : std::next(it);

    // THE SIDE: a user set's key (its sound from a key of any set); what the pad is
    float sy = Y0;
    if (user) {
        rect(a, SX, Y0, SW, 360, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
        if (D.sel < 0 || !D.sets.is(J::ARR)) {
            text(a, a.font, 14, SX + 12, Y0 + 12, SILK_DIM, "A user set: touch a pad to choose its sound.");
        } else {
            DrumKey e;
            e.key = D.sel;
            for (const auto &k : D.keys)
                if (k.key == D.sel)
                    e = k;
            const int ss = e.skey >= 0 ? e.set : -1;
            const int bs = D.browse >= 0 ? D.browse : ss;
            const J *set = nullptr;
            std::string ssname = "set " + std::to_string(ss);
            for (const J &x : D.sets.a) {
                if ((int)x.a[0].d() == bs)
                    set = &x;
                if ((int)x.a[0].d() == ss)
                    ssname = x.a[1].s;
            }
            text(a, a.bold, 14, SX + 12, Y0 + 10, SILK, "KEY " + note_name_sharp(D.sel));
            text(a, a.font, 14, SX + 100, Y0 + 10, LCD, std::to_string(D.sel));
            text(a, a.font, 14, SX + 12, Y0 + 32, SILK_DIM,
                 fit(a, a.font, 14, e.skey >= 0 ? "Plays " + e.name + " from " + ssname + "." : "No sound yet.", SW - 24));
            const float ly = Y0 + 58, lh = 360 - 66, cw = (SW - 32) / 2;
            const int ns = (int)D.sets.a.size();
            const int ts = scroll_list(a, "uksets", SX + 12, ly, cw, lh, ns, 30, D.list_scroll["uksets"], [&](int i, float y) {
                const J &x = D.sets.a[(size_t)i];
                const bool on = (int)x.a[0].d() == bs;
                rect(a, SX + 12, y, cw - 8, 27, on ? LCD : BTN, 4);
                text(a, a.font, 14, SX + 18, y + 6, on ? LCD_BG : SILK, fit(a, a.font, 14, x.a[1].s, cw - 20));
            });
            if (ts >= 0)
                D.browse = (int)D.sets.a[(size_t)ts].a[0].d();
            if (set) {
                const J &sk = set->a[2];
                const int tk = scroll_list(a, "ukkeys", SX + 20 + cw, ly, cw, lh, (int)sk.a.size(), 30, D.list_scroll["ukkeys"], [&](int i, float y) {
                    const J &x = sk.a[(size_t)i];
                    const bool on = (int)set->a[0].d() == ss && (int)x.a[0].d() == e.skey;
                    rect(a, SX + 20 + cw, y, cw - 8, 27, on ? LCD : BTN, 4);
                    const std::string nn = note_name_sharp((int)x.a[0].d());
                    text(a, a.bold, 14, SX + 26 + cw, y + 6, on ? LCD_BG : SILK, nn);
                    text(a, a.font, 14, SX + 34 + cw + text_w(a, a.bold, 14, nn), y + 6, on ? LCD_BG : SILK_DIM,
                         fit(a, a.font, 14, x.a[1].s, cw - 34 - text_w(a, a.bold, 14, nn)));
                });
                if (tk >= 0) {
                    const int u = (int)num(&D.d, "user");
                    call(a, "{\"call\":\"udrum_set\",\"set\":" + std::to_string(u) + ",\"key\":" + std::to_string(D.sel) +
                                ",\"code\":11,\"v\":" + std::to_string((int)set->a[0].d()) + "}");
                    call(a, "{\"call\":\"udrum_set\",\"set\":" + std::to_string(u) + ",\"key\":" + std::to_string(D.sel) +
                                ",\"code\":12,\"v\":" + std::to_string((int)sk.a[(size_t)tk].a[0].d()) + "}");
                    call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(a.row) + ",\"key\":" + std::to_string(D.sel) + ",\"v\":100}");
                    call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(a.row) + ",\"key\":" + std::to_string(D.sel) + ",\"v\":0}");
                    J rr = call(a, "{\"call\":\"drums\"}");
                    if (const J *x = rr.get("drums"))
                        drums_take(a, *x);
                }
            } else
                text(a, a.font, 14, SX + 20 + cw, ly + 6, SILK_DIM, "Choose a set.");
        }
        sy = Y0 + 368;
    }
    rect(a, SX, sy, SW, Y1 - sy, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
    if (D.touched < 0) {
        const auto ls = wrap(a, a.font, 14, "Touch a pad for what it is and what it was fitted to.", SW - 24);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, SX + 12, sy + 12 + i * 18, LCD_DIM, ls[i]);
        return;
    }
    DrumKey e;
    e.key = D.touched;
    for (const auto &k : D.keys)
        if (k.key == D.touched)
            e = k;
    int nkit = kit, nkey = D.touched;
    if (user) {
        if (e.skey < 0)
            return;
        nkit = e.set;
        nkey = e.skey;
    }
    const J *rn = drum_note(about, nkit, nkey);
    text(a, a.bold, 14, SX + 12, sy + 10, SILK, fit(a, a.bold, 14, note_name_sharp(D.touched) + " " + e.name, SW - 24));
    if (!rn || !rn->is(J::ARR) || rn->a.size() < 2) {
        text(a, a.font, 14, SX + 12, sy + 32, LCD_DIM, "No notes for this one.");
        return;
    }
    const int rt = (int)rn->a[0].d();
    const J *lv = about.get("levels");
    const auto rl = wrap(a, a.font, 14, std::to_string(rt) + " \xc2\xb7 " +
         (lv && lv->is(J::ARR) && rt >= 0 && rt < (int)lv->a.size() && lv->a[(size_t)rt].is(J::STR) ? lv->a[(size_t)rt].s : ""), SW - 24);
    for (size_t i = 0; i < rl.size(); i++)
        text(a, a.font, 14, SX + 12, sy + 30 + i * 18, LCD, rl[i]);
    const float by = sy + 36 + rl.size() * 18;
    const auto ls = wrap(a, a.font, 14, rn->a[1].is(J::STR) ? rn->a[1].s : "", SW - 24);
    const size_t maxl = (size_t)std::max(1.0f, (Y1 - by - 8) / 18);
    for (size_t i = 0; i < ls.size() && i < maxl; i++)
        text(a, a.font, 14, SX + 12, by + i * 18, SILK_DIM,
             i + 1 == maxl && ls.size() > maxl ? fit(a, a.font, 14, ls[i] + " \xe2\x80\xa6", SW - 24) : ls[i]);
}

}  // namespace nui
