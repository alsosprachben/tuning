// THE SYNTH CARD (ui/app.js's): the part's synth as the Messenger's panel
// lays it out -- its sections in columns (LFO 1 with the left hand under
// it, the oscillators, mixer, filter, envelopes, delay), each control at its
// place ("row.col[.rows]" in the engine's knob table). A knob, a wave knob
// with its scope, a switch or a segmented one; the engine answers each move
// with its words; a double-tap gives the patch's back; a changed control's
// value is its own colour. LAYER A / B where the patch has two.
#pragma once

#include "app.h"
#include "widgets.h"

namespace nui {

// THE KNOB TABLE (hello's "knobs"): what each control is
struct Knob {
    int knob = 0, at = 0, row = 1, col = 1, rows = 1;
    std::string column, generic, kind;
    bool centred = false;
    std::vector<double> steps;
    std::vector<std::string> words;
};

struct SynthUi {
    bool loaded = false;
    std::vector<Knob> knobs;
    J synth;                            // ({row, layer, layers, pn[knob], text[i], own[knob]})
    int layer = 0, for_row = -1;
    std::map<int, std::string> text;   // (a knob's words, as the engine last answered a move)
};
static SynthUi g_syn;

// THE WAVES, as the engine makes them (kit.js's Wave: moog.py _osc_parts, _sub_cached)
static const double W_TRI = 0.335, W_SAW = 0.5, W_SQUARE = 0.68, W_FOLD_MAX = 5, W_PULSE_MIN = 0.025, W_SUB_SQUARE = 0.3,
                    W_SUB_PULSE_MIN = 0.0033;
inline double w_reflect(double x)
{
    x = std::fmod(std::fmod(x + 1, 4) + 4, 4);
    return x <= 2 ? x - 1 : 3 - x;
}
inline double w_tri(double x) { return x < 0.5 ? -1 + 4 * x : 3 - 4 * x; }
inline double w_pulse(double d, double c, double x) { return x >= c - d / 2 && x < c + d / 2 ? 1 : -1; }
inline double w_osc(double s, double x)
{
    if (s < W_TRI)
        return w_reflect((1 + (W_FOLD_MAX - 1) * (W_TRI - s) / W_TRI) * w_tri(x));
    if (s < W_SAW) {
        const double a = (s - W_TRI) / (W_SAW - W_TRI);
        return (1 - a) * w_tri(x) + a * (-1 + 2 * x);
    }
    if (s < W_SQUARE) {
        const double a = (s - W_SAW) / (W_SQUARE - W_SAW);
        return (1 - a) * (-1 + 2 * x) + a * w_pulse(0.5, 0.75, x);
    }
    return w_pulse(0.5 - (0.5 - W_PULSE_MIN) * (s - W_SQUARE) / (1 - W_SQUARE), 0.75, x);
}
inline double w_sub(double s, double x)
{
    if (s < W_SUB_SQUARE) {
        const double a = s / W_SUB_SQUARE;
        return (1 - a) * w_tri(x) + a * w_pulse(0.5, 0.5, x);
    }
    return w_pulse(0.5 - (0.5 - W_SUB_PULSE_MIN) * (s - W_SUB_SQUARE) / (1 - W_SUB_SQUARE), 0.5, x);
}
// (two periods across the scope, fine enough for a 2% pulse)
inline void scope(App &a, float x, float y, float w, float h, bool sub, double s)
{
    rect(a, x, y, w, h, IM_COL32(0x15, 0x17, 0x1a, 255), 4);
    dl()->AddLine(P(a, x + 2, y + h / 2), P(a, x + w - 2, y + h / 2), IM_COL32(0x33, 0x36, 0x3a, 255), 1);
    const int N = 400;
    dl()->PathClear();
    for (int i = 0; i <= N; i++) {
        const double ph = std::fmod(2.0 * i / N, 1.0);
        const double v = sub ? w_sub(s, i == N ? 0.9999 : ph) : w_osc(s, i == N ? 0.9999 : ph);
        dl()->PathLineTo(ImVec2(a.org.x + (x + 3 + (float)i / N * (w - 6)) * a.k,
                                a.org.y + (y + h / 2 - (float)v * (h / 2 - 4)) * a.k));
    }
    dl()->PathStroke(LCD, 0, 1.5f * a.k);
}

inline void syn_load(App &a)
{
    SynthUi &Y = g_syn;
    Y.loaded = true;
    J h = call(a, "{\"call\":\"hello\"}");
    if (const J *ks = h.get("knobs"); ks && ks->is(J::ARR))
        for (const J &x : ks->a) {
            Knob k;
            k.knob = (int)num(&x, "knob");
            k.at = (int)num(&x, "at");
            k.column = str(&x, "column");
            k.generic = str(&x, "generic");
            k.kind = str(&x, "kind");
            k.centred = flag(&x, "centred");
            sscanf(str(&x, "group").c_str(), "%d.%d.%d", &k.row, &k.col, &k.rows);
            if (const J *st = x.get("steps"); st && st->is(J::ARR))
                for (const J &v : st->a)
                    k.steps.push_back(v.d());
            if (const J *ws = x.get("words"); ws && ws->is(J::ARR))
                for (const J &v : ws->a)
                    k.words.push_back(v.is(J::STR) ? v.s : "");
            Y.knobs.push_back(k);
        }
}
inline void syn_refresh(App &a)
{
    SynthUi &Y = g_syn;
    J r = call(a, "{\"call\":\"synth\",\"row\":" + std::to_string(a.row) + ",\"layer\":" + std::to_string(Y.layer) + "}");
    if (const J *s = r.get("synth")) {
        Y.synth = *s;
        Y.for_row = a.row;
        Y.text.clear();
    }
}
inline double syn_pn(App &a, const Knob &k)
{
    const std::string key = "syn" + std::to_string(g_syn.layer) + ":" + std::to_string(k.knob);
    auto it = a.hold.find(key);
    if (it != a.hold.end() && ImGui::GetTime() < it->second.second)
        return it->second.first;
    const J *pn = g_syn.synth.get("pn");
    return pn && pn->is(J::ARR) && k.knob < (int)pn->a.size() ? pn->a[(size_t)k.knob].d() : 0.0;
}
inline bool syn_own(const Knob &k)
{
    const J *o = g_syn.synth.get("own");
    return o && o->is(J::ARR) && k.knob < (int)o->a.size() && o->a[(size_t)k.knob].d() != 0;
}
inline void syn_set(App &a, const Knob &k, int i, double v)
{
    a.hold["syn" + std::to_string(g_syn.layer) + ":" + std::to_string(k.knob)] = {v, ImGui::GetTime() + 0.6};
    J r = call(a, "{\"call\":\"synth_set\",\"row\":" + std::to_string(a.row) + ",\"layer\":" + std::to_string(g_syn.layer) +
                      ",\"knob\":" + std::to_string(k.knob) + ",\"v\":" + jnum(v) + "}");
    if (const J *t = r.get("text"); t && t->is(J::STR))
        g_syn.text[i] = t->s;
    // (marked changed at once: the engine's own mark comes with the next push)
    J &own = g_syn.synth.o["own"];
    if (own.is(J::ARR) && k.knob < (int)own.a.size())
        own.a[(size_t)k.knob] = sess::integer(1);
}
inline void syn_forget(App &a, const Knob &k)
{
    call(a, "{\"call\":\"synth_forget\",\"row\":" + std::to_string(a.row) + ",\"layer\":" + std::to_string(g_syn.layer) +
                ",\"knob\":" + std::to_string(k.knob) + "}");
    a.hold.erase("syn" + std::to_string(g_syn.layer) + ":" + std::to_string(k.knob));
    syn_refresh(a);
}

// A SWITCH (off / on): a pill; a tap flips it, a double-tap the patch's
inline int toggle(App &a, const char *id, float cx, float cy, bool on, const std::string &label, bool own, float lw = 0)
{
    float dummy = 0;
    const int f = gesture(a.K, id, P(a, cx - 32, cy - 18), P(a, cx + 32, cy + 34), dummy, Range());
    rect(a, cx - 28, cy - 15, 56, 30, on ? LCD : IM_COL32(0x15, 0x17, 0x1a, 255), 15);
    dl()->AddCircleFilled(P(a, on ? cx + 13 : cx - 13, cy), 11 * a.k, on ? LCD_BG : CAP, 24);
    label_c(a, a.bold, 14, cx, cy + 20, own ? OWN : SILK_DIM, label, lw);
    return f;
}
// SEGMENTS: one of the words lit; vertical where they are many or long
inline int segments(App &a, const std::string &id, float cx, float cy, const std::vector<std::string> &words, int sel,
                    const std::string &label, bool own, int &picked, float lw = 0, float xmin = -1e9f, float xmax = 1e9f)
{
    bool vert = words.size() > 2;
    for (const auto &w : words)
        vert = vert || w.size() > 6;
    float maxw = 0;
    for (const auto &w : words)
        maxw = std::max(maxw, text_w(a, a.font, 14, w));
    // (a row too wide for its cell stacks)
    vert = vert || (lw > 0 && std::max(40.0f, maxw + 16) * words.size() > lw);
    const float bw = std::max(vert ? 54.0f : 40.0f, maxw + 16), bh = vert ? (a.tab ? 30 : 23) : (a.tab ? 44 : 38);   // (the iPad's taller: fingers)
    const int n = (int)words.size();
    const float W = vert ? bw : bw * n, H = vert ? bh * n : bh, y0 = cy - H / 2;
    // (kept within its section; a stack wider than its cell clear of the one before)
    const float x0 = std::max(xmin, std::min(cx - W / 2, xmax - W));
    cx = x0 + W / 2;
    picked = -1;
    int flags = 0;
    for (int i = 0; i < n; i++) {
        const float x = vert ? x0 : x0 + i * bw, y = vert ? y0 + i * bh : y0;
        const std::string bid = id + "_" + std::to_string(i);
        float dummy = 0;
        const int f = gesture(a.K, bid.c_str(), P(a, x, y), P(a, x + bw, y + bh), dummy, Range());
        if (f & K_TAP)
            picked = i;
        flags |= f;
        rect(a, x, y, bw - 1, bh - 1, i == sel ? (own ? OWN : SILK) : IM_COL32(0x2a, 0x2e, 0x33, 255), 3);
        text_c(a, a.font, 14, x + bw / 2, y + (bh - 14) / 2, i == sel ? PANEL : SILK_DIM, words[(size_t)i]);
    }
    label_c(a, a.bold, 14, cx, y0 + H + 6, own ? OWN : SILK_DIM, label, lw);
    return flags;
}

inline void draw_synth(App &a)
{
    SynthUi &Y = g_syn;
    if (!Y.loaded)
        syn_load(a);
    if (Y.for_row != a.row)
        syn_refresh(a);
    const J *p = part(a, a.row);
    const int layers = (int)num(&Y.synth, "layers");
    const bool T = a.tab;               // (the iPad's: its card from y 210 to 734, two pages)
    const float HX = T ? 22 : 34, HY = T ? 224 : 356, BY = T ? 216 : 346, BH = T ? 44 : 38, HX1 = T ? 1105 : 1886;
    const float TX = heading(a, HX, HY, "SYNTH", "synth");
    if (layers <= 0) {
        text(a, a.font, 21, HX, T ? 270 : 400, SILK_DIM,
             layers < 0 ? std::string("Reading the part\xe2\x80\xa6")
                        : (p ? str(p, "name") : std::string("This part")) + " is not a synth.");
        text(a, a.font, 14, HX, T ? 300 : 432, SILK_DIM,
             "The synth programs (Synth Lead, Synth Pad, the synth basses, brass and strings) bring their knobs here.");
        return;
    }
    text(a, a.font, 14, TX, HY + 1, OWN, fit(a, a.font, 14, "part " + pad2(a.row + 1) + " \xc2\xb7 " + (p ? str(p, "name") : ""), T ? 200 : 900));
    // (the iPad's two pages: the sound's sources and shaping; its movement and time)
    static int page = 0;
    if (T)
        for (int pg = 0; pg < 2; pg++) {
            const std::string id = "sypage" + std::to_string(pg);
            if (button(a, id.c_str(), 300 + pg * 214, BY, 208, BH, pg ? "LFO \xc2\xb7 ENV \xc2\xb7 DELAY" : "OSC \xc2\xb7 MIX \xc2\xb7 FILTER",
                       page == pg, true, 21))
                page = pg;
        }
    // the head: back to the patch (how many changed), the layers
    int changed = 0;
    for (const Knob &k : Y.knobs)
        changed += syn_own(k);
    const float bbw = T ? (layers >= 2 ? 200 : 360) : 420;
    if (button(a, "synback", HX1 - bbw, BY, bbw, BH,
               changed ? std::to_string(changed) + (T && layers >= 2 ? " CHANGED \xc2\xb7 BACK" : " CHANGED \xc2\xb7 BACK TO THE PATCH")
                       : "AS THE PATCH", false, changed > 0, T ? 21 : 14)) {
        for (const Knob &k : Y.knobs)
            if (syn_own(k))
                call(a, "{\"call\":\"synth_forget\",\"row\":" + std::to_string(a.row) + ",\"layer\":" +
                            std::to_string(Y.layer) + ",\"knob\":" + std::to_string(k.knob) + "}");
        syn_refresh(a);
    }
    if (layers >= 2)
        for (int l = 0; l < 2; l++) {
            const std::string id = "layer" + std::to_string(l);
            if (button(a, id.c_str(), HX1 - bbw - (T ? 176 : 260) + l * (T ? 86 : 124), BY, T ? 82 : 120, BH, l ? "LAYER B" : "LAYER A",
                       Y.layer == l, true, T ? 14 : 14)) {
                Y.layer = l;
                take_parts(a, call(a, "{\"call\":\"select\",\"row\":" + std::to_string(a.row) + ",\"layer\":" + std::to_string(l) + "}"));
                syn_refresh(a);
            }
        }

    // THE COLUMNS: the panel's sections, their widths in proportion
    struct Col {
        const char *name;
        float weight;
        int label_col;                  // (a first column for the rows' names)
    };
    // (in proportion to the controls side by side in each: a row's number a half)
    static const Col COLS[] = {{"LFO 1", 2.6f, 0}, {"Oscillators", 5.6f, 1}, {"Mixer", 1.8f, 0},
                               {"Filter", 2.4f, 0}, {"Envelopes", 5.2f, 1}, {"Delay", 2.2f, 0}};
    // (the iPad's pages: the left hand a column of its own, LFO 1 the full height for its stacks)
    static const Col PAGES[2][4] = {{{"Oscillators", 5.6f, 1}, {"Mixer", 1.8f, 0}, {"Filter", 2.4f, 0}, {nullptr, 0, 0}},
                                    {{"LFO 1", 2.2f, 0}, {"Left hand", 2.3f, 0}, {"Envelopes", 4.4f, 1}, {"Delay", 1.8f, 0}}};
    std::vector<Col> cols;
    if (T) {
        for (const Col &c : PAGES[page])
            if (c.name)
                cols.push_back(c);
    } else
        cols.assign(std::begin(COLS), std::end(COLS));
    float tot = 0;
    for (const Col &c : cols)
        tot += c.weight;
    const float X0 = T ? 18 : 26, X1 = T ? 1115 : 1894, gap = T ? 6 : 8, top = T ? 266 : 394, bottom = T ? 728 : 1056;
    const float avail = X1 - X0 - gap * (cols.size() - 1);
    float cx0 = X0;
    for (const Col &col : cols) {
        const float cw = avail * col.weight / tot;
        rect(a, cx0, top, cw, bottom - top, IM_COL32(0x1f, 0x22, 0x26, 255), 8);
        // a column's sections: itself, and what stacks under it (the left hand under LFO 1)
        std::vector<std::pair<std::string, std::pair<float, float>>> secs;   // (name, (y0, y1))
        if (std::string(col.name) == "LFO 1" && !T) {
            secs.push_back({"LFO 1", {top, top + 0.62f * (bottom - top)}});
            secs.push_back({"Left hand", {top + 0.62f * (bottom - top), bottom}});
        } else
            secs.push_back({col.name, {top, bottom}});
        for (const auto &sec : secs) {
            const float sy0 = sec.second.first, sy1 = sec.second.second;
            if (sy0 > top)
                rect(a, cx0 + 10, sy0, cw - 20, 1, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
            std::string up = sec.first;
            for (char &ch : up)
                ch = (char)toupper((unsigned char)ch);
            heading(a, cx0 + 12, sy0 + 10, up, "synth:" + sec.first);
            // its grid: rows and columns from the controls' places
            int nr = 1, nc = 1;
            for (const Knob &k : Y.knobs)
                if (k.column == sec.first) {
                    nr = std::max(nr, k.row + k.rows - 1);
                    nc = std::max(nc, k.col);
                }
            const int lc = sec.first == "Oscillators" || sec.first == "Envelopes" ? 1 : 0;
            const float gx = cx0 + 6, gy = sy0 + 34, gw = cw - 12, gh = sy1 - sy0 - 40;
            const float cellw = gw / (nc + (sec.first == "Oscillators" ? 1 : 0) - (sec.first == "Envelopes" ? 0 : 0)),
                        cellh = gh / nr;
            (void)lc;
            // the rows' names
            if (sec.first == "Oscillators")
                for (int r = 1; r <= 2; r++)
                    text_c(a, a.font, 35, gx + cellw * 0.35f, gy + (r - 1) * cellh + cellh / 2 - 20, SILK_DIM, std::to_string(r));
            if (sec.first == "Envelopes") {
                static const char *ENV[2] = {"FILTER", "AMPLIFIER"};
                for (int r = 0; r < 2; r++) {
                    text(a, a.bold, 14, gx + 4, gy + r * cellh + cellh / 2 - 16, SILK_DIM, ENV[r]);
                    text(a, a.bold, 14, gx + 4, gy + r * cellh + cellh / 2, SILK_DIM, "ENVELOPE");
                }
            }
            for (size_t i = 0; i < Y.knobs.size(); i++) {
                const Knob &k = Y.knobs[i];
                if (k.column != sec.first)
                    continue;
                const int c = k.col + (sec.first == "Oscillators" ? 1 : 0);
                const float ccx = gx + (c - 0.5f) * cellw, ccy = gy + (k.row - 1) * cellh + k.rows * cellh / 2;
                const bool own = syn_own(k);
                const std::string id = "k" + std::to_string(k.knob);
                const double pn = syn_pn(a, k);
                const J *tx = Y.synth.get("text");
                std::string words = Y.text.count((int)i) ? Y.text[(int)i]
                                    : tx && tx->is(J::ARR) && i < tx->a.size() && tx->a[i].is(J::STR) ? tx->a[i].s : "";
                if (!k.steps.empty()) {
                    // a switch: off/on a pill; else segments
                    int sel = 0;
                    for (size_t s = 0; s < k.steps.size(); s++)
                        if (std::fabs(k.steps[s] - pn) < 1e-6)
                            sel = (int)s;
                    std::string label = k.generic;
                    for (char &ch : label)
                        ch = (char)toupper((unsigned char)ch);
                    if (k.steps.size() == 2 && k.words.size() == 2 && k.words[0] == "off" && k.words[1] == "on") {
                        const int f = toggle(a, id.c_str(), ccx, ccy - 10, sel == 1, label, own, cellw - 6);
                        if (f & K_RESET)
                            syn_forget(a, k);
                        else if (f & K_TAP)
                            syn_set(a, k, (int)i, k.steps[sel == 1 ? 0 : 1]);
                    } else {
                        int picked;
                        // (a stack wider than its cell starts at its cell's left, so it clears the control before)
                        const float cl = gx + (c - 1) * cellw;
                        const int f = segments(a, id, ccx, ccy - 10, k.words, sel, label, own, picked, cellw - 6,
                                               k.words.size() > 2 ? cl : gx, gx + gw);
                        if (f & K_RESET)
                            syn_forget(a, k);
                        else if (picked >= 0 && picked != sel)
                            syn_set(a, k, (int)i, k.steps[(size_t)picked]);
                    }
                    continue;
                }
                // a knob: a wave's with its scope; the cutoff big
                const bool wave = k.kind == "wave" || k.kind == "subwave", big = k.kind == "hz";
                float v01 = (float)pn;
                std::vector<float> det;
                if (k.kind == "wave")
                    det = {(float)W_TRI, (float)W_SAW, (float)W_SQUARE};
                else if (k.kind == "subwave")
                    det = {(float)W_SUB_SQUARE};
                else if (k.centred)
                    det = {0.5f};
                const float size = std::max(a.tab ? 44.0f : 0.0f, big ? std::min(110.0f, cellw * 0.8f) : std::min(56.0f, cellw * 0.6f));   // (44 points the least on the iPad)
                float ky = ccy - (big ? 20 : 14);
                if (wave) {
                    const float sw = std::min(96.0f, cellw - 10);
                    scope(a, ccx - sw / 2, ky - size / 2 - 50, sw, 36, k.kind == "subwave", pn);
                    ky += 12;
                }
                std::string label = k.generic;
                for (char &ch : label)
                    ch = (char)toupper((unsigned char)ch);
                const int f = knob(a, id.c_str(), ccx, ky, size, v01, label, words, k.centred, det, cellw - 6, own);
                if (f & K_CHANGED)
                    syn_set(a, k, (int)i, v01);
                if (f & K_RESET)
                    syn_forget(a, k);
            }
        }
        cx0 += cw + gap;
    }
}

}  // namespace nui
