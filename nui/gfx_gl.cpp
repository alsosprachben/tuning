// gfx_gl.cpp -- gfx.h on OpenGL 3.3 core (Linux; macOS's too, where asked):
// the few GL calls of our own looked up at run time as ImGui's backend does
// (no link to a GL library: the system's, whatever SDL opened)
#include "gfx.h"

#include <SDL3/SDL_opengl.h>

#include <cstdio>
#include <vector>

#include "imgui.h"
#include "backends/imgui_impl_opengl3.h"
#include "backends/imgui_impl_sdl3.h"

namespace nui {

namespace {
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
Gl gl;
SDL_GLContext glc = nullptr;
}  // namespace

SDL_Window *gfx_window(const char *title, int w, int h, SDL_WindowFlags flags)
{
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
#ifdef __APPLE__
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_FLAGS, SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG);     // (macOS's core 3.3: only so)
#endif
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_Window *win = SDL_CreateWindow(title, w, h, flags | SDL_WINDOW_OPENGL);
    if (!win) {
        fprintf(stderr, "nvlive: --app: no window (%s)\n", SDL_GetError());
        return nullptr;
    }
    glc = SDL_GL_CreateContext(win);
    if (!glc || !(SDL_GL_MakeCurrent(win, glc), gl.load())) {
        fprintf(stderr, "nvlive: --app: no OpenGL 3.3 (%s)\n", SDL_GetError());
        SDL_DestroyWindow(win);
        return nullptr;
    }
    SDL_GL_SetSwapInterval(1);
    return win;
}

bool gfx_init(SDL_Window *win)
{
    return ImGui_ImplSDL3_InitForOpenGL(win, glc) && ImGui_ImplOpenGL3_Init("#version 330");
}

void gfx_begin(SDL_Window *, float r, float g, float b)
{
    ImGui_ImplOpenGL3_NewFrame();
    gl.ClearColor(r, g, b, 1.0f);
}

void gfx_end(SDL_Window *win, const char *shot)
{
    int w, h;
    SDL_GetWindowSizeInPixels(win, &w, &h);
    gl.Viewport(0, 0, w, h);
    gl.Clear(GL_COLOR_BUFFER_BIT);
    ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
    if (shot) {
        std::vector<unsigned char> px((size_t)w * h * 3);
        gl.PixelStorei(GL_PACK_ALIGNMENT, 1);
        gl.ReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE, px.data());
        if (FILE *f = fopen(shot, "wb")) {
            fprintf(f, "P6\n%d %d\n255\n", w, h);
            for (int y = h - 1; y >= 0; y--)
                fwrite(&px[(size_t)y * w * 3], 1, (size_t)w * 3, f);
            fclose(f);
        }
    }
    SDL_GL_SwapWindow(win);
}

void gfx_shutdown(SDL_Window *)
{
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplSDL3_Shutdown();
    SDL_GL_DestroyContext(glc);
    glc = nullptr;
}

}  // namespace nui
