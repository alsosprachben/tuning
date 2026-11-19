// gfx_metal.mm -- gfx.h on Metal (macOS, iOS): the window's Metal view and
// its CAMetalLayer, a command queue, and ImGui's Metal backend -- each frame
// a drawable cleared, ImGui's lists encoded on it, presented. A test's shot:
// the drawable blitted to a shared buffer before it is presented, read when
// the frame has run (BGRA to RGB, top row first)
#include "gfx.h"

#import <Metal/Metal.h>
#import <QuartzCore/QuartzCore.h>

#include <SDL3/SDL_metal.h>

#include <cstdio>
#include <vector>

#include "imgui.h"
#include "backends/imgui_impl_metal.h"
#include "backends/imgui_impl_sdl3.h"

namespace nui {

namespace {
SDL_MetalView view = nullptr;
CAMetalLayer *layer = nil;
id<MTLDevice> dev = nil;
id<MTLCommandQueue> queue = nil;
MTLRenderPassDescriptor *rpd = nil;
// (the frame under way: begun by gfx_begin, ended by gfx_end)
id<CAMetalDrawable> drawable = nil;
id<MTLCommandBuffer> cmd = nil;
id<MTLRenderCommandEncoder> enc = nil;
}  // namespace

SDL_Window *gfx_window(const char *title, int w, int h, SDL_WindowFlags flags)
{
    SDL_Window *win = SDL_CreateWindow(title, w, h, flags | SDL_WINDOW_METAL);
    if (!win) {
        fprintf(stderr, "nvlive: --app: no window (%s)\n", SDL_GetError());
        return nullptr;
    }
    view = SDL_Metal_CreateView(win);
    layer = view ? (__bridge CAMetalLayer *)SDL_Metal_GetLayer(view) : nil;
    dev = MTLCreateSystemDefaultDevice();
    if (!layer || !dev) {
        fprintf(stderr, "nvlive: --app: no Metal (%s)\n", SDL_GetError());
        if (view)
            SDL_Metal_DestroyView(view);
        view = nullptr;
        SDL_DestroyWindow(win);
        return nullptr;
    }
    layer.device = dev;
    layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
    layer.framebufferOnly = NO;             // (a test's shot blits from it)
    queue = [dev newCommandQueue];
    rpd = [MTLRenderPassDescriptor new];
    return win;
}

bool gfx_init(SDL_Window *win)
{
    return ImGui_ImplSDL3_InitForMetal(win) && ImGui_ImplMetal_Init(dev);
}

void gfx_begin(SDL_Window *win, float r, float g, float b)
{
    int w, h;
    SDL_GetWindowSizeInPixels(win, &w, &h);
    layer.drawableSize = CGSizeMake(w, h);
    drawable = [layer nextDrawable];
    cmd = [queue commandBuffer];
    rpd.colorAttachments[0].clearColor = MTLClearColorMake(r, g, b, 1.0);
    rpd.colorAttachments[0].texture = drawable.texture;
    rpd.colorAttachments[0].loadAction = MTLLoadActionClear;
    rpd.colorAttachments[0].storeAction = MTLStoreActionStore;
    enc = [cmd renderCommandEncoderWithDescriptor:rpd];
    ImGui_ImplMetal_NewFrame(rpd);
}

void gfx_end(SDL_Window *, const char *shot)
{
    ImGui_ImplMetal_RenderDrawData(ImGui::GetDrawData(), cmd, enc);
    [enc endEncoding];
    id<MTLBuffer> buf = nil;
    const NSUInteger w = drawable.texture.width, h = drawable.texture.height;
    if (shot && drawable) {
        buf = [dev newBufferWithLength:w * h * 4 options:MTLResourceStorageModeShared];
        id<MTLBlitCommandEncoder> bl = [cmd blitCommandEncoder];
        [bl copyFromTexture:drawable.texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0)
                 sourceSize:MTLSizeMake(w, h, 1) toBuffer:buf destinationOffset:0 destinationBytesPerRow:w * 4
          destinationBytesPerImage:w * h * 4];
        [bl endEncoding];
    }
    if (drawable)
        [cmd presentDrawable:drawable];
    [cmd commit];
    if (buf) {
        [cmd waitUntilCompleted];
        const unsigned char *src = (const unsigned char *)buf.contents;
        std::vector<unsigned char> row(w * 3);
        if (FILE *f = fopen(shot, "wb")) {
            fprintf(f, "P6\n%d %d\n255\n", (int)w, (int)h);
            for (NSUInteger y = 0; y < h; y++) {
                for (NSUInteger x = 0; x < w; x++) {
                    const unsigned char *p = src + (y * w + x) * 4;     // (B, G, R, A)
                    row[x * 3] = p[2];
                    row[x * 3 + 1] = p[1];
                    row[x * 3 + 2] = p[0];
                }
                fwrite(row.data(), 1, row.size(), f);
            }
            fclose(f);
        }
    }
    drawable = nil;
    cmd = nil;
    enc = nil;
}

void gfx_shutdown(SDL_Window *)
{
    ImGui_ImplMetal_Shutdown();
    ImGui_ImplSDL3_Shutdown();
    if (view)
        SDL_Metal_DestroyView(view);
    view = nullptr;
    layer = nil;
    queue = nil;
    dev = nil;
    rpd = nil;
}

}  // namespace nui
