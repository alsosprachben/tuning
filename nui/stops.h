// THE STOPS CARD (the retired web interface's): the selected part's organ as a stop jamb --
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
    const bool IP = a.tab;              // (the iPad's: its card from y 210 to card_y1 + 6)
    const float X0 = IP ? 20 : 34, X1 = IP ? 1113 : 1886, HY = IP ? 224 : 356, Y0_ = IP ? 260 : 394, Y1_ = card_y1(a);
    const float TX = heading(a, X0, HY, "STOPS", "stops");
    const int prog = (int)num(&T.st, "program", -1);
    const std::string part_name = str(&T.st, "part");
    text(a, a.font, 14, TX, HY + 1, OWN, "part " + pad2(a.row + 1) + " \xc2\xb7 " + part_name);

    // NO ORGAN: the organs, a tap puts one on the part
    if (prog < 0) {
        text(a, a.font, 21, X0, Y0_ + 6, SILK_DIM, (part_name.empty() ? std::string("This part") : part_name) +
                                                    " has no stops. Pick one with stops for part " + pad2(a.row + 1) + ":");
        int i = 0;
        if (T.organs.is(J::ARR))
            for (const J &pg : T.organs.a)
                for (const Patch &p : L.patches)
                    if (!p.drums && p.variation == 0 && p.program == (int)pg.d()) {
                        const float x = X0 + (i % (IP ? 3 : 4)) * 300, y = Y0_ + 56 + (i / (IP ? 3 : 4)) * 64;
                        const std::string id = "org" + std::to_string(p.pick);
                        ImGui::SetCursorScreenPos(P(a, x, y));
                        const bool hit = ImGui::InvisibleButton(id.c_str(), ImVec2(290 * a.k, 54 * a.k));
                        rect(a, x, y, 290, 54, ImGui::IsItemActive() ? PANEL_HI : IM_COL32(0x1f, 0x22, 0x26, 255), 8);
                        frame(a, x, y, 290, 54, EDGE, 8, 1);
                        char pn[8];
                        snprintf(pn, sizeof pn, "%03d", p.program);
                        text(a, a.font, 21, x + 10, y + (54 - a.lh(21)) / 2, LCD, pn);
                        const float nx = 22 + text_w(a, a.font, 21, pn);
                        text(a, a.font, 14, x + nx, y + (54 - a.lh(14)) / 2, SILK, fit(a, a.font, 14, p.name, 280 - nx));
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
    // (the card's words: a stop's label where the voice gives one -- "Vibrato" for the
    //  engine's "tremulant" -- its name otherwise)
    std::vector<std::string> labels = names;
    if (const J *n = T.st.get("labels"); n && n->is(J::ARR) && n->a.size() == names.size())
        for (size_t i = 0; i < names.size(); i++)
            if (n->a[i].is(J::STR) && !n->a[i].s.empty())
                labels[i] = n->a[i].s;
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
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), HY + 1, SILK_DIM, info);

    const J *drive = T.st.get("drive");
    const bool has_drive = drive && drive->is(J::ARR) && drive->a.size() >= 3;
    const float aboutH = IP ? 30 : 44, DW = IP ? 220 : 350, JX1 = has_drive ? X1 - DW - 14 : X1, JY0 = Y0_, JY1 = Y1_ - aboutH - (IP ? 8 : 14);
    const float LH = a.lh(14) + (IP ? 3 : 4);
    const J *rows = T.st.get("rows");
    const int nrows = rows && rows->is(J::ARR) ? (int)rows->a.size() : 0;
    const float rgap = a.tab ? 8 : 12, rh = nrows ? std::min(140.0f, (JY1 - JY0 - rgap * (nrows - 1)) / nrows) : 0;
    // (the tabs as wide as the widest row lets them, 150 the most)
    const float tg = IP ? 6 : 10, gg = IP ? 16 : 26, rp = IP ? 8 : 12;
    float tw = 150;
    for (int ri = 0; ri < nrows; ri++) {
        const J &row = rows->a[(size_t)ri];
        int nt = 0;
        const int ng = (int)row.a.size();
        for (const J &g : row.a)
            nt += (int)g.a.size();
        if (nt)
            tw = std::min(tw, (JX1 - X0 - 2 * 14 - (ng - 1) * gg - (nt - ng) * tg) / nt);
    }
    const float th = rh - 2 * rp;
    for (int ri = 0; ri < nrows; ri++) {
        const J &row = rows->a[(size_t)ri];
        const float y = JY0 + ri * (rh + rgap);
        look::tray(a, X0, y, JX1 - X0, rh, 10);
        float x = X0 + 14;
        for (size_t gi = 0; gi < row.a.size(); gi++) {
            if (gi) {
                rect(a, x + gg / 2, y + rp, 1, rh - 2 * rp, IM_COL32(0x3a, 0x3f, 0x45, 255), 0);
                x += gg;
            }
            for (const J &rv : row.a[gi].a) {
                const int r = (int)rv.d();
                const bool on = r >= 0 && r < (int)drawn.size() && drawn[(size_t)r];
                const float ty = y + rp;
                const std::string id = "tab" + std::to_string(r);
                ImGui::SetCursorScreenPos(P(a, x, ty));
                const bool hit = ImGui::InvisibleButton(id.c_str(), ImVec2(tw * a.k, th * a.k));
                const bool held = ImGui::IsItemActive();
                look::chip(a, x, ty, tw, th, on, held);
                const auto np = stop_parts(r < (int)labels.size() ? labels[(size_t)r] : std::to_string(r), feet);
                const auto ls = wrap(a, a.bold, 14, np.first, tw - 14);
                const size_t nl = std::min<size_t>(3, ls.size());
                // (a name alone centred in its tab, as a drawbar's footage is; above its footage otherwise)
                const float ly0 = np.second.empty() ? ty + (th - nl * LH) / 2 : ty + (IP ? 6 : 10);
                for (size_t li = 0; li < nl; li++)
                    text_c(a, a.bold, 14, x + tw / 2, ly0 + li * LH, on ? LCD_BG : SILK, ls[li]);
                if (!np.second.empty()) {   // (the footage; a drawbar's alone, big where it fits, centred)
                    const float fs = np.first.empty() && text_w(a, a.font, 35, np.second) <= tw - 14 ? 35 : 21;
                    text_c(a, a.font, fs, x + tw / 2, np.first.empty() ? ty + (th - a.lh(fs)) / 2 : ty + th - a.lh(21) - (IP ? 6 : 10),
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
    const float RH = IP ? 170 : 250, RG = IP ? 8 : 14;    // (the rotary's tray under it: room for its SPREAD knob)
    const float CH = 0;                                    // (the cabinet: the AMP card's)
    if (has_drive) {
        const float dx = X1 - DW, dy = JY0, dw = DW, dh = JY1 - JY0 - RH - RG - CH;
        look::tray(a, dx, dy, dw, dh, 10);
        heading(a, dx + 14, dy + 12, "DRIVE", "drive");
        const double now = drive->a[0].d(), voice = drive->a[1].d(), mine = drive->a[2].d();
        auto it = a.hold.find("drive");
        const bool held = it != a.hold.end() && ImGui::GetTime() < it->second.second;
        const double v = held ? (it->second.first < 0 ? voice : it->second.first) : now;
        const bool own = held ? it->second.first >= 0 : mine >= 0;
        float v01 = (float)(v / 3.0);
        char vt[16];
        snprintf(vt, sizeof vt, "%.2f", v);
        // (the knob at the left, the way back beside it: the tray shares the column with the cabinet's)
        const float KS = IP ? 56 : 76, kx = dx + 18 + KS / 2, ky = dy + 34 + (dh - 34) / 2 - (IP ? 12 : 14);
        const int f = knob(a, "drive", kx, ky, KS, v01, "DRIVE", vt, false, {}, 0, own);
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
        const float bx_ = dx + KS + 36, bw_ = dw - KS - 46, bh_ = IP ? 44 : 38;
        const auto note = wrap(a, a.font, 14, "Clean at 0, a growl as it turns up.", bw_);
        for (size_t i = 0; !IP && i < note.size() && i < 2; i++)     // (the iPad's: no room)
            text(a, a.font, 14, bx_, ky - KS / 2 - 4 + i * LH, SILK_DIM, note[i]);
        char bt[48];
        snprintf(bt, sizeof bt, own ? "BACK TO THE PATCH'S %.2f" : "AS THE PATCH (%.2f)", voice);
        if (button(a, "driveback", bx_, IP ? ky - bh_ / 2 : ky + KS / 2 - bh_ + 6, bw_, bh_, bt, false, own))
            back();
        // THE ROTARY HEARD: the cabinet in the room (an organ's way: its
        // direction turning) or two mics round it (a recording's: wide), and
        // the mics' spread -- the part's, kept across its program changes
        const float ry = dy + dh + RG;
        look::tray(a, dx, ry, dw, RH, 10);
        heading(a, dx + 14, ry + 12, "ROTARY", "rotary");
        const J *pr = part(a, a.row);
        const J *rv = pr ? pr->get("rotary") : nullptr;
        int mode = rv && rv->is(J::ARR) && rv->a.size() >= 2 ? (int)rv->a[0].d() : -1;
        double spread = rv && rv->is(J::ARR) && rv->a.size() >= 2 ? rv->a[1].d() : -1.0;
        auto ht = a.hold.find("rotary");
        if (ht != a.hold.end() && ImGui::GetTime() < ht->second.second) {      // (shown at once; the push confirms)
            mode = (int)std::floor(ht->second.first / 1000.0);
            spread = std::fmod(ht->second.first, 1000.0) - 1.0;
        }
        const bool mics = mode == 1;
        const double sp = spread >= 0.0 ? spread : 96.0 * 180.0 / 127.0;     // (a Rotary type's Separate 96)
        auto set = [&](int m, double sd) {
            a.hold["rotary"] = {m * 1000.0 + (sd < 0 ? 0.0 : sd + 1.0), ImGui::GetTime() + 0.6};
            call(a, "{\"call\":\"rotary_set\",\"row\":" + std::to_string(a.row) + ",\"mode\":" + std::to_string(m)
                        + ",\"spread\":" + jnum(sd) + "}");
        };
        const float bw = (dw - 34) / 2, by = ry + (IP ? 36 : 44), bh = IP ? 44 : 38;
        if (button(a, "rotroom", dx + 12, by, bw, bh, "IN THE ROOM", !mics))
            set(0, spread);
        if (button(a, "rotmics", dx + 22 + bw, by, bw, bh, "TWO MICS", mics))
            set(1, spread);
        if (mics) {
            float v01 = (float)(sp / 180.0);
            char vt[16];
            snprintf(vt, sizeof vt, "%.0f\xc2\xb0", sp);
            const int f = knob(a, "rotspread", dx + dw / 2, by + bh + (IP ? 34 : 58), IP ? 40 : 60, v01, "SPREAD", vt, false, {},
                               0, spread >= 0.0);
            if (f & K_CHANGED)
                set(1, std::round(v01 * 180.0));
            if (f & K_RESET)
                set(1, -1.0);
        } else {
            const auto rn = wrap(a, a.font, 14, "The cabinet heard where it stands: its horn and drum turning toward you and away.",
                                 dw - 28);
            for (size_t i = 0; i < rn.size(); i++)
                text(a, a.font, 14, dx + 14, by + bh + (IP ? 10 : 16) + i * LH, SILK_DIM, rn[i]);
        }
    }

    // WHAT IT IS: the stop last touched, else the organ's own words and a hint -- a line
    const float ay = Y1_ - aboutH, aw = X1 - X0;
    look::tray(a, X0, ay, aw, aboutH, 8);
    const J *org = nullptr;
    if (const J *ss = L.about.get("stops"))
        org = ss->get(std::to_string(prog).c_str());
    std::string title, body;
    if (org && T.touched >= 0 && T.touched_prog == prog && T.touched < (int)names.size()) {
        title = labels[(size_t)T.touched];
        if (const J *os = org->get("stops"))
            body = str(os, names[(size_t)T.touched].c_str());
    } else {
        title = part_name;
        body = patch_desc(a, part(a, a.row));
        if (org)
            body += (body.empty() ? "" : ". ") + std::string("Touch a stop for what it is.");
    }
    const float tx = X0 + 12 + text_w(a, a.bold, 14, title) + 14;
    text(a, a.bold, 14, X0 + 12, ay + (aboutH - a.lh(14)) / 2, SILK, title);
    text(a, a.font, 14, tx, ay + (aboutH - a.lh(14)) / 2, SILK_DIM, body);
}

}  // namespace nui
