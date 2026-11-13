// mpe.h -- MPE's zones (M1-100-UM), as tonelib.MpeZones keeps them: n[(group,
// side)] the member count, side 0 the Lower Zone (manager channel 1 of its
// group), 1 the Upper (manager 16). THE NEWEST ZONE WINS (2.2.1): an MCM that
// reaches channels the other zone holds takes them, and a zone left with no
// member -- or whose manager was taken -- goes.
#ifndef NV_MPE_H
#define NV_MPE_H

#include <algorithm>
#include <map>
#include <set>
#include <utility>
#include <vector>

namespace nv {

static const int MPE_MANAGER_BEND = 2, MPE_MEMBER_BEND = 48;     // (tonelib's, 2.2.5)
// what a manager's control change does NOT copy to its members
// (blockrender._MPE_NOT_FANNED): the RPN machinery, bank select, CC74, the modes
inline bool mpe_not_fanned(int c)
{
    static const int N[] = {0, 6, 32, 38, 74, 96, 97, 98, 99, 100, 101, 126, 127};
    for (int x : N)
        if (x == c)
            return true;
    return false;
}

struct MpeZones {
    std::map<std::pair<int, int>, int> n;

    explicit operator bool() const { return !n.empty(); }

    static std::set<int> chans(int g, int side, int cnt)
    {
        std::set<int> s;
        const int b = 16 * g;
        if (side == 0) {
            s.insert(b);
            for (int c = b + 1; c < b + 1 + cnt; c++)
                s.insert(c);
        } else {
            s.insert(b + 15);
            for (int c = b + 15 - cnt; c < b + 15; c++)
                s.insert(c);
        }
        return s;
    }
    // {channel: (group, side)} for every channel in MPE
    std::map<int, std::pair<int, int>> channels() const
    {
        std::map<int, std::pair<int, int>> out;
        for (auto &kv : n)
            for (int c : chans(kv.first.first, kv.first.second, kv.second))
                out[c] = kv.first;
        return out;
    }
    // an MCM on channel ch: the channels whose zone changed (cut and reset,
    // 2.2.3); false where ch is no manager channel
    bool mcm(int ch, int count, std::set<int> &changed)
    {
        changed.clear();
        const int g = ch / 16, c = ch % 16;
        if (c != 0 && c != 15)
            return false;
        const int side = c == 0 ? 0 : 1;
        const auto before = channels();
        count = std::max(0, std::min(15, count));
        if (count == 0)
            n.erase(std::make_pair(g, side));
        else {
            n[std::make_pair(g, side)] = count;
            const std::set<int> mine = chans(g, side, count);
            const std::pair<int, int> other(g, 1 - side);
            auto it = n.find(other);
            if (it != n.end()) {
                int m = it->second;
                auto hits = [&](int k) {
                    for (int x : chans(g, other.second, k))
                        if (mine.count(x))
                            return true;
                    return false;
                };
                while (m > 0 && hits(m))
                    m--;
                const int mgr = 16 * g + (other.second == 1 ? 15 : 0);
                if (m == 0 || mine.count(mgr))
                    n.erase(other);
                else
                    n[other] = m;
            }
        }
        const auto after = channels();
        std::set<int> all;
        for (auto &kv : before)
            all.insert(kv.first);
        for (auto &kv : after)
            all.insert(kv.first);
        for (int x : all) {
            auto b = before.find(x), a = after.find(x);
            const bool same = (b == before.end()) == (a == after.end()) && (b == before.end() || b->second == a->second);
            if (!same)
                changed.insert(x);
        }
        return true;
    }
    bool zone_of(int ch, std::pair<int, int> *z = nullptr) const
    {
        for (auto &kv : n) {
            const auto s = chans(kv.first.first, kv.first.second, kv.second);
            if (s.count(ch)) {
                if (z)
                    *z = kv.first;
                return true;
            }
        }
        return false;
    }
    int manager_of(int ch) const
    {
        std::pair<int, int> z;
        if (!zone_of(ch, &z))
            return -1;
        return 16 * z.first + (z.second == 0 ? 0 : 15);
    }
    bool is_manager(int ch) const { return zone_of(ch) && manager_of(ch) == ch; }
    bool is_member(int ch) const { return zone_of(ch) && manager_of(ch) != ch; }
    // the member channels of ch's zone, lowest first
    std::vector<int> members(int ch) const
    {
        std::pair<int, int> z;
        std::vector<int> out;
        if (!zone_of(ch, &z))
            return out;
        const int m = manager_of(ch);
        for (int x : chans(z.first, z.second, n.at(z)))
            if (x != m)
                out.push_back(x);
        return out;
    }
    int lowest_member(int ch) const
    {
        std::vector<int> ms = members(ch);
        return ms.empty() ? -1 : ms[0];
    }
};

}  // namespace nv

#endif
