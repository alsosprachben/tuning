// A CONTROL's SHEET (kit.js's sheet, a long-press): what it is now, its value
// typed on a number pad (or a keyboard), SET, BACK TO THE PATCH (the
// control's own reset, as a double-tap), CLOSE. Over everything while open.
#pragma once

#include "app.h"
#include "library.h"

namespace nui {

inline void draw_sheet(App &a)
{
    App::Sheet &s = a.sheet;
    rect(a, 0, 0, a.W, a.H, IM_COL32(0x0c, 0x0d, 0x0f, 235), 0);
    // (the canvas's own: the laptop's, the iPad's -- one column, the pad under the value; the
    //  phone's too short for that: the value on the left, the pad on the right, the buttons beside it)
    const bool PH = a.ph;
    const float W = PH ? 800 : 620, H = PH ? std::min(380.0f, a.H - 16) : 720, x = (a.W - W) / 2, y = (a.H - H) / 2;
    const float LW = PH ? 280 : W - 48;     // (the value's column)
    look::module(a, x, y, W, H, 12);
    text(a, a.bold, 14, x + 24, y + 22, SILK, s.title);
    look::lcd_text(a, 21, x + 24, y + 46, LCD, fit(a, a.font, 21, s.now, LW));
    text(a, a.font, 14, x + 24, y + 86, SILK_DIM, s.label);
    look::lcd_window(a, x + 24, y + 106, LW, 60, true);
    look::lcd_text(a, 35, x + 40, y + 118, s.fresh ? LCD_DIM : LCD, fit(a, a.font, 35, s.typed + "_", LW - 32));   // (dim: a digit replaces it)
    look::glass(a, x + 24, y + 106, LW, 60);
    float hy = y + 176;
    char lo[32], hi[32];
    snprintf(lo, sizeof lo, "%.*f", s.digits, s.lo);
    snprintf(hi, sizeof hi, "%.*f", s.digits, s.hi);
    const std::string range = TF("{0} to {1}.", {lo, hi});
    for (const auto &l : wrap(a, a.font, 14, (s.hint.empty() ? std::string() : s.hint + " ") + range, LW)) {
        text(a, a.font, 14, x + 24, hy, SILK_DIM, l);
        hy += 18;
    }
    // (a keyboard's typing too)
    ImGuiIO &io = ImGui::GetIO();
    for (int i = 0; i < io.InputQueueCharacters.Size; i++) {
        const ImWchar c = io.InputQueueCharacters[i];
        if (c == '-')
            s.typed = !s.typed.empty() && s.typed[0] == '-' ? s.typed.substr(1) : "-" + s.typed;
        else if ((c >= '0' && c <= '9') || c == '.') {
            if (s.fresh)
                s.typed.clear();
            s.typed += (char)c;
        }
        if (c == '-' || (c >= '0' && c <= '9') || c == '.')
            s.fresh = false;
    }
    if (ImGui::IsKeyPressed(ImGuiKey_Backspace) && !s.typed.empty()) {
        s.typed.pop_back();
        s.fresh = false;
    }
    bool set = ImGui::IsKeyPressed(ImGuiKey_Enter) || ImGui::IsKeyPressed(ImGuiKey_KeypadEnter);
    if (ImGui::IsKeyPressed(ImGuiKey_Escape)) {
        s.open = false;
        return;
    }
    // THE PAD
    static const char *KEYS[4][3] = {{"7", "8", "9"}, {"4", "5", "6"}, {"1", "2", "3"}, {"-", "0", "."}};
    const float kx = PH ? x + 24 + LW + 24 : x + 24, ky = PH ? y + 24 : y + 236, kw = PH ? 100 : 120, g = 8,
                kh = PH ? (H - 48 - 3 * g) / 4 : 64;
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 3; c++) {
            const std::string k = KEYS[r][c], id = "sk" + k;
            if (button(a, id.c_str(), kx + c * (kw + g), ky + r * (kh + g), kw, kh, k, false, true, 28)) {
                if (k == "-")
                    s.typed = !s.typed.empty() && s.typed[0] == '-' ? s.typed.substr(1) : "-" + s.typed;
                else {
                    if (s.fresh)        // (the first digit a new value, not more of the old)
                        s.typed.clear();
                    if (s.typed.size() < 16)
                        s.typed += k;
                }
                s.fresh = false;
            }
        }
    const float sx = kx + 3 * (kw + g) + 12, sw = x + W - 24 - sx;
    if (button(a, "skback", sx, ky, sw, kh, "\xe2\x86\x90", false, true, a.tab ? 21 : 14) && !s.typed.empty()) {
        s.typed.pop_back();
        s.fresh = false;
    }
    if (button(a, "skclear", sx, ky + kh + g, sw, kh, T("CLEAR"), false, true, a.tab ? 21 : 14)) {
        s.typed.clear();
        s.fresh = false;
    }
    // (BACK TO THE PATCH under the value; CLOSE, SET: the laptop's and iPad's at the foot, the phone's
    //  under the pad's ← and CLEAR)
    const float by = y + H - 24 - 50;
    if (s.can_reset && button(a, "skreset", x + 24, PH ? y + H - 24 - kh : by, PH ? LW : 230, PH ? kh : 50, T("BACK TO THE PATCH"), false, true, a.tab ? 21 : 14)) {
        a.sheet_reset.insert(s.key);
        s.open = false;
        return;
    }
    if (PH ? button(a, "skclose", sx, ky + 2 * (kh + g), sw, kh, T("CLOSE"), false, true, 14)
           : button(a, "skclose", x + W - 24 - 2 * 140 - 10, by, 140, 50, T("CLOSE"), false, true, a.tab ? 21 : 14)) {
        s.open = false;
        return;
    }
    set = (PH ? button(a, "skset", sx, ky + 3 * (kh + g), sw, kh, T("SET"), true, true, 14)
              : button(a, "skset", x + W - 24 - 140, by, 140, 50, T("SET"), true, true, a.tab ? 21 : 14)) || set;
    if (set) {
        char *end = nullptr;
        const double v = strtod(s.typed.c_str(), &end);
        if (end && end != s.typed.c_str()) {
            a.sheet_set[s.key] = std::max(s.lo, std::min(s.hi, v));
            s.open = false;
        }
    }
}

}  // namespace nui
