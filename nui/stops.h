// THE STOPS CARD (ui/app.js's): the selected part's organ as a stop jamb --
// the voice's rows as the panel has them (stops_of's rows), each row's
// groups apart, a tab lit when drawn. A tap draws or retires it; the whole
// registration goes to the engine (stops_set). A tonewheel organ's DRIVE
// beside it; under it what the stop last touched is (about.json). A part
// that is no organ offers the organs.
#pragma once

#include "app.h"
#include "library.h"
#include "widgets.h"

namespace nui {

struct StopsUi {
    J st;                               // (stops_of: row, program, part, names, rows, drawn, drive?)
    int for_row = -1;
    std::vector<int> mine;              // (the drawn a tap made, held a moment over the pushes)
    double mine_until = 0;
    int touched = -1, touched_prog = -1;
    J organs;                           // (the organs a part without stops is offered)
    bool organs_asked = false;
};
static StopsUi g_stops;

inline void stops_take(const J &st, App &a)
{
    StopsUi &T = g_stops;
    if ((int)num(&st, "row", -1) != a.row)
        return;                         // (the part before: a select crossed it)
    if ((int)num(&st, "program", -1) != (int)num(&T.st, "program", -1) || T.for_row != a.row)
        T.touched = -1;
    T.st = st;
    T.for_row = a.row;
}
inline std::vector<int> stops_drawn()
{
    StopsUi &T = g_stops;
    if (!T.mine.empty() && ImGui::GetTime() < T.mine_until)
        return T.mine;
    T.mine.clear();
    std::vector<int> d;
    if (const J *x = T.st.get("drawn"); x && x->is(J::ARR))
        for (const J &v : x->a)
            d.push_back(v.d() != 0);
    return d;
}

// "principal 16" -> ("Principal", "16'"); "mixture III" -> ("Mixture", "III")
inline std::pair<std::string, std::string> stop_parts(const std::string &nm, bool feet)
{
    static const std::set<std::string> FEET = {"32", "16", "10-2/3", "8", "5-1/3", "4", "2-2/3", "2", "1-3/5", "1-1/3", "1"};
    auto cap = [](std::string t) {
        for (size_t i = 0; i < t.size(); i++)
            if (i == 0 || t[i - 1] == ' ')
                t[i] = (char)toupper((unsigned char)t[i]);
        return t;
    };
    if (FEET.count(nm))                 // (a drawbar: its footage alone)
        return {"", nm + "\xe2\x80\xb2"};
    const size_t sp = nm.rfind(' ');
    if (sp != std::string::npos) {
        const std::string tail = nm.substr(sp + 1);
        bool roman = !tail.empty(), num_ = !tail.empty() && isdigit((unsigned char)tail[0]);
        for (char c : tail)
            roman = roman && (c == 'I' || c == 'V' || c == 'X');
        for (char c : tail)
            num_ = num_ && (isdigit((unsigned char)c) || c == '-' || c == '/');
        if (roman || num_)
            return {cap(nm.substr(0, sp)), tail + (feet && FEET.count(tail) ? "\xe2\x80\xb2" : "")};
    }
    return {cap(nm), ""};
}

inline void draw_stops(App &a)
{
    StopsUi &T = g_stops;
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    if (T.for_row != a.row || !T.organs_asked) {
        T.organs_asked = true;
        J r = call(a, "{\"call\":\"stops\",\"row\":" + std::to_string(a.row) + "}");
        T.for_row = -1;
        if (const J *s = r.get("stops"))
            stops_take(*s, a);
        if (const J *o = r.get("organs"))
            T.organs = *o;
        T.for_row = a.row;
    }
    const float X0 = 34, X1 = 1886;
    text(a, a.bold, 14, X0, 356, SILK, "STOPS");
    const int prog = (int)num(&T.st, "program", -1);
    const std::string part_name = str(&T.st, "part");
    text(a, a.font, 14, X0 + 76, 357, OWN, "part " + pad2(a.row + 1) + " \xc2\xb7 " + part_name);

    // NO ORGAN: the organs, a tap puts one on the part
    if (prog < 0) {
        text(a, a.font, 21, X0, 400, SILK_DIM, (part_name.empty() ? std::string("This part") : part_name) +
                                                    " has no stops. Put an organ on part " + pad2(a.row + 1) + ":");
        int i = 0;
        if (T.organs.is(J::ARR))
            for (const J &pg : T.organs.a)
                for (const Patch &p : L.patches)
                    if (!p.drums && p.variation == 0 && p.program == (int)pg.d()) {
                        const float x = X0 + (i % 4) * 300, y = 450 + (i / 4) * 64;
                        const std::string id = "org" + std::to_string(p.pick);
                        ImGui::SetCursorScreenPos(P(a, x, y));
                        const bool hit = ImGui::InvisibleButton(id.c_str(), ImVec2(290 * a.k, 54 * a.k));
                        rect(a, x, y, 290, 54, ImGui::IsItemActive() ? PANEL_HI : IM_COL32(0x1f, 0x22, 0x26, 255), 8);
                        frame(a, x, y, 290, 54, EDGE, 8, 1);
                        char pn[8];
                        snprintf(pn, sizeof pn, "%03d", p.program);
                        text(a, a.font, 21, x + 10, y + 16, LCD, pn);
                        text(a, a.font, 14, x + 72, y + 20, SILK, fit(a, a.font, 14, p.name, 210));
                        if (hit) {
                            call(a, "{\"call\":\"part_pick\",\"row\":" + std::to_string(a.row) + ",\"pick\":" +
                                        std::to_string(p.pick) + "}");
                            T.for_row = -1;     // (asked again: the organ's stops)
                        }
                        i++;
                    }
        return;
    }

    // THE JAMB
    std::vector<std::string> names;
    if (const J *n = T.st.get("names"); n && n->is(J::ARR))
        for (const J &x : n->a)
            names.push_back(x.is(J::STR) ? x.s : "");
    bool feet = false;
    {
        int nums = 0, ok = 0;
        static const std::set<std::string> FEET = {"32", "16", "10-2/3", "8", "5-1/3", "4", "2-2/3", "2", "1-3/5", "1-1/3", "1"};
        for (const auto &n : names) {
            const size_t sp = n.rfind(' ');
            if (sp == std::string::npos || !isdigit((unsigned char)n[sp + 1]))
                continue;
            nums++;
            ok += FEET.count(n.substr(sp + 1)) > 0;
        }
        feet = nums > 0 && ok == nums;
    }
    std::vector<int> drawn = stops_drawn();
    drawn.resize(names.size(), 0);
    int k = 0;
    for (int d : drawn)
        k += d;
    const std::string info = std::to_string(k) + " of " + std::to_string(names.size()) + " drawn";
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), 357, SILK_DIM, info);

    const J *drive = T.st.get("drive");
    const bool has_drive = drive && drive->is(J::ARR) && drive->a.size() >= 3;
    const float aboutH = 140, JX1 = has_drive ? X1 - 364 : X1, JY0 = 394, JY1 = 1056 - aboutH - 14;
    const J *rows = T.st.get("rows");
    const int nrows = rows && rows->is(J::ARR) ? (int)rows->a.size() : 0;
    const float rgap = 12, rh = nrows ? std::min(140.0f, (JY1 - JY0 - rgap * (nrows - 1)) / nrows) : 0;
    const float th = rh - 24, tw = 150, tg = 10, gg = 26;
    for (int ri = 0; ri < nrows; ri++) {
        const J &row = rows->a[(size_t)ri];
        const float y = JY0 + ri * (rh + rgap);
        rect(a, X0, y, JX1 - X0, rh, IM_COL32(0x1f, 0x22, 0x26, 255), 10);
        frame(a, X0, y, JX1 - X0, rh, EDGE, 10, 1);
        float x = X0 + 14;
        for (size_t gi = 0; gi < row.a.size(); gi++) {
            if (gi) {
                rect(a, x + gg / 2, y + 12, 1, rh - 24, IM_COL32(0x3a, 0x3f, 0x45, 255), 0);
                x += gg;
            }
            for (const J &rv : row.a[gi].a) {
                const int r = (int)rv.d();
                const bool on = r >= 0 && r < (int)drawn.size() && drawn[(size_t)r];
                const float ty = y + 12;
                const std::string id = "tab" + std::to_string(r);
                ImGui::SetCursorScreenPos(P(a, x, ty));
                const bool hit = ImGui::InvisibleButton(id.c_str(), ImVec2(tw * a.k, th * a.k));
                const bool held = ImGui::IsItemActive();
                rect(a, x, ty, tw, th, on ? LCD : held ? PANEL_HI : CAP, 8);
                frame(a, x, ty, tw, th, on ? IM_COL32(0xff, 0xd2, 0x7a, 255) : EDGE, 8, 1);
                const auto np = stop_parts(r < (int)names.size() ? names[(size_t)r] : std::to_string(r), feet);
                const auto ls = label_lines(a, a.bold, 14, np.first, tw - 14);
                for (size_t li = 0; li < ls.size(); li++)
                    text_c(a, a.bold, 14, x + tw / 2, ty + 10 + li * 17, on ? LCD_BG : SILK, fit(a, a.bold, 14, ls[li], tw - 10));
                if (!np.second.empty()) {   // (the footage; a drawbar's alone, big where it fits, centred)
                    const float fs = np.first.empty() && text_w(a, a.font, 35, np.second) <= tw - 14 ? 35 : 21;
                    text_c(a, a.font, fs, x + tw / 2, np.first.empty() ? ty + (th - fs) / 2 : ty + th - 31,
                           on ? LCD_BG : SILK_DIM, np.second);
                }
                if (hit && r >= 0 && r < (int)drawn.size()) {
                    drawn[(size_t)r] = !drawn[(size_t)r];
                    T.mine = drawn;
                    T.mine_until = ImGui::GetTime() + 0.6;
                    T.touched = r;
                    T.touched_prog = prog;
                    std::string d = "[";
                    for (size_t j = 0; j < drawn.size(); j++)
                        d += (j ? "," : "") + std::to_string(drawn[j]);
                    call(a, "{\"call\":\"stops_set\",\"row\":" + std::to_string(a.row) + ",\"drawn\":" + d + "]}");
                }
                x += tw + tg;
            }
            x -= tg;
        }
    }

    // A TONEWHEEL ORGAN's DRIVE (the wheel is its swell): the valve before the rotors, 0 to 3
    if (has_drive) {
        const float dx = X1 - 350, dy = JY0, dw = 350, dh = JY1 - JY0;
        rect(a, dx, dy, dw, dh, IM_COL32(0x1f, 0x22, 0x26, 255), 10);
        frame(a, dx, dy, dw, dh, EDGE, 10, 1);
        text(a, a.bold, 14, dx + 14, dy + 12, SILK, "DRIVE");
        const double now = drive->a[0].d(), voice = drive->a[1].d(), mine = drive->a[2].d();
        auto it = a.hold.find("drive");
        const bool held = it != a.hold.end() && ImGui::GetTime() < it->second.second;
        const double v = held ? (it->second.first < 0 ? voice : it->second.first) : now;
        const bool own = held ? it->second.first >= 0 : mine >= 0;
        float v01 = (float)(v / 3.0);
        char vt[16];
        snprintf(vt, sizeof vt, "%.2f", v);
        const int f = knob(a, "drive", dx + dw / 2, dy + 110, 110, v01, "DRIVE", vt, false, {}, 0, own);
        if (f & K_CHANGED) {
            const double d = std::round(v01 * 3.0 * 100) / 100;
            a.hold["drive"] = {d, ImGui::GetTime() + 0.6};
            call(a, "{\"call\":\"drive_set\",\"row\":" + std::to_string(a.row) + ",\"v\":" + jnum(d) + "}");
        }
        const auto back = [&] {
            a.hold["drive"] = {-1, ImGui::GetTime() + 0.6};
            call(a, "{\"call\":\"drive_set\",\"row\":" + std::to_string(a.row) + ",\"v\":-1}");
        };
        if (f & K_RESET)
            back();
        const auto note = wrap(a, a.font, 14, "The valve before the rotors: clean at 0, a growl as it turns up. The mod wheel is the swell.", dw - 28);
        for (size_t i = 0; i < note.size(); i++)
            text(a, a.font, 14, dx + 14, dy + 220 + i * 18, SILK_DIM, note[i]);
        char bt[48];
        snprintf(bt, sizeof bt, own ? "BACK TO THE VOICE'S %.2f" : "AS THE VOICE (%.2f)", voice);
        if (button(a, "driveback", dx + 14, dy + dh - 52, dw - 28, 38, bt, false, own))
            back();
    }

    // WHAT IT IS: the stop last touched, else the organ's patch and a hint
    const float ay = 1056 - aboutH, aw = X1 - X0;
    rect(a, X0, ay, aw, aboutH, IM_COL32(0x1f, 0x22, 0x26, 255), 8);
    const J *org = nullptr;
    if (const J *ss = L.about.get("stops"))
        org = ss->get(std::to_string(prog).c_str());
    std::string title, body, hint;
    const J *e = nullptr;
    if (org && T.touched >= 0 && T.touched_prog == prog && T.touched < (int)names.size())
        if (const J *os = org->get("stops"))
            if ((e = os->get(names[(size_t)T.touched].c_str())))
                title = names[(size_t)T.touched];
    if (!e) {
        const J *p = part(a, a.row);
        title = part_name;
        if (const J *pr = L.about.get("programs"); pr && p)
            e = pr->get((std::to_string((int)num(p, "program")) + "." + std::to_string((int)num(p, "variation"))).c_str());
        if (org)
            hint = str(org, "panel") + ": touch a stop for what it is.";
    }
    text(a, a.bold, 14, X0 + 12, ay + 10, SILK, fit(a, a.bold, 14, title, aw - 420));
    int lines_from = 0;
    if (e && e->is(J::ARR) && e->a.size() >= 2) {
        const int r = (int)e->a[0].d();
        const J *lv = L.about.get("levels");
        const std::string rt = std::to_string(r) + " \xc2\xb7 " +
                               (lv && lv->is(J::ARR) && r >= 0 && r < (int)lv->a.size() && lv->a[(size_t)r].is(J::STR) ? lv->a[(size_t)r].s : "");
        text(a, a.font, 14, X1 - 12 - text_w(a, a.font, 14, rt), ay + 10, LCD, rt);
        body = e->a[1].is(J::STR) ? e->a[1].s : "";
    }
    auto lines = wrap(a, a.font, 14, body, aw - 24);
    const size_t maxl = hint.empty() ? 5 : 4;
    for (size_t i = 0; i < lines.size() && i < maxl; i++, lines_from++)
        text(a, a.font, 14, X0 + 12, ay + 32 + i * 18, SILK_DIM,
             i + 1 == maxl && lines.size() > maxl ? fit(a, a.font, 14, lines[i] + " \xe2\x80\xa6", aw - 24) : lines[i]);
    if (!hint.empty())
        text(a, a.font, 14, X0 + 12, ay + 32 + lines_from * 18, LCD_DIM, fit(a, a.font, 14, hint, aw - 24));
}

}  // namespace nui
