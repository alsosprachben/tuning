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
    const float W = 620, H = 720, x = (a.W - W) / 2, y = (a.H - H) / 2;   // (the canvas's own: the laptop's, the iPad's)
    look::module(a, x, y, W, H, 12);
    text(a, a.bold, 14, x + 24, y + 22, SILK, s.title);
    look::lcd_text(a, 21, x + 24, y + 46, LCD, fit(a, a.font, 21, s.now, W - 48));
    text(a, a.font, 14, x + 24, y + 86, SILK_DIM, s.label);
    look::lcd_window(a, x + 24, y + 106, W - 48, 60, true);
    look::lcd_text(a, 35, x + 40, y + 118, LCD, s.typed + "_");
    look::glass(a, x + 24, y + 106, W - 48, 60);
    float hy = y + 176;
    char range[64];
    snprintf(range, sizeof range, "%.*f to %.*f", s.digits, s.lo, s.digits, s.hi);
    for (const auto &l : wrap(a, a.font, 14, (s.hint.empty() ? std::string() : s.hint + " ") + range + ".", W - 48)) {
        text(a, a.font, 14, x + 24, hy, SILK_DIM, l);
        hy += 18;
    }
    // (a keyboard's typing too)
    ImGuiIO &io = ImGui::GetIO();
    for (int i = 0; i < io.InputQueueCharacters.Size; i++) {
        const ImWchar c = io.InputQueueCharacters[i];
        if ((c >= '0' && c <= '9') || c == '.' || c == '-')
            s.typed += (char)c;
    }
    if (ImGui::IsKeyPressed(ImGuiKey_Backspace) && !s.typed.empty())
        s.typed.pop_back();
    bool set = ImGui::IsKeyPressed(ImGuiKey_Enter) || ImGui::IsKeyPressed(ImGuiKey_KeypadEnter);
    if (ImGui::IsKeyPressed(ImGuiKey_Escape)) {
        s.open = false;
        return;
    }
    // THE PAD
    static const char *KEYS[4][3] = {{"7", "8", "9"}, {"4", "5", "6"}, {"1", "2", "3"}, {"-", "0", "."}};
    const float kx = x + 24, ky = y + 236, kw = 120, kh = 64, g = 8;
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 3; c++) {
            const std::string k = KEYS[r][c], id = "sk" + k;
            if (button(a, id.c_str(), kx + c * (kw + g), ky + r * (kh + g), kw, kh, k, false, true, 28)) {
                if (k == "-")
                    s.typed = !s.typed.empty() && s.typed[0] == '-' ? s.typed.substr(1) : "-" + s.typed;
                else if (s.typed.size() < 16)
                    s.typed += k;
            }
        }
    const float sx = kx + 3 * (kw + g) + 12, sw = x + W - 24 - sx;
    if (button(a, "skback", sx, ky, sw, kh, "\xe2\x86\x90", false, true, a.tab ? 21 : 14) && !s.typed.empty())
        s.typed.pop_back();
    if (button(a, "skclear", sx, ky + kh + g, sw, kh, "CLEAR", false, true, a.tab ? 21 : 14))
        s.typed.clear();
    const float by = y + H - 24 - 50;
    if (s.can_reset && button(a, "skreset", x + 24, by, 230, 50, "BACK TO THE PATCH", false, true, a.tab ? 21 : 14)) {
        a.sheet_reset.insert(s.key);
        s.open = false;
        return;
    }
    if (button(a, "skclose", x + W - 24 - 2 * 140 - 10, by, 140, 50, "CLOSE", false, true, a.tab ? 21 : 14)) {
        s.open = false;
        return;
    }
    set = button(a, "skset", x + W - 24 - 140, by, 140, 50, "SET", true, true, a.tab ? 21 : 14) || set;
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
