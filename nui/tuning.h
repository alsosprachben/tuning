// THE TUNING CARD (ui/app.js's): the rig's tuner (every part: the patches
// built again in it), grouped by what it is for; its shape drawn -- an
// octave's notes in cents from equal temperament, and how far each key
// strays across the keyboard (stretch); the Eastern tuning the Indian
// voices play (a raga system, a raga, Sa).
#pragma once

#include "app.h"
#include "drums.h"

namespace nui {

struct TuningUi {
    bool open = false, lists = false, measured = false;
    J t;                                // (tuning_of: tuner, now, shape {a4, cents[128]}, eastern)
    std::vector<std::pair<std::string, std::string>> tuners;
    std::vector<std::string> systems, ragas;
    std::string pending;                // (the tuner asked for, till the engine has it)
    std::string east_mine;              // (the eastern spec this screen set, held a moment)
    double east_until = 0;
    float scroll = 0;
};
static TuningUi g_tn;

inline void tn_take(const J &r)
{
    TuningUi &T = g_tn;
    const J *t = r.get("tuning");
    if (!t)
        return;
    if (const J *ts = t->get("tuners"); ts && ts->is(J::ARR)) {
        T.lists = true;
        T.tuners.clear();
        T.systems.clear();
        T.ragas.clear();
        for (const J &x : ts->a)
            T.tuners.push_back({x.a[0].s, x.a.size() > 1 && x.a[1].is(J::STR) ? x.a[1].s : ""});
        if (const J *s = t->get("systems"); s && s->is(J::ARR))
            for (const J &x : s->a)
                T.systems.push_back(x.s);
        if (const J *s = t->get("ragas"); s && s->is(J::ARR))
            for (const J &x : s->a)
                T.ragas.push_back(x.s);
    }
    T.t = *t;
}
inline void tuning_card(App &a, bool open)
{
    TuningUi &T = g_tn;
    if (open == T.open)
        return;
    T.open = open;
    tn_take(call(a, std::string("{\"call\":\"tuning\",\"open\":") + (open ? "1" : "0") + ",\"lists\":" + (T.lists ? "0" : "1") + "}"));
}

// A SCROLLING AREA: a drag scrolls it, a still tap comes back as a point in its content
inline bool scroll_area(App &a, const char *id, float x, float y, float w, float h, float content, float &scroll, ImVec2 &tap)
{
    struct T {
        bool down = false, moved = false;
        ImVec2 p0{0, 0};
        float s0 = 0;
    };
    static std::map<std::string, T> ts;
    T &t = ts[id];
    scroll = std::max(0.0f, std::min(scroll, std::max(0.0f, content - h)));
    ImGui::SetCursorScreenPos(P(a, x, y));
    ImGui::InvisibleButton(id, ImVec2(w * a.k, h * a.k));
    const ImVec2 m = ImGui::GetIO().MousePos;
    const float mx = (m.x - a.org.x) / a.k, my = (m.y - a.org.y) / a.k;
    if (ImGui::IsItemHovered() && ImGui::GetIO().MouseWheel != 0)
        scroll = std::max(0.0f, std::min(std::max(0.0f, content - h), scroll - ImGui::GetIO().MouseWheel * 80));
    if (ImGui::IsItemActivated()) {
        t.down = true;
        t.moved = false;
        t.p0 = ImVec2(mx, my);
        t.s0 = scroll;
    }
    if (ImGui::IsItemActive() && t.down) {
        if (!t.moved && std::fabs(my - t.p0.y) * a.k > SLOP)
            t.moved = true;
        if (t.moved)
            scroll = std::max(0.0f, std::min(std::max(0.0f, content - h), t.s0 - (my - t.p0.y)));
    }
    bool tapped = false;
    if (ImGui::IsItemDeactivated() && t.down) {
        t.down = false;
        if (!t.moved) {
            tap = ImVec2(t.p0.x - x, t.p0.y - y + scroll);
            tapped = true;
        }
    }
    if (content > h) {
        const float bh = std::max(30.0f, h * h / content), by = y + (h - bh) * scroll / (content - h);
        rect(a, x + w - 4, by, 3, bh, SILK_DIM, 1);
    }
    return tapped;
}

// WORDS AS BUTTONS flowing along rows: the one hit (else -1); y advanced past them
inline int flow_buttons(App &a, const std::string &id, float x, float &y, float w, const std::vector<std::string> &words,
                        const std::vector<bool> &lit, float bh = 30, float ws = 0)
{
    float cx = x;
    int hit = -1;
    if (a.tab)                          // (fingers: 44 points the least each way, the words 3x unless asked)
        bh = std::max(bh, 44.0f);
    if (ws <= 0)
        ws = a.tab ? 21 : 14;
    for (size_t i = 0; i < words.size(); i++) {
        const float bw = std::max(a.tab ? 44.0f : 0.0f, text_w(a, a.font, ws, words[i]) + 18);
        if (cx > x && cx + bw > x + w) {
            cx = x;
            y += bh + 5;
        }
        const std::string bid = id + std::to_string(i);
        ImGui::SetCursorScreenPos(P(a, cx, y));
        if (ImGui::InvisibleButton(bid.c_str(), ImVec2(bw * a.k, bh * a.k)))
            hit = (int)i;
        const bool on = i < lit.size() && lit[i];
        look::chip(a, cx, y, bw, bh, on, ImGui::IsItemActive());
        text_c(a, a.font, ws, cx + bw / 2, y + (bh - a.lh(ws)) / 2, on ? LCD_BG : SILK, words[i]);
        cx += bw + 5;
    }
    y += bh + 8;
    return hit;
}

// "raga:<system>[/<raga>]@<sa>" taken apart, and put together
struct East {
    std::string system, raga, sa = "c#";
};
inline East east_parts(const std::string &e)
{
    East p;
    if (e.rfind("raga:", 0) != 0)
        return p;
    std::string b = e.substr(5);
    const size_t at = b.find('@');
    if (at != std::string::npos) {
        std::string sa = b.substr(at + 1);
        sa = sa.substr(0, sa.find(':'));
        if (!sa.empty())
            p.sa = sa;
        b = b.substr(0, at);
    }
    const size_t sl = b.find('/');
    p.system = b.substr(0, sl);
    if (sl != std::string::npos)
        p.raga = b.substr(sl + 1);
    return p;
}
inline std::string east_spec(const East &p)
{
    return p.system.empty() ? "" : "raga:" + p.system + (p.raga.empty() ? "" : "/" + p.raga) + "@" + p.sa;
}

inline void draw_tuning(App &a)
{
    TuningUi &T = g_tn;
    if (!T.t.is(J::OBJ))
        tn_take(call(a, "{\"call\":\"tuning\",\"open\":1,\"lists\":1}"));
    // (the iPad's: its card from y 210 to 734, two pages -- the tuners and their shape; the Eastern tuning)
    const bool IP = a.tab;
    static int page = 0;
    const float X0 = IP ? 20 : 34, X1 = IP ? 1113 : 1886, Y0 = IP ? 266 : 394, Y1 = IP ? 728 : 1056, HY = IP ? 224 : 356;
    const float LH = a.lh(14) + (IP ? 3 : 4);
    text(a, a.font, 14, heading(a, X0, HY, "TUNING", "tuning"), HY + 1, OWN, "every part");
    if (IP)
        for (int pg = 0; pg < 2; pg++) {
            const std::string id = "tnpage" + std::to_string(pg);
            if (button(a, id.c_str(), 300 + pg * 196, 216, 190, 44, pg ? "EASTERN" : "TUNERS", page == pg, true, 21))
                page = pg;
        }
    if (!T.t.is(J::OBJ) || !T.lists)
        return;
    const std::string tuner = str(&T.t, "tuner"), now = str(&T.t, "now");
    if (T.pending == tuner)
        T.pending.clear();
    const bool building = tuner != now;
    const std::string info = building ? "building the patches in " + tuner + "\xe2\x80\xa6" : "playing " + now;
    const std::string info_ = fit(a, a.font, 14, info, IP ? 300 : 900);
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info_), HY + 1, building ? OWN : SILK_DIM, info_);
    if (building)
        a.animate = true;

    // THE TUNERS, grouped by what they are for
    static const std::vector<std::pair<const char *, std::vector<std::string>>> GROUPS = {
        {"Concert pitch, A=440", {"gm2", "hybrid440", "hybridmeanpiano", "stretchedhelmholtz", "even"}},
        {"Baroque pitch, A=415", {"hybrid", "stretch", "werckmeister", "sankey", "meantone"}},
        {"Pure octaves: pipes", {"hybridharm", "hybridharm440", "hybridmean"}}};
    std::vector<std::pair<std::string, std::vector<const std::pair<std::string, std::string> *>>> groups;
    std::set<std::string> named;
    for (const auto &g : GROUPS) {
        std::vector<const std::pair<std::string, std::string> *> v;
        for (const auto &n : g.second) {
            named.insert(n);
            for (const auto &t : T.tuners)
                if (t.first == n)
                    v.push_back(&t);
        }
        groups.push_back({g.first, v});
    }
    std::vector<const std::pair<std::string, std::string> *> raga, other;
    for (const auto &t : T.tuners)
        if (t.first.rfind("raga:", 0) == 0)
            raga.push_back(&t);
        else if (!named.count(t.first))
            other.push_back(&t);
    groups.push_back({"Indian, every part", raga});
    groups.push_back({"Other systems", other});
    const float LW = IP ? 600 : 1070, cols = IP ? 2 : 3, gap = 8, tw = (LW - 10 - gap * (cols - 1)) / cols, th = 64, hh = 30;
    // (the layout, then the touch, then the drawing)
    struct Tile {
        const std::pair<std::string, std::string> *t;
        float x, y;
    };
    std::vector<Tile> tiles;
    std::vector<std::pair<std::string, float>> heads;
    float cy = 0;
    for (const auto &g : groups) {
        if (g.second.empty())
            continue;
        heads.push_back({g.first, cy});
        cy += hh;
        for (size_t i = 0; i < g.second.size(); i++)
            tiles.push_back({g.second[i], (i % (int)cols) * (tw + gap), cy + (i / (int)cols) * (th + gap)});
        cy += ((g.second.size() + (int)cols - 1) / (int)cols) * (th + gap) + 6;
    }
    ImVec2 tap;
    if (!IP || page == 0) {
    if (scroll_area(a, "tnlist", X0, Y0, LW, Y1 - Y0, cy, T.scroll, tap))
        for (const Tile &t : tiles)
            if (tap.x >= t.x && tap.x < t.x + tw && tap.y >= t.y && tap.y < t.y + th) {
                T.pending = t.t->first;
                tn_take(call(a, "{\"call\":\"tuner_set\",\"name\":\"" + t.t->first + "\"}"));
            }
    dl()->PushClipRect(P(a, X0, Y0), P(a, X0 + LW, Y1), true);
    for (const auto &h : heads) {
        std::string up = h.first;
        for (char &c : up)
            c = (char)toupper((unsigned char)c);
        text(a, a.bold, 14, X0, Y0 + h.second - T.scroll + 8, SILK, up);
    }
    for (const Tile &t : tiles) {
        const float x = X0 + t.x, y = Y0 + t.y - T.scroll;
        if (y + th < Y0 || y > Y1)
            continue;
        const bool cur = t.t->first == tuner && !building, pend = t.t->first == tuner && building || t.t->first == T.pending;
        look::chip(a, x, y, tw, th, cur);
        if (pend)
            frame(a, x, y, tw, th, LCD, 8, 2.0f);
        text(a, a.font, 14, x + 10, y + (IP ? 6 : 8), cur ? LCD_BG : LCD, fit(a, a.font, 14, t.t->first, tw - 20));
        const auto ls = wrap(a, a.font, 14, t.t->second, tw - 20);
        for (size_t i = 0; i < ls.size() && i < 2; i++)
            text(a, a.font, 14, x + 10, y + (IP ? 9 : 11) + (i + 1) * LH, cur ? LCD_BG : SILK_DIM,
                 i == 1 && ls.size() > 2 ? fit(a, a.font, 14, ls[i] + "\xe2\x80\xa6", tw - 20) : ls[i]);
    }
    dl()->PopClipRect();

    // THE SHAPE: an octave in cents from equal temperament; each octave's stretch across the keyboard
    }
    const float SX = X0 + LW + 12, SW = X1 - SX, SH = IP ? Y1 - Y0 : 330;
    if (!IP || page == 0) {
    look::tray(a, SX, Y0, SW, SH, 9);
    const float tsx = heading(a, SX + 12, Y0 + 10, "THE TUNING", "tn:shape");
    const J *shape = T.t.get("shape");
    const double a4 = num(shape, "a4");
    text(a, a.font, 14, tsx, Y0 + 11, LCD, tuner + (a4 > 0 ? " \xc2\xb7 A4 = " + jnum(a4) + " Hz" : ""));
    const J *cents = shape ? shape->get("cents") : nullptr;
    auto cv = [&](int n, double &v) {
        if (!cents || !cents->is(J::ARR) || n >= (int)cents->a.size() || !cents->a[(size_t)n].is(J::NUM))
            return false;
        v = cents->a[(size_t)n].d();
        return true;
    };
    const float gx = SX + 14, gw = SW - 28;
    if (!cents || !cents->is(J::ARR)) {
        text(a, a.font, 14, gx, Y0 + 150, SILK_DIM, "this tuner has no fixed table (it follows the file or the music)");
    } else {
        static const char *NN[12] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
        const float top = Y0 + 50, h1 = 96, mid = top + h1 / 2, sc = (h1 / 2) / 30, bw = gw / 12;
        text(a, a.font, 14, gx, Y0 + 32, SILK_DIM, "C4 to B4, cents from equal temperament");
        rect(a, gx, mid, gw, 1, IM_COL32(0x3a, 0x3f, 0x45, 255), 0);
        for (int i = 0; i < 12; i++) {
            const float x = gx + i * bw;
            double v;
            if (cv(60 + i, v)) {
                const float hh_ = std::max(-h1 / 2, std::min(h1 / 2, (float)v * sc));
                rect(a, x + bw * 0.2f, hh_ > 0 ? mid - hh_ : mid, bw * 0.6f, std::max(1.0f, std::fabs(hh_)), LCD, 0);
                char b[16];
                snprintf(b, sizeof b, std::fabs(v) < 10 ? "%+.1f" : "%+.0f", v);
                text_c(a, a.font, 14, x + bw / 2, hh_ > 0 ? mid - hh_ - a.lh(14) - 3 : mid - hh_ + 3, SILK, b);
            }
            text_c(a, a.font, 14, x + bw / 2, top + h1 + 4, SILK_DIM, NN[i]);
        }
        const float top2 = top + h1 + 50, h2 = 90, mid2 = top2 + h2 / 2, sc2 = (h2 / 2) / 40;
        text(a, a.font, 14, gx, top2 - 22, SILK_DIM, "A0 to C8: each octave's stretch from 2:1, in cents");
        rect(a, gx, mid2, gw, 1, IM_COL32(0x3a, 0x3f, 0x45, 255), 0);
        dl()->PathClear();
        for (int n = 21; n <= 108; n++) {
            double v, b;
            if (!cv(n, v) || !cv(60 + n % 12, b))
                continue;
            const float x = gx + (n - 21) / 87.0f * gw, yy = mid2 - std::max(-h2 / 2, std::min(h2 / 2, (float)(v - b) * sc2));
            dl()->PathLineTo(P(a, x, yy));
            if (n % 12 == 0)
                text_c(a, a.font, 14, x, top2 + h2 + 2, SILK_DIM, "C" + std::to_string(n / 12 - 1));
        }
        dl()->PathStroke(LCD, 0, 2.0f * a.k);
        text(a, a.font, 14, gx + gw - text_w(a, a.font, 14, "+40"), top2, SILK_DIM, "+40");
        text(a, a.font, 14, gx + gw - text_w(a, a.font, 14, "-40"), top2 + h2 - 14, SILK_DIM, "-40");
    }

    // THE EASTERN TUNING the Indian voices' parts play
    }
    if (IP && page == 0)
        return;
    // (the iPad's Eastern tuning a page across the card)
    const float EX = IP ? X0 : SX, EW = IP ? X1 - X0 : SW, EY = IP ? Y0 : Y0 + SH + 10;
    look::tray(a, EX, EY, EW, Y1 - EY, 9);
    text(a, a.font, 14, heading(a, EX + 12, EY + 10, "EASTERN TUNING", "tn:east"), EY + 11, LCD, "the Indian voices' parts");
    if (!T.east_mine.empty() && ImGui::GetTime() > T.east_until)
        T.east_mine.clear();
    East p = east_parts(T.east_mine.empty() ? str(&T.t, "eastern") : T.east_mine);
    const bool measured = p.system.rfind("saraga_", 0) == 0 || T.measured;
    bool changed = false;
    float ey = EY + 36;
    {
        std::vector<std::string> w = {"Off"};
        std::vector<bool> lit = {p.system.empty() && !T.measured};
        std::vector<std::string> sys;
        for (const auto &s : T.systems)
            if (s.rfind("saraga_", 0) != 0) {
                sys.push_back(s);
                w.push_back(s);
                lit.push_back(s == p.system);
            }
        w.push_back("measured ragas\xe2\x80\xa6");
        lit.push_back(measured);
        const int h = flow_buttons(a, "tnsys", EX + 12, ey, EW - 24, w, lit);
        if (h == 0) {
            p.system.clear();
            p.raga.clear();
            T.measured = false;
            changed = true;
        } else if (h == (int)w.size() - 1) {
            T.measured = true;
        } else if (h > 0) {
            p.system = sys[(size_t)h - 1];
            T.measured = false;
            changed = true;
        }
    }
    if (measured) {
        std::vector<std::string> w, sys;
        std::vector<bool> lit;
        for (const auto &s : T.systems)
            if (s.rfind("saraga_", 0) == 0) {
                std::string n = s.substr(7);
                std::replace(n.begin(), n.end(), '_', ' ');
                w.push_back(n);
                sys.push_back(s);
                lit.push_back(s == p.system);
            }
        const int h = flow_buttons(a, "tnmeas", EX + 12, ey, EW - 24, w, lit, 26);
        if (h >= 0) {
            p.system = sys[(size_t)h];
            p.raga.clear();
            changed = true;
        }
    } else if (!p.system.empty()) {
        std::vector<std::string> w = {"No raga"};
        std::vector<bool> lit = {p.raga.empty()};
        for (const auto &r : T.ragas) {
            w.push_back(r);
            lit.push_back(r == p.raga);
        }
        const int h = flow_buttons(a, "tnraga", EX + 12, ey, EW - 24, w, lit, 26);
        if (h >= 0) {
            p.raga = h ? T.ragas[(size_t)h - 1] : "";
            changed = true;
        }
    }
    if (!p.system.empty()) {
        static const std::vector<std::string> SA = {"c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"};
        std::vector<std::string> w;
        std::vector<bool> lit;
        for (const auto &k : SA) {
            std::string u = k;
            u[0] = (char)toupper((unsigned char)u[0]);
            w.push_back(u);
            lit.push_back(k == p.sa);
        }
        text(a, a.bold, 14, EX + 12, ey + ((IP ? 44 : 30) - a.lh(14)) / 2, SILK, "SA");
        const int h = flow_buttons(a, "tnsa", EX + 50, ey, EW - 62, w, lit, 30);
        if (h >= 0) {
            p.sa = SA[(size_t)h];
            changed = true;
        }
    }
    std::string sa_up = p.sa;
    if (!sa_up.empty())
        sa_up[0] = (char)toupper((unsigned char)sa_up[0]);
    std::string say;
    if (p.system.empty())
        say = "Off: the Indian instruments play the tuner above.";
    else {
        std::string sys = p.system;
        if (sys.rfind("saraga_", 0) == 0) {
            sys = sys.substr(7);
            std::replace(sys.begin(), sys.end(), '_', ' ');
            sys = "raga " + sys + " as measured (Saraga)";
        }
        say = "The Indian instruments' parts play " + sys + (p.raga.empty() ? "" : ", raga " + p.raga) + ", Sa on " + sa_up +
              " (unless the tuner above is itself Indian).";
    }
    for (const auto &l : wrap(a, a.font, 14, say, EW - 24)) {
        text(a, a.font, 14, EX + 12, ey, SILK_DIM, l);
        ey += LH;
    }
    if (changed) {
        T.east_mine = east_spec(p);
        T.east_until = ImGui::GetTime() + 1.5;
        tn_take(call(a, "{\"call\":\"eastern_set\",\"spec\":\"" + T.east_mine + "\"}"));
        if (T.east_mine.empty())
            T.east_mine = " ";          // (Off held too: a spec no system parses)
    }
}

}  // namespace nui
