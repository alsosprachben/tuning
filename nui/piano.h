// THE PIANO CARD (the retired web interface's): the selected part's pedals as the engine
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
inline std::string pedal_say(int v) { return v <= 0 ? std::string(T("UP")) : v >= 127 ? std::string(T("DOWN")) : TF("HALF {0}", {std::to_string(v)}); }
inline std::string note_name_sharp(int n)
{
    static const char *N[12] = {"C", "C\xe2\x99\xaf", "D", "D\xe2\x99\xaf", "E", "F", "F\xe2\x99\xaf", "G",
                                "G\xe2\x99\xaf", "A", "A\xe2\x99\xaf", "B"};
    return std::string(N[((n % 12) + 12) % 12]) + std::to_string(n / 12 - 1);
}

// A PEDAL: a tall cap, lit and lowered when down
inline bool pedal_btn(App &a, const char *id, float cx, float y, bool on, const char *name, const char *note)
{
    const float w = a.tab ? 64 : 84, h = a.tab ? 110 : 150, x = cx - w / 2, dy = on ? (a.tab ? 4 : 6) : 0;
    ImGui::SetCursorScreenPos(P(a, x, y));
    const bool hit = ImGui::InvisibleButton(id, ImVec2(w * a.k, h * a.k));
    // (a pedal of turned metal, convex across: lit along its crown, darker to
    // its sides and toward the floor; down, it sinks and its shadow goes;
    // on, its metal warm with the light)
    ImDrawList *d = dl();
    const bool held = ImGui::IsItemActive();
    if (!on)
        look::shadow(a, x, y, w, h, 12, 6, 5, 0.6f);
    const int i0 = d->VtxBuffer.Size;
    d->AddRectFilled(P(a, x, y + dy), P(a, x + w, y + h + dy), IM_COL32(255, 255, 255, 255), 30 * a.k, ImDrawFlags_RoundCornersBottom);
    d->AddRectFilled(P(a, x, y + dy), P(a, x + w, y + 20 + dy), IM_COL32(255, 255, 255, 255), 10 * a.k, ImDrawFlags_RoundCornersTop);
    const ImU32 lo = on ? IM_COL32(0x8a, 0x5e, 0x14, 255) : IM_COL32(0x3a, 0x3e, 0x43, 255),
                hi = on ? IM_COL32(0xf0, 0xb1, 0x3a, 255) : held ? IM_COL32(0x60, 0x65, 0x6b, 255) : IM_COL32(0x7a, 0x7f, 0x86, 255);
    look::shade_v(d, i0, P(a, 0, y + dy).y, P(a, 0, y + h + dy).y, hi, lo);
    // its crown: a band of light along it, a little left of the middle, fading toward the floor
    const float cx0 = x + w * 0.42f, iy0 = y + dy + 6, iy1 = y + h + dy - 16;
    const ImU32 c0 = look::grey(1, 0.0f), c1 = look::grey(1, on ? 0.30f : 0.38f), c2 = look::grey(1, on ? 0.10f : 0.12f);
    d->AddRectFilledMultiColor(P(a, x + 5, iy0), P(a, cx0, iy1), c0, c1, c2, c0);
    d->AddRectFilledMultiColor(P(a, cx0, iy0), P(a, x + w - 5, iy1), c1, c0, c0, c2);
    d->AddRect(P(a, x, y + dy), P(a, x + w, y + h + dy), look::grey(0, 0.7f), 12 * a.k, 0, 1.0f * a.k);
    const float LH = a.lh(14) + 3;
    text_c(a, a.bold, 14, cx, y + h + (a.tab ? 10 : 16), on ? LCD : SILK, name);
    const auto ls = wrap(a, a.font, 14, note, a.tab ? 84 : 124);
    for (size_t i = 0; i < ls.size(); i++)
        text_c(a, a.font, 14, cx, y + h + (a.tab ? 12 : 20) + (i + 1) * LH, SILK_DIM, ls[i]);
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
    const bool IP = a.tab, PH = a.ph;   // (the iPad's: its card from y 210 to card_y1 + 6; the phone's from 106, two pages)
    const float X0 = PH ? 14 : IP ? 20 : 34, X1 = IP ? (PH ? 818 : 1113) : 1886, HY = PH ? 120 : IP ? 224 : 356, LH = a.lh(14) + (IP ? 3 : 4);
    const float TX = heading(a, X0, HY, T("PIANO"), "piano");
    if (!N.pn.is(J::OBJ))
        return;
    static int ppage = 0;               // (the phone's: 0 the pedals and the pedal key, 1 the dampers)
    if (PH) {
        static const char *PN[2] = {N_("PEDALS"), N_("DAMPERS")};
        float px_ = TX + 6;
        for (int pg = 0; pg < 2; pg++) {
            const float w = text_w(a, a.font, 21, T(PN[pg])) + 28;
            const std::string id = "pnpage" + std::to_string(pg);
            if (button(a, id.c_str(), px_, 112, w, 40, T(PN[pg]), ppage == pg, true, 21))
                ppage = pg;
            px_ += w + 4;
        }
    } else
        text(a, a.font, 14, TX, HY + 1, OWN, TF("part {0}", {pad2(a.row + 1)}) + " \xc2\xb7 " + str(&N.pn, "part"));
    const int ch = (int)num(&N.pn, "channel", -1);
    const std::string info = ch < 0 ? std::string(T("pedals on every channel")) : TF("pedals on channel {0}", {std::to_string(ch + 1)});
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), PH ? 147 : HY + 1, SILK_DIM, info);

    const float aboutH = 0, Y0 = PH ? 160 : IP ? 260 : 394, Y1 = (card_y1(a)) - aboutH - (IP ? 8 : 10);
    // (the phone's: the pedals and the pedal key side by side; the dampers a page the card's width)
    const float c1 = PH ? 400 : IP ? 300 : 430, gap = IP ? 6 : 8, c3 = PH ? X1 - X0 - c1 - gap : IP ? 280 : 400,
                c2 = PH ? X1 - X0 : X1 - X0 - c1 - c3 - 2 * gap;
    auto col = [&](float x, float w, const char *title, const char *key) {
        look::tray(a, x, Y0, w, Y1 - Y0, 9);
        return heading(a, x + 12, Y0 + 10, title, key);
    };

    // THE PEDALS: soft and sostenuto; the sustain a fader with its quick values
    if (!PH || ppage == 0) {
    col(X0, c1, T("PEDALS"), "piano:pedals");   // i18n-skip (the help key)
    const bool soft = flag(&N.pn, "soft"), sost = flag(&N.pn, "sostenuto");
    const float py = PH ? Y0 + 50 : IP ? Y1 - 200 : Y1 - 290;
    if (pedal_btn(a, "pdsoft", X0 + (IP ? 52 : 76), py, soft, T("SOFT"), T("una corda")))
        pedal(a, 67, soft ? 0 : 127);
    if (pedal_btn(a, "pdsost", X0 + (IP ? 146 : 206), py, sost, T("SOSTENUTO"), T("holds the keys down as it goes down")))
        pedal(a, 66, sost ? 0 : 127);
    float sus = (float)num(&N.pn, "sustain");
    const float fx = X0 + (IP ? 246 : 350), fy0 = Y0 + (IP ? 44 : 50), fh = PH ? Y1 - Y0 - 90 : Y1 - Y0 - (IP ? 258 : 270);   // (its value and name clear of DOWN)
    {
        const int f = fader(a, "pdsus", fx, fy0, fh, sus, 0, 127, 1, {64}, T("SUSTAIN"), pedal_say((int)std::lround(sus)));
        if (f & K_CHANGED)
            pedal(a, 64, (int)std::lround(sus));
        if (f & K_RESET)
            pedal(a, 64, 0);
    }
    const int si = (int)num(&N.pn, "sustain");
    static const struct { const char *n; int v; } Q[3] = {{N_("DOWN"), 127}, {N_("HALF"), 64}, {N_("UP"), 0}};
    for (int i = 0; i < 3; i++) {
        const bool on = Q[i].v == 64 ? si > 0 && si < 127 : si == Q[i].v;
        const std::string id = std::string("pq") + Q[i].n;
        // (the phone's beside the fader: under it there is no room)
        if (button(a, id.c_str(), PH ? fx + 36 : fx - (IP ? 46 : 50), PH ? Y0 + 44 + i * 50 : Y1 - (IP ? 150 : 150) + i * (IP ? 48 : 46),
                   IP ? 92 : 100, IP ? 44 : 38, T(Q[i].n), on, true, IP ? 21 : 14))
            pedal(a, 64, Q[i].v);
    }
    }

    // THE DAMPERS: each one's rest on its strings, over the keyboard (88 keys, A0 to C8)
    if (!PH || ppage == 1) {
    const float dx = PH ? X0 : X0 + c1 + gap;
    const float dsx = col(dx, c2, T("DAMPERS"), "piano:dampers");   // i18n-skip (the help key)
    // (a part that is not a piano: its pedals still reach its channel; no strings to show)
    const J *pp = part(a, a.row);
    const bool is_piano = pp && !flag(pp, "drums") && (int)num(pp, "program") < 8;
    if (!is_piano) {
        float my = Y0 + (IP ? 40 : 50);
        for (const auto &l : wrap(a, a.font, 21, TF("{0} is not a piano.", {pp ? str(pp, "name") : std::string(T("This part"))}), c2 - 24)) {
            text(a, a.font, 21, dx + 12, my, SILK_DIM, l);
            my += a.lh(21) + 4;
        }
        for (const auto &l : wrap(a, a.font, 14, T("The pedals still go to its channel; the dampers are drawn for a piano's strings."), c2 - 24)) {
            text(a, a.font, 14, dx + 12, my + 6, SILK_DIM, l);
            my += LH;
        }
        (void)dsx;
    } else {
    const J *ct = N.pn.get("contact");
    const int n = ct && ct->is(J::ARR) ? (int)ct->a.size() : 0;
    int on_ = 0, off_ = 0;
    for (int i = 0; i < n; i++) {
        const double c = ct->a[(size_t)i].d();
        on_ += c > 0.98;
        off_ += c < 0.02;
    }
    const std::string say = n && off_ == n ? std::string(T("all lifted: every string rings")) : on_ == n ? std::string(T("all on the strings"))
        : TF("{0} resting lightly, {1} on the strings, {2} lifted", {std::to_string(n - on_ - off_), std::to_string(on_), std::to_string(off_)});
    text(a, a.font, 14, dsx, Y0 + 11, LCD, say);
    {
        // (the phone's drawing as tall as its page lets it, its words beside it)
        const float W = PH ? std::min(c2 - 24, (Y1 - Y0 - 60) / 330.0f * 880.0f) : c2 - 24, sx = dx + 12, s = W / 880.0f,
                    top = Y0 + (IP ? 40 : 50);
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
                look::white_key(a, sx + x, kbY, w - 1, 96 * s);
                wi++;
            }
        }
        for (auto &b : blacks)
            look::black_key(a, sx + b.first, kbY, b.second, 58 * s);
        look::keybed(a, sx, kbY, wi * kw);
        wi = 0;
        for (int i = 0; i < n; i++)
            if (!is_black(21 + i)) {
                if ((21 + i) % 12 == 0)
                    text_c(a, a.font, 14, sx + wi * kw + kw / 2, kbY + 96 * s + 3, SILK_DIM, "C" + std::to_string((21 + i) / 12 - 1));
                wi++;
            }
        // where the dampers leave the strings, by the pedal's value
        std::string band;
        if (const J *b = N.pn.get("band"); b && b->is(J::ARR))
            for (const J &e : b->a)
                if (e.is(J::ARR) && e.a.size() >= 3)
                    band += (band.empty() ? "" : " \xc2\xb7 ") + note_name_sharp((int)e.a[0].d()) + " " +
                            std::to_string((int)e.a[1].d()) + "\xe2\x80\x93" + std::to_string((int)e.a[2].d());
        const auto ls = wrap(a, a.font, 14, TF("Where the dampers leave the strings, by the pedal's value: {0}. The bass dampers are heavier and leave later.", {band}), PH ? c2 - W - 60 : W);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, PH ? sx + W + 24 : sx, PH ? top + i * LH : kbY + 96 * s + (IP ? 14 : 16) + (i + 1) * LH, SILK_DIM, ls[i]);
    }

    }
    }
    if (PH && ppage != 0)
        return;

    // THE PEDAL KEY: keys held as the sustain pedal
    const float kx = X1 - c3;           // (the phone's beside the pedals)
    col(kx, c3, T("PEDAL KEY"), "piano:key");   // i18n-skip (the help key)
    float ky = Y0 + (IP ? 32 : 36);
    for (const auto &l : wrap(a, a.font, 14, T("A key held as the sustain pedal: held, the dampers lift; push into it and they come down to the strings."), c3 - 24)) {
        text(a, a.font, 14, kx + 12, ky, SILK_DIM, l);
        ky += LH;
    }
    ky += 10;
    int nk = 0;
    if (const J *ks = N.pn.get("keys"); ks && ks->is(J::ARR))
        for (const J &k : ks->a) {
            nk++;
            text(a, a.font, 21, kx + 12, ky + 8, LCD, note_name_sharp((int)num(&k, "key")));
            const int kc = (int)num(&k, "channel", -1);
            std::string t = flag(&k, "press") ? T("held: up \xc2\xb7 pushed: down") : T("held: dampers up");
            if (kc >= 0)
                t += " \xc2\xb7 " + TF("ch {0}", {std::to_string(kc + 1)});
            text(a, a.font, 14, kx + 70, ky + 12, SILK_DIM, fit(a, a.font, 14, t, c3 - 190));
            const std::string id = "pkrm" + std::to_string((int)num(&k, "i"));
            if (button(a, id.c_str(), X1 - 110, ky, 98, IP ? 44 : 34, T("REMOVE"))) {
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
        text(a, a.font, 14, kx + 70, ky + 12, SILK_DIM, T("set when nvlive started"));
        ky += 44;
    }
    if (!nk) {
        text(a, a.font, 14, kx + 12, ky, SILK_DIM, T("No key is the pedal yet."));
        ky += 28;
    }
    const bool learning = flag(&N.pn, "learning");
    const bool blink = learning && std::fmod(ImGui::GetTime(), 1.0) < 0.5;
    if (button(a, "pklearn", kx + 12, ky + 6, c3 - 24, IP ? 44 : 40, learning ? T("PRESS THE KEY NOW\xe2\x80\xa6 (TAP TO STOP)") : T("LEARN A KEY"), blink)) {
        call(a, std::string("{\"call\":\"pedal_key_learn\",\"on\":") + (learning ? "0" : "1") + "}");
        N.pn.o["learning"] = sess::boolean(!learning);
    }
    if (learning || N.want_cc >= 0)
        a.animate = true;               // (the blink; a pedal's last value still to go)
    ky += IP ? 62 : 66;
    for (const auto &l : wrap(a, a.font, 14, flag(&N.pn, "strings")
                                                 ? T("Sympathetic strings: on. The first part's undamped strings ring with what is played.")
                                                 : T("Sympathetic strings: off (nvlive was started without them)."), c3 - 24)) {
        text(a, a.font, 14, kx + 12, ky, SILK_DIM, l);
        ky += LH;
    }
}

}  // namespace nui
