// THE KEYS CARD: a keyboard to touch, for trying a sound and for showing it
// -- every finger its own key (a chord held, a glissando slid), as hard as
// the touch settings say (touchvel.h: VEL, the card's own or Setup's), on the
// selected part's channel (drum_hit: a note on, and its release); OCTAVE
// moves it, SUSTAIN holds what it plays (pedal_set 64). A finger drawn along
// a held key, as the player chooses (VEL's panel): a glissando, a bend (one
// key's width a semitone, the latest finger's), or aftertouch (drawn toward
// the front edge, the deepest finger's) -- key_ctl. Four octaves on the laptop, three on the iPad, two on the
// phone. A mouse plays one key where nothing has touched the screen (on a
// touch screen SDL makes a mouse of a finger too: that is not played twice).
#pragma once

#include <algorithm>
#include <map>

#include "app.h"
#include "look.h"
#include "touchvel.h"

namespace nui {

struct KeysUi {
    int base = 48;                                  // (the lowest key, a C: C3)
    bool sustain = false, open = false, vel_open = false;
    int row = -1;                                   // (the part its notes went to)
    Fingers F;
    std::map<int, int> vel;                         // (a held key and how hard it was struck: its light)
    std::map<unsigned long long, ImVec2> f0;        // (each held finger where it landed: a bend's or a press's start)
    std::vector<unsigned long long> order;          // (the held fingers, the latest last: the bend is its)
    float bend = 0;                                 // (the bend sent, semitones; the pressure sent)
    int press = 0;
};
static KeysUi g_keys;

inline void keys_note(App &a, int row, int key, int v)
{
    call(a, "{\"call\":\"drum_hit\",\"free\":1,\"row\":" + std::to_string(row) + ",\"key\":" + std::to_string(key) +
                ",\"v\":" + std::to_string(v) + "}");
}
// (every key let go -- the card shut, the part changed -- and the pedal up)
inline void keys_release(App &a)
{
    KeysUi &K = g_keys;
    fingers_release(K.F, [&](int k) {
        if (K.row >= 0)
            keys_note(a, K.row, k, 0);
    });
    K.vel.clear();
    K.f0.clear();
    K.order.clear();
    if (K.row >= 0 && K.bend != 0)
        call(a, "{\"call\":\"key_ctl\",\"kind\":\"bend\",\"semis\":0,\"row\":" + std::to_string(K.row) + "}");
    if (K.row >= 0 && K.press != 0)
        call(a, "{\"call\":\"key_ctl\",\"kind\":\"press\",\"v\":0,\"row\":" + std::to_string(K.row) + "}");
    K.bend = 0;
    K.press = 0;
    if (K.sustain && K.row >= 0)
        call(a, "{\"call\":\"pedal_set\",\"row\":" + std::to_string(K.row) + ",\"cc\":64,\"v\":0}");
    K.sustain = false;
}
inline void keys_card(App &a, bool open)
{
    KeysUi &K = g_keys;
    if (open == K.open)
        return;
    K.open = open;
    if (!open)
        keys_release(a);
}

inline void draw_keys_card(App &a)
{
    KeysUi &K = g_keys;
    const bool IP = a.tab, PH = a.ph;
    const float X0 = PH ? 14 : IP ? 20 : 34, X1 = IP ? (PH ? 818 : 1113) : 1886, HY = PH ? 120 : IP ? 224 : 356;
    const float Y1 = card_y1(a);
    if (K.row != a.row) {               // (another part: what this one held is let go)
        keys_release(a);
        K.row = a.row;
    }
    const float TX = heading(a, X0, HY, T("KEYS"), "keys");
    const J *p = part(a, a.row);
    std::string sub = TF("part {0} \xc2\xb7 {1}", {pad2(a.row + 1), str(p, "name")});
    if (g_touch.last_v >= 0)
        sub += " \xc2\xb7 " + TF("vel {0}", {std::to_string(g_touch.last_v)});

    // OCTAVE and SUSTAIN, at the card's right
    const int oct = PH ? 2 : IP ? 3 : 4;
    const float bh = PH ? 40 : 44, by = PH ? HY - 8 : HY - 10, B = 21;
    float bx = X1;
    auto key_btn = [&](const char *id, const std::string &lab, bool lit, bool en) {
        const float w = text_w(a, a.bold, B, lab) + 28;
        bx -= w;
        const bool hit = button(a, id, bx, by, w, bh, lab.c_str(), lit, en, B);
        bx -= 8;
        return hit;
    };
    if (key_btn("kysus", T("SUSTAIN"), K.sustain, true)) {
        K.sustain = !K.sustain;
        call(a, "{\"call\":\"pedal_set\",\"row\":" + std::to_string(a.row) + ",\"cc\":64,\"v\":" + (K.sustain ? "127" : "0") + "}");
    }
    if (key_btn("kyup", T("OCTAVE \xe2\x96\xb6"), false, K.base + 12 * oct < 120))
        K.base += 12;
    const std::string range = note_name(K.base) + "\xe2\x80\x93" + note_name(K.base + 12 * oct);
    bx -= text_w(a, a.font, 14, range) + 4;
    text(a, a.font, 14, bx, by + bh / 2 - a.lh(14) / 2, SILK, range);
    bx -= 12;
    if (key_btn("kydn", T("\xe2\x97\x80 OCTAVE"), false, K.base > 0))
        K.base -= 12;
    if (key_btn("kyvel", TF("VEL {0}", {touch_says("keys")}), K.vel_open, true)) {
        K.vel_open = !K.vel_open;
        keys_release(a);
    }
    text(a, a.font, 14, TX, HY + 1, LCD, fit(a, a.font, 14, sub, bx - TX - 8));

    // THE KEYBOARD: from the controls down to the card's foot
    // (VEL open: its settings over the keys, which wait)
    const float KY0 = (PH ? 160 : IP ? 262 : 404), KY1 = Y1 - 8, kh = KY1 - KY0, bkh = kh * 0.6f;
    const int lo = K.base, hi = K.base + 12 * oct;      // (C to C)
    int nwhite = 0;
    for (int k = lo; k <= hi; k++)
        nwhite += !is_black(k);
    const float ww = (X1 - X0) / nwhite;
    auto left = [&](int k) {
        int w = 0;
        for (int j = lo; j < k; j++)
            w += !is_black(j);
        return is_black(k) ? X0 + w * ww - ww * 0.32f : X0 + w * ww;
    };
    auto width = [&](int k) { return is_black(k) ? ww * 0.64f : ww; };
    // (a point to its key and how hard: black keys over the white ones' upper part)
    auto key_at = [&](float x, float y, int &v) {
        if (x < X0 || x >= X1 || y < KY0 || y >= KY1)
            return -1;
        int key = -1;
        if (y < KY0 + bkh)
            for (int k = lo; k <= hi; k++)
                if (is_black(k) && x >= left(k) && x < left(k) + width(k))
                    key = k;
        if (key < 0)
            for (int k = lo; k <= hi; k++)
                if (!is_black(k) && x >= left(k) && x < left(k) + ww)
                    key = k;
        const float depth = is_black(key) ? bkh : kh;
        v = touch_velocity_by(touch_for("keys"), (y - KY0) / depth);
        return key;
    };

    if (K.vel_open) {                   // (how hard, at the left; a finger drawn, at the right)
        look::tray(a, X0, KY0, X1 - X0, kh, 9);
        const float CW = (X1 - X0) / 2 - 21, RX = X0 + (X1 - X0) / 2 + 7;
        float y = KY0 + 14;
        text(a, a.bold, 14, X0 + 14, y, SILK, fit(a, a.bold, 14, T("HOW HARD A TOUCH PLAYS ON THESE KEYS"), CW));
        y += a.lh(14) + 10;
        if (touch_panel(a, "kyv", g_touch.keys, &g_touch.keys_own, X0 + 14, y, CW))
            touch_save(a);
        for (const auto &l : wrap(a, a.font, 14, T("Position: the key's front edge plays hardest. VEL again to play."), CW)) {
            text(a, a.font, 14, X0 + 14, y + 4, SILK_DIM, l);
            y += a.lh(14) + 3;
        }
        float ry = KY0 + 14;
        text(a, a.bold, 14, RX, ry, SILK, fit(a, a.bold, 14, T("A FINGER DRAWN ALONG A HELD KEY"), CW));
        ry += a.lh(14) + 10;
        {
            static const char *SL[3] = {"glide", "bend", "press"};
            std::vector<bool> lit;
            for (const char *x : SL)
                lit.push_back(g_touch.slide == x);
            const int h = flow_buttons(a, "kyslide", RX, ry, CW, {T("GLISSANDO"), T("BEND"), T("AFTERTOUCH")}, lit);
            if (h >= 0) {
                g_touch.slide = SL[h];
                touch_save(a);
            }
        }
        const char *say = g_touch.slide == "bend" ? N_("Bend: drawn sideways, a key's width a semitone, up to the bend range (Setup).")
                          : g_touch.slide == "press" ? N_("Aftertouch: drawn toward the front edge, the key pressed harder.")
                                                     : N_("Glissando: drawn along the keys, each one plays in turn.");
        for (const auto &l : wrap(a, a.font, 14, T(say), CW)) {
            text(a, a.font, 14, RX, ry + 4, SILK_DIM, l);
            ry += a.lh(14) + 3;
        }
        return;
    }
    // (the bed: the keyboard's own ImGui item, so a mouse on it plays it and no card gesture takes it)
    ImGui::SetCursorScreenPos(P(a, X0, KY0));
    ImGui::InvisibleButton("keysbed", ImVec2((X1 - X0) * a.k, kh * a.k));
    const bool mouse_on = ImGui::IsItemActive() && !a.touch_seen;

    // (each finger -- and the mouse -- its key now; a change plays: the old key let go, the new one struck.
    //  Bending or pressing, a held finger keeps its key wherever it is drawn)
    const bool glide = g_touch.slide == "glide";
    std::map<unsigned long long, ImVec2> pts;
    for (const auto &t : a.touches)
        pts[t.first] = ImVec2((t.second.x - a.org.x) / a.k, (t.second.y - a.org.y) / a.k);
    if (mouse_on) {
        const ImVec2 m = ImGui::GetIO().MousePos;
        pts[~0ull] = ImVec2((m.x - a.org.x) / a.k, (m.y - a.org.y) / a.k);
    }
    std::map<unsigned long long, std::pair<int, int>> now;     // (finger -> key, velocity)
    for (const auto &p : pts) {
        auto h = K.F.held.find(p.first);
        if (!glide && h != K.F.held.end()) {
            now[p.first] = {h->second, 0};
            continue;
        }
        int v = 0;
        const int k = key_at(p.second.x, p.second.y, v);
        if (k >= 0)
            now[p.first] = {k, v};
    }
    fingers_step(K.F, now, glide, [&](int k, int v) {
        keys_note(a, a.row, k, v);
        K.vel[k] = v;
        g_touch.last_v = v;
    }, [&](int k) {
        keys_note(a, a.row, k, 0);
        K.vel.erase(k);
    });
    // (where each held finger landed, the latest last; the lifted forgotten)
    for (auto it = K.f0.begin(); it != K.f0.end();)
        it = K.F.held.count(it->first) ? std::next(it) : K.f0.erase(it);
    K.order.erase(std::remove_if(K.order.begin(), K.order.end(), [&](unsigned long long f) { return !K.F.held.count(f); }),
                  K.order.end());
    for (const auto &h : K.F.held)
        if (!K.f0.count(h.first) && pts.count(h.first)) {
            K.f0[h.first] = pts[h.first];
            K.order.push_back(h.first);
        }
    // (the bend: the latest finger's sideways travel past a wobble, a key's width -- an average one,
    //  7/12 of a white key -- a semitone; the pressure: the deepest travel toward the front edge)
    float bend = 0;
    int press = 0;
    if (g_touch.slide == "bend" && !K.order.empty() && pts.count(K.order.back())) {
        const float semi = ww * 7 / 12, dx = pts[K.order.back()].x - K.f0[K.order.back()].x, dead = semi * 0.25f;
        if (std::fabs(dx) > dead)
            bend = std::round((dx - (dx > 0 ? dead : -dead)) / semi * 64) / 64;     // (in 1/64 semitones)
    }
    if (g_touch.slide == "press")
        for (const auto &f : K.f0)
            if (pts.count(f.first))
                press = std::max(press, (int)std::lround(std::max(0.0f, std::min(1.0f, (pts[f.first].y - f.second.y) / (kh * 0.35f))) * 127));
    if (bend != K.bend) {
        char b[160];
        snprintf(b, sizeof b, "{\"call\":\"key_ctl\",\"kind\":\"bend\",\"semis\":%.4f,\"row\":%d}", bend, a.row);
        call(a, b);
        K.bend = bend;
    }
    if (press != K.press) {
        call(a, "{\"call\":\"key_ctl\",\"kind\":\"press\",\"v\":" + std::to_string(press) + ",\"row\":" + std::to_string(a.row) + "}");
        K.press = press;
    }
    if (!K.F.held.empty())
        a.animate = true;

    // (drawn: the white keys, then the black over them; a held key lit)
    // (a held key lit, the brighter the harder it was struck)
    const ImU32 LIT_W = IM_COL32(0xf3, 0xc8, 0x78, 255), LIT_B = IM_COL32(0xb0, 0x74, 0x18, 255);
    auto lit = [&](int k, ImU32 off, ImU32 on) {
        auto it = K.vel.find(k);
        return it == K.vel.end() ? off : look::mix(off, on, 0.35f + 0.65f * it->second / 127.0f);
    };
    for (int k = lo; k <= hi; k++)
        if (!is_black(k)) {
            look::white_key(a, left(k), KY0, ww - 1, kh, lit(k, KEY_W, LIT_W));
            if (k % 12 == 0)
                text(a, a.font, 14, left(k) + 4, KY1 - a.lh(14) - 6, SILK_DIM, note_name(k));
        }
    for (int k = lo; k <= hi; k++)
        if (is_black(k))
            look::black_key(a, left(k), KY0, width(k), bkh, lit(k, KEY_B, LIT_B));
}

}  // namespace nui
