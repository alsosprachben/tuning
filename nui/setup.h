// THE SETUP CARD (ui/app.js's): the MIDI inputs (each plugged-in device on
// or off, merged), playing as a module (the input read as a sound module
// reads it, your parts set aside and put back), the Messenger, the globals
// every part plays through (livetui's GLOBALS), the room, how program
// changes are read, and rubato's borrowed time. QUIT in the head.
#pragma once

#include "app.h"
#include "effects.h"
#include "files.h"

namespace nui {

struct SetupUi {
    bool open = false;
    J s, mod;                           // (setup_of: rate, block, globals, inputs, messenger, room, rubato; module_of)
    std::vector<std::string> rooms;
};
static SetupUi g_su;

inline void su_take(const J &r)
{
    if (const J *s = r.get("setup"))
        g_su.s = *s;
    if (const J *m = r.get("module"))
        g_su.mod = *m;
}
inline void setup_card(App &a, bool open)
{
    SetupUi &U = g_su;
    if (open == U.open)
        return;
    U.open = open;
    su_take(call(a, std::string("{\"call\":\"setup\",\"open\":") + (open ? "1" : "0") + "}"));
    if (open) {
        su_take(call(a, "{\"call\":\"module\"}"));
        if (U.rooms.empty())
            if (const J *rs = call(a, "{\"call\":\"hello\"}").get("rooms"); rs && rs->is(J::ARR))
                for (const J &r : rs->a)
                    U.rooms.push_back(r.is(J::STR) ? r.s : "");
    }
}

inline void draw_setup(App &a)
{
    SetupUi &U = g_su;
    if (!U.s.is(J::OBJ)) {
        U.open = false;
        setup_card(a, true);
    }
    // (the iPad's: its card from y 210 to 734, two pages -- the input; the sound)
    const bool IP = a.tab;
    static int page = 0;
    const float X0 = IP ? 20 : 34, X1 = IP ? 1113 : 1886, Y0 = IP ? 266 : 394, Y1 = IP ? 728 : 1056, HY = IP ? 224 : 356;
    const float LH = a.lh(14) + (IP ? 3 : 4);
    const float TX = heading(a, X0, HY, "SETUP", "setup");
    if (IP)
        for (int pg = 0; pg < 2; pg++) {
            const std::string id = "supage" + std::to_string(pg);
            if (button(a, id.c_str(), 300 + pg * 196, 216, 190, 44, pg ? "SOUND" : "INPUT", page == pg, true, 21))
                page = pg;
        }
    if (!U.s.is(J::OBJ))
        return;
    const double rate = num(&U.s, "rate"), block = num(&U.s, "block");
    char inf[96];
    snprintf(inf, sizeof inf, "%.0f Hz \xc2\xb7 %.0f frames a block (%.2f ms)", rate, block, rate > 0 ? 1000 * block / rate : 0.0);
    if (IP) {                           // (shorter, between the pages and QUIT)
        char sh[48];
        snprintf(sh, sizeof sh, "%.0f Hz \xc2\xb7 %.0f frames", rate, block);
        text(a, a.font, 14, 700, HY + 1, SILK_DIM, sh);
    } else
        text(a, a.font, 14, TX, HY + 1, SILK_DIM, inf);
    // QUIT (a second tap within 3 s, as the panel's)
    const double now = ImGui::GetTime();
    const bool armed = now - a.quit_armed < 3.0;
    if (armed)
        a.animate = true;
    if (button(a, "suquit", X1 - 250, IP ? 216 : 346, 250, IP ? 44 : 38, armed ? "TAP AGAIN TO QUIT" : "QUIT CLAVITONE", armed, true,
               IP ? 21 : 14)) {
        if (armed)
            a.quit = true;
        else
            a.quit_armed = now;
    }
    const J *g = U.s.get("globals");
    auto gv = [&](size_t i) { return g && g->is(J::ARR) && i < g->a.size() ? g->a[i].d() : 0.0; };
    auto gset = [&](int i, double v) {
        call(a, "{\"call\":\"global_set\",\"i\":" + std::to_string(i) + ",\"v\":" + jnum(v) + "}");
        J &gg = U.s.o["globals"];      // (shown at once; the push confirms)
        if (gg.is(J::ARR) && (size_t)i < gg.a.size()) {
            J n;
            n.t = J::NUM;
            n.num = jnum(v);
            gg.a[(size_t)i] = n;
        }
    };

    // MIDI IN, PLAY AS A MODULE, THE MESSENGER
    const float AW = IP ? X1 - X0 : 760, BW = IP ? 690 : 640, gap = IP ? 6 : 10, AX = X0, BX = IP ? X0 : AX + AW + gap,
                CX = BX + BW + gap, CW = X1 - CX;
    const bool show_in = !IP || page == 0, show_snd = !IP || page == 1;
    for (const auto &b : {std::pair<float, float>{AX, AW}, {BX, BW}, {CX, CW}}) {
        if ((b.first == AX && b.second == AW && !show_in) || (!(b.first == AX && b.second == AW) && !show_snd))
            continue;
        look::tray(a, b.first, Y0, b.second, Y1 - Y0, 9);
    }
    auto head = [&](float x, float &y, const char *h, const char *sub, const char *key) {
        const float hx = heading(a, x + 12, y, h, key);
        if (sub)
            text(a, a.font, 14, hx, y + 1, LCD, sub);
        y += 26;
    };
    float y = Y0 + 10;
    if (show_in) {
    head(AX, y, "MIDI IN", "several at once, merged; kept in the session", "su:midi");
    const J *ins = U.s.get("inputs");
    if (!ins || !ins->is(J::ARR) || ins->a.empty()) {
        text(a, a.font, 14, AX + 12, y, SILK_DIM, "No MIDI devices plugged in.");
        y += 24;
    } else
        for (const J &d : ins->a) {
            const bool on = flag(&d, "on");
            const std::string path = str(&d, "path"), id = "suin" + path;
            ImGui::SetCursorScreenPos(P(a, AX + 12, y));
            if (ImGui::InvisibleButton(id.c_str(), ImVec2((AW - 24) * a.k, 50 * a.k))) {
                call(a, "{\"call\":\"input_set\",\"path\":" + jstr(path) + ",\"on\":" + (on ? "0" : "1") + "}");
                for (J &x : U.s.o["inputs"].a)
                    if (str(&x, "path") == path)
                        x.o["on"] = sess::boolean(!on);
            }
            look::latch(a, AX + 12, y, AW - 24, 50, on);
            text(a, a.font, 14, AX + 24, y + (IP ? 7 : 8), on ? LCD : SILK, str(&d, "name"));
            std::string p = path;
            if (p.rfind("/dev/snd/", 0) == 0)
                p = p.substr(9);
            text(a, a.font, 14, AX + 24, y + (IP ? 11 : 12) + LH, SILK_DIM, p + " \xc2\xb7 " + (on ? (flag(&d, "open") ? "reading" : "wanted, not open") : "off"));
            y += 56;
        }
    if (!str(&U.s, "input_err").empty()) {
        text(a, a.font, 14, AX + 12, y, BAD, fit(a, a.font, 14, str(&U.s, "input_err"), AW - 24));
        y += 22;
    }
    y += 10;
    head(AX, y, "PLAY AS A MODULE", "a sequencer or DAW sending whole songs", "su:module");
    {
        static const std::vector<std::pair<std::string, std::string>> MODS = {
            {"off", "OFF: MY PARTS"}, {"auto", "AUTO"}, {"gm", "GM"}, {"ours", "GS: OURS"}, {"sc55", "GS: SC-55"}, {"sc88", "GS: SC-88"},
            {"sc88pro", "GS: SC-88PRO"}, {"sc8850", "GS: SC-8850"}, {"cm64", "GS: INIT CM-64"}, {"mt32", "MT-32"}, {"cm64u", "CM-64"}};
        const std::string mode = U.mod.is(J::OBJ) ? str(&U.mod, "mode") : "off", eff = str(&U.mod, "eff"), stage = str(&U.mod, "stage");
        const bool busy = flag(&U.mod, "busy");
        std::vector<std::string> w;
        std::vector<bool> lit;
        for (const auto &m : MODS) {
            std::string t = m.second;
            if (m.first == "auto" && mode == "auto" && !eff.empty())
                t += ": " + (eff == "gs" ? std::string("GS") : eff == "leaving" ? std::string("leaving") : fl_mode_label(eff));
            w.push_back(t);
            lit.push_back(m.first == mode);
        }
        const int h = flow_buttons(a, "sumod", AX + 12, y, AW - 24, w, lit);
        if (h >= 0 && !busy)
            su_take(call(a, "{\"call\":\"module\",\"mode\":\"" + MODS[(size_t)h].first + "\"}"));
        if (busy)
            a.animate = true;
        std::string st = mode == "off" ? "Off: the input plays your own parts."
                                       : (stage.empty() ? "" : (char)toupper((unsigned char)stage[0]) + stage.substr(1) + ". ") +
                                             "Sixteen parts, one per channel; OFF puts your parts back.";
        for (const auto &l : wrap(a, a.font, 14, st, AW - 24)) {
            text(a, a.font, 14, AX + 12, y, SILK_DIM, l);
            y += LH;
        }
        if (const J *rep = U.mod.get("report"); rep && rep->is(J::ARR) && !rep->a.empty()) {
            text(a, a.bold, 14, AX + 12, y + 4, SILK, "What the MT-32 did with the input");
            y += 26;
            static float rs = 0;
            lines_box(a, "sumodrep", AX + 12, y, AW - 24, 110, *rep, rs);
            y += 118;
        }
    }
    y += 10;
    head(AX, y, "THE MESSENGER", nullptr, "su:msgr");
    {
        const J *m = U.s.get("messenger");
        const std::string line = str(m, "line");
        text(a, a.font, 14, AX + 12, y, SILK_DIM,
             line.empty() ? "None set." : line == "-" ? "Looked for when the program is a Messenger patch." : "On " + line + ".");
        y += 24;
        const bool reads = flag(m, "reads"), pre = flag(m, "pre107");
        const int h = flow_buttons(a, "sumsg", AX + 12, y, AW - 24, {"READ ITS KNOBS", "FIRMWARE BEFORE 1.0.7"}, {reads, pre});
        if (h >= 0) {
            const char *k = h ? "pre107" : "reads";
            const bool v = h ? pre : reads;
            call(a, std::string("{\"call\":\"messenger_set\",\"") + k + "\":" + (v ? "0" : "1") + "}");
            U.s.o["messenger"].o[k] = sess::boolean(!v);
        }
    }

    }
    // SOUND: the globals every part plays through
    if (!show_snd)
        return;
    y = Y0 + 10;
    head(BX, y, "SOUND", "every part", "su:sound");
    struct Gl {
        int i;
        const char *label;
        double lo, hi, step;
        int fmt;                        // (0 dB, 1 plain, 2 st, 3 cents, 4 percent, 5 ms with 0 off)
    };
    static const Gl GLOB[8] = {{0, "Master", -60, 0, 0.5, 0},   {1, "Headroom", 0, 24, 0.5, 0}, {2, "Limiter knee", 0.1, 1, 0.02, 1},
                               {3, "Bend range", 0, 24, 0.5, 2}, {4, "Mod depth", 0, 200, 5, 3}, {9, "Mod rate", 0, 1.5, 0.05, 4},
                               {5, "Aftertouch", 0, 24, 0.5, 0}, {14, "Stand-in", 0, 100, 5, 5}};
    const int NK = IP ? 8 : 4;          // (the iPad's eight to a row)
    const float kcw = (BW - 24) / NK;
    for (int k = 0; k < 8; k++) {
        const Gl &q = GLOB[k];
        const int n = (int)std::lround((q.hi - q.lo) / q.step);
        std::vector<int> vals = irange(0, n);
        std::vector<std::string> shown;
        for (int j = 0; j <= n; j++) {
            const double v = q.lo + j * q.step;
            char b[32];
            if (q.fmt == 0)
                snprintf(b, sizeof b, "%.1f dB", v);
            else if (q.fmt == 1)
                snprintf(b, sizeof b, "%.2f", v);
            else if (q.fmt == 2)
                snprintf(b, sizeof b, "%.1f st", v);
            else if (q.fmt == 3)
                snprintf(b, sizeof b, "%.0f c", v);
            else if (q.fmt == 5)
                snprintf(b, sizeof b, v > 0 ? "%.0f ms" : "OFF", v);
            else
                snprintf(b, sizeof b, "+%.0f%%", v * 100);
            shown.push_back(b);
        }
        const int cur = fx_val(a, "g" + std::to_string(q.i), (int)std::lround((gv((size_t)q.i) - q.lo) / q.step));
        int picked;
        list_knob(a, "sug" + std::to_string(q.i), BX + 12 + (k % NK + 0.5f) * kcw, y + 34 + (k / NK) * 112, IP ? 48 : 50, vals, shown, cur,
                  q.label, false, kcw - 6, picked);
        if (picked != cur) {
            fx_mine(a, "g" + std::to_string(q.i), picked);
            call(a, "{\"call\":\"global_set\",\"i\":" + std::to_string(q.i) + ",\"v\":" + jnum(std::round((q.lo + picked * q.step) * 1e4) / 1e4) + "}");
        }
    }
    y += IP ? 116 : 240;
    {
        const bool gpu = gv(6) > 0.5, tail = gv(7) > 0.5;
        const int h = flow_buttons(a, "susw", BX + 12, y, BW - 24, {"THE GPU", "THE ROOM'S TAIL"}, {gpu, tail});
        if (h == 0)
            gset(6, gpu ? 0 : 1);
        else if (h == 1)
            gset(7, tail ? 0 : 1);
    }
    y += 6;
    text(a, a.bold, 14, BX + 12, y, SILK, "THE ROOM");
    y += IP ? 18 : 24;
    {
        std::vector<bool> lit;
        for (const auto &r : U.rooms)
            lit.push_back(r == str(&U.s, "room"));
        const int h = flow_buttons(a, "suroom", BX + 12, y, BW - 24, U.rooms, lit, 30, IP ? 14 : 0);
        if (h >= 0) {
            gset(8, h);
            U.s.o["room"] = sess::str(U.rooms[(size_t)h]);
        }
    }
    y += 6;
    text(a, a.bold, 14, BX + 12, y, SILK, "PROGRAM CHANGES READ AS");
    y += IP ? 18 : 24;
    {
        static const std::vector<std::string> STDS = {"ours", "SC-55", "SC-88", "SC-88Pro", "SC-8850"};
        std::vector<bool> lit;
        for (int i = 0; i < 5; i++)
            lit.push_back((int)std::lround(gv(13)) == i);
        const int h = flow_buttons(a, "sustd", BX + 12, y, BW - 24, STDS, lit);
        if (h >= 0)
            gset(13, h);
    }

    // BORROWED TIME (rubato)
    y = Y0 + 10;
    head(CX, y, "BORROWED TIME", "rubato", "su:rubato");
    const J *r = U.s.get("rubato");
    auto rv = [&](size_t i) { return r && r->is(J::ARR) && i < r->a.size() ? r->a[i].d() : 0.0; };
    auto ms = [&](double f) {
        char b[32];
        snprintf(b, sizeof b, "%.1f ms", rate > 0 ? 1000 * f / rate : 0.0);
        return std::string(b);
    };
    {                                   // (the switch: on by default, kept in the session)
        const bool want = flag(&U.s, "rubato_want");
        const int h = flow_buttons(a, "surub", CX + 12, y, CW - 24, {"BORROW TIME WHEN LATE"}, {want});
        if (h == 0) {
            call(a, std::string("{\"call\":\"rubato_set\",\"on\":") + (want ? "false" : "true") + "}");
            U.s.o["rubato_want"] = sess::boolean(!want);   // (shown at once; the push confirms)
        }
        y += 8;
    }
    std::string note;
    if (flag(&U.s, "rubato_on")) {
        const std::pair<std::string, std::string> rows[5] = {{"Callbacks that waited", jnum(rv(0))},
                                                             {"Time held, ever", ms(rv(1))},
                                                             {"Owed now", ms(rv(2))},
                                                             {"Time returned", ms(rv(6)) + " (" + jnum(rv(5)) + " cuts)"},
                                                             {"Held by the partials ringing on", ms(rv(7))}};
        for (const auto &row : rows) {
            text(a, a.font, 14, CX + 12, y, SILK_DIM, fit(a, a.font, 14, row.first, CW - 150));
            text(a, a.font, 14, CX + CW - 12 - text_w(a, a.font, 14, row.second), y, LCD, row.second);
            y += IP ? LH + 6 : 24;
        }
        y += 8;
        note = "When a block is late, the sound already playing is held on and the time is borrowed; it is given back where no note falls.";
    } else
        note = "Off: a block that is late drops out, a click.";
    for (const auto &l : wrap(a, a.font, 14, note, CW - 24)) {
        text(a, a.font, 14, CX + 12, y, SILK_DIM, l);
        y += LH;
    }
}

}  // namespace nui
