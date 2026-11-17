// THE SCENES CARD (ui/app.js's): the presets (the whole setup) and the
// scenes (each channel's controls), kept beside the session and shared with
// live.py and the apps: a tap chooses one, LOAD or RECALL brings it, SAVE
// OVER keeps the present one in it, DELETE takes it out; a new one named on
// the screen's own keys. The metronome, and the GS reset (a second tap).
#pragma once

#include "app.h"
#include "effects.h"
#include "library.h"
#include "tuning.h"

namespace nui {

struct ScenesUi {
    bool open = false;
    J s;                                // (scenes_of: presets [{name, parts, tuner}], scenes [{name, n}], kept, metro [bpm, bell, dB])
    std::string sel_preset, sel_scene, msg;
    double msg_until = 0, reset_armed = 0;
    // a name being typed: for which call
    std::string naming, name;
    float scroll_p = 0, scroll_s = 0;
    int last_bpm = 100;
};
static ScenesUi g_sc;

inline void sc_take(const J &r)
{
    if (const J *s = r.get("scenes"))
        g_sc.s = *s;
}
inline void scenes_card(App &a, bool open)
{
    ScenesUi &C = g_sc;
    if (open == C.open)
        return;
    C.open = open;
    sc_take(call(a, std::string("{\"call\":\"scenes\",\"open\":") + (open ? "1" : "0") + "}"));
}
inline std::string jstr(const std::string &s)       // (a string as JSON)
{
    return sess::dump(sess::str(s));
}
inline void sc_do(App &a, const std::string &c, const std::string &name)
{
    ScenesUi &C = g_sc;
    J r = call(a, "{\"call\":\"" + c + "\",\"name\":" + jstr(name) + "}");
    C.msg = str(&r, "msg");
    if (C.msg.empty() && r.get("error"))
        C.msg = str(&r, "error");
    C.msg_until = ImGui::GetTime() + 4;
    if (c.size() > 7 && c.compare(c.size() - 7, 7, "_delete") == 0)
        C.sel_preset.clear(), C.sel_scene.clear();
    if (r.get("scenes"))
        sc_take(r);
    else
        sc_take(call(a, "{\"call\":\"scenes\"}"));
}

// a list of named items, the chosen one opened with its actions
inline void sc_list(App &a, const char *id, float x, float y, float w, float h, const J *items, std::string &sel, float &scroll,
                    const std::function<std::string(const J &)> &say, const std::vector<std::pair<const char *, std::string>> &acts)
{
    const float ih = 58, oh = 50;
    const int n = items && items->is(J::ARR) ? (int)items->a.size() : 0;
    std::vector<float> ys;
    float cy = 0;
    for (int i = 0; i < n; i++) {
        ys.push_back(cy);
        cy += ih + (str(&items->a[(size_t)i], "name") == sel ? oh : 0) + 6;
    }
    ImVec2 tap;
    const bool tapped = scroll_area(a, id, x, y, w, h, cy, scroll, tap);
    dl()->PushClipRect(P(a, x, y), P(a, x + w, y + h), true);
    for (int i = 0; i < n; i++) {
        const J &it = items->a[(size_t)i];
        const std::string nm = str(&it, "name");
        const bool on = nm == sel;
        const float iy = y + ys[(size_t)i] - scroll, th = ih + (on ? oh : 0);
        rect(a, x, iy, w - 8, th, on ? IM_COL32(0x33, 0x2a, 0x16, 255) : IM_COL32(0x26, 0x2a, 0x2e, 255), 7);
        frame(a, x, iy, w - 8, th, on ? LCD : EDGE, 7, on ? 1.5f : 1);
        text(a, a.font, 21, x + 12, iy + 8, LCD, fit(a, a.font, 21, nm, w - 32));
        text(a, a.font, 14, x + 12, iy + 34, SILK_DIM, fit(a, a.font, 14, say(it), w - 32));
        if (on) {
            const float bw = (w - 8 - 24 - 2 * 8) / 3;
            for (size_t k = 0; k < acts.size(); k++) {
                const float bx = x + 12 + k * (bw + 8), by = iy + ih;
                rect(a, bx, by, bw, 38, BTN, 7);
                frame(a, bx, by, bw, 38, EDGE, 7, 1);
                text_c(a, a.bold, 14, bx + bw / 2, by + 12, SILK, acts[k].first);
                if (tapped && tap.x >= bx - x && tap.x < bx - x + bw && tap.y >= ys[(size_t)i] + ih && tap.y < ys[(size_t)i] + ih + 38) {
                    dl()->PopClipRect();
                    sc_do(a, acts[k].second, nm);
                    return;
                }
            }
        }
        if (tapped && tap.y >= ys[(size_t)i] && tap.y < ys[(size_t)i] + ih)
            sel = on ? "" : nm;
    }
    dl()->PopClipRect();
    if (!n)
        text(a, a.font, 14, x, y + 6, SILK_DIM, std::string(id) == "scp" ? "No presets yet." : "No scenes yet.");
}

inline void draw_scenes(App &a)
{
    ScenesUi &C = g_sc;
    LibUi &L = g_lib;
    if (!L.loaded)
        lib_load(a);
    if (!C.s.is(J::OBJ))
        sc_take(call(a, "{\"call\":\"scenes\",\"open\":1}"));
    const float X0 = 34, X1 = 1886, Y0 = 394, Y1 = 1056;
    text(a, a.bold, 14, X0, 356, SILK, "SCENES");
    if (!C.s.is(J::OBJ))
        return;
    if (ImGui::GetTime() > C.msg_until)
        C.msg.clear();
    const std::string info = !C.msg.empty() ? C.msg : flag(&C.s, "kept") ? "" : "No session file: presets and scenes cannot be kept.";
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), 357, C.msg.empty() ? SILK_DIM : OWN, info);
    if (!C.msg.empty())
        a.animate = true;

    // A NAME, typed on the screen's own keys (or a keyboard's)
    if (!C.naming.empty()) {
        const float W = 900, x = (1920 - W) / 2;
        rect(a, x - 20, Y0, W + 40, Y1 - Y0, IM_COL32(0x1f, 0x22, 0x26, 255), 10);
        frame(a, x - 20, Y0, W + 40, Y1 - Y0, LCD_DIM, 10, 1.5f);
        text(a, a.bold, 14, x, Y0 + 16, SILK, C.naming == "preset_save" ? "SAVE THIS SETUP AS" : "SAVE THE CONTROLS AS");
        rect(a, x, Y0 + 44, W, 56, LCD_BG, 4);
        frame(a, x, Y0 + 44, W, 56, LCD, 4, 1.5f);
        text(a, a.font, 28, x + 14, Y0 + 58, LCD, C.name + "_");
        ImGuiIO &io = ImGui::GetIO();
        for (int i = 0; i < io.InputQueueCharacters.Size; i++) {
            const ImWchar c = io.InputQueueCharacters[i];
            if (c >= 32 && c < 127 && C.name.size() < 40)
                C.name += (char)c;
        }
        if (ImGui::IsKeyPressed(ImGuiKey_Backspace) && !C.name.empty())
            C.name.pop_back();
        bool save = ImGui::IsKeyPressed(ImGuiKey_Enter);
        if (ImGui::IsKeyPressed(ImGuiKey_Escape)) {
            C.naming.clear();
            return;
        }
        save = osk(a, C.name, x, Y0 + 130, W, true, "SAVE") || save;
        if (button(a, "nmcancel", x, Y1 - 64, 200, 46, "CANCEL")) {
            C.naming.clear();
            return;
        }
        std::string nm = C.name;
        while (!nm.empty() && nm.back() == ' ')
            nm.pop_back();
        while (!nm.empty() && nm[0] == ' ')
            nm.erase(0, 1);
        if (button(a, "nmsave", x + W - 200, Y1 - 64, 200, 46, "SAVE", !nm.empty(), !nm.empty()) || (save && !nm.empty())) {
            const std::string c = C.naming;
            C.naming.clear();
            sc_do(a, c, nm);
        }
        return;
    }

    // THE PRESETS: the whole setup
    const float PW = 720, SW = 600, gap = 10, SX = X0 + PW + gap, MX = SX + SW + gap, MW = X1 - MX;
    rect(a, X0, Y0, PW, Y1 - Y0, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
    frame(a, X0, Y0, PW, Y1 - Y0, EDGE, 9, 1);
    text(a, a.bold, 14, X0 + 12, Y0 + 10, SILK, "PRESETS");
    text(a, a.font, 14, X0 + 24 + text_w(a, a.bold, 14, "PRESETS"), Y0 + 11, LCD, "the whole setup: parts, routes, tuning, effects");
    auto parts_say = [&](const J &p) {
        std::string s;
        if (const J *ps = p.get("parts"); ps && ps->is(J::ARR))
            for (const J &q : ps->a) {
                const int pg = (int)q.a[0].d(), v = (int)q.a[1].d();
                const bool dr = q.a[2].d() != 0;
                std::string nm = dr ? "kit " + std::to_string(pg) : "program " + std::to_string(pg);
                for (const Patch &x : L.patches)
                    if (x.drums == dr && x.program == pg && (dr || x.variation == v)) {
                        nm = x.name;
                        break;
                    }
                s += (s.empty() ? "" : " + ") + nm;
            }
        const std::string t = str(&p, "tuner");
        return s + (t.empty() ? "" : " \xc2\xb7 " + t);
    };
    sc_list(a, "scp", X0 + 12, Y0 + 40, PW - 24, Y1 - Y0 - 110, C.s.get("presets"), C.sel_preset, C.scroll_p, parts_say,
            {{"LOAD", "preset_load"}, {"SAVE OVER", "preset_save"}, {"DELETE", "preset_delete"}});
    if (button(a, "presetsave", X0 + 12, Y1 - 58, 300, 44, "SAVE THIS SETUP AS\xe2\x80\xa6")) {
        C.naming = "preset_save";
        C.name.clear();
    }

    // THE SCENES: each channel's controls
    rect(a, SX, Y0, SW, Y1 - Y0, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
    frame(a, SX, Y0, SW, Y1 - Y0, EDGE, 9, 1);
    text(a, a.bold, 14, SX + 12, Y0 + 10, SILK, "SCENES");
    text(a, a.font, 14, SX + 24 + text_w(a, a.bold, 14, "SCENES"), Y0 + 11, LCD, fit(a, a.font, 14, "each channel's controls: levels, pans, sends, pedals", SW - 120));
    sc_list(a, "scs", SX + 12, Y0 + 40, SW - 24, Y1 - Y0 - 110, C.s.get("scenes"), C.sel_scene, C.scroll_s,
            [](const J &c) {
                const int n = (int)num(&c, "n");
                return std::to_string(n) + " setting" + (n == 1 ? "" : "s");
            },
            {{"RECALL", "scene_recall"}, {"SAVE OVER", "scene_save"}, {"DELETE", "scene_delete"}});
    if (button(a, "scenesave", SX + 12, Y1 - 58, 320, 44, "SAVE THE CONTROLS AS\xe2\x80\xa6")) {
        C.naming = "scene_save";
        C.name.clear();
    }

    // THE METRONOME: the globals 10 (bpm, 0 off), 11 (its bell every n beats), 12 (its level)
    rect(a, MX, Y0, MW, Y1 - Y0, IM_COL32(0x1f, 0x22, 0x26, 255), 9);
    frame(a, MX, Y0, MW, Y1 - Y0, EDGE, 9, 1);
    text(a, a.bold, 14, MX + 12, Y0 + 10, SILK, "METRONOME");
    const J *m = C.s.get("metro");
    auto mv = [&](size_t i) { return m && m->is(J::ARR) && i < m->a.size() ? m->a[i].d() : 0.0; };
    const int bpm = (int)std::lround(mv(0));
    if (bpm > 0)
        C.last_bpm = bpm;
    auto gset = [&](int i, int v) {
        call(a, "{\"call\":\"global_set\",\"i\":" + std::to_string(i) + ",\"v\":" + std::to_string(v) + "}");
        J &mm = C.s.o["metro"];         // (shown at once; the push confirms)
        if (mm.is(J::ARR) && (size_t)(i - 10) < mm.a.size())
            mm.a[(size_t)(i - 10)] = sess::integer(v);
    };
    {
        const float cw = (MW - 24) / 4, ky = Y0 + 90;
        const bool on = bpm > 0;
        rect(a, MX + 12 + cw / 2 - 28, ky - 15, 56, 30, on ? LCD : IM_COL32(0x15, 0x17, 0x1a, 255), 15);
        dl()->AddCircleFilled(P(a, on ? MX + 12 + cw / 2 + 13 : MX + 12 + cw / 2 - 13, ky), 11 * a.k, on ? LCD_BG : CAP, 24);
        ImGui::SetCursorScreenPos(P(a, MX + 12, ky - 30));
        if (ImGui::InvisibleButton("metroon", ImVec2(cw * a.k, 60 * a.k)))
            gset(10, on ? 0 : C.last_bpm);
        text_c(a, a.bold, 14, MX + 12 + cw / 2, ky + 24, SILK_DIM, "ON");
        int picked;
        list_knob(a, "metbpm", MX + 12 + 1.5f * cw, ky, 48, irange(30, 300), {}, on ? bpm : C.last_bpm, "Tempo", false, cw - 4, picked);
        if (picked != (on ? bpm : C.last_bpm)) {
            C.last_bpm = picked;
            if (on)
                gset(10, picked);
        }
        std::vector<std::string> bs = {"none"};
        for (int n = 1; n <= 16; n++)
            bs.push_back(std::to_string(n) + " beats");
        const int bell = (int)std::lround(mv(1));
        list_knob(a, "metbell", MX + 12 + 2.5f * cw, ky, 48, irange(0, 16), bs, bell, "Bell every", false, cw - 4, picked);
        if (picked != bell)
            gset(11, picked);
        std::vector<std::string> ds;
        for (int n = -40; n <= 12; n++)
            ds.push_back((n > 0 ? "+" : "") + std::to_string(n) + " dB");
        const int db = (int)std::lround(mv(2));
        list_knob(a, "metdb", MX + 12 + 3.5f * cw, ky, 48, irange(-40, 12), ds, db, "Level", false, cw - 4, picked);
        if (picked != db)
            gset(12, picked);
    }
    // THE GS RESET: a second tap within 3 s sends it
    float gy = Y0 + 220;
    rect(a, MX + 12, gy - 12, MW - 24, 1, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
    text(a, a.bold, 14, MX + 12, gy, SILK, "GS RESET");
    gy += 24;
    for (const auto &l : wrap(a, a.font, 14, "Every part back to program 1, the controllers, effects and receive settings to power-on, as a sequencer's GS Reset.", MW - 24)) {
        text(a, a.font, 14, MX + 12, gy, SILK_DIM, l);
        gy += 18;
    }
    const bool armed = ImGui::GetTime() < C.reset_armed;
    if (armed)
        a.animate = true;
    if (button(a, "gsreset", MX + 12, gy + 10, MW - 24, 46, armed ? "TAP AGAIN TO RESET" : "GS RESET",
               armed && std::fmod(ImGui::GetTime(), 0.8) < 0.4)) {
        if (armed) {
            C.reset_armed = 0;
            call(a, "{\"call\":\"gs_reset\"}");
            C.msg = "GS reset sent";
            C.msg_until = ImGui::GetTime() + 4;
        } else
            C.reset_armed = ImGui::GetTime() + 3;
    }
}

}  // namespace nui
