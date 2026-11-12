// gsdisplay.h -- the Sound Canvas's display, as gsdisplay.py reads it.
//
// The text and 16 x 16 dot pages a GS file writes to the module's LCD (a DT1
// to model 45H at 10 00 00, 10 0p xx, 10 20 00/01: the SC-88 Pro's manual,
// Appendix, "Display data"): parsed, kept, and shown -- by nvlive's panel
// (slab.cpp's part, nv_part_display) and as text beside a render
// (nvrender's OUT.display.txt, gsdisplay.timeline's lines). The sound is
// untouched.

#ifndef NV_GSDISPLAY_H
#define NV_GSDISPLAY_H

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace gsd {

struct Display {
    uint8_t mem[5][128] = {};
    int steps = 6;                          // the display time, 0.48 s a step (2.88 s)
    std::string text;
    double text_at = -1.0, page_at = -1.0;  // (-1: never)
    int page = 0;

    double hold() const { return steps * 0.48; }

    // gsdisplay.parse + Display.apply: d an exclusive's bytes (F0 and F7 or
    // not); true where it was one of the display's, its sum right
    bool apply(const uint8_t *d0, size_t n0, double now)
    {
        size_t a0 = n0 && d0[0] == 0xF0 ? 1 : 0;
        size_t n = n0 - a0 - (n0 > a0 && d0[n0 - 1] == 0xF7 ? 1 : 0);
        const uint8_t *d = d0 + a0;
        if (n < 9 || d[0] != 0x41 || d[2] != 0x45 || d[3] != 0x12 || d[4] != 0x10)
            return false;
        int sum = 0;
        for (size_t i = 4; i < n; i++)
            sum += d[i];
        if (sum % 128 != 0)
            return false;
        const uint8_t a1 = d[5], a2 = d[6], *body = d + 7;
        const size_t nb = n - 8;
        if (!nb || !((a1 == 0 && a2 == 0) || (a1 >= 1 && a1 <= 5) || (a1 == 0x20 && a2 <= 1)))
            return false;
        if (a1 == 0 && a2 == 0) {
            text.clear();
            for (size_t i = 0; i < nb && i < 32; i++)
                if (body[i] >= 0x20 && body[i] <= 0x7F)
                    text += (char)body[i];
            text_at = now;
        } else if (a1 >= 1 && a1 <= 5) {
            for (size_t i = 0; i < nb; i++)
                if (a2 + i < 128)
                    mem[a1 - 1][a2 + i] = body[i] & 0x1F;
            if (a1 == 1 && a2 < 0x40) {     // page 1: shown at once
                page = 1;
                page_at = now;
            }
        } else if (a2 == 0) {
            page = body[0] < 10 ? body[0] : 10;
            page_at = now;
            if (nb >= 2)
                steps = body[1] & 0x0F;
        } else {
            steps = body[0] & 0x0F;
        }
        return true;
    }

    // Display.page_rows: page n's dots, rows[16 r + c]
    void page_rows(int n, unsigned char *rows) const
    {
        const uint8_t *m = mem[(n + 1) / 2 - 1] + (n % 2 ? 0 : 0x40);
        for (int r = 0; r < 16; r++)
            for (int c = 0; c < 16; c++) {
                const int s = c / 5;
                const uint8_t b = m[16 * s + r];
                rows[16 * r + c] = s < 3 ? (b & (0x10 >> (c % 5))) != 0 : (b & 0x10) != 0;
            }
    }
};

// gsdisplay.timeline: one message at time t into the file's lines (text, and
// a page drawn in '#' and '.'), as the Python writes them
inline void timeline_add(Display &D, const uint8_t *d, size_t n, double t, std::vector<std::string> &out)
{
    const double ta = D.text_at, pa = D.page_at;
    if (!D.apply(d, n, t))
        return;
    char st[32], b[96];
    snprintf(st, sizeof st, "[%02d:%05.2f]", (int)(t / 60.0), t - 60.0 * (int)(t / 60.0));
    if (D.text_at != ta) {
        snprintf(b, sizeof b, "%s text (%.2f s): ", st, D.hold());
        out.push_back(b + D.text);
    }
    if (D.page_at != pa) {
        if (D.page) {
            snprintf(b, sizeof b, "%s page %d (%.2f s):", st, D.page, D.hold());
            out.push_back(b);
            unsigned char rows[256];
            D.page_rows(D.page, rows);
            for (int r = 0; r < 16; r++) {
                std::string ln = "    ";
                for (int c = 0; c < 16; c++)
                    ln += rows[16 * r + c] ? '#' : '.';
                out.push_back(ln);
            }
        } else {
            out.push_back(std::string(st) + " the level bars");
        }
    }
}

}  // namespace gsd

#endif
