// THE PARTS CARD (the retired web interface's): the keyboard's map -- each part a lane over
// its keys, its ends dragged to set them, a tap selecting it -- and a strip
// per part: its name, pan, level, KEY, CH, MUTE, SOLO and touch; LAYER,
// SPLIT and REMOVE in the card's head.
#pragma once

#include "app.h"
#include "widgets.h"

namespace nui {

// THE KEYBOARD's GEOMETRY (all 128 keys, the white ones even)
struct Keys {
    float x = 0, w = 1;
    int white_of[128];
    int nwhite = 0;
    void init(float x0, float width)
    {
        x = x0;
        w = width;
        nwhite = 0;
        for (int k = 0; k < 128; k++)
            white_of[k] = is_black(k) ? -1 : nwhite++;
    }
    float ww() const { return w / nwhite; }
    float left(int k) const
    {
        if (!is_black(k))
            return x + white_of[k] * ww();
        return x + white_of[k - 1] * ww() + ww() * 0.68f;
    }
    float right(int k) const { return is_black(k) ? left(k) + ww() * 0.64f : left(k) + ww(); }
    int at(float px) const
    {
        int best = 0;
        for (int k = 0; k < 128; k++)
            if (!is_black(k) && px >= left(k))
                best = k;
        // (a black key over the white one's upper part: by the nearest centre)
        for (int k = 0; k < 128; k++)
            if (is_black(k) && px >= left(k) && px < right(k))
                return k;
        return best;
    }
};

struct PartsUi {
    int first = 0;                      // (the iPad's strips: the first shown, a page at a time)
    // a lane end dragged: its part, which end, and whether it moved
    int drag_row = -1, drag_end = 0;    // (end: -1 lo, 1 hi, 0 none: a tap)
    bool drag_moved = false;
    float drag_x0 = 0;
};
static PartsUi g_parts;

// A STRIP's NAME: its first words beside the number, the rest on the line under
inline void strip_name(App &a, const std::string &nm, float x1, float y, float x2, float w1, float lh, bool dim)
{
    std::string first, rest = nm;
    for (size_t i = nm.size(); i > 0; i--)          // (the most words that fit beside the number)
        if ((i == nm.size() || nm[i] == ' ') && text_w(a, a.font, 14, nm.substr(0, i)) <= w1) {
            first = nm.substr(0, i);
            rest = i < nm.size() ? nm.substr(i + 1) : "";
            break;
        }
    text(a, a.font, 14, x1, y, dim ? SILK_DIM : SILK, first);
    if (!rest.empty())
        text(a, a.font, 14, x2, y + lh, dim ? SILK_DIM : SILK, rest);
}
// A LANE's LABEL: the part and its range, the range left off where the lane is too short for both
// (a lane a few keys wide: its part's name whole on its strip below)
inline std::string lane_label(App &a, const std::string &part, const std::string &range, float w)
{
    const std::string both = part + "  " + range;
    if (text_w(a, a.font, 14, both) <= w)
        return both;
    return text_w(a, a.font, 14, part) <= w ? part : fit(a, a.font, 14, part, w);
}

inline void draw_strips_tab(App &a, float X0, float X1, float sy, float Y1);
inline void draw_strips_phone(App &a, float X0, float X1, float sy, float Y1, float BY);
inline void draw_parts(App &a)
{
    const int n = nparts(a);
    const bool T = a.tab, PH = a.ph;    // (the iPad's layout: its card from y 210 to card_y1 + 6; the phone's from 106)
    const float X0 = PH ? 14 : T ? 22 : 34, X1 = PH ? 818 : T ? 1111 : 1886, HY = PH ? 120 : T ? 224 : 356,
                BH = PH ? 40 : T ? 44 : 38, BY = PH ? 112 : T ? 216 : 346;
    // THE HEAD: the card's name, its message, LAYER, SPLIT, REMOVE
    const float TX = heading(a, X0, HY, nui::T("PARTS"), "parts");   // (nui::T: the bool T here is the iPad's)
    if (!a.msg.empty())
        text(a, a.font, 14, TX, HY, BAD, fit(a, a.font, 14, a.msg, PH ? 300 : T ? 500 : 1200));
    auto act = [&](const char *name) {
        J r = call(a, std::string("{\"call\":\"") + name + "\",\"row\":" + std::to_string(a.row) + "}");
        const J *ok = r.get("ok");
        a.msg = ok && ok->d(1) == 0 ? str(&r, "error") : "";
        take_parts(a, r);
        a.row = std::min(a.row, std::max(0, nparts(a) - 1));
    };
    const float bs = T ? 21 : 14;
    if (button(a, "layer", X1 - 372, BY, 116, BH, nui::T("LAYER"), false, true, bs))
        act("part_layer");
    if (button(a, "split", X1 - 248, BY, 116, BH, nui::T("SPLIT"), false, true, bs))
        act("part_split");
    if (button(a, "remove", X1 - 124, BY, 124, BH, nui::T("REMOVE"), false, true, bs))
        act("part_delete");

    // THE KEYBOARD: 128 keys, the octaves named under them
    Keys kb;
    kb.init(X0, X1 - X0);
    const float ky = PH ? 160 : T ? 270 : 396, kh = PH ? 32 : T ? 40 : 56;
    for (int k = 0; k < 128; k++)
        if (!is_black(k))
            look::white_key(a, kb.left(k), ky, kb.ww() - 1, kh);
    for (int k = 0; k < 128; k++)
        if (is_black(k))
            look::black_key(a, kb.left(k), ky, kb.right(k) - kb.left(k), kh * 0.62f);
    look::keybed(a, X0, ky, X1 - X0);
    for (int k = 0; k < 128; k += 12)
        text(a, a.font, 14, kb.left(k) + 3, ky + kh + 3, SILK_DIM, note_name(k));
    // THE LANES: a part each over its keys (taller for few parts)
    const float lane = PH ? std::max(5.0f, std::min(16.0f, std::floor(40.0f / std::max(1, n))))
                     : T ? std::max(6.0f, std::min(22.0f, std::floor(88.0f / std::max(1, n))))
                         : std::max(10.0f, std::min(24.0f, std::floor(150.0f / std::max(1, n))));
    const float ly0 = ky + kh + (PH ? 10 : T ? 12 : 20);
    PartsUi &U = g_parts;
    for (int i = 0; i < n; i++) {
        const int lo = (int)pv(a, i, "lo"), hi = (int)pv(a, i, "hi", 127);
        const float y = ly0 + i * lane, x0 = kb.left(lo), x1 = kb.right(hi);
        const bool sel = i == a.row, dim = pv(a, i, "muted") != 0 || num(part(a, i), "solo") == 2;
        rect(a, x0, y + 1, std::max(4.0f, x1 - x0), lane - 3, sel ? IM_COL32(0x5a, 0x41, 0x12, 255)
                                                                   : dim ? IM_COL32(0x2a, 0x2a, 0x2a, 255)
                                                                         : IM_COL32(0x45, 0x34, 0x14, 255), 3);
        rect(a, x0, y + 1, 5, lane - 3, LCD, 0);
        rect(a, x1 - 5, y + 1, 5, lane - 3, LCD, 0);
        if (lane >= (PH ? 12 : T ? 10 : 14))
            text(a, a.font, 14, x0 + 9, y + (lane - 14) / 2, dim ? SILK_DIM : LCD,
                 lane_label(a, pad2(i + 1) + " " + str(part(a, i), "name"), TF("{0} to {1}", {note_name(lo), note_name(hi)}),
                            std::max(30.0f, x1 - x0 - 14)));
        // a lane's touch: near an end, that end follows the finger by key; else a tap selects
        ImGui::SetCursorScreenPos(P(a, X0, y));
        ImGui::PushID(i);
        ImGui::InvisibleButton("lane", ImVec2((X1 - X0) * a.k, lane * a.k));
        const bool activated = ImGui::IsItemActivated(), active = ImGui::IsItemActive(),
                   ended = ImGui::IsItemDeactivated();
        ImGui::PopID();
        const float mx = (ImGui::GetIO().MousePos.x - a.org.x) / a.k;
        if (activated) {
            const float near = 28 / a.k, dl_ = std::fabs(mx - x0), dr = std::fabs(mx - x1);
            U.drag_row = i;
            U.drag_end = dl_ < near && dl_ <= dr ? -1 : dr < near ? 1 : 0;
            U.drag_moved = false;
            U.drag_x0 = mx;
        }
        if (active && U.drag_row == i && U.drag_end) {
            if (!U.drag_moved && std::fabs(mx - U.drag_x0) * a.k < 6)
                ;
            else {
                U.drag_moved = true;
                const int key = kb.at(mx);
                int nlo = lo, nhi = hi;
                if (U.drag_end < 0)
                    nlo = std::min(key, hi);
                else
                    nhi = std::max(key, lo);
                if (nlo != lo || nhi != hi) {
                    keep(a, i, "lo", nlo);
                    keep(a, i, "hi", nhi);
                    call(a, "{\"call\":\"part_set\",\"row\":" + std::to_string(i) + ",\"lo\":" + std::to_string(nlo) +
                                ",\"hi\":" + std::to_string(nhi) + "}");
                }
            }
        }
        if (ended && U.drag_row == i) {
            if (!U.drag_moved)
                select(a, i);
            U.drag_row = -1;
        }
    }

    // THE STRIPS: a part each, side by side
    if (PH) {
        draw_strips_phone(a, X0, X1, ly0 + n * lane + 6, card_y1(a), BY);
        return;
    }
    if (T) {
        draw_strips_tab(a, X0, X1, ly0 + n * lane + 10, card_y1(a));
        return;
    }
    const float sy = ly0 + n * lane + 14, sh = card_y1(a) - sy;
    const float gap = 10, sw = std::max(108.0f, std::min(240.0f, (X1 - X0 - gap * (n - 1)) / std::max(1, n)));
    for (int i = 0; i < n; i++) {
        const J *p = part(a, i);
        const float x = X0 + i * (sw + gap), cx = x + sw / 2;
        const bool sel = i == a.row, dim = pv(a, i, "muted") != 0 || num(p, "solo") == 2;
        look::tray(a, x, sy, sw, sh, 8);
        if (sel)
            frame(a, x, sy, sw, sh, LCD, 8, 2.0f);
        // the head: a tap selects
        ImGui::SetCursorScreenPos(P(a, x, sy));
        ImGui::PushID(100 + i);
        if (ImGui::InvisibleButton("head", ImVec2(sw * a.k, 60 * a.k)))
            select(a, i);
        tap_yields(a);
        ImGui::PopID();
        const float nw = text_w(a, a.font, 21, pad2(i + 1));
        text(a, a.font, 21, x + 8, sy + 8, dim ? SILK_DIM : LCD, pad2(i + 1));
        // (its name whole: beside the number, its rest on a second line)
        strip_name(a, str(p, "name"), x + 8 + nw + 8, sy + 13, x + 8, sw - nw - 24, a.lh(14) + 3, dim);
        char pr[32];
        snprintf(pr, sizeof pr, nui::T("prog %03d%s"), (int)num(p, "program"),
                 num(p, "variation") ? ("." + std::to_string((int)num(p, "variation"))).c_str() : "");
        text(a, a.font, 14, x + 8, sy + 52, SILK_DIM, std::string(flag(p, "drums") ? nui::T("drums") : pr));
        // the pan knob
        const int pan = (int)pv(a, i, "pan", 64);
        float pv01 = pan / 127.0f;
        const std::string pid = "pan" + std::to_string(i);
        int f = knob(a, pid.c_str(), cx, sy + 104, 56, pv01, nui::T("PAN"), pan_text(pan), true, {64 / 127.0f});
        if (f & K_CHANGED)
            part_cc(a, i, 10, "pan", (int)std::lround(pv01 * 127));
        if (f & K_RESET)
            part_cc(a, i, 10, "pan", 64);
        // KEY and CH (the strip's LCD fields)
        const float fy = sy + 170, fw = (sw - 20) / 2;
        float key = (float)pv(a, i, "transpose");
        const std::string kid = "key" + std::to_string(i), cid = "ch" + std::to_string(i);
        f = lcd_field(a, kid.c_str(), x + 6, fy, fw, 44, key, -24, 24, nui::T("KEY"), signed_text((int)key), false, 14);
        if (f & K_CHANGED)
            part_set(a, i, "transpose", key);
        if (f & K_RESET)
            part_set(a, i, "transpose", 0);
        float ch = (float)pv(a, i, "channel", -1) + 1;
        f = lcd_field(a, cid.c_str(), x + 14 + fw, fy, fw, 44, ch, 0, 16, nui::T("CH"), ch ? std::to_string((int)ch) : nui::T("ALL"),
                      false, 14);
        if (f & K_CHANGED)
            part_set(a, i, "channel", ch - 1);
        // the level fader (-30..+10 dB, 0 a detent, half-dB steps)
        const float fy0 = fy + 60, fh = std::max(60.0f, sh - (fy0 - sy) - 150);
        float lv = (float)pv(a, i, "level_db");
        const std::string lid = "lvl" + std::to_string(i);
        f = fader(a, lid.c_str(), cx, fy0, fh, lv, -30, 10, 0.5f, {0.0f}, nui::T("LEVEL"), db_text(lv) + " dB");
        if (f & K_CHANGED)
            part_set(a, i, "level_db", lv);
        if (f & K_RESET)
            part_set(a, i, "level_db", 0);
        // MUTE, SOLO, and the touch: velocity or fixed
        const float by = sy + sh - 92, bw = (sw - 18) / 2;
        const std::string mid = "m" + std::to_string(i), oid = "s" + std::to_string(i), tid = "t" + std::to_string(i);
        const bool muted = pv(a, i, "muted") != 0;
        if (button(a, mid.c_str(), x + 6, by, bw, 38, nui::T("MUTE"), muted))
            part_set(a, i, "muted", muted ? 0 : 1);
        if (button(a, oid.c_str(), x + 12 + bw, by, bw, 38, nui::T("SOLO"), num(p, "solo") == 1))
            take_parts(a, call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(i) + "}"));
        const bool fixed = pv(a, i, "touch_fixed") != 0;
        if (button(a, tid.c_str(), x + 6, by + 46, sw - 12, 38, fixed ? nui::T("FIXED") : nui::T("VEL"), fixed)) {
            keep(a, i, "touch_fixed", fixed ? 0 : 1, 1.0);
            call(a, "{\"call\":\"part_touch\",\"row\":" + std::to_string(i) + ",\"fixed\":" + (fixed ? "0" : "1") + "}");
        }
    }
}

// THE iPad's STRIPS: pan and level as knobs side by side, KEY and CH, MUTE
// and SOLO, the touch -- every control 44 points or more; as many as fit,
// a page at a time (the arrows in the head)
inline void draw_strips_tab(App &a, float X0, float X1, float sy, float Y1)
{
    PartsUi &U = g_parts;
    const int n = nparts(a);
    const float gap = 6, sw = 128, sh = Y1 - sy;
    const int fit_ = std::max(1, (int)((X1 - X0 + gap) / (sw + gap)));
    // (the selected part kept in view)
    if (a.row < U.first)
        U.first = a.row;
    if (a.row >= U.first + fit_)
        U.first = a.row - fit_ + 1;
    U.first = std::max(0, std::min(U.first, std::max(0, n - fit_)));
    if (n > fit_) {
        const std::string pg = TF("{0}\xe2\x80\x93{1} of {2}", {std::to_string(U.first + 1), std::to_string(std::min(n, U.first + fit_)), std::to_string(n)});
        text(a, a.font, 14, X1 - 372 - 150 - text_w(a, a.font, 14, pg) - 8, 232, SILK_DIM, pg);
        if (button(a, "spl", X1 - 372 - 150, 216, 70, 44, "\xe2\x97\x80", false, U.first > 0, 21) && U.first > 0)
            U.first = std::max(0, U.first - fit_);
        if (button(a, "spr", X1 - 372 - 76, 216, 70, 44, "\xe2\x96\xb6", false, U.first + fit_ < n, 21) && U.first + fit_ < n)
            U.first = std::min(n - fit_, U.first + fit_);
    }
    for (int i = U.first; i < n && i < U.first + fit_; i++) {
        const J *p = part(a, i);
        const float x = X0 + (i - U.first) * (sw + gap), cx = x + sw / 2;
        const bool sel = i == a.row, dim = pv(a, i, "muted") != 0 || num(p, "solo") == 2;
        look::tray(a, x, sy, sw, sh, 6);
        if (sel)
            frame(a, x, sy, sw, sh, LCD, 6, 2.0f);
        ImGui::SetCursorScreenPos(P(a, x, sy));
        ImGui::PushID(100 + i);
        if (ImGui::InvisibleButton("head", ImVec2(sw * a.k, 44 * a.k)))
            select(a, i);
        tap_yields(a);
        ImGui::PopID();
        // the head: its number 3x, its name and program 2x
        text(a, a.font, 21, x + 6, sy + 6, dim ? SILK_DIM : LCD, pad2(i + 1));
        const float nw = text_w(a, a.font, 21, pad2(i + 1));
        strip_name(a, str(p, "name"), x + 10 + nw, sy + 8, x + 6, sw - nw - 16, a.lh(14) + 2, dim);
        char pr[32];
        snprintf(pr, sizeof pr, T("prog %03d%s"), (int)num(p, "program"),
                 num(p, "variation") ? ("." + std::to_string((int)num(p, "variation"))).c_str() : "");
        text(a, a.font, 14, x + 6, sy + 8 + 2 * (a.lh(14) + 2), SILK_DIM, std::string(flag(p, "drums") ? T("drums") : pr));
        // pan and level, knobs side by side
        const float ky = sy + 74;
        const int pan = (int)pv(a, i, "pan", 64);
        float pv01 = pan / 127.0f;
        const std::string pid = "pan" + std::to_string(i), lid = "lvl" + std::to_string(i);
        int f = knob(a, pid.c_str(), x + sw * 0.27f, ky, 46, pv01, T("PAN"), pan_text(pan), true, {64 / 127.0f});
        if (f & K_CHANGED)
            part_cc(a, i, 10, "pan", (int)std::lround(pv01 * 127));
        if (f & K_RESET)
            part_cc(a, i, 10, "pan", 64);
        const float lv = (float)pv(a, i, "level_db");
        float lv01 = (lv + 30) / 40.0f;
        f = knob(a, lid.c_str(), x + sw * 0.73f, ky, 46, lv01, T("LEVEL"), db_text(lv), false, {30 / 40.0f});
        if (f & K_CHANGED)
            part_set(a, i, "level_db", std::round((lv01 * 40 - 30) * 2) / 2);
        if (f & K_RESET)
            part_set(a, i, "level_db", 0);
        // KEY and CH
        const float fy = ky + 58, fw = (sw - 16) / 2;
        float key = (float)pv(a, i, "transpose");
        const std::string kid = "key" + std::to_string(i), cid = "ch" + std::to_string(i);
        f = lcd_field(a, kid.c_str(), x + 5, fy, fw, 44, key, -24, 24, T("KEY"), signed_text((int)key), false, 21);
        if (f & K_CHANGED)
            part_set(a, i, "transpose", key);
        if (f & K_RESET)
            part_set(a, i, "transpose", 0);
        float ch = (float)pv(a, i, "channel", -1) + 1;
        f = lcd_field(a, cid.c_str(), x + 11 + fw, fy, fw, 44, ch, 0, 16, T("CH"), ch ? std::to_string((int)ch) : T("ALL"), false, 21);
        if (f & K_CHANGED)
            part_set(a, i, "channel", ch - 1);
        // MUTE, SOLO, and the touch, at the foot
        const float by = sy + sh - 2 * 44 - 10, bw = (sw - 16) / 2;
        const std::string mid = "m" + std::to_string(i), oid = "s" + std::to_string(i), tid = "t" + std::to_string(i);
        const bool muted = pv(a, i, "muted") != 0;
        if (button(a, mid.c_str(), x + 5, by, bw, 44, T("MUTE"), muted, true, 21))
            part_set(a, i, "muted", muted ? 0 : 1);
        if (button(a, oid.c_str(), x + 11 + bw, by, bw, 44, T("SOLO"), num(p, "solo") == 1, true, 21))
            take_parts(a, call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(i) + "}"));
        const bool fixed = pv(a, i, "touch_fixed") != 0;
        if (button(a, tid.c_str(), x + 5, by + 48, sw - 10, 44, fixed ? T("FIXED") : T("VEL"), fixed, true, 21)) {
            keep(a, i, "touch_fixed", fixed ? 0 : 1, 1.0);
            call(a, "{\"call\":\"part_touch\",\"row\":" + std::to_string(i) + ",\"fixed\":" + (fixed ? "0" : "1") + "}");
        }
    }
}

// THE PHONE's STRIPS: short (the card ~300 points tall), so each a column of
// two tiers -- the head and knobs, then KEY/CH and MUTE/SOLO/VEL -- five across
inline void draw_strips_phone(App &a, float X0, float X1, float sy, float Y1, float BY)
{
    PartsUi &U = g_parts;
    const int n = nparts(a);
    const float gap = 6, sw = 156, sh = Y1 - sy;
    const int fit_ = std::max(1, (int)((X1 - X0 + gap) / (sw + gap)));
    if (a.row < U.first)
        U.first = a.row;
    if (a.row >= U.first + fit_)
        U.first = a.row - fit_ + 1;
    U.first = std::max(0, std::min(U.first, std::max(0, n - fit_)));
    if (n > fit_) {                     // (pages of parts: beside LAYER)
        const float px_ = X1 - 372 - 6 - 2 * 56;
        if (button(a, "spl", px_, BY, 52, 40, "\xe2\x97\x80", false, U.first > 0, 21) && U.first > 0)
            U.first = std::max(0, U.first - fit_);
        if (button(a, "spr", px_ + 56, BY, 52, 40, "\xe2\x96\xb6", false, U.first + fit_ < n, 21) && U.first + fit_ < n)
            U.first = std::min(n - fit_, U.first + fit_);
    }
    for (int i = U.first; i < n && i < U.first + fit_; i++) {
        const J *p = part(a, i);
        const float x = X0 + (i - U.first) * (sw + gap);
        const bool sel = i == a.row, dim = pv(a, i, "muted") != 0 || num(p, "solo") == 2;
        look::tray(a, x, sy, sw, sh, 6);
        if (sel)
            frame(a, x, sy, sw, sh, LCD, 6, 2.0f);
        ImGui::SetCursorScreenPos(P(a, x, sy));
        ImGui::PushID(100 + i);
        if (ImGui::InvisibleButton("head", ImVec2(sw * a.k, 30 * a.k)))
            select(a, i);
        tap_yields(a);
        ImGui::PopID();
        // the head: its number and name on a line
        text(a, a.font, 21, x + 6, sy + 5, dim ? SILK_DIM : LCD, pad2(i + 1));
        const float nw = text_w(a, a.font, 21, pad2(i + 1));
        text(a, a.font, 14, x + 12 + nw, sy + 8, dim ? SILK_DIM : SILK, fit(a, a.font, 14, str(p, "name"), sw - nw - 18));
        // pan and level
        const float ky = sy + 44;
        const int pan = (int)pv(a, i, "pan", 64);
        float pv01 = pan / 127.0f;
        const std::string pid = "pan" + std::to_string(i), lid = "lvl" + std::to_string(i);
        int f = knob(a, pid.c_str(), x + sw * 0.27f, ky, 30, pv01, T("PAN"), pan_text(pan), true, {64 / 127.0f});
        if (f & K_CHANGED)
            part_cc(a, i, 10, "pan", (int)std::lround(pv01 * 127));
        if (f & K_RESET)
            part_cc(a, i, 10, "pan", 64);
        const float lv = (float)pv(a, i, "level_db");
        float lv01 = (lv + 30) / 40.0f;
        f = knob(a, lid.c_str(), x + sw * 0.73f, ky, 30, lv01, T("LEVEL"), db_text(lv), false, {30 / 40.0f});
        if (f & K_CHANGED)
            part_set(a, i, "level_db", std::round((lv01 * 40 - 30) * 2) / 2);
        if (f & K_RESET)
            part_set(a, i, "level_db", 0);
        // KEY and CH, then MUTE SOLO VEL at the foot
        const float by = sy + sh - 34 - 5, fy = by - 4 - 36, fw = (sw - 14) / 2;
        float key = (float)pv(a, i, "transpose");
        const std::string kid = "key" + std::to_string(i), cid = "ch" + std::to_string(i);
        f = lcd_field(a, kid.c_str(), x + 5, fy, fw, 36, key, -24, 24, T("KEY"), signed_text((int)key), false, 21);
        if (f & K_CHANGED)
            part_set(a, i, "transpose", key);
        if (f & K_RESET)
            part_set(a, i, "transpose", 0);
        float ch = (float)pv(a, i, "channel", -1) + 1;
        f = lcd_field(a, cid.c_str(), x + 9 + fw, fy, fw, 36, ch, 0, 16, T("CH"), ch ? std::to_string((int)ch) : T("ALL"), false, 21);
        if (f & K_CHANGED)
            part_set(a, i, "channel", ch - 1);
        const float bw = (sw - 18) / 3;
        const std::string mid = "m" + std::to_string(i), oid = "s" + std::to_string(i), tid = "t" + std::to_string(i);
        const bool muted = pv(a, i, "muted") != 0;
        if (button(a, mid.c_str(), x + 5, by, bw, 34, T("MUTE"), muted, true, 14))
            part_set(a, i, "muted", muted ? 0 : 1);
        if (button(a, oid.c_str(), x + 9 + bw, by, bw, 34, T("SOLO"), num(p, "solo") == 1, true, 14))
            take_parts(a, call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(i) + "}"));
        const bool fixed = pv(a, i, "touch_fixed") != 0;
        if (button(a, tid.c_str(), x + 13 + 2 * bw, by, bw, 34, fixed ? T("FIXED") : T("VEL"), fixed, true, 14)) {
            keep(a, i, "touch_fixed", fixed ? 0 : 1, 1.0);
            call(a, "{\"call\":\"part_touch\",\"row\":" + std::to_string(i) + ",\"fixed\":" + (fixed ? "0" : "1") + "}");
        }
    }
}

}  // namespace nui
