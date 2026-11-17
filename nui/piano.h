// THE PIANO CARD (ui/app.js's): the selected part's pedals as the engine
// has them (a file's, the keyboard's, these) -- soft, sostenuto, the sustain
// as a fader with DOWN / HALF / UP -- each damper's rest on its strings at
// the sustain's value (a half pedal: the bass's heavier dampers still
// touching), and the keys held as the pedal (learned, removed). The engine
// pushes the pedals while the card is open ("piano" open 1).
#pragma once

#include "app.h"
#include "library.h"
#include "widgets.h"

namespace nui {

struct PianoUi {
    bool open = false;
    J pn;                               // (piano_of: row, part, channel, sustain, soft, sostenuto, contact[88], band, keys, ...)
    // what this screen just sent stands until the engine has it
    int mine_cc = -1, mine_v = 0;
    double mine_until = 0;
    // (a drag's values at most 30 a second; the last always goes)
    int want_cc = -1, want_v = 0;
    double sent_t = 0;
};
static PianoUi g_piano;

inline void piano_take(App &a, const J &pn)
{
    PianoUi &N = g_piano;
    if ((int)num(&pn, "row", -1) != a.row)
        return;
    N.pn = pn;
    if (ImGui::GetTime() < N.mine_until) {
        if (N.mine_cc == 64)
            N.pn.o["sustain"] = sess::integer(N.mine_v);
        else
            N.pn.o[N.mine_cc == 66 ? "sostenuto" : "soft"] = sess::boolean(N.mine_v > 0);
    }
}
// the card opened or shut: the engine pushes the pedals only while it is open
inline void piano_card(App &a, bool open)
{
    PianoUi &N = g_piano;
    if (open == N.open)
        return;
    N.open = open;
    J r = call(a, std::string("{\"call\":\"piano\",\"open\":") + (open ? "1" : "0") + "}");
    if (const J *p = r.get("piano"))
        piano_take(a, *p);
}
inline void pedal(App &a, int cc, int v)
{
    PianoUi &N = g_piano;
    N.mine_cc = cc;
    N.mine_v = v;
    N.mine_until = ImGui::GetTime() + 0.6;
    if (cc == 64)
        N.pn.o["sustain"] = sess::integer(v);
    else
        N.pn.o[cc == 66 ? "sostenuto" : "soft"] = sess::boolean(v > 0);
    N.want_cc = cc;
    N.want_v = v;
}
inline void pedal_flush(App &a)
{
    PianoUi &N = g_piano;
    if (N.want_cc < 0 || ImGui::GetTime() - N.sent_t < 0.033)
        return;
    call(a, "{\"call\":\"pedal_set\",\"row\":" + std::to_string(a.row) + ",\"cc\":" + std::to_string(N.want_cc) +
                ",\"v\":" + std::to_string(N.want_v) + "}");
    N.sent_t = ImGui::GetTime();
    N.want_cc = -1;
}
inline std::string pedal_say(int v) { return v <= 0 ? "UP" : v >= 127 ? "DOWN" : "HALF " + std::to_string(v); }
inline std::string note_name_sharp(int n)
{
    static const char *N[12] = {"C", "C\xe2\x99\xaf", "D", "D\xe2\x99\xaf", "E", "F", "F\xe2\x99\xaf", "G",
                                "G\xe2\x99\xaf", "A", "A\xe2\x99\xaf", "B"};
    return std::string(N[((n % 12) + 12) % 12]) + std::to_string(n / 12 - 1);
}

// A PEDAL: a tall cap, lit and lowered when down
inline bool pedal_btn(App &a, const char *id, float cx, float y, bool on, const char *name, const char *note)
{
    const float w = 84, h = 150, x = cx - w / 2, dy = on ? 6 : 0;
    ImGui::SetCursorScreenPos(P(a, x, y));
    const bool hit = ImGui::InvisibleButton(id, ImVec2(w * a.k, h * a.k));
    const ImU32 c = on ? LCD : ImGui::IsItemActive() ? PANEL_HI : CAP;
    dl()->AddRectFilled(P(a, x, y + dy), P(a, x + w, y + h + dy), c, 30 * a.k, ImDrawFlags_RoundCornersBottom);
    dl()->AddRectFilled(P(a, x, y + dy), P(a, x + w, y + 20 + dy), c, 10 * a.k, ImDrawFlags_RoundCornersTop);
    frame(a, x, y + dy, w, h, EDGE, 10, 1);
    text_c(a, a.bold, 14, cx, y + h + 16, on ? LCD : SILK, name);
    const auto ls = wrap(a, a.font, 14, note, 124);
    for (size_t i = 0; i < ls.size(); i++)
        text_c(a, a.font, 14, cx, y + h + 36 + i * 17, SILK_DIM, ls[i]);
    return hit;
}

inline void draw_piano(App &a)
{
    PianoUi &N = g_piano;
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    if ((int)num(&N.pn, "row", -1) != a.row) {
        J r = call(a, "{\"call\":\"piano\",\"open\":1}");
        if (const J *p = r.get("piano"))
            piano_take(a, *p);
    }
    pedal_flush(a);
    const float X0 = 34, X1 = 1886;
    text(a, a.bold, 14, X0, 356, SILK, "PIANO");
    if (!N.pn.is(J::OBJ))
        return;
    text(a, a.font, 14, X0 + 76, 357, OWN, "part " + pad2(a.row + 1) + " \xc2\xb7 " + str(&N.pn, "part"));
    const int ch = (int)num(&N.pn, "channel", -1);
    const std::string info = ch < 0 ? "pedals on every channel" : "pedals on channel " + std::to_string(ch + 1);
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), 357, SILK_DIM, info);

    const float aboutH = 140, Y0 = 394, Y1 = 1056 - aboutH - 10;
    const float c1 = 430, c3 = 400, gap = 8, c2 = X1 - X0 - c1 - c3 - 2 * gap;
    auto col = [&](float x, float w, const char *title) {
        rect(a, x, Y0, w, Y1 - Y0, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
        frame(a, x, Y0, w, Y1 - Y0, EDGE, 9, 1);
        text(a, a.bold, 14, x + 12, Y0 + 10, SILK, title);
    };

    // THE PEDALS: soft and sostenuto; the sustain a fader with its quick values
    col(X0, c1, "PEDALS");
    const bool soft = flag(&N.pn, "soft"), sost = flag(&N.pn, "sostenuto");
    const float py = Y1 - 290;
    if (pedal_btn(a, "pdsoft", X0 + 76, py, soft, "SOFT", "una corda"))
        pedal(a, 67, soft ? 0 : 127);
    if (pedal_btn(a, "pdsost", X0 + 206, py, sost, "SOSTENUTO", "holds the keys down as it goes down"))
        pedal(a, 66, sost ? 0 : 127);
    float sus = (float)num(&N.pn, "sustain");
    const float fx = X0 + 350, fy0 = Y0 + 50, fh = Y1 - Y0 - 270;
    {
        const int f = fader(a, "pdsus", fx, fy0, fh, sus, 0, 127, 1, {64}, "SUSTAIN", pedal_say((int)std::lround(sus)));
        if (f & K_CHANGED)
            pedal(a, 64, (int)std::lround(sus));
        if (f & K_RESET)
            pedal(a, 64, 0);
    }
    const int si = (int)num(&N.pn, "sustain");
    static const struct { const char *n; int v; } Q[3] = {{"DOWN", 127}, {"HALF", 64}, {"UP", 0}};
    for (int i = 0; i < 3; i++) {
        const bool on = Q[i].v == 64 ? si > 0 && si < 127 : si == Q[i].v;
        const std::string id = std::string("pq") + Q[i].n;
        if (button(a, id.c_str(), fx - 50, Y1 - 150 + i * 46, 100, 38, Q[i].n, on))
            pedal(a, 64, Q[i].v);
    }

    // THE DAMPERS: each one's rest on its strings, over the keyboard (88 keys, A0 to C8)
    const float dx = X0 + c1 + gap;
    col(dx, c2, "DAMPERS");
    const J *ct = N.pn.get("contact");
    const int n = ct && ct->is(J::ARR) ? (int)ct->a.size() : 0;
    int on_ = 0, off_ = 0;
    for (int i = 0; i < n; i++) {
        const double c = ct->a[(size_t)i].d();
        on_ += c > 0.98;
        off_ += c < 0.02;
    }
    const std::string say = n && off_ == n ? "all lifted: every string rings" : on_ == n ? "all on the strings"
        : std::to_string(n - on_ - off_) + " resting lightly, " + std::to_string(on_) + " on the strings, " + std::to_string(off_) + " lifted";
    text(a, a.font, 14, dx + 110, Y0 + 11, LCD, say);
    {
        const float W = c2 - 24, sx = dx + 12, s = W / 880.0f, top = Y0 + 50;
        const float kw = W / 52, lift = 110 * s, strY = top + 190 * s, kbY = top + 230 * s;
        dl()->AddLine(P(a, sx, strY), P(a, sx + W, strY), SILK_DIM, 1.5f * a.k);
        int wi = 0;
        std::vector<std::pair<float, float>> blacks;
        for (int i = 0; i < n; i++) {
            const int note = 21 + i;
            const bool blk = is_black(note);
            const float x = blk ? wi * kw - kw * 0.32f : wi * kw, w = blk ? kw * 0.64f : kw;
            const double c = ct->a[(size_t)i].d();
            const float y = strY - 40 * s - (float)(1 - c) * lift;
            const ImU32 fc = c > 0.98 ? LCD : c > 0.02 ? LCD_DIM : IM_COL32(0x3d, 0x3a, 0x33, 255);
            rect(a, sx + x + w * 0.18f, y, w * 0.64f, 40 * s, fc, 2);
            frame(a, sx + x + w * 0.18f, y, w * 0.64f, 40 * s, EDGE, 2, 1);
            if (blk)
                blacks.push_back({x, w});
            else {
                rect(a, sx + x, kbY, w - 1, 96 * s, KEY_W, 1.5f);
                wi++;
            }
        }
        for (auto &b : blacks)
            rect(a, sx + b.first, kbY, b.second, 58 * s, KEY_B, 1.5f);
        wi = 0;
        for (int i = 0; i < n; i++)
            if (!is_black(21 + i)) {
                if ((21 + i) % 12 == 0)
                    text_c(a, a.font, 14, sx + wi * kw + kw / 2, kbY + 96 * s + 4, SILK_DIM, "C" + std::to_string((21 + i) / 12 - 1));
                wi++;
            }
        // where the dampers leave the strings, by the pedal's value
        std::string band;
        if (const J *b = N.pn.get("band"); b && b->is(J::ARR))
            for (const J &e : b->a)
                if (e.is(J::ARR) && e.a.size() >= 3)
                    band += (band.empty() ? "" : " \xc2\xb7 ") + note_name_sharp((int)e.a[0].d()) + " " +
                            std::to_string((int)e.a[1].d()) + "\xe2\x80\x93" + std::to_string((int)e.a[2].d());
        const auto ls = wrap(a, a.font, 14, "Where the dampers leave the strings, by the pedal's value: " + band +
                                                 ". The bass dampers are heavier and leave later.", W);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, sx, kbY + 96 * s + 34 + i * 18, SILK_DIM, ls[i]);
    }

    // THE PEDAL KEY: keys held as the sustain pedal
    const float kx = X1 - c3;
    col(kx, c3, "PEDAL KEY");
    float ky = Y0 + 36;
    for (const auto &l : wrap(a, a.font, 14, "A key held as the sustain pedal: held, the dampers lift; push into it and they come down to the strings.", c3 - 24)) {
        text(a, a.font, 14, kx + 12, ky, SILK_DIM, l);
        ky += 18;
    }
    ky += 10;
    int nk = 0;
    if (const J *ks = N.pn.get("keys"); ks && ks->is(J::ARR))
        for (const J &k : ks->a) {
            nk++;
            text(a, a.font, 21, kx + 12, ky + 8, LCD, note_name_sharp((int)num(&k, "key")));
            const int kc = (int)num(&k, "channel", -1);
            std::string t = flag(&k, "press") ? "held: up \xc2\xb7 pushed: down" : "held: dampers up";
            if (kc >= 0)
                t += " \xc2\xb7 ch " + std::to_string(kc + 1);
            text(a, a.font, 14, kx + 70, ky + 12, SILK_DIM, fit(a, a.font, 14, t, c3 - 190));
            const std::string id = "pkrm" + std::to_string((int)num(&k, "i"));
            if (button(a, id.c_str(), X1 - 110, ky + 2, 98, 34, "REMOVE")) {
                J r = call(a, "{\"call\":\"pedal_key_remove\",\"i\":" + std::to_string((int)num(&k, "i")) + "}");
                if (flag(&r, "ok")) {
                    J p = call(a, "{\"call\":\"piano\"}");
                    if (const J *x = p.get("piano"))
                        piano_take(a, *x);
                }
            }
            ky += 44;
        }
    const int fk = (int)num(&N.pn, "fixed_key", -1);
    if (fk >= 0) {
        nk++;
        text(a, a.font, 21, kx + 12, ky + 8, LCD, note_name_sharp(fk));
        text(a, a.font, 14, kx + 70, ky + 12, SILK_DIM, "set when nvlive started");
        ky += 44;
    }
    if (!nk) {
        text(a, a.font, 14, kx + 12, ky, SILK_DIM, "No key is the pedal yet.");
        ky += 28;
    }
    const bool learning = flag(&N.pn, "learning");
    const bool blink = learning && std::fmod(ImGui::GetTime(), 1.0) < 0.5;
    if (button(a, "pklearn", kx + 12, ky + 6, c3 - 24, 40, learning ? "PRESS THE KEY NOW\xe2\x80\xa6 (TAP TO STOP)" : "LEARN A KEY", blink)) {
        call(a, std::string("{\"call\":\"pedal_key_learn\",\"on\":") + (learning ? "0" : "1") + "}");
        N.pn.o["learning"] = sess::boolean(!learning);
    }
    if (learning || N.want_cc >= 0)
        a.animate = true;               // (the blink; a pedal's last value still to go)
    ky += 66;
    for (const auto &l : wrap(a, a.font, 14, flag(&N.pn, "strings")
                                                 ? "Sympathetic strings: on. The first part's undamped strings ring with what is played."
                                                 : "Sympathetic strings: off (nvlive was started without them).", c3 - 24)) {
        text(a, a.font, 14, kx + 12, ky, SILK_DIM, l);
        ky += 18;
    }

    // WHAT IT IS: the part's patch
    const float ay = 1056 - aboutH, aw = X1 - X0;
    rect(a, X0, ay, aw, aboutH, IM_COL32(0x1f, 0x22, 0x26, 255), 8);
    const J *p = part(a, a.row);
    const J *e = nullptr;
    if (const J *pr = L.about.get("programs"); pr && p && !flag(p, "drums"))
        e = pr->get((std::to_string((int)num(p, "program")) + "." + std::to_string((int)num(p, "variation"))).c_str());
    if (e && e->is(J::ARR) && e->a.size() >= 2) {
        text(a, a.bold, 14, X0 + 12, ay + 10, SILK, fit(a, a.bold, 14, str(p, "name"), aw - 420));
        const int r = (int)e->a[0].d();
        const J *lv = L.about.get("levels");
        const std::string rt = std::to_string(r) + " \xc2\xb7 " +
                               (lv && lv->is(J::ARR) && r >= 0 && r < (int)lv->a.size() && lv->a[(size_t)r].is(J::STR) ? lv->a[(size_t)r].s : "");
        text(a, a.font, 14, X1 - 12 - text_w(a, a.font, 14, rt), ay + 10, LCD, rt);
        const auto lines = wrap(a, a.font, 14, e->a[1].is(J::STR) ? e->a[1].s : "", aw - 24);
        for (size_t i = 0; i < lines.size() && i < 5; i++)
            text(a, a.font, 14, X0 + 12, ay + 32 + i * 18, SILK_DIM,
                 i == 4 && lines.size() > 5 ? fit(a, a.font, 14, lines[i] + " \xe2\x80\xa6", aw - 24) : lines[i]);
    }
}

}  // namespace nui
