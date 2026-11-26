// nui.cpp -- CLAVITONE's NATIVE INTERFACE: the touch UI drawn by us on the
// GPU, in the engine's own process (nvlive --app), the web UI (ui/) its
// reference. SDL3 the window, touch and pen; Dear ImGui the layout, text and
// input; every control ours, in the front panel's colours and Ben's code7
// bitmap font (bdf.h). It talks to the engine as the web page does -- the
// same JSON calls (nv_ui_call) and pushes (nv_ui_poll) -- with no server,
// no browser, no socket.
//
// LIGHT AT REST: a frame is drawn only when something changed (an input, a
// push that differs from the last); otherwise the loop waits on events.
//
// TESTS (NUI_SCRIPT=FILE): a line each, "wait MS", "tap X Y" (a finger down
// and up there, in the 1920x1080 design's units), "shot PATH" (the frame as
// a PPM), "quit" -- with SDL_VIDEODRIVER=offscreen, headless.
#include <SDL3/SDL.h>
#ifdef __APPLE__
#include <TargetConditionals.h>
#endif

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "imgui.h"
#include "backends/imgui_impl_sdl3.h"

#include "gfx.h"

#include "app.h"
#include "bdf.h"
#include "panel.h"
#include "parts.h"
#include "library.h"
#include "synth.h"
#include "stops.h"
#include "piano.h"
#include "drums.h"
#include "effects.h"
#include "amp.h"
#include "matrix.h"
#include "tuning.h"
#include "control.h"
#include "scenes.h"
#include "files.h"
#include "setup.h"
#include "help.h"
#include "sheet.h"

namespace nui {

// (SCENES after PARTS: a setup's parts arranged, then saved and brought back -- Ben 2026-11-25)
static const char *CARDS[][2] = {{"parts", "PARTS"}, {"scenes", "SCENES"}, {"library", "LIBRARY"}, {"synth", "SYNTH"},
                                 {"stops", "STOPS"}, {"piano", "PIANO"}, {"drums", "DRUMS"}, {"amp", "AMP"},
                                 {"effects", "EFFECTS"}, {"matrix", "MATRIX"}, {"tuning", "TUNING"}, {"control", "CONTROL"},
                                 {"files", "FILES"}, {"setup", "SETUP"}};


static void draw(App &a)
{
    const ImGuiIO &io = ImGui::GetIO();
    // (the rect the layout fits: the safe area where the window has one, else the whole)
    const float sx = a.safe_w > 0 ? a.safe_x : 0.0f, sy = a.safe_w > 0 ? a.safe_y : 0.0f;
    const ImVec2 ds = a.safe_w > 0 ? ImVec2(a.safe_w, a.safe_h) : io.DisplaySize;
    // THE LAYOUT: the iPad's where the screen is its shape (narrower than 16:10.5) or NUI_LAYOUT=ipad says so
    {
        const char *lay = getenv("NUI_LAYOUT");
        // (the phone's: NUI_LAYOUT=phone, or a screen under 500 points tall -- a phone in landscape)
        a.ph = lay ? !strcmp(lay, "phone") : ds.y < 500.0f;
        a.tab = a.ph || (lay ? !strcmp(lay, "ipad") : ds.x / std::max(1.0f, ds.y) < 1.65f);
        a.W = a.ph ? 832.0f : a.tab ? 1133.0f : 1920.0f;
        // (the iPad's as tall as the screen's shape: 744 on an iPad mini's
        //  1133x744, 787 on an 11-inch iPad's 1180x820 -- the cards' feet follow, card_y1)
        a.H = a.ph ? std::max(400.0f, std::floor(832.0f * ds.y / std::max(1.0f, ds.x)))
            : a.tab ? std::max(744.0f, std::floor(1133.0f * ds.y / std::max(1.0f, ds.x))) : 1080.0f;
        a.ts = a.tab ? 0.5f : 1.0f;
    }
    a.k = std::min(ds.x / a.W, ds.y / a.H);
    {                                       // (the sizes as this screen has them: each change said -- NUI_DEBUG_SCALE, or iOS's log)
        static float said_w = 0, said_h = 0;
#if defined(__APPLE__) && TARGET_OS_IPHONE
        const bool say = true;
#else
        const bool say = getenv("NUI_DEBUG_SCALE") != nullptr;
#endif
        if (say && (io.DisplaySize.x != said_w || io.DisplaySize.y != said_h)) {
            said_w = io.DisplaySize.x;
            said_h = io.DisplaySize.y;
            fprintf(stderr, "nui: display %.1fx%.1f, safe %.0f,%.0f %.0fx%.0f, framebuffer scale %.2f, k %.3f, px(14) %.2f\n",
                    io.DisplaySize.x, io.DisplaySize.y, a.safe_x, a.safe_y, a.safe_w, a.safe_h,
                    io.DisplayFramebufferScale.x, a.k, px(a, 14));
        }
    }
    a.K.k = a.k;
    a.org = ImVec2(std::floor(sx + (ds.x - a.W * a.k) / 2), std::floor(sy + (ds.y - a.H * a.k) / 2));
    ImGui::SetNextWindowPos(ImVec2(0, 0));
    ImGui::SetNextWindowSize(io.DisplaySize);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(0, 0));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
    ImGui::PushStyleColor(ImGuiCol_WindowBg, ImGui::ColorConvertU32ToFloat4(PAGE));
    ImGui::Begin("clavitone", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove |
                                            ImGuiWindowFlags_NoBringToFrontOnFocus | ImGuiWindowFlags_NoScrollWithMouse);
    // (the bitmap font's pixels sampled as pixels)
    dl()->AddCallback(ImGui::GetPlatformIO().DrawCallback_SetSamplerNearest, nullptr);
    if (!a.help.empty() && a.help[0] == '@')        // (a ? touched: the viewer opened at its topic)
        help_open(a, a.help.substr(1));
    if (a.sheet.open) {                 // A CONTROL's SHEET, over everything while it is open
        draw_sheet(a);
        ImGui::End();
        ImGui::PopStyleColor();
        ImGui::PopStyleVar(2);
        return;
    }
    if (!a.help.empty()) {              // THE HELP, over everything while it is open
        draw_help(a);
        ImGui::End();
        ImGui::PopStyleColor();
        ImGui::PopStyleVar(2);
        return;
    }
    const int nc = (int)(sizeof CARDS / sizeof CARDS[0]);
    if (a.ph) {                         // THE PHONE's: two rows, then the card (or the cards' menu over it)
        draw_display_phone(a);
        std::string title;
        for (int i = 0; i < nc; i++)
            if (a.card == CARDS[i][0])
                title = CARDS[i][1];
        if (button(a, "cards", 6, 56, 150, 44, title + " \xe2\x96\xbe", a.cards_open, true, 21))
            a.cards_open = !a.cards_open;
        look::module(a, 6, 106, 820, a.H - 112, 6.0f);
        if (a.cards_open) {             // (every card a key, and the help: one tap away)
            const float gx = 14, gy = 114, cw = (804 - 4 * 8) / 5.0f, ch = 56;
            for (int i = 0; i <= nc; i++) {
                const float x = gx + (i % 5) * (cw + 8), y = gy + (i / 5) * (ch + 8);
                if (i == nc) {
                    if (button(a, "help", x, y, cw, ch, "HELP", false, true, 21)) {
                        a.cards_open = false;
                        help_open(a, "basics");
                    }
                } else if (button(a, CARDS[i][0], x, y, cw, ch, CARDS[i][1], a.card == CARDS[i][0], true, 21)) {
                    a.card = CARDS[i][0];
                    a.cards_open = false;
                }
            }
            ImGui::End();
            ImGui::PopStyleColor();
            ImGui::PopStyleVar(2);
            return;
        }
    } else if (a.tab) {                        // THE iPad's: the panel shorter, the tabs 44 points tall, the card below
        draw_display_tab(a);
        draw_keys_tab(a);
        const float X = 10, Y = 160, gap = 4, w = (1113 - gap * nc - 44) / nc;
        for (int i = 0; i < nc; i++)
            if (button(a, CARDS[i][0], X + i * (w + gap), Y, w, 44, CARDS[i][1], a.card == CARDS[i][0], true, 21))
                a.card = CARDS[i][0];
        if (button(a, "help", X + nc * (w + gap), Y, 44, 44, "?", false, true, 21))
            help_open(a, "basics");
        look::module(a, 10, 210, 1113, a.H - 220, 6.0f);
    } else {
        draw_display(a);
        draw_keys(a);
        // THE CARD TABS, and the card (each built from the web's in turn)
        const float X = 14, Y = 276, gap = 8, w = (1892 - gap * nc - 56) / nc;
        for (int i = 0; i < nc; i++)
            if (button(a, CARDS[i][0], X + i * (w + gap), Y, w, 46, CARDS[i][1], a.card == CARDS[i][0]))
                a.card = CARDS[i][0];
        if (button(a, "help", X + nc * (w + gap), Y, 56, 46, "?"))
            help_open(a, "basics");
        look::module(a, 14, 338, 1892, 728, 10.0f);
    }
    piano_card(a, a.card == "piano");   // (the engine pushes the pedals only while it is open)
    if (a.card != "amp")
        amp_open(a, false);             // (...and the amp's only while its card is)
    drums_card(a, a.card == "drums");   // (...and the kit and its hits)
    effects_card(a, a.card == "effects");
    matrix_card(a, a.card == "matrix");
    tuning_card(a, a.card == "tuning");
    control_card(a, a.card == "control");
    scenes_card(a, a.card == "scenes" || a.card == "control");   // (the metronome is on the Control card)
    files_card(a, a.card == "files");
    setup_card(a, a.card == "setup");
    // (on the iPad, a card not yet laid out for it says so)
    static const std::set<std::string> TAB_READY = {"parts", "library", "synth", "stops", "piano", "drums", "amp", "effects", "matrix", "tuning", "control", "scenes", "files", "setup"};
    // (on the phone, a card not laid out for its height: the iPad's height, the
    //  phone's width, scrolled -- a drag on the card's empty ground, or the wheel)
    static const std::set<std::string> PHONE_READY = {"parts", "library"};
    static std::map<std::string, float> card_scroll, card_foot;     // (the foot: as drawn last frame, in iPad units)
    const bool virt = a.ph && !PHONE_READY.count(a.card);
    const ImVec2 org0 = a.org;
    float vscroll = 0, vmax = 0;
    if (virt) {
        float &sc = card_scroll[a.card];
        const float top = 106, bot = a.H - 6, view = bot - top - 4;
        const auto ft = card_foot.find(a.card);
        const float content = (ft != card_foot.end() ? std::min(728.0f, ft->second) : 728.0f) + 8 - 210;
        vmax = std::max(0.0f, content - view);
        if (const char *s0 = getenv("NUI_CARD_SCROLL"))     // (the tour's: a card shown scrolled to its foot)
            sc = (float)atof(s0) * vmax;
        sc = std::max(0.0f, std::min(sc, vmax));
        vscroll = sc;
        ImGui::PushClipRect(P(a, 6, top + 2), P(a, 826, bot - 2), true);
        a.org.y = std::floor(a.org.y + (top - 210 - sc) * a.k);
        a.vcard = true;
    }
    const int vtx0 = dl()->VtxBuffer.Size;  // (what the card draws: its lowest point, for its scroll's reach)
    if (a.ph && !virt) {
    } else if (a.tab && !TAB_READY.count(a.card)) {
        text(a, a.font, 21, 24, 226, SILK_DIM, "This card's iPad layout is still to come; the laptop's has it.");
    } else if (a.card == "parts") {
        draw_parts(a);
    } else if (a.card == "library") {
        draw_library(a);
    } else if (a.card == "synth") {
        draw_synth(a);
    } else if (a.card == "stops") {
        draw_stops(a);
    } else if (a.card == "piano") {
        draw_piano(a);
    } else if (a.card == "drums") {
        draw_drums(a);
    } else if (a.card == "amp") {
        draw_amp(a);                    // (amp_open: the engine pushes the card's state while it is up)
    } else if (a.card == "effects") {
        draw_effects(a);
    } else if (a.card == "matrix") {
        draw_matrix(a);
    } else if (a.card == "tuning") {
        draw_tuning(a);
    } else if (a.card == "control") {
        draw_control(a);
    } else if (a.card == "scenes") {
        draw_scenes(a);
    } else if (a.card == "files") {
        draw_files(a);
    } else if (a.card == "setup") {
        draw_setup(a);
    } else {
        std::string title;
        for (int i = 0; i < nc; i++)
            if (a.card == CARDS[i][0])
                title = CARDS[i][1];
        text(a, a.bold, 14, 34, 356, SILK, title);
        text(a, a.font, 21, 34, 400, SILK_DIM, "Not built in the native interface yet: the web interface has it (nvlive --ui).");
    }
    if (a.ph && !virt) {                // (the phone's own cards)
        if (a.card == "parts")
            draw_parts(a);
        else if (a.card == "library")
            draw_library(a);
    }
    if (virt) {                         // (the scrolled card's place: a rail at its right edge)
        // (its scroll: a touch on the card that no control took, dragged; or the wheel off a control --
        //  judged after the card, so a control under the finger always has it first)
        static bool sdrag = false;
        static float sy0 = 0, ss0 = 0;
        float &sc = card_scroll[a.card];
        const ImGuiIO &io = ImGui::GetIO();
        const float my = (io.MousePos.y - org0.y) / a.k, mx = (io.MousePos.x - org0.x) / a.k;
        const bool in = mx >= 6 && mx < 826 && my >= 106 && my < a.H - 6;
        if (ImGui::IsMouseClicked(0) && in && !ImGui::IsAnyItemActive()) {
            sdrag = true;
            sy0 = my;
            ss0 = sc;
        }
        if (sdrag && ImGui::IsMouseDown(0))
            sc = std::max(0.0f, std::min(vmax, ss0 - (my - sy0)));
        else
            sdrag = false;
        if (in && io.MouseWheel != 0 && !ImGui::IsAnyItemHovered())
            sc = std::max(0.0f, std::min(vmax, sc - io.MouseWheel * 40));
        if (sdrag)
            a.animate = true;
        {
            float lo = 0;
            const ImDrawList *d = dl();
            for (int i = vtx0; i < d->VtxBuffer.Size; i++)
                lo = std::max(lo, d->VtxBuffer[i].pos.y);
            const float foot = (lo - a.org.y) / a.k;            // (in the card's own units)
            if (std::fabs(card_foot[a.card] - foot) > 1)
                a.animate = true;                               // (its reach changed: drawn again with it)
            card_foot[a.card] = foot;
        }
        a.org = org0;
        a.vcard = false;
        ImGui::PopClipRect();
        if (vmax > 0) {
            const float top = 110, h = a.H - 6 - 4 - top, th = std::max(30.0f, h * h / (h + vmax));
            rect(a, 821, top, 3, h, IM_COL32(0x2b, 0x2f, 0x34, 255), 1.5f);
            rect(a, 821, top + (h - th) * vscroll / vmax, 3, th, SILK_DIM, 1.5f);
        }
    }
    ImGui::End();
    ImGui::PopStyleColor();
    ImGui::PopStyleVar(2);
}

// ...and the engine's pushes: true if the screen should change
static bool poll(App &a)
{
    char *s = nv_ui_poll(a.h, a.w);
    if (!s)
        return false;
    J m;
    sess::parse(s, m);
    nv_ui_free(s);
    bool changed = false;
    if (const J *x = m.get("meters")) {
        std::string t = sess::dump(*x);
        if (t != a.last_meters) {
            a.last_meters = t;
            a.meters = *x;
            changed = true;
        }
    }
    if (const J *x = m.get("build")) {
        a.build = *x;
        changed = true;
    }
    if (const J *x = m.get("synth")) {     // (the part's synth as the engine has it: the Messenger's knobs, a preset)
        if ((int)num(x, "row", -1) == a.row && (int)num(x, "layer") == g_syn.layer) {
            g_syn.synth = *x;
            g_syn.for_row = a.row;
            g_syn.text.clear();
            changed = true;
        }
    }
    if (m.get("setup") || m.get("module")) {
        su_take(m);
        changed = true;
    }
    if (m.get("files") || m.get("list")) {
        fl_take(m);
        changed = true;
    }
    if (m.get("scenes")) {
        sc_take(m);
        changed = true;
    }
    if (m.get("control")) {
        ct_take(m);
        changed = true;
    }
    if (m.get("tuning")) {
        tn_take(m);
        changed = true;
    }
    if (m.get("matrix")) {
        mx_take(a, m);
        changed = true;
    }
    if (const J *x = m.get("effects")) {
        g_fx.e = *x;
        changed = true;
    }
    if (const J *x = m.get("drums")) {
        drums_take(a, *x);
        changed = true;
    }
    if (const J *x = m.get("hits")) {      // (the pads lit as they are played)
        drums_hits(*x);
        changed = true;
    }
    if (const J *x = m.get("piano")) {
        piano_take(a, *x);
        changed = true;
    }
    if (const J *x = m.get("amp")) {       // (the AMP card's: its valve, its Leslie, as a wheel or a file moves them)
        amp_take(a, *x);
        changed = true;
    }
    if (const J *x = m.get("stops")) {     // (the part's registration: a file's, a preset's, a new organ)
        stops_take(*x, a);
        changed = true;
    }
    if (const J *x = m.get("parts")) {
        a.parts = *x;
        a.row = std::min(a.row, std::max(0, nparts(a) - 1));
        changed = true;
    }
    return changed;
}

// ---- tests: the text audit's report on a shot (NUI_TEXT_AUDIT): appended,
// a "== SHOT" line and then CUT, OVERLAP and SPILL lines, tab-separated
static void audit_write(const char *path, const std::string &shot)
{
    const Audit &A = audit();
    FILE *f = fopen(path, "a");
    if (!f)
        return;
    fprintf(f, "== %s\n", shot.c_str());
    for (const auto &c : A.cuts)
        fprintf(f, "CUT\t%s\n", c.c_str());
    if (getenv("NUI_TEXT_AUDIT_ALL"))       // (every text box, for a probe)
        for (const auto &t : A.texts)
            fprintf(f, "TEXT\t%s\t%.1f,%.1f %.1fx%.1f\n", t.s.c_str(), t.x0, t.y0, t.x1 - t.x0, t.y1 - t.y0);
    const float m = 1.0f;               // (a pixel's touch is not an overlap)
    const auto &T = A.texts;
    for (size_t i = 0; i < T.size(); i++)
        for (size_t j = i + 1; j < T.size(); j++) {
            const auto &p = T[i], &q = T[j];
            if (p.s == q.s && std::fabs(p.x0 - q.x0) < 3 && std::fabs(p.y0 - q.y0) < 3)
                continue;               // (the same text drawn twice: a shadow, an engraving)
            if (p.x0 + m < q.x1 && q.x0 + m < p.x1 && p.y0 + m < q.y1 && q.y0 + m < p.y1)
                fprintf(f, "OVERLAP\t%s\t%s\t%.0f,%.0f\n", p.s.c_str(), q.s.c_str(), p.x0, p.y0);
            // (two texts on one line closer than a space: read as one -- "LEVEL FEEDBACK")
            else if (std::fabs((p.y1 - p.y0) - (q.y1 - q.y0)) < 1 &&
                     std::min(p.y1, q.y1) - std::max(p.y0, q.y0) > 2.0f) {
                // (two texts of one size: a big number beside its name is set apart by its size)
                // (side by side, at all level with each other)
                const float gap = p.x0 < q.x0 ? q.x0 - p.x1 : p.x0 - q.x1;
                if (gap >= -m && gap < std::min(10.0f, 0.6f * (p.y1 - p.y0)))
                    fprintf(f, "CROWD\t%s\t%s\t%.0f,%.0f\tgap %.1f\n", p.s.c_str(), q.s.c_str(), p.x0, p.y0, gap);
            }
        }
    for (const auto &t : T) {
        // (the smallest box its centre is in: a button, a pocket, a plate)
        const float cx = (t.x0 + t.x1) / 2, cy = (t.y0 + t.y1) / 2;
        const Audit::Box *in = nullptr;
        for (const auto &b : A.boxes)
            if (cx >= b.x0 && cx <= b.x1 && cy >= b.y0 && cy <= b.y1 &&
                (!in || (b.x1 - b.x0) * (b.y1 - b.y0) < (in->x1 - in->x0) * (in->y1 - in->y0)))
                in = &b;
        if (in && (t.x0 < in->x0 - m || t.x1 > in->x1 + m || t.y0 < in->y0 - m || t.y1 > in->y1 + m))
            fprintf(f, "SPILL\t%s\t%.0f,%.0f\tbox %.0f,%.0f %.0fx%.0f\n", t.s.c_str(), t.x0, t.y0, in->x0, in->y0,
                    in->x1 - in->x0, in->y1 - in->y0);
    }
    fclose(f);
}

// ---- tests: the script's steps (NUI_SCRIPT)
struct Step {
    std::string op, arg;
    float x = 0, y = 0, x1 = 0, y1 = 0;
    int ms = 0;
};
// (a path from "~/": under HOME -- iOS's app container, where a test's script and shots go)
static std::string home_path(const std::string &p)
{
    const char *h = getenv("HOME");
    return p.rfind("~/", 0) == 0 && h ? std::string(h) + p.substr(1) : p;
}
static std::vector<Step> load_script(const char *path)
{
    std::vector<Step> out;
    std::ifstream f(path);
    std::string l;
    while (std::getline(f, l)) {
        std::istringstream s(l);
        Step st;
        s >> st.op;
        if (st.op == "wait")
            s >> st.ms;
        else if (st.op == "tap")
            s >> st.x >> st.y;
        else if (st.op == "drag")             // (drag X0 Y0 X1 Y1 MS: a finger down, moved there, up)
            s >> st.x >> st.y >> st.x1 >> st.y1 >> st.ms;
        else if (st.op == "press") {          // (press X Y MS: a finger held still there, then up -- a long-press)
            s >> st.x >> st.y >> st.ms;
            st.op = "drag";
            st.x1 = st.x;
            st.y1 = st.y;
        } else if (st.op == "fingers")          // (fingers N: N fingers resting -- fine mode at 2)
            s >> st.ms;
        else if (st.op == "shot")
            s >> st.arg;
        else if (st.op == "call")             // (call JSON: an API call, as a card makes it -- the rest of the line)
            std::getline(s >> std::ws, st.arg);
        if (!st.op.empty() && st.op[0] != '#')
            out.push_back(st);
    }
    return out;
}
}  // namespace nui

// THE SYSTEM's FILE PICKER (iOS's: the app shell's, ios/main.mm, defines
// these over the defaults here -- none elsewhere): whether there is one, open
// it for MIDI files, and take a file picked (copied into the app's own
// folders; its path into buf: 1, else 0)
extern "C" __attribute__((weak)) int nui_pick_available(void) { return 0; }
extern "C" __attribute__((weak)) void nui_pick_midi(void) {}
extern "C" __attribute__((weak)) int nui_pick_take(char *, int) { return 0; }

// THE WINDOW, on the calling thread until it closes: 0, or why it could not open
// (stopped: the host's own stop -- Ctrl-C, the engine ending -- asked each turn)
extern "C" int nui_run(nv_host *h, const char *fonts_dir, int windowed, int (*stopped)(void))
{
    using namespace nui;
    if (!SDL_Init(SDL_INIT_VIDEO)) {
        fprintf(stderr, "nvlive: --app: no window (%s)\n", SDL_GetError());
        return 1;
    }
    // (the window's size: NUI_SIZE=WxH, for the layouts of other screens -- the iPad mini's 1133x744)
    int ww = 1920, wh = 1080;
    if (const char *sz = getenv("NUI_SIZE"))
        sscanf(sz, "%dx%d", &ww, &wh);
    // (its graphics: OpenGL on Linux, Metal on macOS and iOS -- gfx.h)
    SDL_Window *win = gfx_window("Clavitone", ww, wh,
                                 SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY | (windowed ? 0 : SDL_WINDOW_FULLSCREEN));
    if (!win) {
        SDL_Quit();
        return 1;
    }
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO &io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.ConfigFlags |= ImGuiConfigFlags_NoMouseCursorChange;
    if (!gfx_init(win)) {
        fprintf(stderr, "nvlive: --app: its renderer would not start\n");
        SDL_DestroyWindow(win);
        SDL_Quit();
        return 1;
    }

    // THE FONT: code7, its wide glyphs merged in; small caps for the bold
    static Bdf c7, c7w, c7sc;
    auto load = [&](const char *name, Bdf &b) {
        std::ifstream f(std::string(fonts_dir) + "/" + name, std::ios::binary);
        std::stringstream ss;
        ss << f.rdbuf();
        return bdf_parse(ss.str(), b);
    };
    if (!load("code7.bdf", c7) || !load("code7sc.bdf", c7sc)) {
        fprintf(stderr, "nvlive: --app: code7's BDFs are not in %s\n", fonts_dir);
        return 1;
    }
    App a;
    a.h = h;
    a.ui_dir = std::string(fonts_dir).substr(0, std::string(fonts_dir).rfind('/'));
    a.w = nv_ui_watch_new();
    a.font = bdf_add(io.Fonts, &c7, "code7", false);
    if (load("code7w.bdf", c7w))
        bdf_add(io.Fonts, &c7w, "code7w", true);
    a.lcd = bdf_add(io.Fonts, &c7, "code7dots", false, BDF_DOTS);     // (the display's: its pixels dots)
    if (c7w.g.size())
        bdf_add(io.Fonts, &c7w, "code7wdots", true, BDF_DOTS);
    a.bold = bdf_add(io.Fonts, &c7sc, "code7sc", false);
    if (c7w.g.size())
        bdf_add(io.Fonts, &c7w, "code7w", true);
    io.FontDefault = a.font;

    // the engine's state, as the web page asks it at its start
    call(a, "{\"call\":\"hello\"}");
    if (const J *ps = call(a, "{\"call\":\"parts\"}").get("parts"))
        a.parts = *ps;

    const char *sp = getenv("NUI_SCRIPT");
    std::vector<Step> script = sp ? load_script(home_path(sp).c_str()) : std::vector<Step>();
    size_t si = 0;
    auto t_wait = std::chrono::steady_clock::now();
    int settle = 3;                         // (frames to draw after a change: ImGui's own state settles)
    int pending_up = 0;
    float tap_x = 0, tap_y = 0;
    // a scripted drag in progress: from, to, its frames left and all
    bool dragging = false;
    ImVec2 d0, d1;
    int dframes = 0, dleft = 0;
    int script_fingers = 0;
    std::string shot_path;                  // (a shot: the third frame drawn after its step, read before it is shown)
    int shot_in = 0;
    while (!a.quit && !(stopped && stopped())) {
        bool dirty = false;
        SDL_Event e;
        if (SDL_WaitEventTimeout(&e, 33)) {
            do {
                ImGui_ImplSDL3_ProcessEvent(&e);
                if (e.type == SDL_EVENT_QUIT || e.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED)
                    a.quit = true;
                // (the fingers down: a second one resting makes a drag fine)
                if (e.type == SDL_EVENT_FINGER_DOWN)
                    a.K.fingers++;
                else if ((e.type == SDL_EVENT_FINGER_UP || e.type == SDL_EVENT_FINGER_CANCELED) && a.K.fingers > 0)
                    a.K.fingers--;
                dirty = true;
            } while (SDL_PollEvent(&e));
        }
        if (poll(a))
            dirty = true;
        // the script's next step, when its wait is over
        if (dragging) {                     // (a scripted drag: a step of it each frame)
            const float t = 1.0f - (float)dleft / dframes;
            io.AddMousePosEvent(d0.x + (d1.x - d0.x) * t, d0.y + (d1.y - d0.y) * t);
            if (dleft-- <= 0) {
                io.AddMouseButtonEvent(0, false);
                dragging = false;
            }
            dirty = true;
        } else if (si < script.size() && std::chrono::steady_clock::now() >= t_wait && !pending_up && shot_path.empty()) {
            const Step &st = script[si++];
            if (st.op == "wait")
                t_wait = std::chrono::steady_clock::now() + std::chrono::milliseconds(st.ms);
            else if (st.op == "tap") {
                tap_x = a.org.x + st.x * a.k;
                tap_y = a.org.y + st.y * a.k;
                io.AddMousePosEvent(tap_x, tap_y);
                io.AddMouseButtonEvent(0, true);
                pending_up = 2;
            } else if (st.op == "drag") {
                d0 = ImVec2(a.org.x + st.x * a.k, a.org.y + st.y * a.k);
                d1 = ImVec2(a.org.x + st.x1 * a.k, a.org.y + st.y1 * a.k);
                io.AddMousePosEvent(d0.x, d0.y);
                io.AddMouseButtonEvent(0, true);
                dframes = dleft = std::max(2, st.ms / 16);
                dragging = true;
            } else if (st.op == "fingers") {
                a.K.fingers += st.ms - script_fingers;
                script_fingers = st.ms;
            } else if (st.op == "shot") {
                shot_path = home_path(st.arg);
                shot_in = 3;
            } else if (st.op == "call") {
                const J r = call(a, st.arg);
                fprintf(stderr, "nui: call %s -> %s\n", st.arg.c_str(), sess::dump(r).substr(0, 4000).c_str());
            } else if (st.op == "quit")
                a.quit = true;
            dirty = true;
        } else if (pending_up && --pending_up == 0) {
            io.AddMouseButtonEvent(0, false);
            dirty = true;
        }
        if (a.animate) {
            a.animate = false;
            dirty = true;
        }
        if (a.K.active && !a.K.moved && !a.K.long_fired)
            dirty = true;               // (a press held still: timed for its long-press)
        if (dirty)
            settle = 3;
        if (settle <= 0)
            continue;
        settle--;
        {                               // (the safe area: the screen's corners and home indicator kept clear)
            SDL_Rect r;
            if (const char *sa = getenv("NUI_SAFE"))
                sscanf(sa, "%d,%d,%d,%d", &r.x, &r.y, &r.w, &r.h);
            if ((getenv("NUI_SAFE") || SDL_GetWindowSafeArea(win, &r)) && r.w > 0 && r.h > 0) {
#if defined(__APPLE__) && TARGET_OS_IPHONE
                const float m = 12.0f;  // (an iPad's rounded corners: clear of their curve)
#else
                const float m = 0.0f;
#endif
                a.safe_x = r.x + m;
                a.safe_y = r.y + m;
                a.safe_w = r.w - 2 * m;
                a.safe_h = r.h - 2 * m;
            }
        }
        if (!gfx_begin(win, 0.106f, 0.114f, 0.125f)) {
            // (nothing to draw into -- in the background: no frame, and a rest,
            //  not a spin; drawn again when it comes back)
            SDL_Delay(100);
            settle = std::max(settle, 1);
            continue;
        }
        ImGui_ImplSDL3_NewFrame();
        ImGui::NewFrame();
        {
            Audit &A = audit();
            A.texts.clear();
            A.boxes.clear();
            A.cuts.clear();
        }
        draw(a);
        ImGui::Render();
        const bool shoot = !shot_path.empty() && --shot_in <= 0;
        if (shoot && audit().on)
            audit_write(getenv("NUI_TEXT_AUDIT"), shot_path);
        gfx_end(win, shoot ? shot_path.c_str() : nullptr);
        if (shoot)
            shot_path.clear();
    }
    nv_ui_watch_free(a.w);
    gfx_shutdown(win);
    ImGui::DestroyContext();
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
