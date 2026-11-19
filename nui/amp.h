// THE AMP CARD (Ben, 2026-11-19: "I want people to be able to see what we
// are physically modeling for them"): the selected part's amplifier and what
// it drives, as the voice is modelled -- its VALVE (tubeamp's triode stage:
// its drive, the voice's own or the knob's), its SPEAKER (the voice's own or
// one it offers: patch_map.CAB_CHOICES, each what it is and how we know it),
// and an organ's LESLIE (the half-moon's speed, how the rotors are heard).
// The web's AMP card's, the same calls: "amp" (the valve, the speed, a
// Leslie on), the parts push's "cabinet" and "rotary", drive_set,
// cabinet_set, part_cc 80, rotary_set.
#pragma once

#include "app.h"
#include "library.h"
#include "widgets.h"

namespace nui {

struct AmpUi {
    J st;                               // ("amp": kind, drive [now, voice, mine], speed, leslie, wheel)
    bool open = false;                  // (the engine told the card is up: it pushes "amp" as it changes)
    int for_row = -1;
};
static AmpUi g_amp;

// the engine's push: the part's amp as it moved (a wheel, a speed, a drive)
inline void amp_take(App &a, const J &st)
{
    if ((int)num(&st, "row", -1) == a.row)
        g_amp.st = st;
}
// ...the card up or down (nui.cpp: when another card is shown)
inline void amp_open(App &a, bool on)
{
    if (g_amp.open == on)
        return;
    g_amp.open = on;
    J r = call(a, std::string("{\"call\":\"amp\",\"row\":") + std::to_string(a.row) + ",\"open\":" + (on ? "1" : "0") + "}");
    if (const J *s = r.get("amp"))
        amp_take(a, *s);
}

inline void draw_amp(App &a)
{
    AmpUi &M = g_amp;
    const bool IP = a.tab;
    const float X0 = IP ? 20 : 34, X1 = IP ? 1113 : 1886, HY = IP ? 224 : 356, Y0 = IP ? 266 : 394, Y1 = card_y1(a);
    const float LH = a.lh(14) + (IP ? 3 : 4);
    amp_open(a, true);                  // (the engine pushes it as it moves: nui.cpp's poll, amp_take)
    if (M.for_row != a.row) {           // (another part: its amp asked at once)
        J r = call(a, "{\"call\":\"amp\",\"row\":" + std::to_string(a.row) + "}");
        if (const J *s = r.get("amp"))
            M.st = *s;
        M.for_row = a.row;
    }
    const float TX = heading(a, X0, HY, "AMP", "amp");
    const J *p = part(a, a.row);
    if (p)
        text(a, a.font, 14, TX, HY + 1, OWN, fit(a, a.font, 14, "part " + pad2(a.row + 1) + " \xc2\xb7 " + str(p, "name"), IP ? 600 : 900));
    const int kind = (int)num(&M.st, "kind", 0);
    if (!p || kind == 0 || flag(p, "drums")) {
        const std::string why = p && flag(p, "drums")
                                    ? "A drum set has no amplifier: its drums are heard as they are."
                                    : "This voice plays through no amplifier or speaker of its own -- an acoustic "
                                      "instrument is heard as it is. The Rhodes and Wurlitzer, the organs, the "
                                      "electric guitars and basses have one.";
        const auto ls = wrap(a, a.font, 21, why, X1 - X0);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 21, X0, Y0 + 10 + i * (a.lh(21) + 6), SILK_DIM, ls[i]);
        return;
    }
    const bool organ = kind == 1, les = flag(&M.st, "leslie");
    const float G = IP ? 8 : 14, W = X1 - X0;
    // (the Leslie's column an organ's alone: the speaker takes its width otherwise)
    const float VW = IP ? 300 : 460, LW = organ ? (IP ? 300 : 460) : 0, SW = W - VW - LW - (organ ? 2 : 1) * G;
    const float H = Y1 - Y0;

    // THE VALVE: tubeamp's triode, driven -- 0 clean, 1 the edge of breakup, past it the clip
    {
        const float x = X0, y = Y0;
        look::tray(a, x, y, VW, H, 10);
        heading(a, x + 14, y + 12, "VALVE", "drive");
        const J *dv = M.st.get("drive");
        const double now = dv && dv->is(J::ARR) && dv->a.size() >= 3 ? dv->a[0].d() : 0.0;
        const double voice = dv && dv->is(J::ARR) && dv->a.size() >= 3 ? dv->a[1].d() : 0.0;
        const double mine = dv && dv->is(J::ARR) && dv->a.size() >= 3 ? dv->a[2].d() : -1.0;
        // TWO KNOBS (Ben): the DRIVE set -- the voice's own or the knob's --
        // and what SOUNDS, the mod wheel's scale on it (display only); one
        // range for both, the wheel's whole reach: four times the voice's own,
        // at least 3
        const double wheel = num(&M.st, "wheel", 1.0);
        const double top = std::max(3.0, std::ceil(voice * 4.0));
        auto it = a.hold.find("drive");
        const bool held = it != a.hold.end() && ImGui::GetTime() < it->second.second;
        const double base = held ? (it->second.first < 0 ? voice : it->second.first) : (mine >= 0 ? mine : voice);
        const double sounds = held ? base * wheel : now;
        const bool own = held ? it->second.first >= 0 : mine >= 0;
        float v01 = (float)(base / top), s01 = (float)(sounds / top);
        char vt[16], st_[16];
        snprintf(vt, sizeof vt, "%.2f", base);
        snprintf(st_, sizeof st_, "%.2f", sounds);
        const float KS = IP ? 80 : 120, ky = y + (IP ? 110 : 150);
        const int f = knob(a, "ampdrive", x + VW * 0.28f, ky, KS, v01, "DRIVE", vt, false, {}, 0, own);
        knob(a, "ampsounds", x + VW * 0.72f, ky, KS, s01, "SOUNDING", st_, false, {}, 0, false);    // (display only)
        if (f & K_CHANGED) {
            const double d = std::round(v01 * top * 100) / 100;
            a.hold["drive"] = {d, ImGui::GetTime() + 0.6};
            call(a, "{\"call\":\"drive_set\",\"row\":" + std::to_string(a.row) + ",\"v\":" + jnum(d) + "}");
        }
        const auto back = [&] {
            a.hold["drive"] = {-1, ImGui::GetTime() + 0.6};
            call(a, "{\"call\":\"drive_set\",\"row\":" + std::to_string(a.row) + ",\"v\":-1}");
        };
        if (f & K_RESET)
            back();
        char bt[48];
        snprintf(bt, sizeof bt, own ? "BACK TO THE VOICE'S %.2f" : "AS THE VOICE (%.2f)", voice);
        const float by = ky + KS / 2 + (IP ? 44 : 58);
        if (button(a, "ampdriveback", x + 14, by, VW - 28, IP ? 44 : 40, bt, false, own))
            back();
        const std::string note = voice > 0.0 || now > 0.0
                                     ? "A triode stage before the speaker: clean at 0, the edge of breakup at 1, "
                                       "a clip past it. Its distortion is mostly the notes mixing -- a chord "
                                       "thickens where one note barely would."
                                     : "No valve of its own: turned up, it gains one -- a triode stage before "
                                       "the speaker, the edge of breakup at 1.";
        char wn[96];
        snprintf(wn, sizeof wn, " SOUNDING is the drive with the mod wheel's scale on it (now x%.2f).", wheel);
        const auto ls = wrap(a, a.font, 14, note + (organ ? " The mod wheel is the swell." : std::string(wn)), VW - 28);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, x + 14, by + (IP ? 56 : 54) + i * LH, SILK_DIM, ls[i]);
    }

    // THE SPEAKER: the voice's own, or one it offers -- each what it is, and how we know it
    {
        const float x = X0 + VW + G, y = Y0;
        look::tray(a, x, y, SW, H, 10);
        heading(a, x + 14, y + 12, "SPEAKER", "cabinet");
        LibUi &L = g_lib;
        if (!L.loaded)
            lib_load(a);
        const J *cabs = L.about.get("cabinets"), *owns = L.about.get("cab_own");
        auto label = [&](int c) -> std::string {
            return cabs && cabs->is(J::ARR) && c >= 0 && c < (int)cabs->a.size() && cabs->a[(size_t)c].is(J::ARR)
                       ? cabs->a[(size_t)c].a[0].s : "?";
        };
        auto about = [&](int c) -> std::string {
            return cabs && cabs->is(J::ARR) && c >= 0 && c < (int)cabs->a.size() && cabs->a[(size_t)c].is(J::ARR)
                       ? cabs->a[(size_t)c].a[1].s : "";
        };
        const J *cv = p->get("cabinet");
        std::vector<int> offer;
        int chosen = -1, now = 0;
        if (cv && cv->is(J::ARR) && cv->a.size() >= 3 && cv->a[2].is(J::ARR)) {
            chosen = (int)cv->a[0].d();
            now = (int)cv->a[1].d();
            for (const J &o : cv->a[2].a)
                offer.push_back((int)o.d());
        }
        auto ht = a.hold.find("cabinet");
        if (ht != a.hold.end() && ImGui::GetTime() < ht->second.second)
            now = (int)ht->second.first;
        else if (chosen > 0)
            now = chosen;
        int own = 0;
        if (owns) {
            const J *o = owns->get(std::to_string((int)num(p, "program")) + "." + std::to_string((int)num(p, "variation")));
            own = o ? (int)o->d() : 0;
        }
        std::vector<int> ring = {0};
        ring.insert(ring.end(), offer.begin(), offer.end());
        const int cols = IP ? 2 : 3;
        const float bg = IP ? 6 : 8, bw = (SW - 28 - bg * (cols - 1)) / cols, bh = IP ? 44 : 46;
        for (size_t i = 0; i < ring.size(); i++) {
            const int c = ring[i];
            const float bx = x + 14 + (i % cols) * (bw + bg), by = y + (IP ? 40 : 46) + (i / cols) * (bh + bg);
            const std::string id = "ampcab" + std::to_string(c);
            const std::string lb = c ? label(c) : "OWN \xc2\xb7 " + label(own);
            if (button(a, id.c_str(), bx, by, bw, bh, lb, c == now)) {
                a.hold["cabinet"] = {(double)c, ImGui::GetTime() + 0.8};
                call(a, "{\"call\":\"cabinet_set\",\"row\":" + std::to_string(a.row) + ",\"choice\":"
                            + std::to_string(c ? c : -1) + "}");
            }
        }
        const int rows = ((int)ring.size() + cols - 1) / cols;
        const float ay = y + (IP ? 40 : 46) + rows * (bh + bg) + (IP ? 12 : 18);
        const int shown = now ? now : own;
        text(a, a.bold, 14, x + 14, ay, SILK, now ? label(now) : "OWN \xc2\xb7 " + label(own));
        const auto ls = wrap(a, a.font, 14, about(shown), SW - 28);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, x + 14, ay + LH * (i + 1) + 4, SILK_DIM, ls[i]);
    }

    // THE LESLIE: the half-moon's speed (CC80), how the rotors are heard (the part's rotary)
    if (organ) {
        const float x = X1 - LW, y = Y0;
        look::tray(a, x, y, LW, H, 10);
        heading(a, x + 14, y + 12, "LESLIE", "rotary");
        if (!les) {
            const std::string why = "No Leslie on it now: choose LESLIE under SPEAKER for the horn and drum turning.";
            const auto ls = wrap(a, a.font, 14, why, LW - 28);
            for (size_t i = 0; i < ls.size(); i++)
                text(a, a.font, 14, x + 14, y + (IP ? 44 : 50) + i * LH, SILK_DIM, ls[i]);
            return;
        }
        // (the speed: STOP, SLOW, FAST -- the half-moon, CC80 on the part's channel)
        int speed = (int)num(&M.st, "speed", 1);
        auto hs = a.hold.find("speed");
        if (hs != a.hold.end() && ImGui::GetTime() < hs->second.second)
            speed = (int)hs->second.first;
        text(a, a.font, 14, x + 14, y + (IP ? 40 : 48), SILK_DIM, "SPEED");
        static const char *SN[3] = {"STOP", "SLOW", "FAST"};
        static const int SV[3] = {0, 64, 127};
        const float sb = (LW - 28 - 2 * 6) / 3, sy = y + (IP ? 60 : 70), bh = IP ? 44 : 44;
        for (int s = 0; s < 3; s++) {
            const std::string id = std::string("ampspeed") + SN[s];
            if (button(a, id.c_str(), x + 14 + s * (sb + 6), sy, sb, bh, SN[s], speed == s)) {
                a.hold["speed"] = {(double)s, ImGui::GetTime() + 0.8};
                call(a, "{\"call\":\"part_cc\",\"row\":" + std::to_string(a.row) + ",\"cc\":80,\"v\":" + std::to_string(SV[s]) + "}");
            }
        }
        const auto sn = wrap(a, a.font, 14, "The rotors spin up and down between speeds as a real Leslie's do; "
                                            "a flick of the pitch wheel steps them too.", LW - 28);
        for (size_t i = 0; i < sn.size(); i++)
            text(a, a.font, 14, x + 14, sy + bh + 8 + i * LH, SILK_DIM, sn[i]);
        // (how it is heard: the cabinet in the room, or two mics round it)
        const float ry = sy + bh + 16 + sn.size() * LH + (IP ? 10 : 20);
        text(a, a.font, 14, x + 14, ry, SILK_DIM, "HEARD");
        const J *rv = p->get("rotary");
        int mode = rv && rv->is(J::ARR) && rv->a.size() >= 2 ? (int)rv->a[0].d() : -1;
        double spread = rv && rv->is(J::ARR) && rv->a.size() >= 2 ? rv->a[1].d() : -1.0;
        auto rt = a.hold.find("rotary");
        if (rt != a.hold.end() && ImGui::GetTime() < rt->second.second) {
            mode = (int)std::floor(rt->second.first / 1000.0);
            spread = std::fmod(rt->second.first, 1000.0) - 1.0;
        }
        const bool mics = mode == 1;
        const double sp = spread >= 0.0 ? spread : 96.0 * 180.0 / 127.0;
        auto set = [&](int m, double sd) {
            a.hold["rotary"] = {m * 1000.0 + (sd < 0 ? 0.0 : sd + 1.0), ImGui::GetTime() + 0.6};
            call(a, "{\"call\":\"rotary_set\",\"row\":" + std::to_string(a.row) + ",\"mode\":" + std::to_string(m)
                        + ",\"spread\":" + jnum(sd) + "}");
        };
        const float hb = (LW - 28 - 8) / 2, hy = ry + (IP ? 20 : 24);
        if (button(a, "amproom", x + 14, hy, hb, bh, "IN THE ROOM", !mics))
            set(0, spread);
        if (button(a, "ampmics", x + 22 + hb, hy, hb, bh, "TWO MICS", mics))
            set(1, spread);
        if (mics) {
            float v01 = (float)(sp / 180.0);
            char vt[16];
            snprintf(vt, sizeof vt, "%.0f\xc2\xb0", sp);
            const int f = knob(a, "ampspread", x + LW / 2, hy + bh + (IP ? 50 : 70), IP ? 60 : 80, v01, "SPREAD", vt, false,
                               {}, 0, spread >= 0.0);
            if (f & K_CHANGED)
                set(1, std::round(v01 * 180.0));
            if (f & K_RESET)
                set(1, -1.0);
        } else {
            const auto rn = wrap(a, a.font, 14, "The cabinet heard where it stands: its horn and drum turning toward you and away.",
                                 LW - 28);
            for (size_t i = 0; i < rn.size(); i++)
                text(a, a.font, 14, x + 14, hy + bh + 12 + i * LH, SILK_DIM, rn[i]);
        }
    }
}

}  // namespace nui
