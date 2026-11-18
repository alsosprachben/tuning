// THE FRONT PANEL (the web's #lcd and its keys): the display -- the part,
// its program, its seven fields, the meters, the engine's load -- the part
// keys, PANIC and QUIT, and the jog dial that turns the field selected.
// A field: tap selects it, a drag moves it, a double-tap puts it back.
#pragma once

#include "app.h"
#include "widgets.h"

namespace nui {

static const char *FAMILIES[16] = {"PIANO", "CHROMATIC PERC.", "ORGAN", "GUITAR", "BASS", "STRINGS", "ENSEMBLE",
                                   "BRASS", "REED", "PIPE", "SYNTH LEAD", "SYNTH PAD", "SYNTH EFFECTS", "ETHNIC",
                                   "PERCUSSIVE", "SOUND EFFECTS"};

// THE SEVEN FIELDS (ui/app.js's FIELDS): in field units (LEVEL in half dB)
struct Field {
    const char *label;
    int lo, hi, reset;                  // (reset INT32_MIN: none)
};
static const Field FIELDS[7] = {{"LEVEL", -60, 20, 0}, {"PAN", 0, 127, 64}, {"REVERB", 0, 127, 40},
                                {"CHORUS", 0, 127, 0}, {"DELAY", 0, 127, 0}, {"KEY", -24, 24, 0},
                                {"CH", 0, 16, INT32_MIN}};
inline int field_get(App &a, int i)
{
    const int r = a.row;
    switch (i) {
    case 0: return (int)std::lround(pv(a, r, "level_db") * 2);
    case 1: return (int)pv(a, r, "pan", 64);
    case 2: return (int)pv(a, r, "reverb", 40);
    case 3: return (int)pv(a, r, "chorus");
    case 4: return (int)pv(a, r, "delay");
    case 5: return (int)pv(a, r, "transpose");
    default: return (int)pv(a, r, "channel", -1) + 1;
    }
}
inline void field_set(App &a, int i, int v)
{
    const int r = a.row;
    v = std::max(FIELDS[i].lo, std::min(FIELDS[i].hi, v));
    switch (i) {
    case 0: part_set(a, r, "level_db", v / 2.0); break;
    case 1: part_cc(a, r, 10, "pan", v); break;
    case 2: part_cc(a, r, 91, "reverb", v); break;
    case 3: part_cc(a, r, 93, "chorus", v); break;
    case 4: part_cc(a, r, 94, "delay", v); break;
    case 5: part_set(a, r, "transpose", v); break;
    default: part_set(a, r, "channel", v - 1); break;
    }
}
inline std::string field_text(int i, int v)
{
    switch (i) {
    case 0: return db_text(v / 2.0);
    case 1: return pan_text(v);
    case 5: return signed_text(v);
    case 6: return v ? std::to_string(v) : std::string("ALL");
    default: return std::to_string(v);
    }
}

inline void draw_display(App &a)
{
    const float X = 26, Y = 22, W = 1424, H = 232;
    rect(a, X - 8, Y - 8, W + 16, H + 16, IM_COL32(0x16, 0x18, 0x1b, 255), 10.0f);
    rect(a, X, Y, W, H, LCD_BG, 4.0f);
    const J *p = part(a, a.row);
    text(a, a.font, 14, X + 14, Y + 14, LCD, "PART");
    std::string fam;
    if (p) {
        const int prog = (int)num(p, "program"), var = (int)num(p, "variation"), ch = (int)pv(a, a.row, "channel", -1);
        char b[96];
        if (flag(p, "drums"))
            snprintf(b, sizeof b, "DRUM SET %d", prog);
        else
            snprintf(b, sizeof b, "PROGRAM %03d%s \xc2\xb7 %s", prog, var ? ("." + std::to_string(var)).c_str() : "",
                     var == 127 ? "MT-32" : var == 126 ? "CM-64 PCM" : FAMILIES[(prog >> 3) & 15]);
        fam = std::string(b) + (ch < 0 ? " \xc2\xb7 ALL CH" : " \xc2\xb7 CH " + std::to_string(ch + 1));
    }
    text(a, a.font, 14, X + 92, Y + 14, LCD, fam);
    text(a, a.font, 35, X + 14, Y + 34, LCD, p ? pad2(a.row + 1) : "--");
    text(a, a.font, 35, X + 92, Y + 34, LCD, p ? fit(a, a.font, 35, str(p, "name"), W - 300) : "");
    // the engine's load (the web's #cpu, #voices, #health)
    const J *m = a.meters.is(J::OBJ) ? &a.meters : nullptr;
    char b[64];
    const double bud = num(m, "budget_ms"), mean = num(m, "ms_mean");
    const int cpu = bud > 0 ? (int)std::lround(100.0 * mean / bud) : 0;
    snprintf(b, sizeof b, "%-8s%4d%%", flag(m, "gpu") ? "GPU+CPU" : "CPU", std::min(cpu, 999));
    text(a, a.font, 14, X + W - 170, Y + 14, LCD, b);
    snprintf(b, sizeof b, "%-8s%5d", "VOICES", (int)std::min(99999.0, num(m, "voices")));
    text(a, a.font, 14, X + W - 170, Y + 30, LCD, b);
    std::string health;
    if (num(&a.build, "n") > 0) {
        const double tot = num(&a.build, "total"), done = num(&a.build, "done");
        health = tot > 0 ? "BUILDING " + std::to_string((int)std::lround(100 * done / tot)) + "%" : "BUILDING";
    } else if (num(m, "underruns") > 0)
        health = "UNDERRUNS " + std::to_string((int)num(m, "underruns"));
    else if (flag(m, "rt_dropped"))
        health = "RT DROPPED";
    text(a, a.font, 14, X + W - 170, Y + 46, health.rfind("BUILDING", 0) == 0 ? LCD : BAD, health);
    // the seven fields
    const float fw = (W - 28 - 6 * 8) / 7.0f;
    for (int i = 0; i < 7 && p; i++) {
        const float fx = X + 14 + i * (fw + 8), fy = Y + 80;
        float v = (float)field_get(a, i);
        const int f = lcd_field(a, FIELDS[i].label, fx, fy, fw, 52, v, (float)FIELDS[i].lo, (float)FIELDS[i].hi,
                                FIELDS[i].label, field_text(i, (int)v), a.field == i);
        if (f & (K_TAP | K_ACTIVE))
            a.field = i;
        if (f & K_CHANGED)
            field_set(a, i, (int)v);
        if ((f & K_RESET) && FIELDS[i].reset != INT32_MIN)
            field_set(a, i, FIELDS[i].reset);
    }
    // the meters: sixteen channels, ten steps of 4 dB from -40
    const J *bars = m ? m->get("bars") : nullptr;
    const float mx = X + 14, my = Y + 144, mw = (W - 28) / 16.0f;
    for (int ch = 0; ch < 16; ch++) {
        const double db = bars && bars->is(J::ARR) && ch < (int)bars->a.size() ? bars->a[(size_t)ch].d(-120) : -120;
        const int lit = (int)std::lround((db + 40) / 40 * 10);
        for (int s = 0; s < 10; s++)
            rect(a, mx + ch * mw + 4, my + 54 - s * 6, mw - 8, 4, s < lit ? LCD : LCD_OFF, 0.0f);
        text_c(a, a.font, 14, mx + ch * mw + mw / 2, my + 64, LCD, std::to_string(ch + 1));
    }
}

inline void draw_keys(App &a)
{
    const J *p = part(a, a.row);
    const int n = nparts(a);
    const float X = 1466, Y = 22;
    if (button(a, "prev", X, Y, 118, 48, "\xe2\x97\x80 PART", false, a.row > 0))
        select(a, a.row - 1);
    if (button(a, "next", X + 128, Y, 118, 48, "PART \xe2\x96\xb6", false, a.row + 1 < n))
        select(a, a.row + 1);
    const bool muted = pv(a, a.row, "muted") != 0;
    if (button(a, "mute", X, Y + 58, 118, 48, "MUTE", muted) && p)
        part_set(a, a.row, "muted", muted ? 0 : 1);
    if (button(a, "solo", X + 128, Y + 58, 118, 48, "SOLO", num(p, "solo") == 1) && p)
        take_parts(a, call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(a.row) + "}"));
    if (button(a, "panic", X, Y + 116, 246, 48, "PANIC"))
        call(a, "{\"call\":\"panic\"}");
    // QUIT (the web's Setup card's, here until that card is): two taps within 3 s
    const double now = ImGui::GetTime();
    const bool armed = now - a.quit_armed < 3.0;
    if (button(a, "quit", X, Y + 174, 246, 48, armed ? "TAP AGAIN TO QUIT" : "QUIT CLAVITONE", armed)) {
        if (armed)
            a.quit = true;
        else
            a.quit_armed = now;
    }
    // THE JOG DIAL: the selected field, a step each 15 degrees (45 fine)
    const float cx = 1810, cy = 112, r = 74;
    const int steps = dial(a.K, a.jog, "jog", P(a, cx, cy), r * a.k);
    if (steps && p)
        field_set(a, a.field, field_get(a, a.field) + steps);
    ImDrawList *d = dl();
    const ImVec2 c = P(a, cx, cy);
    d->AddCircleFilled(c, r * a.k, IM_COL32(0x15, 0x17, 0x1a, 255), 64);
    d->AddCircleFilled(c, (r - 6) * a.k, IM_COL32(0x2a, 0x2e, 0x33, 255), 64);
    const float t = (a.jog.rot - 90) * 3.14159265f / 180.0f;
    d->AddCircleFilled(ImVec2(c.x + (r - 22) * a.k * std::cos(t), c.y + (r - 22) * a.k * std::sin(t)), 9 * a.k,
                       IM_COL32(0x15, 0x17, 0x1a, 255), 20);
    text_c(a, a.bold, 14, cx, cy + r + 10, LCD, FIELDS[a.field].label);
}

// ---- THE iPad's PANEL (App::tab: a 1133x744-point canvas, its text half
// the design sizes): the display shorter -- the name line, the seven
// fields, the meters a strip -- and the keys beside it, three rows of two,
// with the jog dial
inline void draw_display_tab(App &a)
{
    const float X = 14, Y = 12, W = 790, H = 140;
    rect(a, X - 4, Y - 4, W + 8, H + 8, IM_COL32(0x16, 0x18, 0x1b, 255), 6.0f);
    rect(a, X, Y, W, H, LCD_BG, 3.0f);
    const J *p = part(a, a.row);
    std::string fam;
    if (p) {
        const int prog = (int)num(p, "program"), var = (int)num(p, "variation"), ch = (int)pv(a, a.row, "channel", -1);
        char b[96];
        if (flag(p, "drums"))
            snprintf(b, sizeof b, "DRUM SET %d", prog);
        else
            snprintf(b, sizeof b, "PROGRAM %03d%s \xc2\xb7 %s", prog, var ? ("." + std::to_string(var)).c_str() : "",
                     var == 127 ? "MT-32" : var == 126 ? "CM-64 PCM" : FAMILIES[(prog >> 3) & 15]);
        fam = std::string(b) + (ch < 0 ? " \xc2\xb7 ALL CH" : " \xc2\xb7 CH " + std::to_string(ch + 1));
    }
    // (the part and its name 4x code7; the rest 2x)
    text(a, a.font, 14, X + 8, Y + 6, LCD, "PART  " + fam);
    text(a, a.font, 28, X + 8, Y + 18, LCD, p ? pad2(a.row + 1) : "--");
    const float nx = X + 8 + text_w(a, a.font, 28, "00") + 10;
    text(a, a.font, 28, nx, Y + 18, LCD, p ? fit(a, a.font, 28, str(p, "name"), W - (nx - X) - 130) : "");
    const J *m = a.meters.is(J::OBJ) ? &a.meters : nullptr;
    char b[64];
    const double bud = num(m, "budget_ms"), mean = num(m, "ms_mean");
    const int cpu = bud > 0 ? (int)std::lround(100.0 * mean / bud) : 0;
    snprintf(b, sizeof b, "%-8s%4d%%", flag(m, "gpu") ? "GPU+CPU" : "CPU", std::min(cpu, 999));
    text(a, a.font, 14, X + W - 96, Y + 6, LCD, b);
    snprintf(b, sizeof b, "%-8s%5d", "VOICES", (int)std::min(99999.0, num(m, "voices")));
    text(a, a.font, 14, X + W - 96, Y + 16, LCD, b);
    std::string health;
    if (num(&a.build, "n") > 0) {
        const double tot = num(&a.build, "total"), done = num(&a.build, "done");
        health = tot > 0 ? "BUILDING " + std::to_string((int)std::lround(100 * done / tot)) + "%" : "BUILDING";
    } else if (num(m, "underruns") > 0)
        health = "UNDERRUNS " + std::to_string((int)num(m, "underruns"));
    else if (flag(m, "rt_dropped"))
        health = "RT DROPPED";
    text(a, a.font, 14, X + W - 96, Y + 26, health.rfind("BUILDING", 0) == 0 ? LCD : BAD, health);
    // the seven fields: 44 points tall, their values 3x
    const float fw = (W - 16 - 6 * 5) / 7.0f;
    for (int i = 0; i < 7 && p; i++) {
        const float fx = X + 8 + i * (fw + 5), fy = Y + 50;
        float v = (float)field_get(a, i);
        const int f = lcd_field(a, FIELDS[i].label, fx, fy, fw, 46, v, (float)FIELDS[i].lo, (float)FIELDS[i].hi,
                                FIELDS[i].label, field_text(i, (int)v), a.field == i);
        if (f & (K_TAP | K_ACTIVE))
            a.field = i;
        if (f & K_CHANGED)
            field_set(a, i, (int)v);
        if ((f & K_RESET) && FIELDS[i].reset != INT32_MIN)
            field_set(a, i, FIELDS[i].reset);
    }
    // the meters, a strip: sixteen channels, ten steps of 4 dB from -40
    const J *bars = m ? m->get("bars") : nullptr;
    const float mx = X + 8, my = Y + 102, mw = (W - 16) / 16.0f;
    for (int ch = 0; ch < 16; ch++) {
        const double db = bars && bars->is(J::ARR) && ch < (int)bars->a.size() ? bars->a[(size_t)ch].d(-120) : -120;
        const int lit = (int)std::lround((db + 40) / 40 * 10);
        for (int s = 0; s < 10; s++)
            rect(a, mx + ch * mw + 2 + s * (mw - 22) / 10, my + 2, (mw - 22) / 10 - 1, 14, s < lit ? LCD : LCD_OFF, 0.0f);
        text(a, a.font, 14, mx + ch * mw + mw - 18, my + 4, LCD_DIM, std::to_string(ch + 1));
    }
    rect(a, X + 8, my + 24, W - 16, 1, LCD_OFF, 0);
}
inline void draw_keys_tab(App &a)
{
    const J *p = part(a, a.row);
    const int n = nparts(a);
    const float X = 814, Y = 10, bw = 98, bh = 44, g = 4;
    if (button(a, "prev", X, Y, bw, bh, "\xe2\x97\x80 PART", false, a.row > 0, 21))
        select(a, a.row - 1);
    if (button(a, "next", X + bw + g, Y, bw, bh, "PART \xe2\x96\xb6", false, a.row + 1 < n, 21))
        select(a, a.row + 1);
    const bool muted = pv(a, a.row, "muted") != 0;
    if (button(a, "mute", X, Y + bh + g, bw, bh, "MUTE", muted, true, 21) && p)
        part_set(a, a.row, "muted", muted ? 0 : 1);
    if (button(a, "solo", X + bw + g, Y + bh + g, bw, bh, "SOLO", num(p, "solo") == 1, true, 21) && p)
        take_parts(a, call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(a.row) + "}"));
    if (button(a, "panic", X, Y + 2 * (bh + g), bw, bh, "PANIC", false, true, 21))
        call(a, "{\"call\":\"panic\"}");
    const double now = ImGui::GetTime();
    const bool armed = now - a.quit_armed < 3.0;
    if (armed)
        a.animate = true;
    if (button(a, "quit", X + bw + g, Y + 2 * (bh + g), bw, bh, armed ? "AGAIN" : "QUIT", armed, true, 21)) {
        if (armed)
            a.quit = true;
        else
            a.quit_armed = now;
    }
    // THE JOG DIAL
    const float cx = 1123 - 50, cy = 64, r = 48;   // (clear of the keys: they end at 1014)
    const int steps = dial(a.K, a.jog, "jog", P(a, cx, cy), r * a.k);
    if (steps && p)
        field_set(a, a.field, field_get(a, a.field) + steps);
    ImDrawList *d = dl();
    const ImVec2 c = P(a, cx, cy);
    d->AddCircleFilled(c, r * a.k, IM_COL32(0x15, 0x17, 0x1a, 255), 64);
    d->AddCircleFilled(c, (r - 4) * a.k, IM_COL32(0x2a, 0x2e, 0x33, 255), 64);
    const float t = (a.jog.rot - 90) * 3.14159265f / 180.0f;
    d->AddCircleFilled(ImVec2(c.x + (r - 16) * a.k * std::cos(t), c.y + (r - 16) * a.k * std::sin(t)), 6 * a.k,
                       IM_COL32(0x15, 0x17, 0x1a, 255), 20);
    text_c(a, a.bold, 14, cx, cy + r + 6, LCD, FIELDS[a.field].label);
}

}  // namespace nui
