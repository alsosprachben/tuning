// THE DRUMS CARD: the selected part's kit as pads, by kind -- a drum machine's
// buttons, the card's width; a pad struck as VEL says, lit as the keyboard,
// a file or the SEQ card plays it (the engine's hits). What a pad is, the
// kits and the user sets are the KITS card's (kits.h), sharing this state.
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
    int level = -1, pan = -1, rxon = -1, play = -1;    // (a user set's key: GS 21's 02, 04, 08, 01; -1 unset)
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
                if (k.a.size() >= 8) {
                    x.level = (int)k.a[4].d();
                    x.pan = (int)k.a[5].d();
                    x.rxon = (int)k.a[6].d();
                    x.play = (int)k.a[7].d();
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

// THE PADS' layout, shared by the card and the touch: the shown keys by kind,
// placed along rows (a group's name over its first pad)
struct PadPl {
    const DrumKey *k;
    int col, row;
    const char *head;
};
struct PadLayout {
    std::vector<PadPl> pl;
    std::vector<float> top;             // (each row's top, from the pads' top)
    float pw = 0, ph = 0, pg = 0, hh = 0, content = 0;
};
inline PadLayout pad_layout(App &a, float PW, bool user, bool sfx, std::vector<const DrumKey *> &shown)
{
    DrumsUi &D = g_drums;
    PadLayout L;
    const bool IP = a.tab, PH = a.ph;
    shown.clear();
    for (const auto &k : D.keys)
        if (!user || (k.key >= 27 && k.key <= 87) || !k.name.empty())
            shown.push_back(&k);
    static const char *ORDER[] = {N_("Kicks"), N_("Snares"), N_("Toms"), N_("Hi-hats"), N_("Cymbals"), N_("Percussion"), N_("Sounds"), N_("Not set")};
    std::map<std::string, std::vector<const DrumKey *>> groups;
    for (const DrumKey *k : shown)
        groups[user && k->name.empty() ? N_("Not set") : sfx ? N_("Sounds") : drum_kind(k->name)].push_back(k);
    const float pw_min = PH ? 118 : IP ? 128 : 150;
    L.ph = PH ? 66 : IP ? 84 : 96;
    L.pg = PH ? 6 : IP ? 6 : 8;
    L.hh = PH ? 20 : IP ? 22 : 26;
    const int cols = std::max(1, (int)((PW + L.pg) / (pw_min + L.pg)));
    L.pw = (PW - L.pg * (cols - 1)) / cols;
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
            L.pl.push_back({it->second[(size_t)i], c, r, i == 0 ? g : nullptr});
            c++;
        }
    }
    // (a row's pads' top: room above for a group's name only where one starts on it)
    std::vector<bool> headed((size_t)r + 1, false);
    for (const PadPl &q : L.pl)
        if (q.head)
            headed[(size_t)q.row] = true;
    L.top.assign((size_t)r + 1, 0);
    for (int i = 0; i <= r; i++)
        L.top[(size_t)i] = (i ? L.top[(size_t)i - 1] + L.ph + L.pg : 0) + (headed[(size_t)i] ? L.hh : 0);
    L.content = L.top[(size_t)r] + L.ph + L.pg;
    return L;
}

// THE DRUMS CARD: the pads alone, the card's width (the kits, what a pad is,
// the user sets: the KITS card). A strip at the right scrolls them without a
// pad struck; a finger drawn up the pads scrolls too (its pad let go)
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
    const bool IP = a.tab, PH = a.ph;
    const float X0 = PH ? 14 : IP ? 20 : 34, X1 = IP ? (PH ? 818 : 1113) : 1886, HY = PH ? 120 : IP ? 224 : 356;
    const float Y0 = PH ? 160 : IP ? 262 : 404, Y1 = card_y1(a) - (PH ? 2 : 0);
    const float TX = heading(a, X0, HY, T("DRUMS"), "drums");
    if (!D.d.is(J::OBJ))
        return;
    const std::string part_name = str(&D.d, "part");
    const bool drums = flag(&D.d, "drums"), user = D.d.get("user") != nullptr;
    // (the heading's right: KITS, then VEL)
    const float bh = PH ? 40 : 44, by = PH ? HY - 8 : HY - 10, B = 21;
    float bx = X1;
    auto hbtn = [&](const char *id, const std::string &lab, bool lit) {
        const float w = text_w(a, a.bold, B, lab) + 28;
        bx -= w;
        const bool hit = button(a, id, bx, by, w, bh, lab, lit, true, B);
        bx -= 8;
        return hit;
    };
    if (hbtn("drkits", T("KITS \xe2\x96\xb8"), false))
        a.card = "kits";
    if (drums && hbtn("drvel", TF("VEL {0}", {touch_says("drums")}), D.vel_open)) {
        D.vel_open = !D.vel_open;
        drums_release(a);
    }
    {
        std::string sub = TF("part {0} \xc2\xb7 {1}", {pad2(a.row + 1), part_name});
        if (g_touch.last_v >= 0 && drums)
            sub += " \xc2\xb7 " + TF("vel {0}", {std::to_string(g_touch.last_v)});
        text(a, a.font, 14, TX, HY + 1, OWN, fit(a, a.font, 14, sub, bx - TX - 4));
    }
    if (!drums) {
        const auto ls = wrap(a, a.font, 21, TF("{0} is not a drum set. Choose a kit for part {1} on the KITS card.",
                                               {part_name.empty() ? std::string(T("This part")) : part_name, pad2(a.row + 1)}), X1 - X0 - 20);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 21, X0 + 10, Y0 + 10 + i * (a.lh(21) + 6), SILK_DIM, ls[i]);
        return;
    }

    // THE PADS by kind, the strip at their right
    const float SB = PH ? 34 : IP ? 34 : 30;            // (the scroll strip's width)
    const float PX0 = X0, PX1 = X1 - SB - 8, SX = X1 - SB;
    const bool sfx = std::regex_search(part_name, std::regex("sfx|sound|effect", std::regex::icase));
    std::vector<const DrumKey *> shown;
    const PadLayout G = pad_layout(a, PX1 - PX0, user, sfx, shown);
    const auto &pl = G.pl;
    const auto &top = G.top;
    const float pw = G.pw, ph = G.ph, pg = G.pg, hh = G.hh;
    const float rowh = ph + pg, content = G.content, view = Y1 - Y0;
    D.scroll = std::max(0.0f, std::min(D.scroll, std::max(0.0f, content - view)));
    {   // (the wheel scrolls)
        const ImVec2 m = ImGui::GetIO().MousePos;
        const float mx = (m.x - a.org.x) / a.k, my = (m.y - a.org.y) / a.k;
        if (mx >= PX0 && mx < X1 && my >= Y0 && my < Y1 && ImGui::GetIO().MouseWheel != 0)
            D.scroll = std::max(0.0f, std::min(content - view, D.scroll - ImGui::GetIO().MouseWheel * rowh));
    }
    if (D.frow != a.row) {              // (another part: what this one held is let go)
        drums_release(a);
        D.frow = a.row;
    }
    // THE STRIP: a drag along it moves the pads (its thumb where they are); a tap
    // above or below its thumb a page that way
    {
        ImGui::SetCursorScreenPos(P(a, SX, Y0));
        ImGui::InvisibleButton("padstrip", ImVec2(SB * a.k, view * a.k));
        tap_yields(a);
        const float my = (ImGui::GetIO().MousePos.y - a.org.y) / a.k;
        const float bhh = content > view ? std::max(44.0f, view * view / content) : view;
        const float span = std::max(1.0f, view - bhh), smax = std::max(0.0f, content - view);
        if (ImGui::IsItemActive() && smax > 0) {
            const float want = (my - Y0 - bhh / 2) / span * smax;
            D.scroll = std::max(0.0f, std::min(want, smax));
            a.animate = true;
        }
        look::tray(a, SX, Y0, SB, view, SB / 2);
        const float by_ = Y0 + (smax > 0 ? span * D.scroll / smax : 0);
        rect(a, SX + 5, by_ + 4, SB - 10, bhh - 8, ImGui::IsItemActive() ? LCD : smax > 0 ? SILK_DIM : EDGE, (SB - 10) / 2);
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
        for (const PadPl &q : pl) {
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
            if (on_pads)                                // (a finger landing elsewhere -- the strip -- is not the pads')
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

    const double now = ImGui::GetTime();
    bool flashing = false;
    if (!D.vel_open) {
        dl()->PushClipRect(P(a, PX0, Y0), P(a, PX1, Y1), true);
        const float LH = a.lh(14) + (IP ? 2 : 3), ty0 = PH ? 5 : IP ? 7 : 9;
        for (const PadPl &q : pl) {
            const float x = PX0 + q.col * (pw + pg), y = Y0 + top[(size_t)q.row] - D.scroll;
            if (q.head)
                text(a, a.bold, 14, x, y - hh + 3, SILK, T(q.head));
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
            text(a, a.font, 14, x + 8, y + ty0, LCD, note_name_sharp(k.key));
            // (the drum's name, on up to two lines -- three where the pad is tall enough)
            const int nl = ph >= 90 ? 3 : 2;
            const auto ls = wrap(a, a.font, 14, k.name.empty() ? "\xe2\x80\x94" : k.name, pw - 14);
            for (size_t i = 0; i < ls.size() && (int)i < nl; i++)
                text(a, a.font, 14, x + 8, y + ty0 + 1 + (i + 1) * LH, unset ? SILK_DIM : SILK,
                     (int)i == nl - 1 && ls.size() > (size_t)nl ? fit(a, a.font, 14, ls[i] + "\xe2\x80\xa6", pw - 14) : ls[i]);
        }
        dl()->PopClipRect();
    }
    if (flashing)
        a.animate = true;
    for (auto it = D.flash.begin(); it != D.flash.end();)
        it = now - it->second.first > 0.5 ? D.flash.erase(it) : std::next(it);
}

}  // namespace nui
