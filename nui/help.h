// THE HELP (the retired web help's viewer): a ? beside every card's name and its
// titled regions (heading()), and the ? key after the card keys, each
// opening the viewer at its topic -- the contents and a search on the left,
// the topic on the right: each button and control by the words printed on
// it and what it does, the guides step by step, links to the topics near
// it, and the card it describes to go to. The topics are help_text.py's,
// as ui/help.json (examples/help_json.py).
#pragma once

#include "app.h"
#include "library.h"
#include "tuning.h"

namespace nui {

struct HelpUi {
    bool loaded = false, typing = false;
    unsigned gen = 0;                   // (the language it was loaded in: i18n().gen; a new language loads it again)
    J help, toc;
    std::string cur, q;
    std::vector<std::string> hist;
    float scroll_nav = 0, scroll_page = 0;
};
static HelpUi g_help;

inline void help_load(App &a)
{
    HelpUi &H = g_help;
    H.loaded = true;
    H.gen = i18n().gen;
    // (the language's own help, ui/help.<code>.json -- help_json.py's, English where untranslated -- else English)
    J j;
    const std::string code = i18n().code;
    if ((code != "en" && sess::load(a.ui_dir + "/help." + code + ".json", j)) || sess::load(a.ui_dir + "/help.json", j)) {
        if (const J *h = j.get("help"))
            H.help = *h;
        if (const J *t = j.get("toc"))
            H.toc = *t;
    }
}
inline const J *topic(const std::string &k) { return g_help.help.get(k.c_str()); }
inline std::string help_text_of(const std::string &k)       // (a topic's words, for the search)
{
    const J *h = topic(k);
    if (!h)
        return "";
    std::string s = str(h, "title") + " " + str(h, "intro");
    if (const J *st = h->get("steps"); st && st->is(J::ARR))
        for (const J &x : st->a)
            s += " " + (x.is(J::STR) ? x.s : "");
    if (const J *ts = h->get("terms"); ts && ts->is(J::ARR))
        for (const J &t : ts->a)
            if (t.is(J::STR))
                s += " " + t.s;
            else if (t.is(J::ARR))
                for (const J &x : t.a)
                    s += " " + (x.is(J::STR) ? x.s : "");
    return lower(s);
}
inline const J *group_of(const std::string &k)
{
    if (g_help.toc.is(J::ARR))
        for (const J &g : g_help.toc.a)
            for (const J &x : g.a[1].a)
                if (x.is(J::STR) && x.s == k)
                    return &g;
    return nullptr;
}
inline std::string card_of(const std::string &k)
{
    static const std::map<std::string, std::string> C = {
        {"synth", "synth"}, {"drive", "stops"},   {"stops", "stops"},     {"piano", "piano"},     {"drums", "drums"},
        {"fx", "effects"},  {"effects", "effects"}, {"matrix", "matrix"}, {"tn", "tuning"},       {"tuning", "tuning"},
        {"ct", "control"},  {"control", "control"}, {"sc", "scenes"},     {"scenes", "scenes"},   {"su", "setup"},
        {"setup", "setup"}, {"parts", "parts"},   {"library", "library"}, {"fl", "files"},        {"files", "files"}};
    auto it = C.find(k.substr(0, k.find(':')));
    return it == C.end() ? "" : it->second;
}
inline void help_open(App &a, const std::string &key)
{
    HelpUi &H = g_help;
    if (!H.loaded || H.gen != i18n().gen)
        help_load(a);
    H.hist.clear();
    H.cur = topic(key) ? key : "basics";
    H.scroll_page = 0;
    a.help = H.cur;
}
inline void help_show(const std::string &key, bool push)
{
    HelpUi &H = g_help;
    if (!topic(key))
        return;
    if (push && !H.cur.empty() && H.cur != key)
        H.hist.push_back(H.cur);
    H.cur = key;
    H.scroll_page = 0;
}

// THE VIEWER, over the whole screen
inline void draw_help(App &a)
{
    HelpUi &H = g_help;
    if (!H.loaded || H.gen != i18n().gen)
        help_load(a);
    if (H.cur.empty())
        H.cur = "basics";
    // (the canvas's own size: the laptop's, the iPad's)
    const float R = a.W - 34, B = a.H - 34;
    rect(a, 0, 0, a.W, a.H, IM_COL32(0x12, 0x14, 0x17, 255), 0);
    look::grain(a, 0, 0, a.W, a.H, 0.02f, 0.05f);
    look::module(a, 14, 14, a.W - 28, a.H - 28, 10);
    // THE TOP: its name, BACK, the search, CLOSE
    text(a, a.bold, 14, 34, 40, LCD, T("HELP"));
    if (button(a, "hvback", 110, 28, 130, a.tab ? 44 : 42, T("\xe2\x97\x80 BACK"), false, !H.hist.empty(), a.tab ? 21 : 14) && !H.hist.empty()) {
        H.cur = H.hist.back();
        H.hist.pop_back();
        H.scroll_page = 0;
    }
    look::lcd_window(a, 256, 28, 520, 42, H.typing);
    look::lcd_text(a, 21, 268, 38, H.q.empty() ? LCD_DIM : LCD, H.q.empty() ? std::string(T("Search help")) : H.q + (H.typing ? "_" : ""), !H.q.empty());
    look::glass(a, 256, 28, 520, 42);
    ImGui::SetCursorScreenPos(P(a, 256, 28));
    if (ImGui::InvisibleButton("hvsearch", ImVec2(520 * a.k, 42 * a.k)))
        H.typing = true;
    if (H.typing) {
        ImGuiIO &io = ImGui::GetIO();
        for (int i = 0; i < io.InputQueueCharacters.Size; i++)
            if (io.InputQueueCharacters[i] >= 32 && io.InputQueueCharacters[i] < 127)
                H.q += (char)io.InputQueueCharacters[i];
        if (ImGui::IsKeyPressed(ImGuiKey_Backspace) && !H.q.empty())
            H.q.pop_back();
        if (ImGui::IsKeyPressed(ImGuiKey_Enter))
            H.typing = false;
    }
    if (ImGui::IsKeyPressed(ImGuiKey_Escape)) {
        if (H.typing)
            H.typing = false;
        else
            a.help.clear();
    }
    if (button(a, "hvclose", R - 150, 28, 150, a.tab ? 44 : 42, T("CLOSE"), false, true, a.tab ? 21 : 14)) {
        a.help.clear();
        H.typing = false;
        return;
    }

    // THE CONTENTS (or what a search found), on the left
    const float NX = 34, NY = 86, NW = a.tab ? 300 : 440, NH = B + 2 - NY - (H.typing ? 5 * 56 + 10 : 0);
    struct Row {
        std::string key, title, sub;
        bool head = false, indent = false;
    };
    std::vector<Row> rows;
    std::vector<std::string> words;
    {
        std::string w;
        for (char c : lower(H.q) + " ")
            if (c == ' ') {
                if (!w.empty())
                    words.push_back(w);
                w.clear();
            } else
                w += c;
    }
    if (!words.empty()) {
        std::vector<Row> hits;
        for (const J &g : H.toc.a)
            for (const J &k : g.a[1].a) {
                const J *h = topic(k.s);
                if (!h)
                    continue;
                const std::string t = help_text_of(k.s);
                bool all = true;
                for (const auto &w : words)
                    all = all && t.find(w) != std::string::npos;
                if (all)
                    hits.push_back({k.s, str(h, "title"), g.a[0].s});
            }
        rows.push_back({"", TF("{0} found", {std::to_string(hits.size())}), "", true});
        rows.insert(rows.end(), hits.begin(), hits.end());
    } else
        for (const J &g : H.toc.a) {
            rows.push_back({"", g.a[0].s, "", true});
            for (const J &k : g.a[1].a)
                if (const J *h = topic(k.s))
                    rows.push_back({k.s, str(h, "title"), "", false, k.s.find(':') != std::string::npos && k.s.rfind("how:", 0) != 0});
        }
    std::vector<float> ry;
    float cy = 0;
    for (const Row &r : rows) {
        ry.push_back(cy);
        cy += r.head ? 34 : r.sub.empty() ? 34 : 50;
    }
    ImVec2 tap;
    if (scroll_area(a, "hvnav", NX, NY, NW, NH, cy, H.scroll_nav, tap)) {
        H.typing = false;
        for (size_t i = 0; i < rows.size(); i++)
            if (!rows[i].head && tap.y >= ry[i] && tap.y < ry[i] + (rows[i].sub.empty() ? 32 : 48))
                help_show(rows[i].key, true);
    }
    dl()->PushClipRect(P(a, NX, NY), P(a, NX + NW, NY + NH), true);
    for (size_t i = 0; i < rows.size(); i++) {
        const Row &r = rows[i];
        const float y = NY + ry[i] - H.scroll_nav;
        if (y > NY + NH || y + 50 < NY)
            continue;
        if (r.head) {
            std::string up = r.title;
            for (char &c : up)
                c = (char)toupper((unsigned char)c);
            text(a, a.bold, 14, NX + 4, y + 12, SILK_DIM, up);
            continue;
        }
        const bool on = r.key == H.cur;
        const float x = NX + (r.indent ? 18 : 0), h = r.sub.empty() ? 32 : 48;
        look::chip(a, x, y, NW - 10 - (x - NX), h, on);
        text(a, a.font, 14, x + 10, y + 9, on ? LCD_BG : SILK, fit(a, a.font, 14, r.title, NW - 40));
        if (!r.sub.empty())
            text(a, a.font, 14, x + 10, y + 27, on ? LCD_BG : SILK_DIM, fit(a, a.font, 14, r.sub, NW - 40));
    }
    dl()->PopClipRect();
    if (H.typing && osk(a, H.q, NX + 10, B + 2 - 5 * 56 + 6, a.tab ? 560 : NW - 20))
        H.typing = false;

    // THE TOPIC, on the right: laid out, then touched, then drawn
    const J *h = topic(H.cur);
    if (!h)
        return;
    const float PX = NX + NW + 20, PY = 86, PW = R - PX, PH = B + 2 - PY, TW = PW - 40;
    struct Op {
        int kind;                       // 0 text, 1 a link (a topic), 2 the card's button
        ImFont *f;
        float size, x, y, w, h;
        ImU32 col;
        std::string s, key;
    };
    std::vector<Op> ops;
    float y = 0;
    auto para = [&](ImFont *f, float size, float x, float w, ImU32 col, const std::string &s, float lh) {
        for (const auto &l : wrap(a, f, size, s, w)) {
            ops.push_back({0, f, size, x, y, 0, 0, col, l, ""});
            y += lh;
        }
    };
    const J *g = group_of(H.cur);
    if (g)
        para(a.font, 14, 0, TW, SILK_DIM, g->a[0].s, 20);
    para(a.font, 28, 0, TW, LCD, str(h, "title"), 36);
    y += 6;
    if (!str(h, "intro").empty()) {
        para(a.font, 14, 0, TW, SILK, str(h, "intro"), 20);
        y += 10;
    }
    if (const J *st = h->get("steps"); st && st->is(J::ARR)) {
        int n = 1;
        for (const J &x : st->a) {
            ops.push_back({0, a.font, 14, 0, y, 0, 0, LCD, std::to_string(n++) + ".", ""});
            para(a.font, 14, 34, TW - 34, SILK, x.is(J::STR) ? x.s : "", 20);
            y += 4;
        }
        y += 6;
    }
    if (const J *ts = h->get("terms"); ts && ts->is(J::ARR))
        for (const J &t : ts->a) {
            if (t.is(J::STR)) {
                y += 10;
                std::string up = t.s;
                for (char &c : up)
                    c = (char)toupper((unsigned char)c);
                para(a.bold, 14, 0, TW, SILK_DIM, up, 24);
                continue;
            }
            if (!t.is(J::ARR) || t.a.size() < 2)
                continue;
            const std::string dt = t.a[0].is(J::STR) ? t.a[0].s : "", dd = t.a[1].is(J::STR) ? t.a[1].s : "";
            const float tw = std::min(260.0f, std::max(120.0f, text_w(a, a.font, 14, dt) + 20));
            const float y0 = y;
            para(a.font, 14, 0, 250, LCD, dt, 20);
            const float y1 = y;
            y = y0;
            para(a.font, 14, std::max(270.0f, tw), TW - std::max(270.0f, tw), SILK, dd, 20);
            y = std::max(y, y1) + 6;
        }
    // see also: the topic's own list, else the rest of its group and the guides that name it
    std::vector<std::string> see;
    if (const J *s = h->get("see"); s && s->is(J::ARR))
        for (const J &x : s->a)
            see.push_back(x.s);
    else {
        if (g)
            for (const J &x : g->a[1].a)
                see.push_back(x.s);
        for (const auto &kv : H.help.o)
            if (const J *s2 = kv.second.get("see"); s2 && s2->is(J::ARR))
                for (const J &x : s2->a)
                    if (x.is(J::STR) && x.s == H.cur)
                        see.push_back(kv.first);
    }
    std::vector<std::string> links;
    for (const auto &k : see)
        if (k != H.cur && topic(k) && std::find(links.begin(), links.end(), k) == links.end())
            links.push_back(k);
    if (!links.empty()) {
        y += 14;
        para(a.bold, 14, 0, TW, SILK_DIM, T("SEE ALSO"), 26);
        float lx = 0;
        for (const auto &k : links) {
            const std::string t = str(topic(k), "title");
            const float bw = text_w(a, a.font, 14, t) + 20;
            if (lx > 0 && lx + bw > TW) {
                lx = 0;
                y += 38;
            }
            ops.push_back({1, a.font, 14, lx, y, bw, 32, SILK, t, k});
            lx += bw + 6;
        }
        y += 44;
    }
    const std::string card = card_of(H.cur);
    if (!card.empty()) {
        y += 10;
        std::string up = card;
        for (char &c : up)
            c = (char)toupper((unsigned char)c);
        ops.push_back({2, a.bold, 14, 0, y, 300, 42, SILK, TF("SHOW THE {0} CARD", {T(up)}), card});
        y += 54;
    }
    if (scroll_area(a, "hvpage", PX, PY, PW, PH, y + 20, H.scroll_page, tap))
        for (const Op &o : ops)
            if (o.kind && tap.x >= o.x + 20 && tap.x < o.x + 20 + o.w && tap.y >= o.y + 10 && tap.y < o.y + 10 + o.h) {
                if (o.kind == 1)
                    help_show(o.key, true);
                else {
                    a.card = o.key;
                    a.help.clear();
                }
                return;
            }
    dl()->PushClipRect(P(a, PX, PY), P(a, PX + PW, PY + PH), true);
    for (const Op &o : ops) {
        const float x = PX + 20 + o.x, yy = PY + 10 + o.y - H.scroll_page;
        if (yy > PY + PH || yy + 40 < PY)
            continue;
        if (o.kind) {
            look::key_cap(a, x, yy, o.w, o.h, false, true);
            if (o.kind == 2)
                text_c(a, o.f, o.size, x + o.w / 2, yy + (o.h - o.size) / 2, SILK, o.s);
            else
                text(a, o.f, o.size, x + 10, yy + (o.h - o.size) / 2, SILK, o.s);
        } else
            text(a, o.f, o.size, x, yy, o.col, o.s);
    }
    dl()->PopClipRect();
}

}  // namespace nui
