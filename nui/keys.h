// THE KEYS CARD: a keyboard to touch, for trying a sound and for showing it
// -- every finger its own key (a chord held, a glissando slid), struck harder
// nearer the key's front edge, on the selected part's channel (drum_hit: a
// note on, and its release); OCTAVE moves it, SUSTAIN holds what it plays
// (pedal_set 64). Four octaves on the laptop, three on the iPad, two on the
// phone. A mouse plays one key where nothing has touched the screen (on a
// touch screen SDL makes a mouse of a finger too: that is not played twice).
#pragma once

#include <map>

#include "app.h"
#include "look.h"

namespace nui {

struct KeysUi {
    int base = 48;                                  // (the lowest key, a C: C3)
    bool sustain = false, open = false;
    int row = -1;                                   // (the part its notes went to)
    std::map<unsigned long long, int> held;         // (a finger -- or the mouse, ~0 -- and the key it holds)
    std::map<int, int> down;                        // (a key and how many fingers hold it)
};
static KeysUi g_keys;

inline void keys_note(App &a, int row, int key, int v)
{
    call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(row) + ",\"key\":" + std::to_string(key) +
                ",\"v\":" + std::to_string(v) + "}");
}
// (every key let go -- the card shut, the part changed -- and the pedal up)
inline void keys_release(App &a)
{
    KeysUi &K = g_keys;
    for (const auto &d : K.down)
        if (d.second > 0 && K.row >= 0)
            keys_note(a, K.row, d.first, 0);
    K.down.clear();
    K.held.clear();
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
    text(a, a.font, 14, TX, HY + 1, LCD, TF("part {0} \xc2\xb7 {1}", {pad2(a.row + 1), str(p, "name")}));

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

    // THE KEYBOARD: from the controls down to the card's foot
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
        v = std::max(30, std::min(127, (int)std::lround(40 + 87 * (y - KY0) / depth)));
        return key;
    };

    // (the bed: the keyboard's own ImGui item, so a mouse on it plays it and no card gesture takes it)
    ImGui::SetCursorScreenPos(P(a, X0, KY0));
    ImGui::InvisibleButton("keysbed", ImVec2((X1 - X0) * a.k, kh * a.k));
    const bool mouse_on = ImGui::IsItemActive() && !a.touch_seen;

    // (each finger -- and the mouse -- its key now; a change plays: the old key let go, the new one struck)
    std::map<unsigned long long, std::pair<int, int>> now;     // (finger -> key, velocity)
    for (const auto &t : a.touches) {
        int v = 0;
        const int k = key_at((t.second.x - a.org.x) / a.k, (t.second.y - a.org.y) / a.k, v);
        if (k >= 0)
            now[t.first] = {k, v};
    }
    if (mouse_on) {
        int v = 0;
        const ImVec2 m = ImGui::GetIO().MousePos;
        const int k = key_at((m.x - a.org.x) / a.k, (m.y - a.org.y) / a.k, v);
        if (k >= 0)
            now[~0ull] = {k, v};
    }
    for (auto it = K.held.begin(); it != K.held.end();) {      // (let go, or slid off its key)
        auto n = now.find(it->first);
        if (n == now.end() || n->second.first != it->second) {
            if (--K.down[it->second] <= 0) {
                keys_note(a, a.row, it->second, 0);
                K.down.erase(it->second);
            }
            it = K.held.erase(it);
        } else
            ++it;
    }
    for (const auto &n : now)                                    // (struck: a new finger, or slid onto a key)
        if (!K.held.count(n.first)) {
            K.held[n.first] = n.second.first;
            if (K.down[n.second.first]++ == 0)
                keys_note(a, a.row, n.second.first, n.second.second);
        }
    if (!K.held.empty())
        a.animate = true;

    // (drawn: the white keys, then the black over them; a held key lit)
    const ImU32 LIT_W = IM_COL32(0xf3, 0xc8, 0x78, 255), LIT_B = IM_COL32(0xb0, 0x74, 0x18, 255);
    for (int k = lo; k <= hi; k++)
        if (!is_black(k)) {
            look::white_key(a, left(k), KY0, ww - 1, kh, K.down.count(k) ? LIT_W : KEY_W);
            if (k % 12 == 0)
                text(a, a.font, 14, left(k) + 4, KY1 - a.lh(14) - 6, SILK_DIM, note_name(k));
        }
    for (int k = lo; k <= hi; k++)
        if (is_black(k))
            look::black_key(a, left(k), KY0, width(k), bkh, K.down.count(k) ? LIT_B : KEY_B);
}

}  // namespace nui
