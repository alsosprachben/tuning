// THE PARTS CARD (ui/app.js's): the keyboard's map -- each part a lane over
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
    // a lane end dragged: its part, which end, and whether it moved
    int drag_row = -1, drag_end = 0;    // (end: -1 lo, 1 hi, 0 none: a tap)
    bool drag_moved = false;
    float drag_x0 = 0;
};
static PartsUi g_parts;

inline void draw_parts(App &a)
{
    const int n = nparts(a);
    const float X0 = 34, X1 = 1886;
    // THE HEAD: the card's name, its message, LAYER, SPLIT, REMOVE
    const float TX = heading(a, X0, 356, "PARTS", "parts");
    if (!a.msg.empty())
        text(a, a.font, 14, TX, 356, BAD, fit(a, a.font, 14, a.msg, 1200));
    auto act = [&](const char *name) {
        J r = call(a, std::string("{\"call\":\"") + name + "\",\"row\":" + std::to_string(a.row) + "}");
        const J *ok = r.get("ok");
        a.msg = ok && ok->d(1) == 0 ? str(&r, "error") : "";
        take_parts(a, r);
        a.row = std::min(a.row, std::max(0, nparts(a) - 1));
    };
    if (button(a, "layer", X1 - 372, 346, 116, 38, "LAYER"))
        act("part_layer");
    if (button(a, "split", X1 - 248, 346, 116, 38, "SPLIT"))
        act("part_split");
    if (button(a, "remove", X1 - 124, 346, 124, 38, "REMOVE"))
        act("part_delete");

    // THE KEYBOARD: 128 keys, the octaves named under them
    Keys kb;
    kb.init(X0, X1 - X0);
    const float ky = 396, kh = 56;
    for (int k = 0; k < 128; k++)
        if (!is_black(k))
            rect(a, kb.left(k), ky, kb.ww() - 1, kh, KEY_W, 1.5f);
    for (int k = 0; k < 128; k++)
        if (is_black(k))
            rect(a, kb.left(k), ky, kb.right(k) - kb.left(k), kh * 0.62f, KEY_B, 1.5f);
    for (int k = 0; k < 128; k += 12)
        text(a, a.font, 14, kb.left(k) + 3, ky + kh + 3, SILK_DIM, note_name(k));
    // THE LANES: a part each over its keys (taller for few parts)
    const float lane = std::max(10.0f, std::min(24.0f, std::floor(150.0f / std::max(1, n))));
    const float ly0 = ky + kh + 20;
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
        if (lane >= 14)
            text(a, a.font, 14, x0 + 9, y + (lane - 14) / 2, dim ? SILK_DIM : LCD,
                 fit(a, a.font, 14, pad2(i + 1) + " " + str(part(a, i), "name") + "  " + note_name(lo) + "\xe2\x80\x93" +
                                        note_name(hi), std::max(30.0f, x1 - x0 - 14)));
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
    const float sy = ly0 + n * lane + 14, sh = 1056 - sy;
    const float gap = 10, sw = std::max(108.0f, std::min(150.0f, (X1 - X0 - gap * (n - 1)) / std::max(1, n)));
    for (int i = 0; i < n; i++) {
        const J *p = part(a, i);
        const float x = X0 + i * (sw + gap), cx = x + sw / 2;
        const bool sel = i == a.row, dim = pv(a, i, "muted") != 0 || num(p, "solo") == 2;
        rect(a, x, sy, sw, sh, sel ? IM_COL32(0x2b, 0x2f, 0x34, 255) : IM_COL32(0x1f, 0x22, 0x26, 255), 8);
        frame(a, x, sy, sw, sh, sel ? LCD : EDGE, 8, sel ? 2.0f : 1.0f);
        // the head: a tap selects
        ImGui::SetCursorScreenPos(P(a, x, sy));
        ImGui::PushID(100 + i);
        if (ImGui::InvisibleButton("head", ImVec2(sw * a.k, 60 * a.k)))
            select(a, i);
        ImGui::PopID();
        const float nw = text_w(a, a.font, 21, pad2(i + 1));
        text(a, a.font, 21, x + 8, sy + 8, dim ? SILK_DIM : LCD, pad2(i + 1));
        text(a, a.font, 14, x + 8 + nw + 8, sy + 13, dim ? SILK_DIM : SILK, fit(a, a.font, 14, str(p, "name"), sw - nw - 24));
        const int lo = (int)pv(a, i, "lo"), hi = (int)pv(a, i, "hi", 127);
        char pr[32];
        snprintf(pr, sizeof pr, "prog %03d%s", (int)num(p, "program"),
                 num(p, "variation") ? ("." + std::to_string((int)num(p, "variation"))).c_str() : "");
        text(a, a.font, 14, x + 8, sy + 36, SILK_DIM,
             fit(a, a.font, 14, std::string(flag(p, "drums") ? "drums" : pr) + " \xc2\xb7 " + note_name(lo) + "\xe2\x80\x93" + note_name(hi), sw - 14));
        // the pan knob
        const int pan = (int)pv(a, i, "pan", 64);
        float pv01 = pan / 127.0f;
        const std::string pid = "pan" + std::to_string(i);
        int f = knob(a, pid.c_str(), cx, sy + 104, 56, pv01, "PAN", pan_text(pan), true, {64 / 127.0f});
        if (f & K_CHANGED)
            part_cc(a, i, 10, "pan", (int)std::lround(pv01 * 127));
        if (f & K_RESET)
            part_cc(a, i, 10, "pan", 64);
        // KEY and CH (the strip's LCD fields)
        const float fy = sy + 170, fw = (sw - 20) / 2;
        float key = (float)pv(a, i, "transpose");
        const std::string kid = "key" + std::to_string(i), cid = "ch" + std::to_string(i);
        f = lcd_field(a, kid.c_str(), x + 6, fy, fw, 44, key, -24, 24, "KEY", signed_text((int)key), false, 14);
        if (f & K_CHANGED)
            part_set(a, i, "transpose", key);
        if (f & K_RESET)
            part_set(a, i, "transpose", 0);
        float ch = (float)pv(a, i, "channel", -1) + 1;
        f = lcd_field(a, cid.c_str(), x + 14 + fw, fy, fw, 44, ch, 0, 16, "CH", ch ? std::to_string((int)ch) : "ALL",
                      false, 14);
        if (f & K_CHANGED)
            part_set(a, i, "channel", ch - 1);
        // the level fader (-30..+10 dB, 0 a detent, half-dB steps)
        const float fy0 = fy + 60, fh = std::max(60.0f, sh - (fy0 - sy) - 150);
        float lv = (float)pv(a, i, "level_db");
        const std::string lid = "lvl" + std::to_string(i);
        f = fader(a, lid.c_str(), cx, fy0, fh, lv, -30, 10, 0.5f, {0.0f}, "LEVEL", db_text(lv) + " dB");
        if (f & K_CHANGED)
            part_set(a, i, "level_db", lv);
        if (f & K_RESET)
            part_set(a, i, "level_db", 0);
        // MUTE, SOLO, and the touch: velocity or fixed
        const float by = sy + sh - 92, bw = (sw - 18) / 2;
        const std::string mid = "m" + std::to_string(i), oid = "s" + std::to_string(i), tid = "t" + std::to_string(i);
        const bool muted = pv(a, i, "muted") != 0;
        if (button(a, mid.c_str(), x + 6, by, bw, 38, "MUTE", muted))
            part_set(a, i, "muted", muted ? 0 : 1);
        if (button(a, oid.c_str(), x + 12 + bw, by, bw, 38, "SOLO", num(p, "solo") == 1))
            take_parts(a, call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(i) + "}"));
        const bool fixed = pv(a, i, "touch_fixed") != 0;
        if (button(a, tid.c_str(), x + 6, by + 46, sw - 12, 38, fixed ? "FIXED" : "VEL", fixed)) {
            keep(a, i, "touch_fixed", fixed ? 0 : 1, 1.0);
            call(a, "{\"call\":\"part_touch\",\"row\":" + std::to_string(i) + ",\"fixed\":" + (fixed ? "0" : "1") + "}");
        }
    }
}

}  // namespace nui
