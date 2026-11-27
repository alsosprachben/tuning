// THE SEQ CARD: the Euclidean sequencer (native/eucseq.h; Ben 2026-11-26) --
// PLAY/STOP, the one TEMPO (the metronome's too), SWING, steps a beat, SYNC;
// then eight lanes, each a drum key struck on HITS of its STEPS spread as
// evenly as they go, turned by ROTATE (a drag sideways along its steps turns
// it too), at its VEL (ACCENT: every nth hit harder), MUTE -- and its timing:
// NUDGE (ahead of or behind the beat, part of a step), DRIFT (a little
// faster or slower than the tempo: Reich's phasing, until SYNC). Each lane its own length: the steps drawn on one
// grid, so lanes of 16, 12 and 7 are seen cycling apart. The engine steps it
// at its samples (slab.cpp's seq_tick); the card shows the step it is on.
#pragma once

#include "../native/eucseq.h"
#include "drums.h"

namespace nui {

struct SeqUi {
    bool open = false;
    J s;                                // (the seq call's: on, bpm, spb, swing, ch, lanes [[key, steps, hits, rot, vel, accent, mute]])
    long pos = -1;                      // (the beat's step last passed; -1 stopped)
    long lpos[nv::SEQ_LANES] = {-1, -1, -1, -1, -1, -1, -1, -1};   // (each lane's: apart from the beat's when it drifts)
    int page = 0;                       // (the iPad's and phone's lane numbers: 0 the pattern's, 1 the timing's)
    int pick = -1;                      // (the lane whose drum is being chosen)
    float scroll = 0, pick_scroll = 0;
    int drag_lane = -1, drag_rot0 = 0;  // (a lane's steps dragged sideways: its rotation then)
    float drag_x0 = 0;
};
static SeqUi g_seq;

inline void seq_take(const J &r)
{
    if (const J *x = r.get("seq"); x && x->is(J::OBJ))
        g_seq.s = *x;
    if (const J *x = r.get("seq_pos"))
        g_seq.pos = (long)x->d(-1);
    if (const J *x = r.get("seq_lpos"); x && x->is(J::ARR))
        for (size_t i = 0; i < x->a.size() && i < (size_t)nv::SEQ_LANES; i++)
            g_seq.lpos[i] = (long)x->a[i].d(-1);
}
inline void seq_card(App &a, bool open)
{
    SeqUi &S = g_seq;
    if (open == S.open)
        return;
    S.open = open;
    S.pick = -1;
    seq_take(call(a, std::string("{\"call\":\"seq\",\"open\":") + (open ? "1" : "0") + "}"));
}
// (a lane's numbers: key, steps, hits, rot, vel, accent, mute, nudge, drift)
inline int seq_lane(int i, int f)
{
    const J *ls = g_seq.s.get("lanes");
    if (!ls || !ls->is(J::ARR) || i >= (int)ls->a.size() || !ls->a[(size_t)i].is(J::ARR) || f >= (int)ls->a[(size_t)i].a.size())
        return 0;
    return (int)ls->a[(size_t)i].a[(size_t)f].d();
}
inline void seq_set(App &a, int lane, const char *f, double v)
{
    char b[160];
    snprintf(b, sizeof b, "{\"call\":\"seq_set\",\"lane\":%d,\"f\":\"%s\",\"v\":%g}", lane, f, v);   // i18n-skip (a call)
    seq_take(call(a, b));
}
// (a drum key's name: the selected part's kit's, else its note)
inline std::string seq_key_name(int key)
{
    if (key < 0)
        return "\xe2\x80\x94";
    for (const auto &k : g_drums.keys)
        if (k.key == key && !k.name.empty())
            return k.name;
    return note_name_sharp(key);
}

inline void draw_seq(App &a)
{
    SeqUi &S = g_seq;
    DrumsUi &D = g_drums;
    if (!S.s.is(J::OBJ))
        seq_take(call(a, "{\"call\":\"seq\",\"open\":1}"));
    if ((int)num(&D.d, "row", -1) != a.row) {
        J r = call(a, "{\"call\":\"drums\",\"open\":1,\"sets\":" + std::string(D.sets.is(J::ARR) ? "0" : "1") + "}");
        if (const J *x = r.get("drums"))
            drums_take(a, *x);
    }
    const bool IP = a.tab, PH = a.ph;
    const float X0 = PH ? 14 : IP ? 20 : 34, X1 = IP ? (PH ? 818 : 1113) : 1886, HY = PH ? 120 : IP ? 224 : 356;
    const float Y0 = PH ? 156 : IP ? 262 : 404, Y1 = card_y1(a) - (PH ? 2 : 0);
    const float TX = heading(a, X0, HY, T("SEQ"), "seq");
    if (!S.s.is(J::OBJ))
        return;
    const bool on = num(&S.s, "on") != 0;
    const int bpm = (int)std::lround(num(&S.s, "bpm", 120)), spb = (int)num(&S.s, "spb", 4), ch = (int)num(&S.s, "ch", 9);
    const int swing = (int)std::lround(num(&S.s, "swing", 50));

    // THE PART it plays: the selected one when it is a drum set, else the first that is
    int prow = -1;
    if (const J *p = part(a, a.row); p && flag(p, "drums"))
        prow = a.row;
    for (int r = 0; r < nparts(a) && prow < 0; r++)
        if (flag(part(a, r), "drums"))
            prow = r;
    {
        std::string sub;
        if (on)
            sub = TF("playing channel {0}", {std::to_string(ch + 1)});
        else if (prow >= 0) {
            const J *p = part(a, prow);
            const int pc = (int)num(p, "channel", -1);
            sub = TF("part {0} \xc2\xb7 {1}", {pad2(prow + 1), str(p, "name")}) + " \xc2\xb7 " +
                  TF("channel {0}", {std::to_string(pc < 0 ? 10 : pc + 1)});
        } else
            sub = T("No drum part: choose a kit for one on the KITS card.");
        text(a, a.font, 14, TX, HY + 1, OWN, fit(a, a.font, 14, sub, X1 - TX - 8));
    }

    // THE TRANSPORT: PLAY/STOP, TEMPO, SWING, STEPS A BEAT
    const float fh = PH ? 44 : IP ? 46 : 52, g = PH ? 6 : 8;
    float x = X0;
    {
        const float pw = PH ? 110 : IP ? 140 : 170;
        if (button(a, "sqplay", x, Y0, pw, fh, on ? T("STOP") : T("PLAY \xe2\x96\xb6"), on, on || prow >= 0, 21)) {
            if (on)
                seq_take(call(a, "{\"call\":\"seq_run\",\"on\":0}"));
            else {
                const int pc = (int)num(part(a, prow), "channel", -1);
                seq_take(call(a, "{\"call\":\"seq_run\",\"on\":1,\"ch\":" + std::to_string(pc < 0 ? 9 : pc) + "}"));
            }
        }
        x += pw + g;
    }
    auto top_field = [&](const char *id, const char *f, float w, int val, int lo, int hi, const std::string &label, const std::string &shown) {
        w = std::max(w, text_w(a, a.lcd ? a.lcd : a.font, 14, label) + 26);     // (a language's longer label: the field wider)
        float v = (float)val;
        const int fl = lcd_field(a, id, x, Y0, w, fh, v, (float)lo, (float)hi, label, shown, false, PH ? 14 : 21);
        if ((fl & K_CHANGED) && (int)v != val)
            seq_set(a, -1, f, (int)v);
        x += w + g;
    };
    const float tw = PH ? 104 : IP ? 130 : 150;
    top_field("sqbpm", "bpm", tw, bpm, 20, 300, T("TEMPO"), std::to_string(bpm));
    top_field("sqswing", "swing", tw, swing, 50, 75, T("SWING"), std::to_string(swing) + "%");
    top_field("sqspb", "spb", tw, spb, 1, 8, T("STEPS A BEAT"), std::to_string(spb));
    {
        const std::string sl = T("SYNC");
        const float sw_ = text_w(a, a.bold, 21, sl) + 28;
        if (button(a, "sqsync", x, Y0, sw_, fh, sl, false, on, 21))
            seq_set(a, -1, "sync", 1);
        x += sw_ + g;
    }
    const bool all = !IP;               // (the laptop: every lane number at once; else a page of them)
    if (!all) {
        float yy = Y0 + (fh - 44) / 2;
        const std::vector<std::string> pg = {T("PATTERN"), T("TIMING")};
        float pw2 = 0;
        for (const auto &w : pg)
            pw2 += std::max(44.0f, text_w(a, a.font, 21, w) + 18) + 5;
        const int h = flow_buttons(a, "sqpage", X1 - pw2, yy, pw2 + 5, pg, {S.page == 0, S.page == 1});
        if (h >= 0)
            S.page = h;
    }

    // THE LANES: a header over the columns, then a row each -- the drum, its steps, STEPS HITS ROT VEL, M
    const float RH = PH ? 34 : IP ? 46 : 62, RG = PH ? 4 : 6;
    const float DB = PH ? 120 : IP ? 170 : 240, FW = PH ? 50 : IP ? 66 : 84, MB = PH ? 40 : IP ? 50 : 64;
    const float SB = PH ? 30 : IP ? 30 : 28;
    const float HDY = Y0 + fh + (PH ? 8 : 12), LY0 = HDY + a.lh(14) + 4;
    const float view = Y1 - LY0, content = nv::SEQ_LANES * (RH + RG);
    const bool scrolls = content > view + 1;
    const float LX1 = X1 - (scrolls ? SB + 8 : 0);
    struct Col {
        const char *f, *head;
        int idx;
    };
    std::vector<Col> cols;
    if (all || S.page == 0) {
        cols.push_back({"steps", N_("STEPS"), 1});
        cols.push_back({"hits", N_("HITS"), 2});
        cols.push_back({"rot", N_("ROTATE"), 3});
    }
    cols.push_back({"vel", N_("VEL"), 4});
    if (all || S.page == 1) {
        cols.push_back({"nudge", N_("NUDGE"), 7});
        cols.push_back({"drift", N_("DRIFT"), 8});
        cols.push_back({"accent", N_("ACCENT"), 5});
    }
    const int nc = (int)cols.size();
    const float MX = LX1 - MB, FX = MX - 8 - nc * FW - (nc - 1) * 6, CX0 = X0 + DB + 8, CX1 = FX - 10;
    int maxsteps = 16;
    for (int i = 0; i < nv::SEQ_LANES; i++)
        maxsteps = std::max(maxsteps, seq_lane(i, 1));
    const float cw = (CX1 - CX0) / maxsteps;
    {
        text(a, a.font, 14, X0, HDY, SILK_DIM, T("DRUM"));
        text(a, a.font, 14, CX0, HDY, SILK_DIM, T("STEPS AS STRUCK"));
        for (int k = 0; k < nc; k++)
            text_c(a, a.font, 14, FX + k * (FW + 6) + FW / 2, HDY, SILK_DIM, fit(a, a.font, 14, T(cols[(size_t)k].head), FW + 4));
        text_c(a, a.font, 14, MX + MB / 2, HDY, SILK_DIM, T("MUTE"));
    }
    S.scroll = std::max(0.0f, std::min(S.scroll, std::max(0.0f, content - view)));
    if (scrolls) {                      // (the strip: a drag along it moves the lanes, as the pads' does)
        const float sx = X1 - SB;
        ImGui::SetCursorScreenPos(P(a, sx, LY0));
        ImGui::InvisibleButton("sqstrip", ImVec2(SB * a.k, view * a.k));
        tap_yields(a);
        const float my = (ImGui::GetIO().MousePos.y - a.org.y) / a.k;
        const float bhh = std::max(44.0f, view * view / content), span = std::max(1.0f, view - bhh), smax = content - view;
        if (ImGui::IsItemActive())
            S.scroll = std::max(0.0f, std::min((my - LY0 - bhh / 2) / span * smax, smax));
        look::tray(a, sx, LY0, SB, view, SB / 2);
        rect(a, sx + 5, LY0 + span * S.scroll / smax + 4, SB - 10, bhh - 8, ImGui::IsItemActive() ? LCD : SILK_DIM, (SB - 10) / 2);
        const ImVec2 m = ImGui::GetIO().MousePos;
        const float mx = (m.x - a.org.x) / a.k;
        if (mx >= X0 && mx < X1 && my >= LY0 && my < Y1 && ImGui::GetIO().MouseWheel != 0)
            S.scroll = std::max(0.0f, std::min(smax, S.scroll - ImGui::GetIO().MouseWheel * (RH + RG)));
    }

    // (a lane's drum being chosen: the kit's keys over the lanes)
    if (S.pick >= 0) {
        look::tray(a, X0, LY0, X1 - X0, view, 9);
        const float px = X0 + 12;
        text(a, a.bold, 14, px, LY0 + 10, SILK, TF("LANE {0}: ITS DRUM", {std::to_string(S.pick + 1)}));
        const float cbw = text_w(a, a.bold, 21, T("CLOSE")) + 28, cbh = PH ? 36 : 44;
        if (button(a, "sqpickx", X1 - 12 - cbw, LY0 + 6, cbw, cbh, T("CLOSE"), false, true, 21))
            S.pick = -1;
        std::vector<int> keys = {-1};
        for (const auto &k : D.keys)
            if (!k.name.empty())
                keys.push_back(k.key);
        if (keys.size() == 1)                   // (no kit's names here: the General MIDI keys by note)
            for (int k = 27; k <= 87; k++)
                keys.push_back(k);
        const float ly = LY0 + cbh + 14, LR = IP ? 48 : 34, LB = IP ? 44 : 30;
        const int cur = S.pick >= 0 ? seq_lane(S.pick, 0) : -1;
        const float lw = X1 - X0 - 24;
        const int tap = scroll_list(a, "sqpick", px, ly, lw, Y1 - 8 - ly, (int)keys.size(), LR, S.pick_scroll, [&](int i, float yy) {
            const int k = keys[(size_t)i];
            const bool lit = k == cur;
            look::chip(a, px, yy, lw - 8, LB, lit);
            const float ty = yy + (LB - a.lh(14)) / 2;
            if (k < 0) {
                text(a, a.font, 14, px + 8, ty, lit ? LCD_BG : SILK, T("none: the lane rests"));
                return;
            }
            text(a, a.bold, 14, px + 8, ty, lit ? LCD_BG : LCD, note_name_sharp(k));
            text(a, a.font, 14, px + 68, ty, lit ? LCD_BG : SILK_DIM, std::to_string(k));
            text(a, a.font, 14, px + 108, ty, lit ? LCD_BG : SILK, fit(a, a.font, 14, seq_key_name(k), lw - 130));
        });
        if (tap >= 0 && S.pick >= 0) {
            const int k = keys[(size_t)tap];
            seq_set(a, S.pick, "key", k);
            if (k >= 0 && prow >= 0) {          // (heard as chosen)
                call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(prow) + ",\"key\":" + std::to_string(k) + ",\"v\":100}");
                call(a, "{\"call\":\"drum_hit\",\"row\":" + std::to_string(prow) + ",\"key\":" + std::to_string(k) + ",\"v\":0}");
            }
            S.pick = -1;
        }
        return;
    }

    dl()->PushClipRect(P(a, X0 - 2, LY0), P(a, X1, Y1), true);
    for (int i = 0; i < nv::SEQ_LANES; i++) {
        const float y = LY0 + i * (RH + RG) - S.scroll;
        if (y + RH < LY0 || y > Y1)
            continue;
        const int key = seq_lane(i, 0), steps = std::max(1, seq_lane(i, 1)), hits = seq_lane(i, 2), rot = seq_lane(i, 3);
        const int mute = seq_lane(i, 6), nudge = seq_lane(i, 7), drift = seq_lane(i, 8);
        const std::string id = "sq" + std::to_string(i);
        // (its drum: a tap chooses another)
        if (button(a, (id + "k").c_str(), X0, y, DB, RH, fit(a, a.bold, 14, seq_key_name(key), DB - 16), false, true, 14)) {
            S.pick = i;
            S.pick_scroll = 0;
        }
        // (its steps: lit where struck, the beats marked, the step it is on framed; dragged sideways, turned)
        const uint32_t pat = nv::euclid(hits, steps, rot);     // (as the engine lays it)
        const long lp = S.lpos[i] >= 0 ? S.lpos[i] : S.pos;
        const int at = on && lp >= 0 ? (int)(lp % steps) : -1;
        const float shift = nudge / 100.0f * cw;        // (its notes drawn where they fall: nudged off their steps)
        for (int s = 0; s < steps; s++) {
            const bool hit = (pat >> s) & 1u;
            const float cx = CX0 + s * cw + (hit ? shift : 0.0f), cy = y + (PH ? 3 : 5), ch_ = RH - (PH ? 6 : 10),
                        w = std::max(2.0f, cw - (cw > 12 ? 3 : 1));
            ImU32 c = hit ? (mute ? IM_COL32(0x80, 0x60, 0x20, 0xff) : LCD) : (s % std::max(1, spb) == 0 ? IM_COL32(0x3a, 0x3c, 0x42, 0xff)
                                                                                                      : IM_COL32(0x2a, 0x2c, 0x31, 0xff));
            rect(a, cx, cy, w, ch_, c, 3);
            if (s == at) {
                frame(a, cx - 1, cy - 1, w + 2, ch_ + 2, IM_COL32(0xff, 0xff, 0xff, 0xe0), 3, 2.0f);
                if (hit && !mute)
                    rect(a, cx, cy, w, ch_, IM_COL32(0xff, 0xf0, 0xc0, 0x90), 3);
            }
        }
        {
            ImGui::SetCursorScreenPos(P(a, CX0, y));
            ImGui::InvisibleButton((id + "c").c_str(), ImVec2((CX1 - CX0) * a.k, RH * a.k));
            tap_yields(a);
            const float mx = (ImGui::GetIO().MousePos.x - a.org.x) / a.k;
            if (ImGui::IsItemActivated()) {
                S.drag_lane = i;
                S.drag_rot0 = rot;
                S.drag_x0 = mx;
            }
            if (ImGui::IsItemActive() && S.drag_lane == i) {
                const int nr = ((S.drag_rot0 + (int)std::lround((mx - S.drag_x0) / cw)) % steps + steps) % steps;
                if (nr != rot)
                    seq_set(a, i, "rot", nr);
            }
            if (ImGui::IsItemDeactivated() && S.drag_lane == i)
                S.drag_lane = -1;
        }
        // (its numbers)
        for (int k = 0; k < nc; k++) {
            const Col &c = cols[(size_t)k];
            const int val = seq_lane(i, c.idx);
            int lo = 0, hi = 127;
            std::string shown = std::to_string(val);
            char b[24];
            if (c.idx == 1)
                lo = 1, hi = 32;
            else if (c.idx == 2)
                hi = steps;
            else if (c.idx == 3)
                hi = steps - 1;
            else if (c.idx == 4)
                lo = 1;
            else if (c.idx == 7) {              // (NUDGE: % of a step, - ahead, + behind)
                lo = -50, hi = 50;
                shown = (val > 0 ? "+" : "") + std::to_string(val) + "%";
            } else if (c.idx == 8) {            // (DRIFT: tenths of a % of the tempo)
                lo = -50, hi = 50;
                snprintf(b, sizeof b, "%s%.1f%%", val > 0 ? "+" : "", val / 10.0);
                shown = b;
            } else if (c.idx == 5) {            // (ACCENT: every nth hit)
                hi = 16;
                shown = val ? "/" + std::to_string(val) : std::string("\xe2\x80\x94");
            }
            float v = (float)val;
            const int fl = lcd_field(a, (id + c.f).c_str(), FX + k * (FW + 6), y, FW, RH, v, (float)lo, (float)hi, "", shown,
                                     c.idx == 8 && drift != 0, PH ? 14 : 21);
            if ((fl & K_CHANGED) && (int)v != val)
                seq_set(a, i, c.f, (int)v);
        }
        if (button(a, (id + "m").c_str(), MX, y, MB, RH, "M", mute != 0, true, PH ? 14 : 21))
            seq_set(a, i, "mute", mute ? 0 : 1);
    }
    dl()->PopClipRect();
    if (on)
        a.animate = true;               // (the step it is on moves)
}

}  // namespace nui
