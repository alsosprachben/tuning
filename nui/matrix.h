// THE MATRIX CARD (the retired web interface's): what each controller moves on the selected
// part's channel (GS's controller matrix, 40 2x) -- the six sources down
// the side, the eleven destinations across, a knob in each cell in the
// destination's own unit. Changed from power-on: orange. Double-tap a cell:
// back to power-on. CC1 and CC2's controller numbers dragged or LEARNed.
#pragma once

#include "app.h"
#include "effects.h"
#include "library.h"

namespace nui {

struct MxDest {
    int lo = 0, hi = 127, zero = 0;
    std::vector<int> vals;
    std::vector<std::string> shown;
};
struct MatrixUi {
    bool open = false;
    std::vector<MxDest> t;
    J m;                                // (cmx_of: row, part, channel, raw[6][11], def[6][11], cc1, cc2, learning, gm2)
};
static MatrixUi g_mx;

inline void mx_take(App &a, const J &r)
{
    MatrixUi &M = g_mx;
    if (const J *t = r.get("tables"); t && t->is(J::ARR) && M.t.empty())
        for (const J &x : t->a) {
            MxDest d;
            d.lo = (int)num(&x, "lo");
            d.hi = (int)num(&x, "hi", 127);
            d.zero = (int)num(&x, "zero");
            d.vals = irange(d.lo, d.hi);
            if (const J *sh = x.get("shown"); sh && sh->is(J::ARR))
                for (const J &s : sh->a)
                    d.shown.push_back(s.is(J::STR) ? s.s : "");
            M.t.push_back(d);
        }
    if (const J *m = r.get("matrix"); m && (int)num(m, "row", -1) == a.row)
        M.m = *m;
}
inline void matrix_card(App &a, bool open)
{
    MatrixUi &M = g_mx;
    if (open == M.open)
        return;
    M.open = open;
    mx_take(a, call(a, std::string("{\"call\":\"matrix\",\"open\":") + (open ? "1" : "0") + ",\"tables\":" +
                           (M.t.empty() ? "1" : "0") + "}"));
}
inline int mx_at(const J &m, const char *k, int i, int j)
{
    const J *x = m.get(k);
    return x && x->is(J::ARR) && i < (int)x->a.size() && j < (int)x->a[(size_t)i].a.size() ? (int)x->a[(size_t)i].a[(size_t)j].d() : 0;
}

inline void draw_matrix(App &a)
{
    MatrixUi &M = g_mx;
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    if ((int)num(&M.m, "row", -1) != a.row)
        mx_take(a, call(a, "{\"call\":\"matrix\"}"));
    const bool IP = a.tab;              // (the iPad's: its card from y 210 to card_y1 + 6, no notes box: the ? has them)
    const float X0 = IP ? 20 : 34, X1 = IP ? 1113 : 1886, Y0 = IP ? 262 : 394, HY = IP ? 224 : 356;
    const float TX = heading(a, X0, HY, "MATRIX", "matrix");
    if (!M.m.is(J::OBJ) || M.t.size() < 11)
        return;
    text(a, a.font, 14, TX, HY + 1, OWN, "part " + pad2(a.row + 1) + " \xc2\xb7 " + str(&M.m, "part"));
    const int ch = (int)num(&M.m, "channel", -1);
    const std::string info = ch < 0 ? "every channel" : "channel " + std::to_string(ch + 1);
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), HY + 1, SILK_DIM, info);
    if (!M.m.get("raw")) {
        text(a, a.font, 21, X0, Y0 + 10, SILK_DIM, "Reading the matrix\xe2\x80\xa6");
        return;
    }
    static const char *SRC[6] = {"Mod wheel", "Pitch bend", "Channel aftertouch", "Poly aftertouch", "CC1", "CC2"};
    static const char *DG[11] = {"", "", "", "LFO 1", "LFO 1", "LFO 1", "LFO 1", "LFO 2", "LFO 2", "LFO 2", "LFO 2"};
    static const char *DN[11] = {"Pitch", "Cutoff", "Amplitude", "Rate", "Pitch", "Filter", "Amp", "Rate", "Pitch", "Filter", "Amp"};
    const float aboutH = 0, SW = IP ? 156 : 252, gy = Y0 + (IP ? 30 : 40), YB = (card_y1(a)) - aboutH - (IP ? 20 : 34);
    const float cw = (X1 - X0 - SW) / 11, rh = (YB - gy) / 6;
    look::tray(a, X0, Y0, X1 - X0, YB - Y0, 9);
    // the destinations across (the LFOs' groups apart)
    for (int j = 0; j < 11; j++) {
        const float cx = X0 + SW + (j + 0.5f) * cw;
        if (*DG[j])
            text_c(a, a.font, 14, cx, Y0 + (IP ? 3 : 4), SILK_DIM, DG[j]);
        std::string d = DN[j];
        for (char &c : d)
            c = (char)toupper((unsigned char)c);
        text_c(a, a.bold, 14, cx, Y0 + (IP ? 14 : 20), SILK, d);
        if (j == 3 || j == 7)
            rect(a, X0 + SW + j * cw, Y0 + 4, 1, YB - Y0 - 8, IM_COL32(0x3a, 0x3f, 0x45, 255), 0);
    }
    const int learning = (int)num(&M.m, "learning");
    for (int i = 0; i < 6; i++) {
        const float ry = gy + i * rh;
        rect(a, X0 + 8, ry, X1 - X0 - 16, 1, IM_COL32(0x2c, 0x30, 0x35, 255), 0);
        // the source: lit where it moves anything
        bool used = false;
        for (int j = 0; j < 11; j++)
            used = used || fx_val(a, "mx" + std::to_string(i) + "." + std::to_string(j), mx_at(M.m, "raw", i, j)) != M.t[(size_t)j].zero;
        text(a, a.bold, 14, X0 + (IP ? 8 : 12), ry + (i >= 4 ? (IP ? 4 : 10) : (rh - a.lh(14)) / 2), used ? LCD : SILK_DIM,
             fit(a, a.bold, 14, SRC[i], SW - 16));
        if (i >= 4) {   // CC1/CC2: which controller (dragged, as the display's fields), or LEARN it
            const char *key = i == 4 ? "cc1" : "cc2";
            float cc = (float)fx_val(a, key, (int)num(&M.m, key));
            const std::string fid = std::string("mxcc") + key;
            const int f = IP ? lcd_field(a, fid.c_str(), X0 + 6, ry + 16, 72, 44, cc, 0, 95, "IS", "CC" + std::to_string((int)cc), false, 21)
                             : lcd_field(a, fid.c_str(), X0 + 12, ry + 26, 96, 50, cc, 0, 95, "IS", "CC" + std::to_string((int)cc), false, 14);
            if (f & K_CHANGED) {
                fx_mine(a, key, (int)cc);
                call(a, "{\"call\":\"cmx_assign\",\"which\":" + std::to_string(i) + ",\"cc\":" + std::to_string((int)cc) + "}");
            }
            const bool on = learning == i;
            const bool blink = on && std::fmod(ImGui::GetTime(), 0.8) < 0.4;
            const std::string bid = "mxlearn" + std::to_string(i);
            if (IP ? button(a, bid.c_str(), X0 + 82, ry + 16, SW - 90, 44, on ? "MOVE\xe2\x80\xa6" : "LEARN", blink)
                   : button(a, bid.c_str(), X0 + 116, ry + 26, SW - 128, 50, on ? "MOVE ONE\xe2\x80\xa6" : "LEARN", blink)) {
                call(a, "{\"call\":\"cmx_learn\",\"which\":" + std::to_string(on ? 0 : i) + "}");
                mx_take(a, call(a, "{\"call\":\"matrix\"}"));
            }
            if (on)
                a.animate = true;
        }
        for (int j = 0; j < 11; j++) {
            const MxDest &d = M.t[(size_t)j];
            const std::string k = "mx" + std::to_string(i) + "." + std::to_string(j);
            const int v = fx_val(a, k, mx_at(M.m, "raw", i, j)), def = mx_at(M.m, "def", i, j);
            const bool centred = std::fabs((float)(d.zero - d.lo) / (d.hi - d.lo) - 0.5f) < 0.05f;
            int picked;
            const int f = list_knob(a, k, X0 + SW + (j + 0.5f) * cw, ry + rh / 2 - (IP ? 6 : 8), IP ? 44 : 40, d.vals, d.shown, v, "", centred,
                                    cw - 6, picked, v != def);
            if (picked != v) {
                fx_mine(a, k, picked);
                call(a, "{\"call\":\"cmx_set\",\"src\":" + std::to_string(i) + ",\"dest\":" + std::to_string(j) + ",\"raw\":" +
                            std::to_string(picked) + "}");
            }
            if (f & K_RESET) {      // (back to power-on)
                fx_mine(a, k, def);
                call(a, "{\"call\":\"cmx_set\",\"src\":" + std::to_string(i) + ",\"dest\":" + std::to_string(j) + ",\"raw\":" +
                            std::to_string(def) + "}");
            }
        }
    }
    // what a file's GM2 messages set (shown, not changed here)
    if (const J *g = M.m.get("gm2"); g && g->is(J::ARR) && !g->a.empty()) {
        std::string s = "Set by a file's GM2 messages (shown, not changed here): ";
        for (size_t i = 0; i < g->a.size(); i++) {
            const J &e = g->a[i];
            const int dj = (int)e.a[1].d();
            s += (i ? " \xc2\xb7 " : "") + std::string("CC") + std::to_string((int)e.a[0].d()) + " \xe2\x86\x92 " +
                 (dj >= 0 && dj < 11 ? std::string(*DG[dj] ? std::string(DG[dj]) + " " : "") + DN[dj] : "") + " " +
                 (e.a[2].is(J::STR) ? e.a[2].s : "");
        }
        text(a, a.font, 14, X0, YB + 8, SILK_DIM, fit(a, a.font, 14, s, X1 - X0));
    }
}

}  // namespace nui
