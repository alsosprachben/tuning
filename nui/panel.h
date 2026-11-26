// THE FRONT PANEL (the web's #lcd and its keys): the display -- the part,
// its program, its seven fields, the meters, the engine's load -- the part
// keys, PANIC and QUIT, and the jog dial that turns the field selected.
// A field: tap selects it, a drag moves it, a double-tap puts it back.
#pragma once

#include "app.h"
#include "widgets.h"
#include "look.h"

namespace nui {

// THE DISPLAY's PATCH WORDS beside the name, whole: at their size on the
// name's baseline if they fit, else a size down, else on two lines filling
// the name's height (the words are capped at two lines' worth)
inline void display_desc(App &a, const std::string &pd, float x, float y, float row_h, float w, float size)
{
    ImFont *f = a.lcd ? a.lcd : a.font;
    if (text_w(a, f, size, pd) <= w) {
        look::lcd_text(a, size, x, y + row_h - a.lh(size) - 2, LCD, pd);
        return;
    }
    const float small = size > 14 ? 14 : size;
    if (text_w(a, f, small, pd) <= w) {
        look::lcd_text(a, small, x, y + row_h - a.lh(small) - 2, LCD, pd);
        return;
    }
    const auto ls = wrap(a, f, small, pd, w);
    const float lh = a.lh(small) + 2, y0 = y + row_h - 2 - lh * std::min<size_t>(2, ls.size());
    for (size_t i = 0; i < ls.size() && i < 2; i++)
        look::lcd_text(a, small, x, y0 + i * lh, LCD, ls[i]);
}

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

// THE DISPLAY's FLOOR: its dark amber, lighter where the light behind it is
// (a grid of cells, each corner shaded: the light's pool, not a flat fill)
inline void lcd_floor(App &a, float x, float y, float w, float h)
{
    ImDrawList *d = dl();
    const int nx = 24, ny = 8;
    auto col = [&](float u, float v) {
        const float dx = (u - 0.5f) * 1.6f, dy = (v - 0.42f) * 1.5f;
        return look::mix(IM_COL32(0x33, 0x23, 0x08, 255), IM_COL32(0x1b, 0x12, 0x04, 255), std::sqrt(dx * dx + dy * dy));
    };
    for (int j = 0; j < ny; j++)
        for (int i = 0; i < nx; i++) {
            const float u0 = (float)i / nx, u1 = (float)(i + 1) / nx, v0 = (float)j / ny, v1 = (float)(j + 1) / ny;
            const ImVec2 p0(a.org.x + (x + u0 * w) * a.k, a.org.y + (y + v0 * h) * a.k),
                p1(a.org.x + (x + u1 * w) * a.k, a.org.y + (y + v1 * h) * a.k);
            d->AddRectFilledMultiColor(p0, p1, col(u0, v0), col(u1, v0), col(u1, v1), col(u0, v1));
        }
}
// A METER's SEGMENT: lit, glowing; unlit, its dark lens
inline void meter_seg(App &a, float x, float y, float w, float h, bool lit)
{
    if (lit) {
        rect(a, x - 1.5f, y - 1.5f, w + 3, h + 3, look::alpha(LCD, 0.18f), 1.5f);
        rect(a, x, y, w, h, LCD, 0.0f);
    } else {
        rect(a, x, y, w, h, LCD_OFF, 0.0f);
    }
}

// THE DISPLAY's HEALTH LINE (the web's #health): a held note that never
// sounded (MISSED), a stand-in note (a key
// whose template was not built yet, played on its neighbour's, retuned)
// in red for 4 s, a note played late for 2 s, else a build, an octave
// filling as played, underruns; warn: red
inline std::string health_line(App &a, const J *m, bool &warn)
{
    const double now = ImGui::GetTime();
    const long lt = (long)num(&a.build, "late"), st = (long)num(&a.build, "stand"), ls = (long)num(&a.build, "lost");
    if (a.seen_lost >= 0 && ls > a.seen_lost) {     // (a held note that never sounded: worst first)
        a.warn = ls - a.seen_lost > 1 ? "MISSED x" + std::to_string(ls - a.seen_lost) : "MISSED NOTE";
        a.warn_red = true;
        a.warn_until = now + 4.0;
    } else if (a.seen_stand >= 0 && st > a.seen_stand) {
        a.warn = st - a.seen_stand > 1 ? "STAND-IN x" + std::to_string(st - a.seen_stand) : "STAND-IN";
        a.warn_red = true;
        a.warn_until = now + 4.0;
    } else if (a.seen_late >= 0 && lt > a.seen_late && (now >= a.warn_until || !a.warn_red)) {
        a.warn = lt - a.seen_late > 1 ? "LATE x" + std::to_string(lt - a.seen_late) : "LATE NOTE";
        a.warn_red = false;
        a.warn_until = now + 2.0;
    }
    a.seen_late = lt;
    a.seen_stand = st;
    a.seen_lost = ls;
    warn = false;
    if (now < a.warn_until) {
        warn = a.warn_red;
        return a.warn;
    }
    if (num(&a.build, "n") > 0) {
        const double tot = num(&a.build, "total"), done = num(&a.build, "done"), mb = num(&a.build, "est_mb");
        // (its size beside the percent, known or sampled; over the budget, the middle octaves first)
        const std::string size = mb >= 1024 ? " \xc2\xb7 " + std::to_string((int)std::lround(mb / 1024.0)) + " GB"
                               : mb > 0 ? " \xc2\xb7 " + std::to_string((int)mb) + " MB" : "";
        return tot > 0 ? "BUILDING " + std::to_string((int)std::lround(100 * done / tot)) + "%" + size +
                             (flag(&a.build, "over") ? " \xc2\xb7 TOO BIG: MIDDLE FIRST" : "")
                       : "BUILDING";
    }
    const std::string fill = str(&a.build, "fill");
    if (!fill.empty())
        return "FILL " + fill;
    warn = true;
    if (num(m, "underruns") > 0)
        return "UNDERRUNS " + std::to_string((int)num(m, "underruns"));
    if (flag(m, "rt_dropped"))
        return "RT DROPPED";
    warn = false;
    return "";
}

std::string patch_desc(App &a, const J *part);   // (library.h: the part's patch's few words)

inline void draw_display(App &a)
{
    const float X = 26, Y = 22, W = 1424, H = 232;
    look::plate(a, 0, 0, a.W, 266);     // (the front panel's plate, under the display, keys and dial)
    look::well(a, X - 8, Y - 8, W + 16, H + 16, 10.0f, IM_COL32(0x0b, 0x0c, 0x0e, 255));
    lcd_floor(a, X, Y, W, H);
    const J *p = part(a, a.row);
    look::lcd_text(a, 14, X + 14, Y + 14, LCD, "PART");
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
    look::lcd_text(a, 14, X + 92, Y + 14, LCD, fam);
    look::lcd_text(a, 35, X + 14, Y + 34, LCD, p ? pad2(a.row + 1) : "--");
    // (the name, and after it the patch's few words -- "Hammond: 16 5-1/3 8 1, Leslie fast")
    const std::string nm = p ? fit(a, a.font, 35, str(p, "name"), W - 300) : "";
    look::lcd_text(a, 35, X + 92, Y + 34, LCD, nm);
    if (p) {
        const float dx = X + 92 + text_w(a, a.lcd ? a.lcd : a.font, 35, nm) + 28, dw = X + W - 190 - dx;
        const std::string pd = patch_desc(a, p);
        if (!pd.empty() && dw > 80)
            display_desc(a, pd, dx, Y + 34, a.lh(35), dw, 21);
    }
    // the engine's load (the web's #cpu, #voices, #health)
    const J *m = a.meters.is(J::OBJ) ? &a.meters : nullptr;
    char b[64];
    const double bud = num(m, "budget_ms"), mean = num(m, "ms_mean");
    const int cpu = bud > 0 ? (int)std::lround(100.0 * mean / bud) : 0;
    snprintf(b, sizeof b, "%-8s%4d%%", flag(m, "gpu") ? "GPU+CPU" : "CPU", std::min(cpu, 999));
    look::lcd_text(a, 14, X + W - 170, Y + 14, LCD, b);
    snprintf(b, sizeof b, "%-8s%5d", "VOICES", (int)std::min(99999.0, num(m, "voices")));
    look::lcd_text(a, 14, X + W - 170, Y + 30, LCD, b);
    bool warn = false;
    const std::string health = health_line(a, m, warn);
    look::lcd_text(a, 14, X + W - 170, Y + 46, warn ? BAD : LCD, fit(a, a.lcd, 14, health, 160));
    // the seven fields
    const float fw = (W - 28 - 6 * 8) / 7.0f;
    for (int i = 0; i < 7 && p; i++) {
        const float fx = X + 14 + i * (fw + 8), fy = Y + 80;
        float v = (float)field_get(a, i);
        const int f = lcd_field(a, FIELDS[i].label, fx, fy, fw, 52, v, (float)FIELDS[i].lo, (float)FIELDS[i].hi,
                                FIELDS[i].label, field_text(i, (int)v), a.field == i, 21, i == 0 ? 0.5f : 1.0f);
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
            meter_seg(a, mx + ch * mw + 4, my + 54 - s * 6, mw - 8, 4, s < lit);
        look::lcd_text_c(a, 14, mx + ch * mw + mw / 2, my + 64, LCD, std::to_string(ch + 1));
    }
    look::glass(a, X, Y, W, H);
}

inline void draw_keys(App &a)
{
    const J *p = part(a, a.row);
    const int n = nparts(a);
    const float X = 1466, Y = 22;
    if (look::key(a, "prev", X, Y, 118, 48, "\xe2\x97\x80 PART", false, a.row > 0, 14, false))
        select(a, a.row - 1);
    if (look::key(a, "next", X + 128, Y, 118, 48, "PART \xe2\x96\xb6", false, a.row + 1 < n, 14, false))
        select(a, a.row + 1);
    const bool muted = pv(a, a.row, "muted") != 0;
    if (look::key(a, "mute", X, Y + 58, 118, 48, "MUTE", muted) && p)
        part_set(a, a.row, "muted", muted ? 0 : 1);
    if (look::key(a, "solo", X + 128, Y + 58, 118, 48, "SOLO", num(p, "solo") == 1) && p)
        take_parts(a, call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(a.row) + "}"));
    if (look::key(a, "panic", X, Y + 116, 246, 48, "PANIC", false, true, 14, false))
        call(a, "{\"call\":\"panic\"}");
    // QUIT (the web's Setup card's, here until that card is): two taps within 3 s
    const double now = ImGui::GetTime();
    const bool armed = now - a.quit_armed < 3.0;
    if (look::key(a, "quit", X, Y + 174, 246, 48, armed ? "TAP AGAIN TO QUIT" : "QUIT CLAVITONE", armed)) {
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
    look::dial_cap(a, cx, cy, r, a.jog.rot);
    text_c(a, a.bold, 14, cx, cy + r + 10, LCD, FIELDS[a.field].label);
}

// ---- THE iPad's PANEL (App::tab: a 1133x744-point canvas, its text half
// the design sizes): the display shorter -- the name line, the seven
// fields, the meters a strip -- and the keys beside it, three rows of two,
// with the jog dial
inline void draw_display_tab(App &a)
{
    const float X = 14, Y = 12, W = 790, H = 140;
    look::plate(a, 0, 0, a.W, 156);
    look::well(a, X - 4, Y - 4, W + 8, H + 8, 6.0f, IM_COL32(0x0b, 0x0c, 0x0e, 255));
    lcd_floor(a, X, Y, W, H);
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
    look::lcd_text(a, 14, X + 8, Y + 6, LCD, "PART  " + fam);
    look::lcd_text(a, 28, X + 8, Y + 18, LCD, p ? pad2(a.row + 1) : "--");
    const float nx = X + 8 + text_w(a, a.font, 28, "00") + 10;
    const std::string nm = p ? fit(a, a.font, 28, str(p, "name"), W - (nx - X) - 130) : "";
    look::lcd_text(a, 28, nx, Y + 18, LCD, nm);
    if (p) {                            // (...and after it the patch's few words)
        const float dx = nx + text_w(a, a.lcd ? a.lcd : a.font, 28, nm) + 16, dw = X + W - 104 - dx;
        const std::string pd = patch_desc(a, p);
        if (!pd.empty() && dw > 60)
            display_desc(a, pd, dx, Y + 18, a.lh(28), dw, 14);
    }
    const J *m = a.meters.is(J::OBJ) ? &a.meters : nullptr;
    char b[64];
    const double bud = num(m, "budget_ms"), mean = num(m, "ms_mean");
    const int cpu = bud > 0 ? (int)std::lround(100.0 * mean / bud) : 0;
    snprintf(b, sizeof b, "%-8s%4d%%", flag(m, "gpu") ? "GPU+CPU" : "CPU", std::min(cpu, 999));
    look::lcd_text(a, 14, X + W - 96, Y + 6, LCD, b);
    snprintf(b, sizeof b, "%-8s%5d", "VOICES", (int)std::min(99999.0, num(m, "voices")));
    look::lcd_text(a, 14, X + W - 96, Y + 16, LCD, b);
    bool warn = false;
    const std::string health = health_line(a, m, warn);
    look::lcd_text(a, 14, X + W - 96, Y + 26, warn ? BAD : LCD, fit(a, a.lcd, 14, health, 90));
    // the seven fields: 44 points tall, their values 3x
    const float fw = (W - 16 - 6 * 5) / 7.0f;
    for (int i = 0; i < 7 && p; i++) {
        const float fx = X + 8 + i * (fw + 5), fy = Y + 50;
        float v = (float)field_get(a, i);
        const int f = lcd_field(a, FIELDS[i].label, fx, fy, fw, 46, v, (float)FIELDS[i].lo, (float)FIELDS[i].hi,
                                FIELDS[i].label, field_text(i, (int)v), a.field == i, 21, i == 0 ? 0.5f : 1.0f);
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
            meter_seg(a, mx + ch * mw + 2 + s * (mw - 22) / 10, my + 2, (mw - 22) / 10 - 1, 14, s < lit);
        look::lcd_text(a, 14, mx + ch * mw + mw - 18, my + 4, LCD_DIM, std::to_string(ch + 1));
    }
    rect(a, X + 8, my + 24, W - 16, 1, LCD_OFF, 0);
    look::glass(a, X, Y, W, H);
}
inline void draw_keys_tab(App &a)
{
    const J *p = part(a, a.row);
    const int n = nparts(a);
    const float X = 814, Y = 10, bw = 98, bh = 44, g = 4;
    if (look::key(a, "prev", X, Y, bw, bh, "\xe2\x97\x80 PART", false, a.row > 0, 21, false))
        select(a, a.row - 1);
    if (look::key(a, "next", X + bw + g, Y, bw, bh, "PART \xe2\x96\xb6", false, a.row + 1 < n, 21, false))
        select(a, a.row + 1);
    const bool muted = pv(a, a.row, "muted") != 0;
    if (look::key(a, "mute", X, Y + bh + g, bw, bh, "MUTE", muted, true, 21) && p)
        part_set(a, a.row, "muted", muted ? 0 : 1);
    if (look::key(a, "solo", X + bw + g, Y + bh + g, bw, bh, "SOLO", num(p, "solo") == 1, true, 21) && p)
        take_parts(a, call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(a.row) + "}"));
    if (look::key(a, "panic", X, Y + 2 * (bh + g), bw, bh, "PANIC", false, true, 21, false))
        call(a, "{\"call\":\"panic\"}");
    const double now = ImGui::GetTime();
    const bool armed = now - a.quit_armed < 3.0;
    if (armed)
        a.animate = true;
    if (look::key(a, "quit", X + bw + g, Y + 2 * (bh + g), bw, bh, armed ? "AGAIN" : "QUIT", armed, true, 21)) {
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
    look::dial_cap(a, cx, cy, r, a.jog.rot);
    text_c(a, a.bold, 14, cx, cy + r + 6, LCD, FIELDS[a.field].label);
}

}  // namespace nui
