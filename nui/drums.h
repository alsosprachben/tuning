// THE DRUMS CARD (the retired web interface's): the selected part's kit as pads, by kind;
// a pad struck harder the higher it is touched, lit as the keyboard or a
// file plays it (the engine's hits). The kits down the side. A user set
// (GS's two): each key takes its sound from a key of any set. Beside the
// pads what the pad last touched is, and the set it borrows from.
#pragma once

#include <functional>
#include <regex>

#include "app.h"
#include "library.h"
#include "piano.h"
#include "touchvel.h"
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
    Fingers F;                          // (each finger the pad it struck: let go on its lift)
    int frow = -1;                      // (the part its pads were struck on)
    std::map<unsigned long long, ImVec2> f0, flast;   // (each finger where it landed, where it was last frame)
    unsigned long long sfinger = 0;     // (the finger scrolling the pads, when pdrag)
    bool vel_open = false;
    std::map<int, std::pair<double, int>> flash;   // key -> (when, velocity)
    float scroll = 0;
    bool pdrag = false;                 // (a finger on the pads dragged: the pads scrolled by it)
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
// (every pad held let go: the card shut, the part changed)
inline void drums_release(App &a)
{
    DrumsUi &D = g_drums;
    fingers_release(D.F, [&](int k) {
        if (D.frow >= 0)
            call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(D.frow) + ",\"key\":" + std::to_string(k) + ",\"v\":0}");
    });
    D.f0.clear();
    D.flast.clear();
    D.pdrag = false;
}
inline void drums_card(App &a, bool open)
{
    DrumsUi &D = g_drums;
    if (open == D.open)
        return;
    D.open = open;
    if (open)
        D.sel = -1;
    else
        drums_release(a);
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
        {N_("Kicks"), std::regex("kick|bass drum|\\bbd\\b", std::regex::icase)},   // i18n-skip
        {N_("Snares"), std::regex("snare|rim|stick|clap|snap|brush", std::regex::icase)},
        {N_("Toms"), std::regex("\\btom", std::regex::icase)},
        {N_("Hi-hats"), std::regex("hat\\b|hi-?hat|\\bhh\\b", std::regex::icase)},   // i18n-skip
        {N_("Cymbals"), std::regex("cymbal|crash|ride|splash|china|chinese", std::regex::icase)}};
    for (const auto &k : K)
        if (std::regex_search(nm, k.second))
            return k.first;
    return N_("Percussion");
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
    const bool IP = a.tab;              // (the iPad's: its card from y 210 to card_y1 + 6)
    const float X0 = IP ? 20 : 34, X1 = IP ? (a.ph ? 818 : 1113) : 1886, Y0 = IP ? 260 : 394, Y1 = card_y1(a), HY = IP ? 224 : 356;
    const float LH = a.lh(14) + (IP ? 3 : 4);
    const float TX = heading(a, X0, HY, T("DRUMS"), "drums");
    if (!D.d.is(J::OBJ))
        return;
    const std::string part_name = str(&D.d, "part");
    const bool drums = flag(&D.d, "drums"), user = D.d.get("user") != nullptr;
    const int kit = (int)num(&D.d, "kit", -1);
    float hx1 = X1;                     // (the heading's right: VEL, then what the set has)
    if (drums) {
        const std::string vl = TF("VEL {0}", {touch_says("drums")});
        const float bw = text_w(a, a.bold, 14, vl) + 24, bh = IP ? 40 : 44;
        if (button(a, "drvel", X1 - bw, HY - (IP ? 8 : 10), bw, bh, vl, D.vel_open, true)) {
            D.vel_open = !D.vel_open;
            drums_release(a);
        }
        hx1 = X1 - bw - 14;
    }
    {
        std::string sub = TF("part {0} \xc2\xb7 {1}", {pad2(a.row + 1), part_name});
        if (g_touch.last_v >= 0)
            sub += " \xc2\xb7 " + TF("vel {0}", {std::to_string(g_touch.last_v)});
        text(a, a.font, 14, TX, HY + 1, OWN, fit(a, a.font, 14, sub, hx1 - TX - (IP ? 190 : 260)));
    }
    if (drums) {
        int nk = 0;
        for (const auto &k : D.keys)
            nk += !user || !k.name.empty();
        const int ch = (int)num(&D.d, "channel", -1);
        const std::string info = nk == 1 ? TF("{0} key \xc2\xb7 channel {1}", {std::to_string(nk), std::to_string(ch < 0 ? 10 : ch + 1)})
                                         : TF("{0} keys \xc2\xb7 channel {1}", {std::to_string(nk), std::to_string(ch < 0 ? 10 : ch + 1)});
        text(a, a.font, 14, hx1 - text_w(a, a.font, 14, info), HY + 1, SILK_DIM, info);
    }

    // THE KITS down the side: a tap puts one on the part
    std::vector<const Patch *> kits;
    for (const Patch &p : L.patches)
        if (p.drums)
            kits.push_back(&p);
    const float KW = IP ? 190 : 250, KR = IP ? 48 : 40, KB = IP ? 44 : 36;   // (a kit's row; its button)
    {
        const int tap = scroll_list(a, "kits", X0, Y0, KW, Y1 - Y0, (int)kits.size(), KR, D.list_scroll["kits"], [&](int i, float y) {
            const Patch &p = *kits[(size_t)i];
            const bool cur = p.program == kit && drums;
            const bool pend = L.picking == p.pick;
            look::chip(a, X0, y, KW - 8, KB, cur);
            if (pend)
                frame(a, X0, y, KW - 8, KB, LCD, 6, 1.5f);
            const float ty = y + (KB - a.lh(14)) / 2, nx = IP ? 36 : 50;
            text(a, a.font, 14, X0 + 8, ty, cur ? LCD_BG : LCD, std::to_string(p.program));
            text(a, a.font, 14, X0 + nx, ty, cur ? LCD_BG : SILK, fit(a, a.font, 14, p.name, KW - nx - 16));
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

    const float SW = IP ? 280 : 400, PX0 = X0 + KW + 8, PX1 = X1 - SW - 8, SX = X1 - SW;
    if (!drums) {
        const auto ls = wrap(a, a.font, 21, TF("{0} is not a drum set. Pick a kit for part {1} from the list.",
                                               {part_name.empty() ? std::string(T("This part")) : part_name, pad2(a.row + 1)}), PX1 - PX0 - 20);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 21, PX0 + 10, Y0 + 10 + i * (a.lh(21) + 6), SILK_DIM, ls[i]);
        return;
    }

    // THE PADS by kind: groups flow along the rows, a group's name over its first pad
    std::vector<const DrumKey *> shown;
    for (const auto &k : D.keys)
        if (!user || (k.key >= 27 && k.key <= 87) || !k.name.empty())
            shown.push_back(&k);
    const bool sfx = std::regex_search(part_name, std::regex("sfx|sound|effect", std::regex::icase));
    static const char *ORDER[] = {N_("Kicks"), N_("Snares"), N_("Toms"), N_("Hi-hats"), N_("Cymbals"), N_("Percussion"), N_("Sounds"), N_("Not set")};
    std::map<std::string, std::vector<const DrumKey *>> groups;
    for (const DrumKey *k : shown)
        groups[user && k->name.empty() ? N_("Not set") : sfx ? N_("Sounds") : drum_kind(k->name)].push_back(k);
    const float pw_min = IP ? 96 : 112, ph = IP ? 70 : 82, pg = IP ? 5 : 6, hh = IP ? 18 : 24;
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
    {   // (the wheel scrolls)
        const ImVec2 m = ImGui::GetIO().MousePos;
        const float mx = (m.x - a.org.x) / a.k, my = (m.y - a.org.y) / a.k;
        if (mx >= PX0 && mx < PX1 && my >= Y0 && my < Y1 && ImGui::GetIO().MouseWheel != 0)
            D.scroll = std::max(0.0f, std::min(content - view, D.scroll - ImGui::GetIO().MouseWheel * rowh));
    }
    if (D.frow != a.row) {              // (another part: what this one held is let go)
        drums_release(a);
        D.frow = a.row;
    }

    // (VEL open: its settings over the pads, which wait)
    if (D.vel_open) {
        look::tray(a, PX0, Y0, PX1 - PX0, view, 9);
        float y = Y0 + 14;
        text(a, a.bold, 14, PX0 + 14, y, SILK, T("HOW HARD A TOUCH PLAYS ON THESE PADS"));
        y += a.lh(14) + 10;
        if (touch_panel(a, "drv", g_touch.drums, &g_touch.drums_own, PX0 + 14, y, PX1 - PX0 - 28))
            touch_save(a);
        for (const auto &l : wrap(a, a.font, 14, T("Position: the pad's top plays hardest. VEL again to play."), PX1 - PX0 - 28)) {
            text(a, a.font, 14, PX0 + 14, y + 4, SILK_DIM, l);
            y += a.lh(14) + 3;
        }
    }

    // THE TOUCH: each finger the pad it lands on, struck once (a slide does not strike another); a
    // finger alone that travels along the pads scrolls them instead -- its pad let go -- and past
    // their ends a scrolled card. The mouse plays where nothing has touched the glass.
    auto pad_at = [&](float x, float y, int &v) {
        if (x < PX0 || x >= PX1 || y < Y0 || y >= Y1)
            return -1;
        for (const Pl &q : pl) {
            const float px = PX0 + q.col * (pw + pg), py = Y0 + top[(size_t)q.row] - D.scroll;
            if (x >= px && x < px + pw && y >= py && y < py + ph) {
                v = touch_velocity_by(touch_for("drums"), 1 - (y - py) / ph);   // (the top the hard end)
                return q.k->key;
            }
        }
        return -1;
    };
    bool mouse_on = false;
    if (!D.vel_open) {
        ImGui::SetCursorScreenPos(P(a, PX0, Y0));
        ImGui::InvisibleButton("padsbed", ImVec2((PX1 - PX0) * a.k, view * a.k));
        mouse_on = ImGui::IsItemActive() && !a.touch_seen;
    }
    std::map<unsigned long long, ImVec2> pts;   // (each finger on the pads, in card units)
    if (!D.vel_open) {
        for (const auto &t : a.touches)
            pts[t.first] = ImVec2((t.second.x - a.org.x) / a.k, (t.second.y - a.org.y) / a.k);
        if (mouse_on) {
            const ImVec2 m = ImGui::GetIO().MousePos;
            pts[~0ull] = ImVec2((m.x - a.org.x) / a.k, (m.y - a.org.y) / a.k);
        }
    }
    for (auto it = D.f0.begin(); it != D.f0.end();)     // (lifted: forgotten)
        if (!pts.count(it->first)) {
            D.flast.erase(it->first);
            if (D.pdrag && D.sfinger == it->first)
                D.pdrag = false;
            it = D.f0.erase(it);
        } else
            ++it;
    for (const auto &p : pts)
        if (!D.f0.count(p.first)) {
            const bool on_pads = p.second.x >= PX0 && p.second.x < PX1 && p.second.y >= Y0 && p.second.y < Y1;
            if (on_pads)                                // (a finger landing elsewhere is not the pads')
                D.f0[p.first] = D.flast[p.first] = p.second;
        }
    if (!D.pdrag && D.f0.size() == 1) {                 // (one finger, travelled along: a scroll)
        const auto &f = *D.f0.begin();
        const ImVec2 at = pts[f.first];
        const float dy = at.y - f.second.y, dx = at.x - f.second.x;
        if (std::fabs(dy) > 12 && std::fabs(dy) > 1.5f * std::fabs(dx)) {
            D.pdrag = true;
            D.sfinger = f.first;
        }
    }
    std::map<unsigned long long, std::pair<int, int>> fnow;
    for (const auto &f : D.f0) {
        if (D.pdrag && f.first == D.sfinger)
            continue;                                   // (the scrolling finger holds no pad)
        int v = 0;
        const ImVec2 at = pts[f.first];
        fnow[f.first] = {pad_at(at.x, at.y, v), v};
    }
    fingers_step(D.F, fnow, false, [&](int k, int v) {
        call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(a.row) + ",\"key\":" + std::to_string(k) +
                    ",\"v\":" + std::to_string(v) + "}");
        g_touch.last_v = v;
        if (D.sel != k)
            D.browse = -1;
        D.sel = D.touched = k;
    }, [&](int k) { call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(a.row) + ",\"key\":" + std::to_string(k) + ",\"v\":0}"); });
    if (D.pdrag) {                                      // (the pads follow it; past their ends, a scrolled card)
        const ImVec2 at = pts[D.sfinger];
        const float want = D.scroll - (at.y - D.flast[D.sfinger].y);
        D.scroll = std::max(0.0f, std::min(want, std::max(0.0f, content - view)));
        if (a.vcard)
            a.vcard_push += want - D.scroll;
    }
    for (auto &f : D.flast)
        if (pts.count(f.first))
            f.second = pts[f.first];
    if (!D.f0.empty())
        a.animate = true;

    const J &about = L.about;
    const double now = ImGui::GetTime();
    bool flashing = false;
    if (!D.vel_open) {
    dl()->PushClipRect(P(a, PX0, Y0), P(a, PX1, Y1), true);
    for (const Pl &q : pl) {
        const float x = PX0 + q.col * (pw + pg), y = Y0 + top[(size_t)q.row] - D.scroll;
        if (q.head)
            text(a, a.bold, 14, x, y - hh + 2, SILK, T(q.head));
        if (y + ph < Y0 || y > Y1)
            continue;
        const DrumKey &k = *q.k;
        const bool unset = user && k.name.empty(), sel = D.sel == k.key;
        if (unset)
            look::tray(a, x, y, pw, ph, 9);
        else
            look::key_cap(a, x, y, pw, ph, false, true);
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
        text(a, a.font, 14, x + 8, y + (IP ? 5 : 7), LCD, kn);
        // (its MIDI key number at the pad's right, apart from the note name)
        const std::string kk = std::to_string(k.key);
        text(a, a.font, 14, x + pw - 8 - text_w(a, a.font, 14, kk), y + (IP ? 5 : 7), SILK_DIM, kk);
        // (the drum's name whole, on up to three lines)
        const auto ls = wrap(a, a.font, 14, k.name.empty() ? "\xe2\x80\x94" : k.name, pw - 14);
        for (size_t i = 0; i < ls.size() && i < 3; i++)
            text(a, a.font, 14, x + 8, y + (IP ? 6 : 8) + (i + 1) * (a.lh(14) + (IP ? 2 : 3)), unset ? SILK_DIM : SILK, ls[i]);
    }
    dl()->PopClipRect();
    if (content > view) {               // (the scroll's place, at the right)
        const float bh = std::max(30.0f, view * view / content), by = Y0 + (view - bh) * D.scroll / (content - view);
        rect(a, PX1 - 6, by, 4, bh, SILK_DIM, 2);
    }
    }
    if (flashing)
        a.animate = true;
    for (auto it = D.flash.begin(); it != D.flash.end();)
        it = now - it->second.first > 0.5 ? D.flash.erase(it) : std::next(it);

    // THE SIDE: a user set's key (its sound from a key of any set); what the pad is
    float sy = Y0;
    if (user) {
        const float UH = IP ? 270 : 360;   // (the user set's panel)
        look::tray(a, SX, Y0, SW, UH, 9);
        if (D.sel < 0 || !D.sets.is(J::ARR)) {
            text(a, a.font, 14, SX + 12, Y0 + 12, SILK_DIM, T("A user set: touch a pad to choose its sound."));
        } else {
            DrumKey e;
            e.key = D.sel;
            for (const auto &k : D.keys)
                if (k.key == D.sel)
                    e = k;
            const int ss = e.skey >= 0 ? e.set : -1;
            const int bs = D.browse >= 0 ? D.browse : ss;
            const J *set = nullptr;
            std::string ssname = TF("set {0}", {std::to_string(ss)});
            for (const J &x : D.sets.a) {
                if ((int)x.a[0].d() == bs)
                    set = &x;
                if ((int)x.a[0].d() == ss)
                    ssname = x.a[1].s;
            }
            const float kx = heading(a, SX + 12, Y0 + 10, TF("KEY {0}", {note_name_sharp(D.sel)}), "drums:user");   // i18n-skip (a help key)
            text(a, a.font, 14, kx, Y0 + 10, LCD, std::to_string(D.sel));
            text(a, a.font, 14, SX + 12, Y0 + 14 + LH, SILK_DIM,
                 fit(a, a.font, 14, e.skey >= 0 ? TF("Plays {0} from {1}.", {e.name, ssname}) : std::string(T("No sound yet.")), SW - 24));
            const float ly = Y0 + 20 + 2 * LH, lh = UH - (ly - Y0) - 8, cw = (SW - 32) / 2, LR = IP ? 48 : 30, LB = IP ? 44 : 27;
            const int ns = (int)D.sets.a.size();
            const int ts = scroll_list(a, "uksets", SX + 12, ly, cw, lh, ns, LR, D.list_scroll["uksets"], [&](int i, float y) {
                const J &x = D.sets.a[(size_t)i];
                const bool on = (int)x.a[0].d() == bs;
                look::chip(a, SX + 12, y, cw - 8, LB, on);
                text(a, a.font, 14, SX + 18, y + (LB - a.lh(14)) / 2, on ? LCD_BG : SILK, fit(a, a.font, 14, x.a[1].s, cw - 20));
            });
            if (ts >= 0)
                D.browse = (int)D.sets.a[(size_t)ts].a[0].d();
            if (set) {
                const J &sk = set->a[2];
                const int tk = scroll_list(a, "ukkeys", SX + 20 + cw, ly, cw, lh, (int)sk.a.size(), LR, D.list_scroll["ukkeys"], [&](int i, float y) {
                    const J &x = sk.a[(size_t)i];
                    const bool on = (int)set->a[0].d() == ss && (int)x.a[0].d() == e.skey;
                    look::chip(a, SX + 20 + cw, y, cw - 8, LB, on);
                    const std::string nn = note_name_sharp((int)x.a[0].d());
                    text(a, a.bold, 14, SX + 26 + cw, y + (LB - a.lh(14)) / 2, on ? LCD_BG : SILK, nn);
                    text(a, a.font, 14, SX + 34 + cw + text_w(a, a.bold, 14, nn), y + (LB - a.lh(14)) / 2, on ? LCD_BG : SILK_DIM,
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
                text(a, a.font, 14, SX + 20 + cw, ly + 6, SILK_DIM, T("Choose a set."));
        }
        sy = Y0 + UH + 8;
    }
    look::tray(a, SX, sy, SW, Y1 - sy, 9);
    if (D.touched < 0) {
        const auto ls = wrap(a, a.font, 14, T("Touch a pad for what it is."), SW - 24);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, SX + 12, sy + 12 + i * LH, LCD_DIM, ls[i]);
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
    // the pad's key and name (whole, wrapped), and the set it borrows from when it does
    const J *rn = drum_note(about, nkit, nkey);
    float y = sy + 10;
    for (const auto &l : wrap(a, a.bold, 14, note_name_sharp(D.touched) + " " + e.name, SW - 24)) {
        text(a, a.bold, 14, SX + 12, y, SILK, l);
        y += LH;
    }
    const std::string w = rn && rn->is(J::STR) ? rn->s : std::string(T("its own sound"));
    for (const auto &l : wrap(a, a.font, 14, w, SW - 24)) {
        text(a, a.font, 14, SX + 12, y + 4, w.rfind("stand-in", 0) == 0 ? LCD : SILK_DIM, l);   // i18n-skip (the engine's note, compared)
        y += LH;
    }
}

}  // namespace nui
