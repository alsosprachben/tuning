// room.cpp -- the native engine's ROOM: the image sources of a source in it.
//
// SynthProperties.image_sources, as _images_for packs it for roomcore.c:
// every image up to `order` bounces, breadth first, a sequence never
// bouncing off the wall it just left, each image kept only the first time
// its POSITION is reached (to 4 decimals, Python's round) -- and with it the
// listener mirrored in the reverse order, the direction the ray departed in.
//
// Walls in WALLS' order (left, right, back, front, floor, ceiling), each an
// axis and a signed plane: -room_left, room_right, -room_back, room_front,
// -room_floor, room_ceiling.

#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#include <vector>

namespace nv {

static const int WALL_AXIS[6] = {0, 0, 1, 1, 2, 2};

// Python's tuple(round(v, 4) for v in p), as a key: glibc's %.4f is the
// correctly rounded decimal, as round() is; -0.0 and 0.0 are one key there
static std::string pos_key(const double *p)
{
    std::string k;
    char b[64];
    for (int i = 0; i < 3; i++) {
        snprintf(b, sizeof b, "%.4f,", p[i]);
        if (!strcmp(b, "-0.0000,"))
            strcpy(b, "0.0000,");
        k += b;
    }
    return k;
}

struct Image {
    std::vector<int> seq;
    double im[3];
};

}  // namespace nv

extern "C" {

// The images of a source at (sx, sy, sz) in a room whose walls stand at
// planes[6]: up to cap of them. nsurf[i] the bounces of image i, surf its
// walls in order (cap * order), img and mir 3 each. Returns the images, -1
// if more than cap.
int nv_images(const double *planes, int order, double sx, double sy, double sz, int cap,
              int *nsurf, int *surf, double *img, double *mir)
{
    using namespace nv;
    if (order <= 0)
        return 0;
    std::set<std::string> seen;
    double s0[3] = {sx, sy, sz};
    seen.insert(pos_key(s0));
    std::vector<Image> frontier(1);
    memcpy(frontier[0].im, s0, sizeof s0);
    int n = 0, ns = 0;
    for (int o = 0; o < order; o++) {
        std::vector<Image> nxt;
        for (const Image &f : frontier) {
            for (int w = 0; w < 6; w++) {
                if (!f.seq.empty() && f.seq.back() == w)
                    continue;
                Image g;
                g.seq = f.seq;
                g.seq.push_back(w);
                memcpy(g.im, f.im, sizeof g.im);
                g.im[WALL_AXIS[w]] = 2.0 * planes[w] - g.im[WALL_AXIS[w]];
                std::string key = pos_key(g.im);
                if (!seen.insert(key).second)
                    continue;
                if (n >= cap)
                    return -1;
                double lis[3] = {0.0, 0.0, 0.0};
                for (int j = (int)g.seq.size() - 1; j >= 0; j--) {
                    int b = g.seq[j];
                    lis[WALL_AXIS[b]] = 2.0 * planes[b] - lis[WALL_AXIS[b]];
                }
                nsurf[n] = (int)g.seq.size();
                for (int b : g.seq)
                    surf[ns++] = b;
                memcpy(img + 3 * n, g.im, sizeof g.im);
                memcpy(mir + 3 * n, lis, sizeof lis);
                n++;
                nxt.push_back(g);
            }
        }
        frontier.swap(nxt);
    }
    return n;
}

}  // extern "C"
