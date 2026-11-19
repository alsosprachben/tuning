// gfx.h -- THE NATIVE INTERFACE's GRAPHICS, behind four calls: OpenGL 3.3 on
// Linux (gfx_gl.cpp), Metal on macOS and iOS (gfx_metal.mm -- iOS has no
// OpenGL worth the name). The window is made here, as its API wants it; ImGui's
// platform half (SDL3) and renderer half started on it; each frame begun
// with its clear colour and ended presented, its pixels saved first where a
// test asked (a PPM, top row first).
#pragma once
#include <SDL3/SDL.h>

namespace nui {

// the window (title, size in points, SDL's flags beside the API's own): NULL
// and why on stderr if it could not be made
SDL_Window *gfx_window(const char *title, int w, int h, SDL_WindowFlags flags);
// ImGui's backends on it (after ImGui::CreateContext): false if not
bool gfx_init(SDL_Window *win);
// a frame: begun (the renderer's NewFrame, its target cleared to rgb), then
// ended -- shot non-NULL: its pixels into that PPM -- and presented
void gfx_begin(SDL_Window *win, float r, float g, float b);
void gfx_end(SDL_Window *win, const char *shot);
void gfx_shutdown(SDL_Window *win);

}  // namespace nui
