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
#include "matrix.h"
#include "tuning.h"
#include "control.h"
#include "scenes.h"
#include "files.h"
#include "setup.h"
#include "help.h"
#include "sheet.h"

namespace nui {

static const char *CARDS[][2] = {{"parts", "PARTS"}, {"library", "LIBRARY"}, {"synth", "SYNTH"}, {"stops", "STOPS"},
                                 {"piano", "PIANO"}, {"drums", "DRUMS"}, {"effects", "EFFECTS"}, {"matrix", "MATRIX"},
                                 {"tuning", "TUNING"}, {"control", "CONTROL"}, {"scenes", "SCENES"},
                                 {"files", "FILES"}, {"setup", "SETUP"}};

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

static void draw(App &a)
{
    const ImGuiIO &io = ImGui::GetIO();
    // THE LAYOUT: the iPad's where the screen is its shape (narrower than 16:10.5) or NUI_LAYOUT=ipad says so
    {
        const char *lay = getenv("NUI_LAYOUT");
        a.tab = lay ? !strcmp(lay, "ipad") : io.DisplaySize.x / std::max(1.0f, io.DisplaySize.y) < 1.65f;
        a.W = a.tab ? 1133.0f : 1920.0f;
        a.H = a.tab ? 744.0f : 1080.0f;
        a.ts = a.tab ? 0.5f : 1.0f;
    }
    a.k = std::min(io.DisplaySize.x / a.W, io.DisplaySize.y / a.H);
    a.K.k = a.k;
    a.org = ImVec2(std::floor((io.DisplaySize.x - a.W * a.k) / 2), std::floor((io.DisplaySize.y - a.H * a.k) / 2));
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
    if (a.tab) {                        // THE iPad's: the panel shorter, the tabs 44 points tall, the card below
        draw_display_tab(a);
        draw_keys_tab(a);
        const float X = 10, Y = 160, gap = 4, w = (1113 - gap * nc - 44) / nc;
        for (int i = 0; i < nc; i++)
            if (button(a, CARDS[i][0], X + i * (w + gap), Y, w, 44, CARDS[i][1], a.card == CARDS[i][0], true, 21))
                a.card = CARDS[i][0];
        if (button(a, "help", X + nc * (w + gap), Y, 44, 44, "?", false, true, 21))
            help_open(a, "basics");
        rect(a, 10, 210, 1113, 524, PANEL, 6.0f);
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
        rect(a, 14, 338, 1892, 728, PANEL, 10.0f);
    }
    piano_card(a, a.card == "piano");   // (the engine pushes the pedals only while it is open)
    drums_card(a, a.card == "drums");   // (...and the kit and its hits)
    effects_card(a, a.card == "effects");
    matrix_card(a, a.card == "matrix");
    tuning_card(a, a.card == "tuning");
    control_card(a, a.card == "control");
    scenes_card(a, a.card == "scenes");
    files_card(a, a.card == "files");
    setup_card(a, a.card == "setup");
    // (on the iPad, a card not yet laid out for it says so)
    static const std::set<std::string> TAB_READY = {"parts", "library", "synth", "stops", "piano", "drums", "effects", "matrix", "tuning", "control", "scenes"};
    if (a.tab && !TAB_READY.count(a.card)) {
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

// ---- tests: the script's steps (NUI_SCRIPT)
struct Step {
    std::string op, arg;
    float x = 0, y = 0, x1 = 0, y1 = 0;
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
// (stopped: the host's own stop -- Ctrl-C, the engine ending -- asked each turn)
extern "C" int nui_run(nv_host *h, const char *fonts_dir, int windowed, int (*stopped)(void))
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
    // (the window's size: NUI_SIZE=WxH, for the layouts of other screens -- the iPad mini's 1133x744)
    int ww = 1920, wh = 1080;
    if (const char *sz = getenv("NUI_SIZE"))
        sscanf(sz, "%dx%d", &ww, &wh);
    SDL_Window *win = SDL_CreateWindow("Clavitone", ww, wh,
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
    a.ui_dir = std::string(fonts_dir).substr(0, std::string(fonts_dir).rfind('/'));
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
                shot_path = st.arg;
                shot_in = 3;
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
        if (!shot_path.empty() && --shot_in <= 0) {
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
