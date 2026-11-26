// THE CONTROL CARD (the retired web interface's): the on-screen controls (a pedal or wheel
// the keyboard lacks), each sent straight to the engine on its channel -- a
// switch latching (press down, press up), the pitch wheel and aftertouch
// springing back when let go. And the routes: the keyboard's own controls
// rewritten -- a key as the sustain, a CC onto another, the wheel's half
// onto a switch -- with learn for the source.
#pragma once

#include "app.h"
#include "piano.h"
#include "synth.h"
#include "tuning.h"

namespace nui {

struct CtKind {
    int key = 0, dflt = 0;
    std::string label, kind;
};
struct ControlUi {
    bool open = false, adding = false;
    std::vector<CtKind> kinds;
    J c;                                // (control_of: controls [{i, key, channel, value, on}], routes [{i, text}], learning, learnt)
    // a new route: its source (0 a CC, 1 the wheel's half, 2 aftertouch, 3 a key), argument, destination, how
    int src = -1, arg = -1, dst = -999, keep = 0, ch = -1, latch = 0, press = 1, waiting = 0;
    // (what this screen sent: a switch's state held a moment; a drag's values at most 30 a second)
    std::map<int, std::pair<int, double>> mine;
    std::map<int, int> want;            // (a control's value still to send)
    std::map<int, double> sent_t;       // (...and when its last went)
};
static ControlUi g_ct;

inline void ct_take(const J &r)
{
    ControlUi &C = g_ct;
    const J *c = r.get("control");
    if (!c)
        return;
    if (const J *ks = c->get("kinds"); ks && ks->is(J::ARR)) {
        C.kinds.clear();
        for (const J &k : ks->a)
            C.kinds.push_back({(int)k.a[0].d(), (int)k.a[3].d(), k.a[1].s, k.a[2].s});
    }
    C.c = *c;
    // a learnt source becomes the new route's
    if (const J *l = c->get("learnt"); l && l->is(J::ARR) && l->a.size() >= 2 && l->a[0].d() != 0 && C.waiting) {
        C.waiting = 0;
        C.src = (int)l->a[0].d() == 1 ? 3 : 0;
        C.arg = (int)l->a[1].d();
    }
}
inline void control_card(App &a, bool open)
{
    ControlUi &C = g_ct;
    if (open == C.open)
        return;
    C.open = open;
    ct_take(call(a, std::string("{\"call\":\"control\",\"open\":") + (open ? "1" : "0") + ",\"kinds\":" + (C.kinds.empty() ? "1" : "0") + "}"));
}
inline CtKind ct_kind(int key)
{
    for (const CtKind &k : g_ct.kinds)
        if (k.key == key)
            return k;
    return {key, 0, "CC" + std::to_string(key), "continuous"};
}
inline void ct_send(int i, int v) { g_ct.want[i] = v; }
inline void ct_flush(App &a)
{
    const double now = ImGui::GetTime();
    for (auto it = g_ct.want.begin(); it != g_ct.want.end();) {
        double &last = g_ct.sent_t[it->first];
        if (now - last < 0.033) {
            a.animate = true;
            ++it;
            continue;
        }
        call(a, "{\"call\":\"control_set\",\"i\":" + std::to_string(it->first) + ",\"v\":" + std::to_string(it->second) + "}");
        last = now;
        it = g_ct.want.erase(it);
    }
}
inline void ct_refresh(App &a) { ct_take(call(a, "{\"call\":\"control\"}")); }

inline void draw_metro_gs(App &a, float x, float y, float w, float y1);     // (scenes.h)
inline void draw_control(App &a)
{
    ControlUi &C = g_ct;
    if (!C.c.is(J::OBJ) || C.kinds.empty())
        ct_take(call(a, "{\"call\":\"control\",\"open\":1,\"kinds\":1}"));
    ct_flush(a);
    // (the iPad's: its card from y 210 to card_y1 + 6, two pages -- the on-screen controls; the routes)
    const bool IP = a.tab;
    static int page = 0;
    const float X0 = IP ? 20 : 34, X1 = IP ? 1113 : 1886, Y0 = IP ? 266 : 394, Y1 = card_y1(a), HY = IP ? 224 : 356;
    const float TX = heading(a, X0, HY, "CONTROL", "control");
    if (IP)
        for (int pg = 0; pg < 3; pg++) {
            static const char *PG[3] = {"CONTROLS", "ROUTES", "METRONOME"};
            const std::string id = "ctpage" + std::to_string(pg);
            if (button(a, id.c_str(), 300 + pg * 196, 216, 190, 44, PG[pg], page == pg, true, 21))
                page = pg;
        }
    // THE METRONOME AND THE GS RESET: under the on-screen controls (the iPad's a page of its own)
    const float MH = IP ? 0 : 190;
    if (IP && page == 2) {
        draw_metro_gs(a, X0, Y0, X1 - X0, Y0 + 200);
        return;
    }
    const J *p = part(a, a.row);
    if (p)
        text(a, a.font, 14, TX, HY + 1, OWN, fit(a, a.font, 14, "part " + pad2(a.row + 1) + " \xc2\xb7 " + str(p, "name"), IP ? 160 : 900));
    const J *ctls = C.c.get("controls"), *routes = C.c.get("routes");
    const int nc = ctls && ctls->is(J::ARR) ? (int)ctls->a.size() : 0, nr = routes && routes->is(J::ARR) ? (int)routes->a.size() : 0;
    const std::string info = std::to_string(nc) + " control" + (nc == 1 ? "" : "s") + " \xc2\xb7 " + std::to_string(nr) + " route" + (nr == 1 ? "" : "s");
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), HY + 1, SILK_DIM, info);
    const int pch = p ? (int)num(p, "channel", -1) : -1;

    // THE ON-SCREEN CONTROLS
    const float LW = IP ? X1 - X0 : 900;
    if (!IP || page == 0) {
    if (!IP)
        draw_metro_gs(a, X0, Y1 - MH, LW, Y1);
    look::tray(a, X0, Y0, LW, Y1 - MH - 10 - Y0, 9);
    text(a, a.font, 14, heading(a, X0 + 12, Y0 + 10, "ON-SCREEN CONTROLS", "ct:strip"), Y0 + 11, LCD, "sent straight to the engine");
    const float cw = IP ? 124 : 136, cy0 = Y0 + 40, ch_ = C.adding ? (IP ? 214 : 250) : Y1 - MH - 10 - Y0 - 52;
    float x = X0 + 12;
    static const int SCAN_V[7] = {0, 18, 37, 55, 73, 91, 110};
    static const std::vector<std::string> SCAN_N = {"off", "V1", "V2", "V3", "C1", "C2", "C3"};
    for (int n = 0; n < nc; n++) {
        const J &c = ctls->a[(size_t)n];
        const int i = (int)num(&c, "i"), key = (int)num(&c, "key"), chn = (int)num(&c, "channel", -1);
        const CtKind k = ct_kind(key);
        std::string label = k.label;
        for (char &ch : label)
            ch = (char)toupper((unsigned char)ch);
        rect(a, x, cy0, cw - 8, ch_, IM_COL32(0x26, 0x2a, 0x2e, 255), 8);
        const float bx = x + (cw - 8) / 2, bottom = cy0 + ch_;
        const std::string id = "ct" + std::to_string(i);
        if (k.kind == "switch") {
            bool on = flag(&c, "on");
            auto m = C.mine.find(i);
            if (m != C.mine.end() && ImGui::GetTime() < m->second.second)
                on = m->second.first != 0;
            if (pedal_btn(a, id.c_str(), bx, cy0 + 20, on, label.c_str(), "")) {
                C.mine[i] = {on ? 0 : 1, ImGui::GetTime() + 0.6};
                call(a, "{\"call\":\"control_set\",\"i\":" + std::to_string(i) + ",\"v\":" + (on ? "0" : "127") + "}");
            }
        } else if (k.kind == "selector") {
            const int v = (int)num(&c, "value");
            int sel = 0;
            for (int j = 0; j < 7; j++)
                if (v >= SCAN_V[j])
                    sel = j;
            int picked;
            segments(a, id, bx, cy0 + 110, SCAN_N, sel, label, false, picked, cw - 14);
            if (picked >= 0 && picked != sel)
                call(a, "{\"call\":\"control_set\",\"i\":" + std::to_string(i) + ",\"v\":" + std::to_string(SCAN_V[picked]) + "}");
        } else {
            const bool bend = k.kind == "bend", spring = bend || k.kind == "pressure";
            float v = (float)num(&c, "value");
            auto w = C.want.find(i);
            if (w != C.want.end())
                v = (float)w->second;
            const float lo = bend ? -8192 : 0, hi = bend ? 8191 : 127;
            char vt[16];
            snprintf(vt, sizeof vt, bend && v > 0 ? "+%d" : "%d", (int)std::lround(v));
            const int f = fader(a, id.c_str(), bx, cy0 + 16, ch_ - 160, v, lo, hi, 1, bend ? std::vector<float>{0} : std::vector<float>{},
                                label, vt);
            if (f & K_CHANGED)
                ct_send(i, (int)std::lround(v));
            if ((f & K_ENDED) && spring)     // (the wheel and aftertouch spring back)
                ct_send(i, 0);
        }
        text_c(a, a.font, 14, bx, bottom - (IP ? 62 : 66), SILK_DIM, chn < 0 ? "every ch" : "ch " + std::to_string(chn + 1));
        const std::string rid = "ctrm" + std::to_string(i);
        if (button(a, rid.c_str(), x + 6, bottom - (IP ? 50 : 44), cw - 20, IP ? 44 : 34, "REMOVE")) {
            call(a, "{\"call\":\"control_remove\",\"i\":" + std::to_string(i) + "}");
            ct_refresh(a);
            return;
        }
        x += cw;
    }
    if (button(a, "ctadd", x, cy0, text_w(a, a.bold, IP ? 21 : 14, "+ ADD A CONTROL") + 30, IP ? 54 : 60, "+ ADD A CONTROL", C.adding, true,
               IP ? 21 : 14))
        C.adding = !C.adding;
    if (C.adding) {     // the kinds, on the part's channel (else every channel)
        float y = cy0 + ch_ + 14;
        text(a, a.font, 14, X0 + 12, y, SILK_DIM,
             "Add a control on " + (pch < 0 ? std::string("every channel") : "channel " + std::to_string(pch + 1) + " (part " + pad2(a.row + 1) + "'s)") + ":");
        y += IP ? 20 : 26;
        std::vector<std::string> w;
        std::vector<bool> lit;
        for (const CtKind &k : C.kinds) {
            w.push_back(k.label);
            bool have = false;
            for (int n = 0; n < nc; n++)
                have = have || ((int)num(&ctls->a[(size_t)n], "key") == k.key && (int)num(&ctls->a[(size_t)n], "channel", -1) == pch);
            lit.push_back(have);
        }
        const int h = flow_buttons(a, "ctkind", X0 + 12, y, LW - 24, w, lit, 28, IP ? 14 : 0);
        if (h >= 0) {
            call(a, "{\"call\":\"control_add\",\"key\":" + std::to_string(C.kinds[(size_t)h].key) + ",\"channel\":" + std::to_string(pch) + "}");
            C.adding = false;
            ct_refresh(a);
        }
    }

    // THE ROUTES: the keyboard's own controls rewritten before the engine hears them
    }
    if (IP && page == 0)
        return;
    const float RX = IP ? X0 : X0 + LW + 10, RW = X1 - RX, RB = IP ? 44 : 32, LB = IP ? 44 : 30;
    look::tray(a, RX, Y0, RW, Y1 - Y0, 9);
    text(a, a.font, 14, heading(a, RX + 12, Y0 + 10, "ROUTES", "ct:routes"), Y0 + 11, LCD, "the keyboard's controls, rewritten first");
    float ry = Y0 + 40;
    if (!nr) {
        text(a, a.font, 14, RX + 12, ry, SILK_DIM, "No routes: the keyboard's controls reach the engine as they are.");
        ry += 30;
    }
    for (int n = 0; n < nr; n++) {
        const J &r = routes->a[(size_t)n];
        text(a, a.font, 14, RX + 12, ry + (RB - a.lh(14)) / 2, SILK, fit(a, a.font, 14, str(&r, "text"), RW - 140));
        const std::string id = "rtrm" + std::to_string((int)num(&r, "i"));
        if (button(a, id.c_str(), RX + RW - 118, ry, 106, RB, "REMOVE")) {
            call(a, "{\"call\":\"route_remove\",\"i\":" + std::to_string((int)num(&r, "i")) + "}");
            ct_refresh(a);
            return;
        }
        ry += RB + 6;
    }
    // A NEW ROUTE: from, to, how
    ry += 10;
    rect(a, RX + 12, ry, RW - 24, 1, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
    ry += 10;
    heading(a, RX + 12, ry, "A NEW ROUTE", "ct:new");
    ry += IP ? 22 : 26;
    const int learning = (int)num(&C.c, "learning");
    const bool blink = std::fmod(ImGui::GetTime(), 0.8) < 0.4;
    if (learning)
        a.animate = true;
    {
        text(a, a.bold, 14, RX + 12, ry + (LB - a.lh(14)) / 2, SILK_DIM, "FROM");
        std::vector<std::string> w = {learning == 1 ? "PRESS A KEY\xe2\x80\xa6" : "A KEY (LEARN)",
                                      learning == 2 ? "MOVE A CONTROL\xe2\x80\xa6" : "A CONTROLLER (LEARN)", "WHEEL UP",
                                      "WHEEL DOWN", "WHEEL EITHER", "AFTERTOUCH"};
        std::vector<bool> lit = {learning == 1 ? blink : C.src == 3, learning == 2 ? blink : C.src == 0,
                                 C.src == 1 && C.arg == 0, C.src == 1 && C.arg == 1, C.src == 1 && C.arg == 2, C.src == 2};
        const int h = flow_buttons(a, "rtfrom", RX + 70, ry, RW - 82, w, lit);
        if (h == 0 || h == 1) {
            const int k = h + 1, on = learning != k;
            C.waiting = on ? k : 0;
            call(a, "{\"call\":\"route_learn\",\"kind\":" + std::to_string(on ? k : 0) + "}");
            C.c.o["learning"] = sess::integer(on ? k : 0);
        } else if (h >= 2 && h <= 4) {
            C.src = 1;
            C.arg = h - 2;
        } else if (h == 5) {
            C.src = 2;
            C.arg = 0;
        }
    }
    {
        text(a, a.bold, 14, RX + 12, ry + (LB - a.lh(14)) / 2, SILK_DIM, "TO");
        std::vector<std::string> w;
        std::vector<bool> lit;
        std::vector<int> keys;
        for (const CtKind &k : C.kinds)
            if (k.key >= 0 || k.key == -3) {
                std::string up = k.label;       // (in capitals, as the FROM row's)
                for (char &c : up)
                    c = (char)toupper((unsigned char)c);
                w.push_back(up);
                lit.push_back(C.dst == k.key);
                keys.push_back(k.key);
            }
        const int h = flow_buttons(a, "rtto", RX + 70, ry, RW - 82, w, lit, 26, IP ? 14 : 0);   // (the many: 2x)
        if (h >= 0)
            C.dst = keys[(size_t)h];
    }
    const CtKind dk = ct_kind(C.dst);
    const bool sw = C.dst != -999 && dk.kind == "switch";
    {
        text(a, a.bold, 14, RX + 12, ry + (LB - a.lh(14)) / 2, SILK_DIM, "HOW");
        std::vector<std::string> w = {"KEEP THE ORIGINAL TOO"};
        std::vector<bool> lit = {C.keep != 0};
        std::vector<int> what = {0};
        if (sw) {
            w.push_back("LATCH (PRESS ON, PRESS OFF)");
            lit.push_back(C.latch != 0);
            what.push_back(1);
        }
        if (C.src == 3 && C.dst == 64) {
            w.push_back("PUSH INTO IT TO DAMP");
            lit.push_back(C.press != 0);
            what.push_back(2);
        }
        w.push_back("EVERY CHANNEL");
        lit.push_back(C.ch < 0);
        what.push_back(3);
        if (pch >= 0) {
            w.push_back("CHANNEL " + std::to_string(pch + 1));
            lit.push_back(C.ch == pch);
            what.push_back(4);
        }
        const int h = flow_buttons(a, "rthow", RX + 70, ry, RW - 82, w, lit);
        if (h >= 0)
            switch (what[(size_t)h]) {
            case 0: C.keep = !C.keep; break;
            case 1: C.latch = !C.latch; break;
            case 2: C.press = !C.press; break;
            case 3: C.ch = -1; break;
            case 4: C.ch = pch; break;
            }
    }
    static const char *KN[12] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
    const std::string src_name = C.src == 3 ? (C.arg >= 0 ? "key " + std::string(KN[C.arg % 12]) + std::to_string(C.arg / 12 - 1) : "a key")
                                 : C.src == 0 ? (C.arg >= 0 ? "CC" + std::to_string(C.arg) : "a controller")
                                 : C.src == 1 ? std::string(C.arg == 0 ? "the pitch wheel up" : C.arg == 1 ? "the pitch wheel down" : "the pitch wheel, either way")
                                 : C.src == 2 ? "aftertouch" : "\xe2\x80\x94";
    const bool ready = C.src >= 0 && (C.src == 1 || C.src == 2 || C.arg >= 0) && C.dst != -999;
    text(a, a.font, 21, RX + 12, ry + ((IP ? 44 : 40) - a.lh(21)) / 2, LCD, fit(a, a.font, 21, src_name + " \xe2\x86\x92 " + (C.dst != -999 ? dk.label : std::string("\xe2\x80\xa6")), RW - 260));
    if (button(a, "rtadd", RX + RW - 232, ry, 220, IP ? 44 : 40, "ADD THE ROUTE", false, ready, IP ? 21 : 14) && ready) {
        const int r7[7] = {C.src, C.src == 2 ? 0 : C.arg, C.dst, C.keep, C.ch, sw ? C.latch : 0, C.src == 3 && C.dst == 64 ? C.press : 0};
        std::string rs = "[";
        for (int j = 0; j < 7; j++)
            rs += (j ? "," : "") + std::to_string(r7[j]);
        call(a, "{\"call\":\"route_add\",\"r\":" + rs + "]}");
        C.src = C.arg = -1;
        C.dst = -999;
        C.keep = C.latch = 0;
        C.ch = -1;
        C.press = 1;
        ct_refresh(a);
    }
}

}  // namespace nui
