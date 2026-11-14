// cmx.h -- THE CONTROLLER MATRIX (ctrlmatrix.py): one channel's routing, a
// source (0 mod, 1 bend, 2 cat, 3 pat, 4 cc1, 5 cc2, 100 + n a CC) and a
// destination (GS_DESTS's 0-10: pitch, cutoff, amp, lfo1 rate/pitch/tvf/tva,
// lfo2's) to a depth in the order set; a reset's the mod wheel's 47 cents of
// LFO1 pitch and the bend's 2 semitones; CC1/CC2 resolved to their numbers.
// The message parse, as ctrlmatrix.parse reads GS 40 2p aa, 40 1p 1F/20 and
// GM2's 7F 09 0s.
#ifndef NV_CMX_H
#define NV_CMX_H

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <cstdint>
#include <utility>
#include <vector>

namespace nv {

struct Cmx {
    std::vector<std::pair<std::pair<int, int>, double>> gs;
    int cc1 = 16, cc2 = 17;
    Cmx() { reset(); }
    void reset()
    {
        gs.clear();
        gs.push_back({{0, 4}, 10 * 600.0 / 127.0});
        gs.push_back({{1, 0}, 2.0});
        cc1 = 16;
        cc2 = 17;
    }
    void set(int src, int dest, double dep)
    {
        for (auto &e : gs)
            if (e.first.first == src && e.first.second == dest) {
                e.second = dep;
                return;
            }
        gs.push_back({{src, dest}, dep});
    }
    // cells(): CC1 and CC2 resolved, zero cells left out, equal keys summed
    std::vector<std::pair<std::pair<int, int>, double>> cells() const
    {
        std::vector<std::pair<std::pair<int, int>, double>> cl;
        for (const auto &e : gs) {
            int src = e.first.first == 4 ? 100 + cc1 : e.first.first == 5 ? 100 + cc2 : e.first.first;
            if (!e.second)
                continue;
            bool got = false;
            for (auto &o : cl)
                if (o.first.first == src && o.first.second == e.first.second) {
                    o.second = o.second + e.second;
                    got = true;
                }
            if (!got)
                cl.push_back({{src, e.first.second}, 0.0 + e.second});
        }
        return cl;
    }
};

// ctrlmatrix.parse on an exclusive's bytes (F0, F7 off): its channel (0-31)
// and what it sets -- kind 1 a GS cell (a, b: source, destination; dep),
// 2 GS CC1/CC2's number (a 4|5, b the CC), 3 GM2 cells (each in out);
// 0 none
struct CmxMsg {
    int ch = -1, kind = 0, a = 0, b = 0;
    double dep = 0.0;
    std::vector<std::pair<std::pair<int, int>, double>> cells;
};
inline bool cmx_parse(const std::vector<uint8_t> &d, CmxMsg &m)
{
    m = CmxMsg();
    if (d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && (d[4] == 0x40 || d[4] == 0x50)) {
        const int blk = d[5] & 0x0F;
        m.ch = (blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0);
        if ((d[5] >> 4) == 2) {
            const int row = d[6] >> 4, col = d[6] & 0x0F, v = d[7];
            if (row > 5 || col > 10)
                return false;
            m.kind = 1;
            m.a = row;
            m.b = col;
            m.dep = col == 0 ? (double)std::max(-24, std::min(24, v - 0x40))
                    : col == 1 ? (v - 0x40) * 9600.0 / 64.0
                    : col == 2 ? (v > 0x40 ? (v - 0x40) / 63.0 : (v - 0x40) / 64.0)
                    : (col == 3 || col == 7) ? (v - 0x40) * 10.0 / 64.0
                    : (col == 4 || col == 8) ? v * 600.0 / 127.0
                    : (col == 5 || col == 9) ? v * 2400.0 / 127.0
                    : v / 127.0;
            return true;
        }
        if ((d[5] >> 4) == 1 && (d[6] == 0x1F || d[6] == 0x20)) {
            m.kind = 2;
            m.a = d[6] == 0x1F ? 4 : 5;
            m.b = d[7];
            return true;
        }
        return false;
    }
    if (d.size() >= 6 && d[0] == 0x7F && d[2] == 0x09 && d[3] >= 1 && d[3] <= 3) {
        static const int GM2D[6] = {0, 1, 2, 4, 5, 6};
        m.ch = d[4] & 0x0F;
        int src = d[3] == 1 ? 2 : d[3] == 2 ? 3 : -1;
        size_t i = 5;
        if (d[3] == 3 && d.size() >= 7) {
            src = 100 + d[5];
            i = 6;
        }
        if (src < 0)
            return false;
        for (; i + 1 < d.size(); i += 2) {
            const int pp = d[i], rr = d[i + 1];
            if (pp >= 6)
                continue;
            const double dep = pp == 0 ? (double)std::max(-24, std::min(24, rr - 0x40))
                               : pp == 1 ? -9600.0 + rr * (9600.0 + 9450.0) / 127.0
                               : pp == 2 ? rr / 64.0 - 1.0
                               : pp == 3 ? rr * 600.0 / 127.0
                               : pp == 4 ? rr * 2400.0 / 127.0
                               : rr / 127.0;
            m.cells.push_back({{src, GM2D[pp]}, dep});
        }
        if (m.cells.empty())
            return false;
        m.kind = 3;
        return true;
    }
    return false;
}

// ---- THE PANEL (ctrlmatrix's panel half: nvlive's C) ----
// gs_depth: a GS 40 2x byte in destination col's unit (cmx_parse's)
inline double cmx_gs_depth(int col, int v)
{
    return col == 0 ? (double)std::max(-24, std::min(24, v - 0x40))
           : col == 1 ? (v - 0x40) * 9600.0 / 64.0
           : col == 2 ? (v > 0x40 ? (v - 0x40) / 63.0 : (v - 0x40) / 64.0)
           : (col == 3 || col == 7) ? (v - 0x40) * 10.0 / 64.0
           : (col == 4 || col == 8) ? v * 600.0 / 127.0
           : (col == 5 || col == 9) ? v * 2400.0 / 127.0
           : v / 127.0;
}
inline double cmx_gm2_depth(int pp, int rr)
{
    return pp == 0 ? (double)std::max(-24, std::min(24, rr - 0x40))
           : pp == 1 ? -9600.0 + rr * (9600.0 + 9450.0) / 127.0
           : pp == 2 ? rr / 64.0 - 1.0
           : pp == 3 ? rr * 600.0 / 127.0
           : pp == 4 ? rr * 2400.0 / 127.0
           : rr / 127.0;
}
// ctrlmatrix.gs_raw: the byte nearest a depth (pitch 28H-58H, the rest 0-127)
inline int cmx_gs_raw(int col, double dep)
{
    const int lo = col == 0 ? 0x28 : 0, hi = col == 0 ? 0x58 : 127;
    int best = lo;
    for (int v = lo + 1; v <= hi; v++) {
        const double a = std::abs(cmx_gs_depth(col, v) - dep),
                     b = std::abs(cmx_gs_depth(col, best) - dep);
        if (a < b || (a == b && std::abs(v - 0x40) < std::abs(best - 0x40)))
            best = v;
    }
    return best;
}
inline int cmx_gm2_raw(int pp, double dep)
{
    int best = 0;
    for (int v = 1; v < 128; v++)
        if (std::abs(cmx_gm2_depth(pp, v) - dep) < std::abs(cmx_gm2_depth(pp, best) - dep))
            best = v;
    return best;
}
// a reset's depth for (source, destination)
inline double cmx_default(int src, int col)
{
    return src == 0 && col == 4 ? 10 * 600.0 / 127.0 : src == 1 && col == 0 ? 2.0 : 0.0;
}
inline const double *cmx_find(const Cmx &m, int src, int col)
{
    for (const auto &e : m.gs)
        if (e.first.first == src && e.first.second == col)
            return &e.second;
    return nullptr;
}
inline int cmx_block(int ch) { return ch == 9 ? 0 : ch < 9 ? ch + 1 : ch; }
inline std::vector<uint8_t> cmx_dt1(uint8_t a, uint8_t b, uint8_t c, uint8_t d)
{
    return {0x41, 0x10, 0x42, 0x12, a, b, c, d, (uint8_t)((128 - (a + b + c + d) % 128) % 128)};
}
// ctrlmatrix.cell_message / assign_message
inline std::vector<uint8_t> cmx_cell_message(int ch, int row, int col, int v)
{
    return cmx_dt1(0x40, (uint8_t)(0x20 | cmx_block(ch)), (uint8_t)((row << 4) | col), (uint8_t)std::max(0, std::min(127, v)));
}
inline std::vector<uint8_t> cmx_assign_message(int ch, int which, int cc)    // (which 4: CC1, 5: CC2)
{
    return cmx_dt1(0x40, (uint8_t)(0x10 | cmx_block(ch)), which == 4 ? 0x1F : 0x20, (uint8_t)std::max(0, std::min(95, cc)));
}
static const int CMX_GM2_PP[11] = {0, 1, 2, -1, 3, 4, 5, -1, -1, -1, -1};     // (a GS column's GM2 pp)
inline std::vector<std::pair<std::pair<int, int>, double>> cmx_gm2_cells(const Cmx &m)
{
    std::vector<std::pair<std::pair<int, int>, double>> g;
    for (const auto &e : m.gs)
        if (e.first.first >= 100)
            g.push_back(e);
    std::sort(g.begin(), g.end(), [](const std::pair<std::pair<int, int>, double> &a,
                                     const std::pair<std::pair<int, int>, double> &b) { return a.first < b.first; });
    return g;
}
inline std::vector<uint8_t> cmx_gm2_message(int ch, int cc, int pp, int rr)
{
    return {0x7F, 0x7F, 0x09, 0x03, (uint8_t)(ch & 15), (uint8_t)cc, (uint8_t)pp, (uint8_t)rr};
}
// ctrlmatrix.scene_messages: what sets matrix m from a reset's
inline std::vector<std::vector<uint8_t>> cmx_scene(int ch, const Cmx &m)
{
    std::vector<std::vector<uint8_t>> out;
    if (m.cc1 != 16)
        out.push_back(cmx_assign_message(ch, 4, m.cc1));
    if (m.cc2 != 17)
        out.push_back(cmx_assign_message(ch, 5, m.cc2));
    for (int row = 0; row < 6; row++)
        for (int col = 0; col < 11; col++) {
            const double *d = cmx_find(m, row, col);
            const double dep = d ? *d : cmx_default(row, col);
            const int v = cmx_gs_raw(col, dep);
            if (v != cmx_gs_raw(col, cmx_default(row, col)))
                out.push_back(cmx_cell_message(ch, row, col, v));
        }
    for (const auto &e : cmx_gm2_cells(m)) {
        const int pp = CMX_GM2_PP[e.first.second];
        if (pp >= 0 && e.second != 0.0)
            out.push_back(cmx_gm2_message(ch, e.first.first - 100, pp, cmx_gm2_raw(pp, e.second)));
    }
    return out;
}
// ctrlmatrix.undo_messages: matrix m back to a reset's but for what the
// exclusives `keep` set again on channel ch
inline std::vector<std::vector<uint8_t>> cmx_undo(int ch, const Cmx &m, const std::vector<std::vector<uint8_t>> &keep)
{
    Cmx st;
    std::vector<std::pair<int, int>> named;
    for (const auto &d : keep) {
        CmxMsg cm;
        if (!cmx_parse(d, cm) || cm.ch != ch)
            continue;
        if (cm.kind == 1) {
            st.set(cm.a, cm.b, cm.dep);
            named.push_back({cm.a, cm.b});
        } else if (cm.kind == 2)
            (cm.a == 4 ? st.cc1 : st.cc2) = cm.b;
        else
            for (auto &c3 : cm.cells) {
                st.set(c3.first.first, c3.first.second, c3.second);
                named.push_back(c3.first);
            }
    }
    auto is_named = [&](int s, int c) { return std::find(named.begin(), named.end(), std::make_pair(s, c)) != named.end(); };
    std::vector<std::vector<uint8_t>> out;
    if (m.cc1 != st.cc1 && st.cc1 == 16)
        out.push_back(cmx_assign_message(ch, 4, 16));
    if (m.cc2 != st.cc2 && st.cc2 == 17)
        out.push_back(cmx_assign_message(ch, 5, 17));
    for (int row = 0; row < 6; row++)
        for (int col = 0; col < 11; col++) {
            const double *d = cmx_find(m, row, col);
            if (d && !is_named(row, col) && *d != cmx_default(row, col))
                out.push_back(cmx_cell_message(ch, row, col, cmx_gs_raw(col, cmx_default(row, col))));
        }
    for (const auto &e : cmx_gm2_cells(m)) {
        const int pp = CMX_GM2_PP[e.first.second];
        if (!is_named(e.first.first, e.first.second) && e.second != 0.0 && pp >= 0)
            out.push_back(cmx_gm2_message(ch, e.first.first - 100, pp, cmx_gm2_raw(pp, 0.0)));
    }
    return out;
}
// ctrlmatrix.printed: a depth in its destination's unit, as the panel prints it
inline std::string cmx_printed(int col, double dep)
{
    char b[48];
    if (col == 0)
        snprintf(b, sizeof b, dep != 0.0 ? "%+d semitones" : "0", (int)std::lround(dep));
    else if (col == 1)
        snprintf(b, sizeof b, dep != 0.0 ? "%+.0f cents" : "%.0f cents", dep);
    else if (col == 5 || col == 9)
        snprintf(b, sizeof b, "%.0f cents", dep);
    else if (col == 2)
        snprintf(b, sizeof b, dep != 0.0 ? "%+.0f %%" : "0", dep * 100.0);
    else if (col == 3 || col == 7)
        snprintf(b, sizeof b, dep != 0.0 ? "%+.1f Hz" : "0", dep);
    else if (col == 4 || col == 8)
        snprintf(b, sizeof b, "%.0f cents", dep);
    else
        snprintf(b, sizeof b, "%.0f %%", dep * 100.0);
    return b;
}

}  // namespace nv

#endif
