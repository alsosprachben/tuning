// cmx_check.cpp -- native/cmx.h's panel half on its own, for
// tests/live/cmx_panel_check.py:
//
//   cmx_check scene CH     exclusives in (decimal bytes a line), the matrix
//                          they set on channel CH; then its scene messages out
//   cmx_check undo CH      the same, then a line "--", then the scene's kept
//                          exclusives; the undo messages out
//   cmx_check printed      every destination's every byte: "col v raw printed"
//                          (raw: gs_raw of the byte's depth)
#include <cstdio>
#include <sstream>
#include <string>
#include <vector>

#include "../../native/cmx.h"

static std::vector<std::vector<uint8_t>> read_msgs(bool *more)
{
    std::vector<std::vector<uint8_t>> out;
    char line[1024];
    *more = false;
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '-') {
            *more = true;
            break;
        }
        std::istringstream is(line);
        std::vector<uint8_t> d;
        int b;
        while (is >> b)
            d.push_back((uint8_t)b);
        if (!d.empty())
            out.push_back(d);
    }
    return out;
}

static void put(const std::vector<std::vector<uint8_t>> &ms)
{
    for (const auto &d : ms) {
        for (size_t i = 0; i < d.size(); i++)
            printf(i ? " %d" : "%d", d[i]);
        printf("\n");
    }
}

int main(int argc, char **argv)
{
    if (argc < 2)
        return 2;
    const std::string mode = argv[1];
    if (mode == "printed") {
        for (int col = 0; col < 11; col++)
            for (int v = col == 0 ? 0x28 : 0; v <= (col == 0 ? 0x58 : 127); v++)
                printf("%d %d %d %s\n", col, v, nv::cmx_gs_raw(col, nv::cmx_gs_depth(col, v)),
                       nv::cmx_printed(col, nv::cmx_gs_depth(col, v)).c_str());
        return 0;
    }
    if (argc < 3)
        return 2;
    const int ch = atoi(argv[2]);
    bool more;
    auto set = read_msgs(&more);
    nv::Cmx m;
    for (const auto &d : set) {
        nv::CmxMsg cm;
        if (!nv::cmx_parse(d, cm) || cm.ch != ch)
            continue;
        if (cm.kind == 1)
            m.set(cm.a, cm.b, cm.dep);
        else if (cm.kind == 2)
            (cm.a == 4 ? m.cc1 : m.cc2) = cm.b;
        else
            for (auto &c3 : cm.cells)
                m.set(c3.first.first, c3.first.second, c3.second);
    }
    if (mode == "scene") {
        put(nv::cmx_scene(ch, m));
        return 0;
    }
    if (mode == "undo") {
        auto keep = more ? read_msgs(&more) : std::vector<std::vector<uint8_t>>();
        put(nv::cmx_undo(ch, m, keep));
        return 0;
    }
    return 2;
}
