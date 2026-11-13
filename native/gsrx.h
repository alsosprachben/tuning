// gsrx.h -- THE PARTS' RECEIVE SETTINGS (GS), as gsrx.py's Receive: RX.
// CHANNEL (40 1p 02: a part on another channel, two parts layered on one, a
// part on none), the Rx switches (40 1p 03-12: a message type, or a CC, not
// received), ASSIGN MODE and the CC1/CC2 controller numbers (kept), master
// pan (40 00 06: an offset on every part's CC10). 40 is group A's parts, 50
// group B's (a two-port file's: channel + 16 x port); a part receives its own
// port's channels. A GS reset or GM System On puts every setting back.
#ifndef NV_GSRX_H
#define NV_GSRX_H

#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <set>
#include <utility>
#include <vector>

namespace nv {

struct GsReceive {
    int nparts = 32;
    std::array<int, 32> rx;                     // each part's channel in its port, 16 OFF
    std::map<int, std::set<int>> rxsw;          // part -> the Rx switches turned off
    std::map<int, int> sel;                     // part -> 1 RPN, 2 NRPN: the last selected
    int mpan = 64;
    std::map<int, int> pan_raw;                 // part -> its CC10 as sent
    std::map<int, int> assign;
    std::map<std::pair<int, int>, int> ccnum;

    explicit GsReceive(int n = 32) : nparts(n) { reset(); }
    void reset()
    {
        for (int p = 0; p < 32; p++)
            rx[p] = p % 16;
        rxsw.clear();
        sel.clear();
        mpan = 64;
        pan_raw.clear();
        assign.clear();
        ccnum.clear();
    }
    bool plain() const
    {
        if (mpan != 64 || !rxsw.empty())
            return false;
        for (int p = 0; p < 32; p++)
            if (rx[p] != p % 16)
                return false;
        return true;
    }
    static int rx_type(int kind, int d1)
    {
        switch (kind) {
        case 0xE0: return 0x03;
        case 0xD0: return 0x04;
        case 0xC0: return 0x05;
        case 0xA0: return 0x07;
        case 0x90: case 0x80: return 0x08;
        }
        (void)d1;
        return -1;
    }
    static int rx_cc(int c)
    {
        switch (c) {
        case 1: return 0x0B; case 7: return 0x0C; case 10: return 0x0D; case 11: return 0x0E;
        case 64: return 0x0F; case 65: return 0x10; case 66: return 0x11; case 67: return 0x12;
        }
        return -1;
    }
    // gsrx.Receive._drop: true where part p does not receive it
    bool drop(int p, int kind, int d0)
    {
        if (kind == 0xB0) {
            if (d0 == 101 || d0 == 100)
                sel[p] = 1;
            else if (d0 == 99 || d0 == 98)
                sel[p] = 2;
        }
        auto it = rxsw.find(p);
        if (it == rxsw.end() || it->second.empty())
            return false;
        const std::set<int> &sw = it->second;
        if (kind != 0xB0)
            return sw.count(rx_type(kind, 0)) > 0;
        if (sw.count(0x06))
            return true;
        if (d0 == 101 || d0 == 100)
            return sw.count(0x09) > 0;
        if (d0 == 99 || d0 == 98)
            return sw.count(0x0A) > 0;
        if (d0 == 6 || d0 == 38 || d0 == 96 || d0 == 97) {
            auto s = sel.find(p);
            const int k = s == sel.end() ? 0 : s->second;
            return (k == 1 && sw.count(0x09)) || (k == 2 && sw.count(0x0A));
        }
        return sw.count(rx_cc(d0)) > 0;
    }
    // gsrx.Receive.route: the parts (channel 0-31) a message on channel ch
    // reaches, each with its value (a CC10 offset by master pan)
    void route(int ch, int kind, int d0, int d1, std::vector<std::pair<int, int>> &out)
    {
        out.clear();
        if (ch >= nparts) {
            out.push_back(std::make_pair(ch, d1));
            return;
        }
        const int g = ch / 16, c = ch % 16;
        bool moved = false;
        for (int p = 0; p < 16; p++)
            moved = moved || rx[16 * g + p] != p;
        std::vector<int> tg;
        if (!moved)
            tg.push_back(ch);
        else
            for (int p = 0; p < 16; p++)
                if (rx[16 * g + p] == c)
                    tg.push_back(16 * g + p);
        for (int p : tg) {
            if (drop(p, kind, d0))
                continue;
            int v = d1;
            if (kind == 0xB0 && d0 == 10) {
                pan_raw[p] = d1;
                if (mpan != 64)
                    v = std::max(0, std::min(127, d1 + mpan - 64));
            }
            out.push_back(std::make_pair(p, v));
        }
    }
    // gsrx.Receive.sysex: -1 where d (F0 and F7 off) is neither a part's
    // receive setting nor master pan; 1 master pan (pans: every part's CC10
    // to send again), 0 another
    int sysex(const std::vector<uint8_t> &d, std::vector<std::pair<int, int>> &pans)
    {
        pans.clear();
        if (!(d.size() >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12 && (d[4] == 0x40 || d[4] == 0x50)))
            return -1;
        if (d[4] == 0x40 && d[5] == 0x00 && d[6] == 0x06) {
            mpan = std::max(1, std::min(127, (int)d[7]));
            for (int p = 0; p < nparts; p++) {
                auto it = pan_raw.find(p);
                pans.push_back(std::make_pair(p, std::max(0, std::min(127, (it == pan_raw.end() ? 64 : it->second) + mpan - 64))));
            }
            return 1;
        }
        if (d[5] >> 4 != 1)
            return -1;
        const int a = d[6];
        if (!(a == 0x02 || (a >= 0x03 && a <= 0x12) || a == 0x14 || a == 0x1F || a == 0x20))
            return -1;
        const int blk = d[5] & 0x0F;
        const int ch = (blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk)) + (d[4] == 0x50 ? 16 : 0);
        if (ch >= nparts)
            return 0;
        const int v = d[7];
        if (a == 0x02)
            rx[ch] = v < 16 ? v : 16;
        else if (a == 0x14)
            assign[ch] = v;
        else if (a == 0x1F || a == 0x20)
            ccnum[std::make_pair(ch, a)] = v;
        else if (v)
            rxsw[ch].erase(a);
        else
            rxsw[ch].insert(a);
        return 0;
    }
};

}  // namespace nv

#endif
