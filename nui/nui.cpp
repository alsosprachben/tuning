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
#include <SDL3/SDL_opengl.h>

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
#include "backends/imgui_impl_opengl3.h"
#include "backends/imgui_impl_sdl3.h"

#include "../native/host.h"
#include "../native/session.h"
#include "bdf.h"

namespace nui {

using J = sess::J;

// THE FEW GL CALLS OF OUR OWN, looked up at run time as ImGui's backend does
// (no link to a GL library: the system's, whatever SDL opened)
struct Gl {
    void (*Viewport)(GLint, GLint, GLsizei, GLsizei) = nullptr;
    void (*ClearColor)(GLfloat, GLfloat, GLfloat, GLfloat) = nullptr;
    void (*Clear)(GLbitfield) = nullptr;
    void (*PixelStorei)(GLenum, GLint) = nullptr;
    void (*ReadPixels)(GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, void *) = nullptr;
    bool load()
    {
        Viewport = (decltype(Viewport))SDL_GL_GetProcAddress("glViewport");
        ClearColor = (decltype(ClearColor))SDL_GL_GetProcAddress("glClearColor");
        Clear = (decltype(Clear))SDL_GL_GetProcAddress("glClear");
        PixelStorei = (decltype(PixelStorei))SDL_GL_GetProcAddress("glPixelStorei");
        ReadPixels = (decltype(ReadPixels))SDL_GL_GetProcAddress("glReadPixels");
        return Viewport && ClearColor && Clear && PixelStorei && ReadPixels;
    }
};
static Gl gl;

// THE FRONT PANEL's COLOURS (ui/style.css's tokens)
static const ImU32 PANEL = IM_COL32(0x23, 0x26, 0x2a, 255), PANEL_HI = IM_COL32(0x2e, 0x32, 0x37, 255),
                   EDGE = IM_COL32(0x12, 0x14, 0x17, 255), SILK = IM_COL32(0xc9, 0xcd, 0xc8, 255),
                   SILK_DIM = IM_COL32(0x8a, 0x91, 0x8b, 255), LCD = IM_COL32(0xf0, 0xb1, 0x3a, 255),
                   LCD_BG = IM_COL32(0x2a, 0x1d, 0x06, 255), LCD_DIM = IM_COL32(0x6b, 0x4c, 0x14, 255),
                   OWN = IM_COL32(0xf0, 0x8a, 0x3c, 255), BAD = IM_COL32(0xe0, 0x53, 0x3c, 255),
                   PAGE = IM_COL32(0x1b, 0x1d, 0x20, 255);

static const char *FAMILIES[16] = {"PIANO", "CHROMATIC PERC.", "ORGAN", "GUITAR", "BASS", "STRINGS", "ENSEMBLE",
                                   "BRASS", "REED", "PIPE", "SYNTH LEAD", "SYNTH PAD", "SYNTH EFFECTS", "ETHNIC",
                                   "PERCUSSIVE", "SOUND EFFECTS"};
static const char *CARDS[][2] = {{"parts", "PARTS"}, {"library", "LIBRARY"}, {"synth", "SYNTH"}, {"stops", "STOPS"},
                                 {"piano", "PIANO"}, {"drums", "DRUMS"}, {"effects", "EFFECTS"}, {"matrix", "MATRIX"},
                                 {"tuning", "TUNING"}, {"control", "CONTROL"}, {"scenes", "SCENES"},
                                 {"files", "FILES"}, {"setup", "SETUP"}};

struct App {
    nv_host *h = nullptr;
    nv_ui_watch *w = nullptr;
    ImFont *font = nullptr, *bold = nullptr;
    float k = 1.0f;                     // design units (1920x1080) to pixels
    ImVec2 org{0, 0};
    J parts, meters, build;
    int row = 0;
    std::string card = "parts";
    std::string last_meters;
    bool quit = false;
    double quit_armed = -10.0;           // (QUIT's first tap: a second within 3 s quits)
};

// THE ENGINE's CALLS (uiapi's): a request, its answer
static J call(App &a, const std::string &req)
{
    J r;
    if (char *s = nv_ui_call(a.h, a.w, req.c_str())) {
        sess::parse(s, r);
        nv_ui_free(s);
    }
    return r;
}

// ...and its pushes: true if the screen should change
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
    if (const J *x = m.get("parts")) {
        a.parts = *x;
        changed = true;
    }
    return changed;
}

static const J *part(const App &a, int r)
{
    return a.parts.is(J::ARR) && r >= 0 && r < (int)a.parts.a.size() ? &a.parts.a[(size_t)r] : nullptr;
}
static double num(const J *o, const char *k, double d = 0.0)
{
    const J *x = o ? o->get(k) : nullptr;
    return x ? x->d(d) : d;
}
static bool flag(const J *o, const char *k)
{
    const J *x = o ? o->get(k) : nullptr;
    return x && x->d(0.0) != 0.0;
}
static std::string str(const J *o, const char *k)
{
    const J *x = o ? o->get(k) : nullptr;
    return x && x->is(J::STR) ? x->s : std::string();
}

// ---- drawing, in design units
static ImVec2 P(const App &a, float x, float y) { return ImVec2(std::floor(a.org.x + x * a.k), std::floor(a.org.y + y * a.k)); }
static float px(const App &a, float size)           // (code7's sizes: whole multiples of its 7 pixels)
{
    const float p = size * a.k;
    return std::max(7.0f, 7.0f * std::floor(p / 7.0f + 0.5f));
}
static void text(App &a, ImFont *f, float size, float x, float y, ImU32 col, const std::string &s)
{
    ImGui::GetWindowDrawList()->AddText(f, px(a, size), P(a, x, y), col, s.c_str());
}
static float text_w(App &a, ImFont *f, float size, const std::string &s)
{
    return f->CalcTextSizeA(px(a, size), FLT_MAX, 0.0f, s.c_str()).x / a.k;
}
static void rect(App &a, float x, float y, float w, float h, ImU32 col, float r = 6.0f)
{
    ImGui::GetWindowDrawList()->AddRectFilled(P(a, x, y), P(a, x + w, y + h), col, r * a.k);
}
static void frame(App &a, float x, float y, float w, float h, ImU32 col, float r = 6.0f, float t = 1.5f)
{
    ImGui::GetWindowDrawList()->AddRect(P(a, x, y), P(a, x + w, y + h), col, r * a.k, 0, t * a.k);
}

// A BUTTON (the web's .hb): acts on release over it, as the touch kit's
static bool button(App &a, const char *id, float x, float y, float w, float h, const std::string &label, bool on = false,
                   bool enabled = true)
{
    ImGui::SetCursorScreenPos(P(a, x, y));
    ImGui::PushID(id);
    const bool hit = ImGui::InvisibleButton("b", ImVec2(w * a.k, h * a.k)) && enabled;
    const bool held = ImGui::IsItemActive();
    ImGui::PopID();
    rect(a, x, y, w, h, on ? LCD : held ? PANEL_HI : IM_COL32(0x26, 0x2a, 0x2e, 255), 8.0f);
    frame(a, x, y, w, h, EDGE, 8.0f, 1.0f);
    const float tw = text_w(a, a.bold, 14, label);
    text(a, a.bold, 14, x + (w - tw) / 2, y + (h - 14) / 2, on ? PANEL : enabled ? SILK : SILK_DIM, label);
    return hit;
}

static std::string pad2(int n)
{
    char b[16];
    snprintf(b, sizeof b, "%02d", n);
    return b;
}

// THE DISPLAY (the web's #lcd): the part, its program, its fields, the meters
static void draw_display(App &a)
{
    const float X = 26, Y = 22, W = 1424, H = 232;
    rect(a, X - 8, Y - 8, W + 16, H + 16, IM_COL32(0x16, 0x18, 0x1b, 255), 10.0f);
    rect(a, X, Y, W, H, LCD_BG, 4.0f);
    const J *p = part(a, a.row);
    // the part, its program, its family and channel
    text(a, a.font, 14, X + 14, Y + 14, LCD, "PART");
    std::string fam;
    if (p) {
        const int prog = (int)num(p, "program"), var = (int)num(p, "variation"), ch = (int)num(p, "channel", -1);
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
    text(a, a.font, 35, X + 92, Y + 34, LCD, p ? str(p, "name") : "");
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
    static const char *LABELS[7] = {"LEVEL", "PAN", "REVERB", "CHORUS", "DELAY", "KEY", "CH"};
    std::string vals[7];
    if (p) {
        char v[32];
        const double db = num(p, "level_db");
        snprintf(v, sizeof v, "%s%.1f", db > 0 ? "+" : "", db);
        vals[0] = v;
        const int pan = (int)num(p, "pan", 64);
        vals[1] = pan < 64 ? "L" + std::to_string(64 - pan) : pan > 64 ? "R" + std::to_string(pan - 64) : "C";
        vals[2] = std::to_string((int)num(p, "reverb", 40));
        vals[3] = std::to_string((int)num(p, "chorus"));
        vals[4] = std::to_string((int)num(p, "delay"));
        const int t = (int)num(p, "transpose");
        vals[5] = (t > 0 ? "+" : "") + std::to_string(t);
        const int ch = (int)num(p, "channel", -1);
        vals[6] = ch < 0 ? "ALL" : std::to_string(ch + 1);
    }
    const float fw = (W - 28 - 6 * 8) / 7.0f;
    for (int i = 0; i < 7; i++) {
        const float fx = X + 14 + i * (fw + 8), fy = Y + 80;
        const bool sel = i == 0;
        rect(a, fx, fy, fw, 52, sel ? LCD : IM_COL32(0x33, 0x24, 0x08, 255), 3.0f);
        frame(a, fx, fy, fw, 52, LCD_DIM, 3.0f, 1.0f);
        text(a, a.font, 14, fx + 10, fy + 6, sel ? LCD_BG : LCD, LABELS[i]);
        text(a, a.font, 21, fx + 10, fy + 24, sel ? LCD_BG : LCD, vals[i]);
    }
    // the meters: sixteen channels, ten steps of 4 dB from -40
    const J *bars = m ? m->get("bars") : nullptr;
    const float mx = X + 14, my = Y + 144, mw = (W - 28) / 16.0f;
    for (int ch = 0; ch < 16; ch++) {
        const double db = bars && bars->is(J::ARR) && ch < (int)bars->a.size() ? bars->a[(size_t)ch].d(-120) : -120;
        const int lit = (int)std::lround((db + 40) / 40 * 10);
        for (int s = 0; s < 10; s++) {
            const float sy = my + 54 - s * 6;
            rect(a, mx + ch * mw + 4, sy, mw - 8, 4, s < lit ? LCD : IM_COL32(0x3a, 0x29, 0x0b, 255), 0.0f);
        }
        const std::string n = std::to_string(ch + 1);
        text(a, a.font, 14, mx + ch * mw + (mw - text_w(a, a.font, 14, n)) / 2, my + 64, LCD, n);
    }
}

// THE PANEL's KEYS (the web's part, mute, solo, panic)
static void draw_keys(App &a)
{
    const J *p = part(a, a.row);
    const int n = a.parts.is(J::ARR) ? (int)a.parts.a.size() : 0;
    const float X = 1466, Y = 22;
    if (button(a, "prev", X, Y, 118, 48, "\xe2\x97\x80 PART", false, a.row > 0) && a.row > 0) {
        a.row--;
        call(a, "{\"call\":\"select\",\"row\":" + std::to_string(a.row) + ",\"layer\":0}");
    }
    if (button(a, "next", X + 128, Y, 118, 48, "PART \xe2\x96\xb6", false, a.row + 1 < n) && a.row + 1 < n) {
        a.row++;
        call(a, "{\"call\":\"select\",\"row\":" + std::to_string(a.row) + ",\"layer\":0}");
    }
    if (button(a, "mute", X, Y + 58, 118, 48, "MUTE", flag(p, "muted")) && p) {
        call(a, "{\"call\":\"part_set\",\"row\":" + std::to_string(a.row) + ",\"muted\":" + (flag(p, "muted") ? "0" : "1") + "}");
        J r = call(a, "{\"call\":\"parts\"}");
        if (const J *ps = r.get("parts"))
            a.parts = *ps;
    }
    if (button(a, "solo", X + 128, Y + 58, 118, 48, "SOLO", num(p, "solo") == 1) && p) {
        call(a, "{\"call\":\"part_solo\",\"row\":" + std::to_string(a.row) + "}");
        J r = call(a, "{\"call\":\"parts\"}");
        if (const J *ps = r.get("parts"))
            a.parts = *ps;
    }
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
}

// THE CARD TABS, and the card (each built from the web's in turn)
static void draw_cards(App &a)
{
    const int nc = (int)(sizeof CARDS / sizeof CARDS[0]);
    const float X = 14, Y = 276, gap = 8, w = (1892 - gap * nc - 56) / nc;
    for (int i = 0; i < nc; i++)
        if (button(a, CARDS[i][0], X + i * (w + gap), Y, w, 46, CARDS[i][1], a.card == CARDS[i][0]))
            a.card = CARDS[i][0];
    button(a, "help", X + nc * (w + gap), Y, 56, 46, "?");
    rect(a, 14, 338, 1892, 728, PANEL, 10.0f);
    std::string title;
    for (int i = 0; i < nc; i++)
        if (a.card == CARDS[i][0])
            title = CARDS[i][1];
    text(a, a.bold, 14, 34, 356, SILK, title);
    text(a, a.font, 21, 34, 400, SILK_DIM, "Not built in the native interface yet: the web interface has it (nvlive --ui).");
}

static void draw(App &a)
{
    const ImGuiIO &io = ImGui::GetIO();
    a.k = std::min(io.DisplaySize.x / 1920.0f, io.DisplaySize.y / 1080.0f);
    a.org = ImVec2(std::floor((io.DisplaySize.x - 1920 * a.k) / 2), std::floor((io.DisplaySize.y - 1080 * a.k) / 2));
    ImGui::SetNextWindowPos(ImVec2(0, 0));
    ImGui::SetNextWindowSize(io.DisplaySize);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(0, 0));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
    ImGui::PushStyleColor(ImGuiCol_WindowBg, ImGui::ColorConvertU32ToFloat4(PAGE));
    ImGui::Begin("clavitone", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove |
                                            ImGuiWindowFlags_NoBringToFrontOnFocus | ImGuiWindowFlags_NoScrollWithMouse);
    // (the bitmap font's pixels sampled as pixels)
    ImGui::GetWindowDrawList()->AddCallback(ImGui::GetPlatformIO().DrawCallback_SetSamplerNearest, nullptr);
    draw_display(a);
    draw_keys(a);
    draw_cards(a);
    ImGui::End();
    ImGui::PopStyleColor();
    ImGui::PopStyleVar(2);
}

// ---- tests: the script's steps (NUI_SCRIPT)
struct Step {
    std::string op, arg;
    float x = 0, y = 0;
    int ms = 0;
};
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
        else if (st.op == "shot")
            s >> st.arg;
        if (!st.op.empty() && st.op[0] != '#')
            out.push_back(st);
    }
    return out;
}
static void shot(const char *path, int w, int h)
{
    std::vector<unsigned char> px((size_t)w * h * 3);
    gl.PixelStorei(GL_PACK_ALIGNMENT, 1);
    gl.ReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE, px.data());
    if (FILE *f = fopen(path, "wb")) {
        fprintf(f, "P6\n%d %d\n255\n", w, h);
        for (int y = h - 1; y >= 0; y--)
            fwrite(&px[(size_t)y * w * 3], 1, (size_t)w * 3, f);
        fclose(f);
    }
}

}  // namespace nui

// THE WINDOW, on the calling thread until it closes: 0, or why it could not open
extern "C" int nui_run(nv_host *h, const char *fonts_dir, int windowed)
{
    using namespace nui;
    if (!SDL_Init(SDL_INIT_VIDEO)) {
        fprintf(stderr, "nvlive: --app: no window (%s)\n", SDL_GetError());
        return 1;
    }
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_Window *win = SDL_CreateWindow("Clavitone", 1920, 1080,
                                       SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY |
                                           (windowed ? 0 : SDL_WINDOW_FULLSCREEN));
    if (!win) {
        fprintf(stderr, "nvlive: --app: no window (%s)\n", SDL_GetError());
        SDL_Quit();
        return 1;
    }
    SDL_GLContext glc = SDL_GL_CreateContext(win);
    if (!glc || !(SDL_GL_MakeCurrent(win, glc), gl.load())) {
        fprintf(stderr, "nvlive: --app: no OpenGL 3.3 (%s)\n", SDL_GetError());
        SDL_DestroyWindow(win);
        SDL_Quit();
        return 1;
    }
    SDL_GL_SetSwapInterval(1);
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO &io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.ConfigFlags |= ImGuiConfigFlags_NoMouseCursorChange;
    ImGui_ImplSDL3_InitForOpenGL(win, glc);
    ImGui_ImplOpenGL3_Init("#version 330");

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
    a.w = nv_ui_watch_new();
    a.font = bdf_add(io.Fonts, &c7, "code7", false);
    if (load("code7w.bdf", c7w))
        bdf_add(io.Fonts, &c7w, "code7w", true);
    a.bold = bdf_add(io.Fonts, &c7sc, "code7sc", false);
    if (c7w.g.size())
        bdf_add(io.Fonts, &c7w, "code7w", true);
    io.FontDefault = a.font;

    // the engine's state, as the web page asks it at its start
    call(a, "{\"call\":\"hello\"}");
    if (const J *ps = call(a, "{\"call\":\"parts\"}").get("parts"))
        a.parts = *ps;

    const char *sp = getenv("NUI_SCRIPT");
    std::vector<Step> script = sp ? load_script(sp) : std::vector<Step>();
    size_t si = 0;
    auto t_wait = std::chrono::steady_clock::now();
    int settle = 3;                         // (frames to draw after a change: ImGui's own state settles)
    int pending_up = 0;
    float tap_x = 0, tap_y = 0;
    std::string shot_path;                  // (a shot: the next frame drawn, read before it is shown)
    while (!a.quit) {
        bool dirty = false;
        SDL_Event e;
        if (SDL_WaitEventTimeout(&e, 33)) {
            do {
                ImGui_ImplSDL3_ProcessEvent(&e);
                if (e.type == SDL_EVENT_QUIT || e.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED)
                    a.quit = true;
                dirty = true;
            } while (SDL_PollEvent(&e));
        }
        if (poll(a))
            dirty = true;
        // the script's next step, when its wait is over
        if (si < script.size() && std::chrono::steady_clock::now() >= t_wait && !pending_up && shot_path.empty()) {
            const Step &st = script[si++];
            if (st.op == "wait")
                t_wait = std::chrono::steady_clock::now() + std::chrono::milliseconds(st.ms);
            else if (st.op == "tap") {
                tap_x = a.org.x + st.x * a.k;
                tap_y = a.org.y + st.y * a.k;
                io.AddMousePosEvent(tap_x, tap_y);
                io.AddMouseButtonEvent(0, true);
                pending_up = 2;
            } else if (st.op == "shot") {
                shot_path = st.arg;
            } else if (st.op == "quit")
                a.quit = true;
            dirty = true;
        } else if (pending_up && --pending_up == 0) {
            io.AddMouseButtonEvent(0, false);
            dirty = true;
        }
        if (dirty)
            settle = 3;
        if (settle <= 0)
            continue;
        settle--;
        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplSDL3_NewFrame();
        ImGui::NewFrame();
        draw(a);
        ImGui::Render();
        int w, hh;
        SDL_GetWindowSizeInPixels(win, &w, &hh);
        gl.Viewport(0, 0, w, hh);
        gl.ClearColor(0.106f, 0.114f, 0.125f, 1.0f);
        gl.Clear(GL_COLOR_BUFFER_BIT);
        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
        if (!shot_path.empty() && settle == 0) {
            shot(shot_path.c_str(), w, hh);
            shot_path.clear();
        }
        SDL_GL_SwapWindow(win);
    }
    nv_ui_watch_free(a.w);
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplSDL3_Shutdown();
    ImGui::DestroyContext();
    SDL_GL_DestroyContext(glc);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
