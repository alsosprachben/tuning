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

}  // namespace nv

#endif
