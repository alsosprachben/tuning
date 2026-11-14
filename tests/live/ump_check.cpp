// ump_check.cpp -- native/ump.h on its own, for tests/live/ump_check.py:
//
//   ump_check bridge [SPEC]    MIDI 1.0 events in ("type ch a b" a line), the
//                              engine's events out ("type ch a b v") -- the
//                              bridge, flushed at the end
//   ump_check timeline FILE    each packet's time and words
//   ump_check decode           packets in (hex words a line), events out
//   ump_check alsa SECONDS     a MIDI 2.0 port: its address, then each UMP
//                              received for SECONDS
#include <chrono>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <poll.h>
#include <sstream>
#include <string>
#include <thread>

#include "../../native/ump.h"

static void put(const nv::ump::Ev &e)
{
    if (e.type == 6) {
        printf("6");
        for (uint8_t b : e.x)
            printf(" %d", b);
        printf("\n");
        return;
    }
    if (std::isnan(e.v))
        printf("%d %d %d %d nan\n", e.type, e.ch, e.a, e.b);
    else
        printf("%d %d %d %d %.17g\n", e.type, e.ch, e.a, e.b, e.v);
}

int main(int argc, char **argv)
{
    if (argc < 2)
        return 2;
    const std::string mode = argv[1];
    if (mode == "bridge") {
        nv::ump::Bridge b;
        b.on = true;
        if (argc > 2 && !b.pt.parse(argv[2]))
            return 3;
        char line[256];
        std::vector<nv::ump::Ev> out;
        while (fgets(line, sizeof line, stdin)) {
            int t, c, a, v;
            if (sscanf(line, "%d %d %d %d", &t, &c, &a, &v) != 4)
                continue;
            b.feed(t, c, a, v, out);
        }
        b.flush_all(out);
        for (auto &e : out)
            put(e);
        printf("ignored %lld\n", b.ignored);
        return 0;
    }
    if (mode == "timeline" && argc > 2) {
        std::vector<uint8_t> f;
        if (FILE *fp = fopen(argv[2], "rb")) {
            int c;
            while ((c = fgetc(fp)) != EOF)
                f.push_back((uint8_t)c);
            fclose(fp);
        }
        std::vector<std::pair<double, std::vector<uint32_t>>> tl;
        if (!nv::ump::read_timeline(f, tl))
            return 4;
        for (auto &e : tl) {
            printf("%.17g", e.first);
            for (uint32_t w : e.second)
                printf(" %" PRIu32, w);
            printf("\n");
        }
        return 0;
    }
    if (mode == "decode") {
        char line[512];
        std::map<int, std::vector<uint8_t>> sx;
        long long ign = 0;
        while (fgets(line, sizeof line, stdin)) {
            std::istringstream is(line);
            std::vector<uint32_t> pk;
            unsigned long w;
            while (is >> w)
                pk.push_back((uint32_t)w);
            if (pk.empty())
                continue;
            pk.resize(4, 0);
            std::vector<nv::ump::Ev> out;
            nv::ump::decode(pk.data(), sx, out, &ign);
            for (auto &e : out)
                put(e);
        }
        printf("ignored %lld\n", ign);
        return 0;
    }
    if (mode == "alsa" && argc > 2) {
        nv::ump::AlsaUmp uc;
        if (!uc.open("ump_check")) {
            printf("error %s\n", uc.err.c_str());
            return 5;
        }
        printf("address %d:%d\n", uc.client, uc.port);
        fflush(stdout);
        std::vector<pollfd> pf;
        for (int fd : uc.fds())
            pf.push_back(pollfd{fd, POLLIN, 0});
        const auto end = std::chrono::steady_clock::now() + std::chrono::duration<double>(atof(argv[2]));
        while (std::chrono::steady_clock::now() < end) {
            if (poll(pf.data(), pf.size(), 50) <= 0)
                continue;
            std::vector<std::vector<uint32_t>> got;
            uc.read_pending(got);
            for (auto &pk : got) {
                printf("ump");
                for (uint32_t w : pk)
                    printf(" %" PRIu32, w);
                printf("\n");
                fflush(stdout);
            }
        }
        return 0;
    }
    return 2;
}
