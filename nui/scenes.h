// THE SCENES CARD (the retired web interface's): the presets (the whole setup) and the
// scenes (each channel's controls), kept beside the session and shared with
// live.py and the apps: a tap chooses one, LOAD or RECALL brings it, SAVE
// OVER keeps the present one in it, DELETE takes it out; a new one named on
// the screen's own keys. (The metronome and the GS reset, drawn here, sit on the Control card.)
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
    const float ih = a.tab ? 50 : 58, oh = a.tab ? 52 : 50, ab = a.tab ? 44 : 38;   // (an item; its actions' row; their height)
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
        look::latch(a, x, iy, w - 8, th, on);
        text(a, a.font, 21, x + 12, iy + (a.tab ? 7 : 8), LCD, fit(a, a.font, 21, nm, w - 32));
        text(a, a.font, 14, x + 12, iy + (a.tab ? 13 : 16) + a.lh(21), SILK_DIM, fit(a, a.font, 14, say(it), w - 32));
        if (on) {
            const float na = (float)std::max<size_t>(1, acts.size()), bw = (w - 8 - 24 - (na - 1) * 8) / na;
            for (size_t k = 0; k < acts.size(); k++) {
                const float bx = x + 12 + k * (bw + 8), by = iy + ih;
                const float bs = a.tab ? 21 : 14;
                look::key_cap(a, bx, by, bw, ab, false, true);
                text_c(a, a.bold, bs, bx + bw / 2, by + (ab - a.lh(bs)) / 2, SILK, acts[k].first);
                if (tapped && tap.x >= bx - x && tap.x < bx - x + bw && tap.y >= ys[(size_t)i] + ih && tap.y < ys[(size_t)i] + ih + ab) {
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
    const bool IP = a.tab;              // (the iPad's: its card from y 210 to card_y1 + 6)
    const float X0 = IP ? 20 : 34, X1 = IP ? (a.ph ? 818 : 1113) : 1886, Y0 = IP ? 260 : 394, Y1 = card_y1(a), HY = IP ? 224 : 356;
    const float LH = a.lh(14) + (IP ? 3 : 4);
    heading(a, X0, HY, "SCENES", "scenes");
    if (!C.s.is(J::OBJ))
        return;
    if (ImGui::GetTime() > C.msg_until)
        C.msg.clear();
    const std::string info = !C.msg.empty() ? C.msg : flag(&C.s, "kept") ? "" : "No session file: presets and scenes cannot be kept.";
    text(a, a.font, 14, X1 - text_w(a, a.font, 14, info), HY + 1, C.msg.empty() ? SILK_DIM : OWN, info);
    if (!C.msg.empty())
        a.animate = true;

    // A NAME, typed on the screen's own keys (or a keyboard's)
    if (!C.naming.empty()) {
        const float W = IP ? (a.ph ? 700 : 760) : 900, x = ((IP ? (a.ph ? 832 : 1133) : 1920) - W) / 2;
        look::module(a, x - 20, Y0, W + 40, Y1 - Y0, 10);
        const float NY = Y0 + (IP ? 30 : 44), NH = IP ? 48 : 56;
        text(a, a.bold, 14, x, Y0 + (IP ? 10 : 16), SILK, C.naming == "preset_save" ? "SAVE THIS SETUP AS" : "SAVE THE CONTROLS AS");
        look::lcd_window(a, x, NY, W, NH, true);
        look::lcd_text(a, 28, x + 14, NY + (NH - a.lh(28)) / 2, LCD, C.name + "_");
        look::glass(a, x, NY, W, NH);
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
        save = osk(a, C.name, x, NY + NH + (IP ? 20 : 30), W, true, "SAVE") || save;
        if (button(a, "nmcancel", x, Y1 - (IP ? 50 : 64), 200, IP ? 44 : 46, "CANCEL", false, true, IP ? 21 : 14)) {
            C.naming.clear();
            return;
        }
        std::string nm = C.name;
        while (!nm.empty() && nm.back() == ' ')
            nm.pop_back();
        while (!nm.empty() && nm[0] == ' ')
            nm.erase(0, 1);
        if (button(a, "nmsave", x + W - 200, Y1 - (IP ? 50 : 64), 200, IP ? 44 : 46, "SAVE", !nm.empty(), !nm.empty(), IP ? 21 : 14) ||
            (save && !nm.empty())) {
            const std::string c = C.naming;
            C.naming.clear();
            sc_do(a, c, nm);
        }
        return;
    }

    // THE PRESETS: the whole setup
    const float gap = IP ? 6 : 10, PW = (X1 - X0 - gap) / 2, SW = X1 - X0 - gap - PW, SX = X0 + PW + gap;
    look::tray(a, X0, Y0, PW, Y1 - Y0, 9);
    text(a, a.font, 14, heading(a, X0 + 12, Y0 + 10, "PRESETS", "sc:presets"), Y0 + 11, LCD,
         "the whole setup: parts, routes, tuning, effects");
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
    sc_list(a, "scp", X0 + 12, Y0 + 40, PW - 24, Y1 - Y0 - (IP ? 104 : 110), C.s.get("presets"), C.sel_preset, C.scroll_p, parts_say,
            {{"LOAD", "preset_load"}, {"SAVE OVER", "preset_save"}, {"DELETE", "preset_delete"}, {"AS MIDI", "preset_midi"}});
    if (button(a, "presetsave", X0 + 12, Y1 - (IP ? 54 : 58), IP ? PW - 24 : 300, 44, "SAVE THIS SETUP AS\xe2\x80\xa6", false, true, IP ? 21 : 14)) {
        C.naming = "preset_save";
        C.name.clear();
    }

    // THE SCENES: each channel's controls
    look::tray(a, SX, Y0, SW, Y1 - Y0, 9);
    text(a, a.font, 14, heading(a, SX + 12, Y0 + 10, "SCENES", "sc:scenes"), Y0 + 11, LCD, "each channel's levels, pans and sends");
    sc_list(a, "scs", SX + 12, Y0 + 40, SW - 24, Y1 - Y0 - (IP ? 104 : 110), C.s.get("scenes"), C.sel_scene, C.scroll_s,
            [](const J &c) {
                const int n = (int)num(&c, "n");
                return std::to_string(n) + " setting" + (n == 1 ? "" : "s");
            },
            {{"RECALL", "scene_recall"}, {"SAVE OVER", "scene_save"}, {"DELETE", "scene_delete"}});
    if (button(a, "scenesave", SX + 12, Y1 - (IP ? 54 : 58), IP ? SW - 24 : 320, 44, IP ? "SAVE THE CONTROLS\xe2\x80\xa6" : "SAVE THE CONTROLS AS\xe2\x80\xa6",
               false, true, IP ? 21 : 14)) {
        C.naming = "scene_save";
        C.name.clear();
    }
}

// THE METRONOME AND THE GS RESET (on the Control card: things you play
// with), in the box MX..MX+MW, Y0..Y1: the metronome on the left, the reset beside it
inline void draw_metro_gs(App &a, float MX, float Y0, float MW, float Y1)
{
    ScenesUi &C = g_sc;
    const bool IP = a.tab;
    const float LH = a.lh(14) + (IP ? 3 : 4);
    if (!C.s.is(J::OBJ))
        sc_take(call(a, "{\"call\":\"scenes\",\"open\":1}"));
    // THE METRONOME: the globals 10 (bpm, 0 off), 11 (its bell every n beats), 12 (its level)
    look::tray(a, MX, Y0, MW, Y1 - Y0, 9);
    const float half = (MW - 24) / 2;
    heading(a, MX + 12, Y0 + 10, "METRONOME", "sc:metro");
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
        const float cw = half / 4, ky = Y0 + (IP ? 80 : 90);
        const bool on = bpm > 0;
        look::switch_(a, MX + 12 + cw / 2, ky, on);
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
    // THE GS RESET: a second tap within 3 s sends it (beside the metronome)
    const float GX = MX + 12 + half + 12, GW = half - 12;
    float gy = Y0 + 10;
    rect(a, GX - 12, Y0 + 10, 1, Y1 - Y0 - 20, IM_COL32(0x33, 0x36, 0x3a, 255), 0);
    heading(a, GX, gy, "GS RESET", "sc:gs");
    gy += IP ? 22 : 24;
    for (const auto &l : wrap(a, a.font, 14, "Every part back to program 000, the controllers, effects and receive settings to power-on, as a sequencer's GS Reset.", GW)) {
        text(a, a.font, 14, GX, gy, SILK_DIM, l);
        gy += LH;
    }
    const bool armed = ImGui::GetTime() < C.reset_armed;
    if (armed)
        a.animate = true;
    if (button(a, "gsreset", GX, gy + 10, GW, IP ? 44 : 46, armed ? "TAP AGAIN TO RESET" : "GS RESET",
               armed && std::fmod(ImGui::GetTime(), 0.8) < 0.4, true, IP ? 21 : 14)) {
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
