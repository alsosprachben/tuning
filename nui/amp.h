// THE AMP CARD (Ben, 2026-11-19: "I want people to be able to see what we
// are physically modeling for them"): the selected part's amplifier and what
// it drives, as the voice is modelled -- its VALVE (tubeamp's triode stage:
// its drive, the voice's own or the knob's), its SPEAKER (the voice's own or
// one it offers: patch_map.CAB_CHOICES, each what it is and how we know it),
// and an organ's LESLIE (the half-moon's speed, how the rotors are heard).
// The web's AMP card's, the same calls: "amp" (the valve, the speed, a
// Leslie on), the parts push's "cabinet", "pickup" and "rotary", drive_set,
// cabinet_set, pickup_set, part_cc 80, rotary_set.
//
// ...and ahead of the valve, a guitar's, a bass's or a Clavinet's PICKUP
// (patch_map.PICKUP_FAMILIES): its switch drawn as the instrument's own --
// a 5-way blade (the Stratocaster's, the Ibanez's), a Jazz Bass's two volume
// knobs, the D6's two rockers (Ben:
// "switch gadgets, like the knobs, more familiar to guitar players") --
// over the string, its coils where they sit, the ones heard lit.
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

// THE PICKUP SWITCH, drawn as its instrument's (the family's "switch"):
// "blade5" a 5-way blade in its slot, "knobs2" a Jazz Bass's two volume
// knobs, "toggle3" a 3-way toggle (no family's now; kept) in
// its ring, "rockers" the Clavinet D6's two rocker tabs (A/B, C/D). pos the
// choices in the switch's order, labels theirs, now the one it is on.
// Returns the choice tapped, -1 none
inline int pk_switch(App &a, const std::string &kind, float x, float y, float w, float h, const std::vector<int> &pos,
                     const std::vector<std::string> &labels, int now)
{
    ImDrawList *d = dl();
    const float k = a.k;
    auto Q = [&](float xx, float yy) { return P(a, xx, yy); };
    const ImU32 CHROME = IM_COL32(0xb9, 0xbe, 0xc2, 255), CHROME_D = IM_COL32(0x6e, 0x74, 0x7a, 255),
                SLOT = IM_COL32(0x0c, 0x0d, 0x0f, 255), TIP = IM_COL32(0xee, 0xea, 0xdc, 255),
                TIP_D = IM_COL32(0xa9, 0xa3, 0x8f, 255);
    int hit = -1;
    auto zone = [&](const char *id, int i, float zx, float zy, float zw, float zh) {
        ImGui::SetCursorScreenPos(Q(zx, zy));
        ImGui::PushID(id);
        ImGui::PushID(i);
        if (ImGui::InvisibleButton("z", ImVec2(std::max(1.0f, zw * k), std::max(1.0f, zh * k))))
            hit = pos[(size_t)i];
        ImGui::PopID();
        ImGui::PopID();
    };
    const int n = (int)pos.size();
    int at = 0;
    for (int i = 0; i < n; i++)
        if (pos[(size_t)i] == now)
            at = i;
    if (kind == "blade5" || n > 3 && kind != "rockers") {
        // THE BLADE: a chrome plate, the slot along it, a detent a position,
        // the white tip where it rests (the neck's end to the left)
        const float py = y + 6, ph = std::min(64.0f, h * 0.45f), sx0 = x + 26, sx1 = x + w - 26;
        d->AddRectFilled(Q(x, py), Q(x + w, py + ph), CHROME_D, ph * 0.5f * k);
        d->AddRectFilled(Q(x + 2, py + 2), Q(x + w - 2, py + ph - 2), CHROME, ph * 0.5f * k);
        d->AddRectFilled(Q(sx0 - 6, py + ph / 2 - 5), Q(sx1 + 6, py + ph / 2 + 5), SLOT, 5 * k);
        for (int i = 0; i < n; i++) {
            const float dx = n > 1 ? sx0 + (sx1 - sx0) * i / (n - 1) : (sx0 + sx1) / 2;
            d->AddLine(Q(dx, py + 6), Q(dx, py + 12), CHROME_D, 2 * k);
            d->AddLine(Q(dx, py + ph - 12), Q(dx, py + ph - 6), CHROME_D, 2 * k);
            label_c(a, a.bold, 14, dx, py + ph + 10, i == at ? LCD : SILK_DIM, labels[(size_t)i], (sx1 - sx0) / std::max(1, n - 1));
            zone("blade", i, dx - (sx1 - sx0) / std::max(2, 2 * (n - 1)), py - 4, (sx1 - sx0) / std::max(1, n - 1),
                 ph + 50);
        }
        const float tx = n > 1 ? sx0 + (sx1 - sx0) * at / (n - 1) : (sx0 + sx1) / 2, tw = 30, th = ph + 18;
        d->AddRectFilled(Q(tx - tw / 2 + 2, py - 9 + 3), Q(tx + tw / 2 + 2, py - 9 + th + 3), IM_COL32(0, 0, 0, 90), 9 * k);
        d->AddRectFilled(Q(tx - tw / 2, py - 9), Q(tx + tw / 2, py - 9 + th), TIP_D, 9 * k);
        d->AddRectFilled(Q(tx - tw / 2 + 2, py - 7), Q(tx + tw / 2 - 2, py - 9 + th - 4), TIP, 8 * k);
        for (int g = 0; g < 4; g++)                 // (its grip's ridges)
            d->AddLine(Q(tx - tw / 2 + 6, py + 2 + g * (th - 22) / 3), Q(tx + tw / 2 - 6, py + 2 + g * (th - 22) / 3),
                       TIP_D, 1.5f * k);
    } else if (kind == "rockers") {
        // THE D6's ROCKERS: A/B and C/D, each tab down on one half -- A C the
        // centre pickup, B C the bridge, B D both in phase, A D both against
        // each other (the DAFx-12 paper's Table 1)
        static const int AB[8] = {0, 0, 0, 0, 0, 1, 1, 0}, CD[8] = {0, 0, 0, 0, 0, 0, 1, 1};
        const int ab = AB[now & 7], cd = CD[now & 7];
        const float tw = std::min(110.0f, (w - 30) / 2), th = std::min(120.0f, h - 30), gx = x + (w - 2 * tw - 30) / 2;
        static const char *NM[2][2] = {{"A", "B"}, {"C", "D"}};
        for (int r = 0; r < 2; r++) {
            const float rx = gx + r * (tw + 30), ry = y + 4;
            const int down = r ? cd : ab;
            d->AddRectFilled(Q(rx - 4, ry - 4), Q(rx + tw + 4, ry + th + 4), SLOT, 8 * k);
            for (int half = 0; half < 2; half++) {
                const float hy = ry + half * th / 2;
                const bool pressed = half == down;
                const ImU32 top = pressed ? IM_COL32(0x1e, 0x20, 0x23, 255) : IM_COL32(0x3c, 0x40, 0x45, 255);
                d->AddRectFilled(Q(rx, hy), Q(rx + tw, hy + th / 2 - 2), top, 6 * k);
                if (!pressed)
                    d->AddRectFilled(Q(rx + 3, hy + 3), Q(rx + tw - 3, hy + 9), IM_COL32(0x58, 0x5d, 0x63, 255), 4 * k);
                text_c(a, a.bold, 21, rx + tw / 2, hy + th / 4 - a.lh(21) / 2 - 1, pressed ? LCD : SILK, NM[r][half]);
                // (a tap on a half: that rocker down there, the other as it is)
                const int nab = r ? ab : half, ncd = r ? half : cd;
                const int c = nab ? (ncd ? 6 : 5) : (ncd ? 7 : 1);
                ImGui::SetCursorScreenPos(Q(rx, hy));
                ImGui::PushID("rock");
                ImGui::PushID(r * 2 + half);
                if (ImGui::InvisibleButton("z", ImVec2(tw * k, th / 2 * k)))
                    hit = c;
                ImGui::PopID();
                ImGui::PopID();
            }
        }
        for (int i = 0; i < n; i++)
            if (pos[(size_t)i] == now)
                text_c(a, a.bold, 14, x + w / 2, y + th + 18, LCD, labels[(size_t)i]);
    } else if (kind == "knobs2") {
        // A JAZZ BASS's TWO VOLUME KNOBS, neck and bridge, each fully up (10)
        // or off: a tap turns one up or off -- one always up
        const bool nk = now == 1 || now == 6 || now == 0, bk = now == 5 || now == 6 || now == 0;
        const float R = std::min(46.0f, h * 0.3f), cy = y + R + 14;
        for (int s = 0; s < 2; s++) {
            const bool up = s ? bk : nk;
            const float cx = x + w * (s ? 0.7f : 0.3f);
            const float A0 = -135, A1 = 135, deg = 3.14159265f / 180.0f;
            auto pt = [&](float rr, float dg) {
                const float tt = (dg - 90) * deg;
                return Q(cx + rr * std::cos(tt), cy + rr * std::sin(tt));
            };
            d->PathClear();
            for (int i = 0; i <= 40; i++)
                d->PathLineTo(pt(R * 0.92f, A0 + (A1 - A0) * i / 40));
            d->PathStroke(IM_COL32(0x15, 0x17, 0x1a, 255), 0, 4.0f * k);
            if (up) {
                for (int i = 0; i <= 40; i++)
                    d->PathLineTo(pt(R * 0.92f, A0 + (A1 - A0) * i / 40));
                d->PathStroke(LCD, 0, 4.0f * k);
            }
            for (int n = 0; n <= 10; n++)       // (its numbers' ticks, 0 to 10)
                d->AddLine(pt(R * 1.02f, A0 + (A1 - A0) * n / 10), pt(R * 1.1f, A0 + (A1 - A0) * n / 10), SILK_DIM, 1.2f * k);
            look::knob_cap(a, cx, cy, R * 0.68f, up ? A1 : A0);
            text_c(a, a.bold, 14, cx, cy + R + 12, up ? LCD : SILK_DIM, s ? "BRIDGE" : "NECK");
            text_c(a, a.font, 14, cx, cy + R + 12 + a.lh(14) + 2, up ? LCD : SILK_DIM, up ? "10" : "0");
            const bool n2 = s ? nk : !nk, b2 = s ? !bk : bk;    // (this knob turned over, the other as it is)
            const int c = n2 && b2 ? 6 : n2 ? 1 : b2 ? 5 : (s ? 1 : 5);
            ImGui::SetCursorScreenPos(Q(cx - R - 10, cy - R - 10));
            ImGui::PushID("jbk");
            ImGui::PushID(s);
            if (ImGui::InvisibleButton("z", ImVec2((2 * R + 20) * k, (2 * R + 50) * k)))
                hit = c;
            ImGui::PopID();
            ImGui::PopID();
        }
    } else {
        // THE TOGGLE: its ring, the lever tilted to the neck (up), straight
        // out (both) or to the bridge (down), its cream tip; the positions named beside
        const float cx = x + std::min(90.0f, w * 0.3f), cy = y + h * 0.45f, R = std::min(40.0f, h * 0.3f);
        // (the ring nut, and the lever out of it: tilted up to the neck, down
        // to the bridge -- straight out at BOTH, seen end on, its tip alone)
        d->AddCircleFilled(Q(cx, cy), R * 0.62f * k, CHROME_D, 32);
        d->AddCircleFilled(Q(cx, cy), R * 0.55f * k, CHROME, 32);
        d->AddCircleFilled(Q(cx, cy), R * 0.22f * k, IM_COL32(0x2b, 0x2e, 0x32, 255), 20);
        const float ang[3] = {-1.0f, 0.0f, 1.0f};
        const float tilt = ang[std::min(at, 2)];
        const float ex = cx + std::fabs(tilt) * R * 0.45f, ey = cy + tilt * R * 1.5f;
        if (tilt != 0.0f) {
            d->AddLine(Q(cx, cy), Q(ex, ey), CHROME_D, 11 * k);
            d->AddLine(Q(cx, cy), Q(ex, ey), CHROME, 7 * k);
        }
        d->AddCircleFilled(Q(ex, ey), 14 * k, TIP_D, 24);
        d->AddCircleFilled(Q(ex - 1, ey - 1), 12 * k, TIP, 24);
        for (int i = 0; i < n && i < 3; i++) {
            const float ly = cy + ang[i] * R * 1.5f - a.lh(14) / 2;
            text(a, a.bold, 14, cx + R + 46, ly, i == at ? LCD : SILK_DIM, labels[(size_t)i]);
            zone("tog", i, x, cy + ang[i] * R * 1.5f - R * 0.75f, w, R * 1.5f);
        }
    }
    return hit;
}

// THE STRING UNDER THE COILS: the last stretch before the bridge (at the
// right), each of the family's coils where it sits, the ones heard lit
inline void pk_string(App &a, float x, float y, float w, const std::vector<double> &all, const std::vector<double> &lit)
{
    if (all.empty())
        return;
    ImDrawList *d = dl();
    const float k = a.k;
    double qmax = 0;
    for (double q : all)
        qmax = std::max(qmax, q);
    qmax *= 1.18;
    const float bx = x + w - 10;
    auto X = [&](double q) { return bx - (float)(q / qmax) * (w - 20); };
    d->AddRectFilled(P(a, bx - 4, y - 14), P(a, bx + 6, y + 14), IM_COL32(0x9a, 0x9f, 0xa3, 255), 2 * k);
    d->AddLine(P(a, x, y), P(a, bx, y), IM_COL32(0xc8, 0xc8, 0xc0, 255), 2 * k);
    for (double q : all) {
        bool on = false;
        for (double l : lit)
            on = on || std::fabs(l - q) < 1e-6;
        const float cx = X(q);
        d->AddRectFilled(P(a, cx - 7, y - 11), P(a, cx + 7, y + 11), on ? LCD : IM_COL32(0x2e, 0x31, 0x35, 255), 3 * k);
        d->AddRect(P(a, cx - 7, y - 11), P(a, cx + 7, y + 11), on ? LCD : SILK_DIM, 3 * k, 0, 1.2f * k);
    }
    text(a, a.font, 14, x, y + 18, SILK_DIM, "\xe2\x86\x90 neck");
    const std::string br = "bridge";
    text(a, a.font, 14, bx - text_w(a, a.font, 14, br) + 6, y + 18, SILK_DIM, br);
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
    // (its pickup: [chosen (-1 none), now (0 its own), [the choices offered]] -- the parts push's)
    std::vector<int> pk_offer;
    int pk_chosen = -1, pk_now = 0;
    if (p) {
        const J *pv = p->get("pickup");
        if (pv && pv->is(J::ARR) && pv->a.size() >= 3 && pv->a[2].is(J::ARR)) {
            pk_chosen = (int)pv->a[0].d();
            pk_now = (int)pv->a[1].d();
            for (const J &o : pv->a[2].a)
                pk_offer.push_back((int)o.d());
        }
    }
    const bool has_pk = p && !flag(p, "drums") && !pk_offer.empty();
    if (!p || (kind == 0 && !has_pk) || flag(p, "drums")) {
        const std::string why = p && flag(p, "drums")
                                    ? "A drum set has no amplifier: its drums are heard as they are."
                                    : "This voice plays through no amplifier or speaker of its own -- an acoustic "
                                      "instrument is heard as it is. The electric pianos, the organs, the "
                                      "electric guitars and basses have one.";
        const auto ls = wrap(a, a.font, 21, why, X1 - X0);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 21, X0, Y0 + 10 + i * (a.lh(21) + 6), SILK_DIM, ls[i]);
        return;
    }
    const bool organ = kind == 1, les = flag(&M.st, "leslie");
    const float G = IP ? 8 : 14, W = X1 - X0;
    // (the Leslie's column an organ's alone: the speaker takes its width otherwise)
    const float PW = has_pk ? (kind == 0 ? W : (IP ? 330 : 520)) : 0;
    const float VW = kind == 0 ? 0 : IP ? 300 : 460, LW = organ ? (IP ? 300 : 460) : 0;
    const float SW = kind == 0 ? 0 : W - PW - VW - LW - (organ ? 2 : 1) * G - (has_pk ? G : 0);
    const float H = Y1 - Y0;

    // THE PICKUP: the switch as the instrument has it, the string under its coils, what it is
    if (has_pk) {
        const float x = X0, y = Y0;
        look::tray(a, x, y, PW, H, 10);
        heading(a, x + 14, y + 12, "PICKUP", "pickup");
        LibUi &L = g_lib;
        if (!L.loaded)
            lib_load(a);
        const J *fams = L.about.get("pickups"), *owns = L.about.get("pk_own");
        std::string fam;
        int own = 0;
        if (owns) {
            const J *o = owns->get(std::to_string((int)num(p, "program")) + "." + std::to_string((int)num(p, "variation")));
            if (o && o->is(J::ARR) && o->a.size() >= 2) {
                fam = o->a[0].s;
                own = (int)o->a[1].d();
            }
        }
        const J *F = fams && !fam.empty() ? fams->get(fam) : nullptr;
        const J *chs = F ? F->get("choices") : nullptr;
        auto ch = [&](int c) -> const J * { return chs ? chs->get(std::to_string(c)) : nullptr; };
        auto lab = [&](int c) -> std::string {
            const J *e = ch(c);
            return e && e->is(J::ARR) && !e->a.empty() ? e->a[0].s : "?";
        };
        auto pts = [&](int c) {
            std::vector<double> v;
            const J *e = ch(c);
            if (e && e->is(J::ARR) && e->a.size() >= 3 && e->a[2].is(J::ARR))
                for (const J &q : e->a[2].a)
                    v.push_back(q.d());
            return v;
        };
        int now = pk_now;
        auto ht = a.hold.find("pickup");
        if (ht != a.hold.end() && ImGui::GetTime() < ht->second.second)
            now = (int)ht->second.first;
        else if (pk_chosen > 0)
            now = pk_chosen;
        const int lit = now ? now : own;
        // (the switch's order: the family's own, neck to bridge)
        std::vector<int> order;
        const J *ord = F ? F->get("order") : nullptr;
        if (ord && ord->is(J::ARR))
            for (const J &o : ord->a)
                if (std::find(pk_offer.begin(), pk_offer.end(), (int)o.d()) != pk_offer.end())
                    order.push_back((int)o.d());
        if (order.empty())
            order = pk_offer;
        std::vector<std::string> labels;
        for (int c : order)
            labels.push_back(lab(c));
        if (F)
            text(a, a.bold, 14, x + 14, y + (IP ? 40 : 48), SILK, str(F, "name"));
        const float sy = y + (IP ? 70 : 84), sh = IP ? 130 : 170;
        a.lab_x0 = x + 8;               // (the end positions' names kept inside the panel)
        a.lab_x1 = x + PW - 8;
        const int c = pk_switch(a, F ? str(F, "switch") : "blade5", x + 20, sy, PW - 40, sh, order, labels, lit);
        a.lab_x0 = a.lab_x1 = 0;
        if (c > 0) {
            a.hold["pickup"] = {(double)c, ImGui::GetTime() + 0.8};
            call(a, "{\"call\":\"pickup_set\",\"row\":" + std::to_string(a.row) + ",\"choice\":"
                        + std::to_string(c == own && pk_chosen < 0 ? -1 : c) + "}");
        }
        float ty = sy + sh + (IP ? 14 : 24);
        std::vector<double> all;
        for (int o : order)
            for (double q : pts(o))
                if (std::find_if(all.begin(), all.end(), [&](double z) { return std::fabs(z - q) < 1e-6; }) == all.end())
                    all.push_back(q);
        if (!all.empty()) {
            pk_string(a, x + 20, ty + 14, PW - 40, all, pts(lit));
            ty += IP ? 50 : 60;
        }
        const bool mine = pk_chosen > 0 && pk_chosen != own;
        if (button(a, "amppkown", x + 14, ty, PW - 28, IP ? 40 : 40,
                   mine ? "BACK TO THE PATCH'S " + lab(own) : "AS THE PATCH \xc2\xb7 " + lab(own), false, mine)) {
            a.hold["pickup"] = {(double)own, ImGui::GetTime() + 0.8};
            call(a, "{\"call\":\"pickup_set\",\"row\":" + std::to_string(a.row) + ",\"choice\":-1}");
        }
        ty += IP ? 52 : 56;
        const J *e = ch(lit);
        std::string ab = e && e->is(J::ARR) && e->a.size() >= 2 ? e->a[1].s : "";
        if (kind == 0)
            ab += " No amplifier of its own: it is heard straight from its pickups.";
        const auto ls = wrap(a, a.font, 14, ab, PW - 28);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, x + 14, ty + i * LH, SILK_DIM, ls[i]);
    }
    if (kind == 0)
        return;

    // THE VALVE: tubeamp's triode, driven -- 0 clean, 1 the edge of breakup, past it the clip
    {
        const float x = X0 + (has_pk ? PW + G : 0), y = Y0;
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
        knob(a, "ampsounds", x + VW * 0.72f, ky, KS, s01, "WITH THE WHEEL", st_, false, {}, 0, false);    // (display only)
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
        snprintf(bt, sizeof bt, own ? "BACK TO THE PATCH'S %.2f" : "AS THE PATCH (%.2f)", voice);
        const float by = ky + KS / 2 + (IP ? 44 : 58);
        if (button(a, "ampdriveback", x + 14, by, VW - 28, IP ? 44 : 40, bt, false, own))
            back();
        const std::string note = voice > 0.0 || now > 0.0
                                     ? "A triode stage before the speaker: clean at 0, the edge of breakup at 1, "
                                       "a clip past it. Its distortion is mostly the notes mixing: a chord "
                                       "thickens where one note barely would."
                                     : "No valve of its own: turned up, it gains one, a triode stage before "
                                       "the speaker, the edge of breakup at 1.";
        char wn[96];
        snprintf(wn, sizeof wn, " WITH THE WHEEL is the drive as the mod wheel scales it (now x%.2f).", wheel);
        const auto ls = wrap(a, a.font, 14, note + (organ ? " The mod wheel is the swell." : std::string(wn)), VW - 28);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, x + 14, by + (IP ? 56 : 54) + i * LH, SILK_DIM, ls[i]);
    }

    // THE SPEAKER: the voice's own, or one it offers -- each what it is, and how we know it
    {
        const float x = X0 + (has_pk ? PW + G : 0) + VW + G, y = Y0;
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
        // (the patch's own first, named; the same speaker not offered again beside it)
        std::vector<int> ring = {0};
        for (int c : offer)
            if (c != own)
                ring.push_back(c);
        const int cols = IP ? 2 : 3;
        const float bg = IP ? 6 : 8, bw = (SW - 28 - bg * (cols - 1)) / cols, bh = IP ? 44 : 46;
        for (size_t i = 0; i < ring.size(); i++) {
            const int c = ring[i];
            const float bx = x + 14 + (i % cols) * (bw + bg), by = y + (IP ? 40 : 46) + (i / cols) * (bh + bg);
            const std::string id = "ampcab" + std::to_string(c);
            const std::string lb = c ? label(c) : "PATCH'S OWN \xc2\xb7 " + label(own);
            if (button(a, id.c_str(), bx, by, bw, bh, lb, c == now)) {
                a.hold["cabinet"] = {(double)c, ImGui::GetTime() + 0.8};
                call(a, "{\"call\":\"cabinet_set\",\"row\":" + std::to_string(a.row) + ",\"choice\":"
                            + std::to_string(c ? c : -1) + "}");
            }
        }
        const int rows = ((int)ring.size() + cols - 1) / cols;
        const float ay = y + (IP ? 40 : 46) + rows * (bh + bg) + (IP ? 12 : 18);
        const int shown = now ? now : own;
        text(a, a.bold, 14, x + 14, ay, SILK, now ? label(now) : "PATCH'S OWN \xc2\xb7 " + label(own));
        const auto ls = wrap(a, a.font, 14, about(shown), SW - 28);
        for (size_t i = 0; i < ls.size(); i++)
            text(a, a.font, 14, x + 14, ay + LH * (i + 1) + 4, SILK_DIM, ls[i]);
    }

    // THE LESLIE: the half-moon's speed (CC80), how the rotors are heard (the part's rotary)
    // -- or a 60's organ's SPECTRA-TONE (patch_map.SPECTRA_CHOICES 10, 11 under
    // SPEAKER): its rocker, Cathedral and Theater (CC80 0, 127), as the web's
    bool offers_st = false;
    if (const J *cv = p ? p->get("cabinet") : nullptr)
        if (cv->is(J::ARR) && cv->a.size() >= 3 && cv->a[2].is(J::ARR))
            for (const J &o : cv->a[2].a)
                offers_st = offers_st || (int)o.d() == 10 || (int)o.d() == 11;
    // (a divider organ's COUPLER SWITCHES -- tonelib.COUPLER_CC's bits: 1 8' Off,
    // 2 16', 4 4', 8 2' -- along the column's foot, the manual's own: the web's)
    auto couplers = [&](float x, float y) {
        const int offer = (int)num(&M.st, "coupler_offer", 0), cur0 = (int)num(&M.st, "couplers", -1);
        if (cur0 < 0 || !offer)
            return;
        int cur = cur0;
        auto hc = a.hold.find("cpl");
        if (hc != a.hold.end() && ImGui::GetTime() < hc->second.second)
            cur = (int)hc->second.first;
        static const char *CN[4] = {"8' OFF", "16'", "4'", "2'"};
        int nb = 0;
        for (int b = 0; b < 4; b++)
            nb += (offer >> b) & 1;
        const float by = y + H - (IP ? 62 : 70), bw = (LW - 28 - (nb - 1) * 6) / (float)nb, bh = 44;
        text(a, a.font, 14, x + 14, by - (IP ? 20 : 24), SILK_DIM, "COUPLERS");
        int k = 0;
        for (int b = 0; b < 4; b++) {
            if (!((offer >> b) & 1))
                continue;
            const std::string id = std::string("ampcpl") + CN[b];
            if (button(a, id.c_str(), x + 14 + k * (bw + 6), by, bw, bh, CN[b], ((cur >> b) & 1) != 0)) {
                const int v = cur ^ (1 << b);
                a.hold["cpl"] = {(double)v, ImGui::GetTime() + 0.8};
                call(a, "{\"call\":\"couplers_set\",\"row\":" + std::to_string(a.row) + ",\"v\":" + std::to_string(v) + "}");
            }
            k++;
        }
    };
    if (organ && offers_st) {
        const float x = X1 - LW, y = Y0;
        look::tray(a, x, y, LW, H, 10);
        heading(a, x + 14, y + 12, "CONE ROTOR", "spectra");
        couplers(x, y);
        if ((int)num(&M.st, "spectra", 0) == 0) {
            const std::string why = "No cone rotor on it now: choose CONE ROTOR or ROTOR CHORUS under SPEAKER for "
                                    "its two speakers turning.";
            const auto ls = wrap(a, a.font, 14, why, LW - 28);
            for (size_t i = 0; i < ls.size(); i++)
                text(a, a.font, 14, x + 14, y + (IP ? 44 : 50) + i * LH, SILK_DIM, ls[i]);
            return;
        }
        int fast = flag(&M.st, "spectra_fast") ? 1 : 0;
        auto hf = a.hold.find("stfast");
        if (hf != a.hold.end() && ImGui::GetTime() < hf->second.second)
            fast = (int)hf->second.first;
        text(a, a.font, 14, x + 14, y + (IP ? 40 : 48), SILK_DIM, "SPEED");
        static const char *RN[2] = {"CATHEDRAL", "THEATER"};
        const float sb = (LW - 28 - 6) / 2, sy = y + (IP ? 60 : 70), bh = 44;
        for (int f = 0; f < 2; f++) {
            const std::string id = std::string("ampst") + RN[f];
            if (button(a, id.c_str(), x + 14 + f * (sb + 6), sy, sb, bh, RN[f], fast == f)) {
                a.hold["stfast"] = {(double)f, ImGui::GetTime() + 0.8};
                call(a, "{\"call\":\"part_cc\",\"row\":" + std::to_string(a.row) + ",\"cc\":80,\"v\":" + (f ? "127" : "0") + "}");
            }
        }
        const auto sn = wrap(a, a.font, 14, "The console's rocker: Cathedral slow, Theater fast. The rotor takes several "
                                            "seconds to climb to Theater and drops back to Cathedral in about one.", LW - 28);
        for (size_t i = 0; i < sn.size(); i++)
            text(a, a.font, 14, x + 14, sy + bh + 8 + i * LH, SILK_DIM, sn[i]);
        return;
    }
    if (organ) {
        const float x = X1 - LW, y = Y0;
        look::tray(a, x, y, LW, H, 10);
        heading(a, x + 14, y + 12, "ROTARY", "rotary");
        if (!les) {
            const std::string why = "No rotary on it now: choose ROTARY under SPEAKER for the horn and drum turning.";
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
        const auto sn = wrap(a, a.font, 14, "The rotors spin up and down between speeds as a real rotary speaker's do; "
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
