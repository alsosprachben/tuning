// host.cpp -- the native live host in libnative (host.h): today the
// export's reader, moved from nvlive.cpp whole; nvlive's main() follows.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <condition_variable>
#include <functional>
#include <map>
#include <sched.h>
#include <spawn.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <mutex>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>
#include "panel.h"
#include "pycompat.h"
#include "hostint.h"

namespace nvh {

bool read_export(const char *path, Export &E)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return false;
    char magic[4];
    int nk, csz, ncls;
    bool ok = fread(magic, 1, 4, f) == 4 && !memcmp(magic, "NVX1", 4) && fread(&nk, 4, 1, f) == 1
              && fread(&csz, 4, 1, f) == 1 && fread(&ncls, 4, 1, f) == 1 && csz == (int)sizeof(NoteClass);
    if (ok) {
        E.k.resize(nk); E.freq.resize(128); E.trim.resize(512); E.cmap.resize(2 * NV_K_DRUMS);
        E.kit_f0.resize(16384); E.kit_seat.resize(16384); E.kit_choke.resize(2 * 16384);
        E.kit_skind.resize(16384); E.kit_spar.resize(NV_SPAR * 16384);
        E.kind.resize(NCOLS); E.fin.resize(NCOLS);
        ok = fread(E.k.data(), 8, nk, f) == (size_t)nk && fread(E.freq.data(), 8, 128, f) == 128
             && fread(E.trim.data(), 8, 512, f) == 512;
        for (int i = 0; ok && i < ncls; i++) {
            E.classes.emplace_back(csz);
            ok = fread(E.classes.back().data(), 1, csz, f) == (size_t)csz;
        }
        ok = ok && fread(E.cmap.data(), 4, 2 * NV_K_DRUMS, f) == 2 * NV_K_DRUMS
             && fread(E.kit_f0.data(), 8, 16384, f) == 16384 && fread(E.kit_seat.data(), 8, 16384, f) == 16384
             && fread(E.kit_choke.data(), 8, 2 * 16384, f) == 2 * 16384
             && fread(E.kit_skind.data(), 4, 16384, f) == 16384 && fread(E.kit_spar.data(), 8, NV_SPAR * 16384, f) == NV_SPAR * 16384
             && fread(E.kind.data(), 4, NCOLS, f) == NCOLS
             && fread(E.fin.data(), 4, NCOLS, f) == NCOLS;
        std::string *ss[4] = {&E.room, &E.libs[0], &E.libs[1], &E.libs[2]};
        for (int i = 0; ok && i < 4; i++) {
            int n;
            ok = fread(&n, 4, 1, f) == 1;
            if (ok) {
                ss[i]->resize(n);
                ok = fread(&(*ss[i])[0], 1, n, f) == (size_t)n;
            }
        }
        // ORGN: the registered organs' tables, each class's organ, each program's
        char om[4];
        int norg = 0, osz = 0;
        ok = ok && fread(om, 1, 4, f) == 4 && !memcmp(om, "ORGN", 4) && fread(&norg, 4, 1, f) == 1
             && fread(&osz, 4, 1, f) == 1 && osz == (int)sizeof(OrganSpec);
        if (ok) {
            E.organs.resize(norg);
            E.cls_organ.resize(ncls);
            E.prog_organ.resize(128);
            ok = fread(E.organs.data(), sizeof(OrganSpec), norg, f) == (size_t)norg
                 && fread(E.cls_organ.data(), 4, ncls, f) == (size_t)ncls && fread(E.prog_organ.data(), 4, 128, f) == 128;
        }
        // LESL: the rotating speaker's constants (leslie.cpp's) and the lobe's kernel
        char lt[4];
        long pos = ftell(f);
        if (ok && fread(lt, 1, 4, f) == 4 && !memcmp(lt, "LESL", 4)) {
            int nl = 0, n = 0;
            ok = fread(&nl, 4, 1, f) == 1;
            if (ok) {
                E.les.resize(nl);
                ok = fread(E.les.data(), 8, nl, f) == (size_t)nl && fread(&n, 4, 1, f) == 1;
            }
            if (ok) {
                E.lobe_lib.resize(n);
                ok = fread(&E.lobe_lib[0], 1, n, f) == (size_t)n;
            }
            // SCAN: the scanner's constants and circuit tables (scanner.cpp's)
            pos = ftell(f);
            if (ok && fread(lt, 1, 4, f) == 4 && !memcmp(lt, "SCAN", 4)) {
                int ns = 0;
                ok = fread(&ns, 4, 1, f) == 1;
                if (ok) {
                    E.scan.resize(ns);
                    ok = fread(E.scan.data(), 8, ns, f) == (size_t)ns;
                }
            } else {
                fseek(f, pos, SEEK_SET);
            }
        // VBOD: the voice parts a track's name declares (voice.c's table)
        {
            long vp = ftell(f);
            char vt[4];
            int vh[3];
            if (ok && fread(vt, 1, 4, f) == 4 && !memcmp(vt, "VBOD", 4) && fread(vh, 4, 3, f) == 3) {
                std::vector<char> blob(vh[2] + 1, 0);
                std::vector<double> vr(vh[0]), vc(vh[0]);
                ok = fread(blob.data(), 1, vh[2], f) == (size_t)vh[2] && fread(vr.data(), 8, vh[0], f) == (size_t)vh[0]
                     && fread(vc.data(), 8, vh[0], f) == (size_t)vh[0];
                if (ok)
                    nv_voice_bodies_set(vh[0], blob.data(), vr.data(), vc.data(), vh[1]);
            } else {
                fseek(f, vp, SEEK_SET);
            }
        }
        // VARS: bank select (native.variation_tables) -- the slots and their
        // classes at each key, the entries a program change selects, GS's and GM 2's tables
        {
            long vp = ftell(f);
            char vt[4];
            int vl = 0;
            if (ok && fread(vt, 1, 4, f) == 4 && !memcmp(vt, "VARS", 4) && fread(&vl, 4, 1, f) == 1) {
                int ns = 0, ne = 0;
                ok = fread(&ns, 4, 1, f) == 1;
                std::vector<int> pvl(3 * (size_t)ns);
                ok = ok && fread(pvl.data(), 4, pvl.size(), f) == pvl.size();
                E.vslot_v.resize(ns);
                for (int s = 0; s < ns; s++)
                    E.vslot_v[s] = pvl[3 * s + 1];
                E.vmap.resize(128 * (size_t)ns);
                ok = ok && fread(E.vmap.data(), 4, E.vmap.size(), f) == E.vmap.size() && fread(&ne, 4, 1, f) == 1;
                E.vents.assign(1, Export::VarEnt{});
                for (int e = 0; ok && e < ne; e++) {
                    int h[3];
                    Export::VarEnt v;
                    ok = fread(h, 4, 3, f) == 3;
                    v.ls.resize(ok ? h[2] : 0);
                    for (auto &l : v.ls)
                        ok = ok && fread(l.data(), 4, 4, f) == 4;
                    E.vents.push_back(v);
                }
                E.vgs.resize(5 * 128 * 128);
                E.vgm2.resize(128 * 128);
                ok = ok && fread(E.vgs.data(), 4, E.vgs.size(), f) == E.vgs.size()
                     && fread(E.vgm2.data(), 4, E.vgm2.size(), f) == E.vgm2.size();
                for (int e = 1; ok && e <= ne; e++)
                    ok = fread(E.vents[e].trim, 8, 2, f) == 2;
                for (int e = 1; ok && e <= ne; e++)
                    ok = fread(&E.vents[e].pcls, 4, 1, f) == 1;
            } else {
                fseek(f, vp, SEEK_SET);
            }
        }
        {                                   // DRON: the file renderer's (a bagpipe's drones)
            long dp = ftell(f);
            char dt[4];
            int dl = 0;
            if (ok && fread(dt, 1, 4, f) == 4 && !memcmp(dt, "DRON", 4) && fread(&dl, 4, 1, f) == 1
                && dl == 4 * 256) {
                E.dmap.resize(256);
                ok = fread(E.dmap.data(), 4, 256, f) == 256;
            } else {
                fseek(f, dp, SEEK_SET);
            }
        }
        // ...then MKIT (the file renderer's: passed) and VNAM (the picker's variations)
        for (;;) {
            long tp = ftell(f);
            char tt[4];
            int tl = 0;
            if (!(ok && fread(tt, 1, 4, f) == 4 && fread(&tl, 4, 1, f) == 1)) {
                fseek(f, tp, SEEK_SET);
                break;
            }
            if (!memcmp(tt, "MKIT", 4)) {
                fseek(f, tl, SEEK_CUR);
            } else if (!memcmp(tt, "EFXU", 4)) {
                E.efxu.resize(tl);
                ok = fread(&E.efxu[0], 1, tl, f) == (size_t)tl;
            } else if (!memcmp(tt, "MTAB", 4)) {
                E.mtab.resize(tl / 8);
                ok = fread(E.mtab.data(), 8, E.mtab.size(), f) == E.mtab.size();
            } else if (!memcmp(tt, "VDRN", 4)) {
                int nv = 0;
                ok = fread(&nv, 4, 1, f) == 1;
                E.vdrn.resize(ok ? nv : 0);
                for (auto &r : E.vdrn)
                    ok = ok && fread(r.data(), 4, 12, f) == 12;
            } else if (!memcmp(tt, "VLIV", 4)) {
                int nv = 0;
                ok = fread(&nv, 4, 1, f) == 1;
                E.vpart.resize(ok ? nv : 0);
                for (auto &r : E.vpart)
                    ok = ok && fread(r.data(), 4, 10, f) == 10;
            } else if (!memcmp(tt, "VNAM", 4)) {
                int nv = 0;
                ok = fread(&nv, 4, 1, f) == 1;
                for (int q = 0; ok && q < nv; q++) {
                    int h[3];
                    ok = fread(h, 4, 3, f) == 3;
                    std::string s(ok ? h[2] : 0, '\0');
                    ok = ok && fread(&s[0], 1, s.size(), f) == s.size();
                    E.vpv.push_back({h[0], h[1]});
                    E.vnames.push_back(s);
                }
            } else {
                fseek(f, tp, SEEK_SET);
                break;
            }
        }
        } else {
            fseek(f, pos, SEEK_SET);
        }
        char lv[4];
        if (ok && fread(lv, 1, 4, f) == 4 && !memcmp(lv, "LIVE", 4)) {
            E.pan.resize(384);
            double bh[2];
            E.live = fread(E.pan.data(), 8, 384, f) == 384 && fread(bh, 8, 2, f) == 2
                     && fread(E.part, 4, 1280, f) == 1280;
            E.beta = bh[0];
            E.headroom = bh[1];
            if (E.live && fread(lv, 1, 4, f) == 4 && !memcmp(lv, "LREG", 4)) {
                for (int p = 0; p < 128 && ok; p++) {
                    Export::Reg &r = E.reg[p];
                    ok = fread(&r.M, 4, 1, f) == 1;
                    if (ok && r.M > 0) {
                        r.modes.resize(r.M);
                        ok = fread(r.modes.data(), sizeof(StringMode), r.M, f) == (size_t)r.M
                             && fread(r.d, 8, 9, f) == 9 && fread(r.i, 4, 3, f) == 3 && fread(r.note, 4, 128, f) == 128;
                        for (std::vector<unsigned char> *v : {&r.cinit, &r.csnap}) {
                            int n = 0;
                            ok = ok && fread(&n, 4, 1, f) == 1;
                            if (ok) {
                                v->resize(n);
                                ok = fread(v->data(), 1, n, f) == (size_t)n;
                            }
                        }
                    }
                }
                if (ok && fread(lv, 1, 4, f) == 4 && !memcmp(lv, "LGPU", 4)) {
                    std::string *gs[3] = {&E.gpu_lib, &E.gpu_damp_lib, &E.gpu_dir};
                    bool g = true;
                    for (int i = 0; g && i < 3; i++) {
                        int n;
                        g = fread(&n, 4, 1, f) == 1;
                        if (g) {
                            gs[i]->resize(n);
                            g = fread(&(*gs[i])[0], 1, n, f) == (size_t)n;
                        }
                    }
                    E.gpu = g && fread(E.gpu_min, 4, 2, f) == 2;
                }
                char r5[5];
                if (ok && fread(r5, 1, 5, f) == 5 && !memcmp(r5, "LROOM", 5)) {
                    int n = 0;
                    bool g = fread(&n, 4, 1, f) == 1;
                    if (g) {
                        E.conv_lib.resize(n);
                        g = fread(&E.conv_lib[0], 1, n, f) == (size_t)n;
                    }
                    for (std::vector<float> *v : {&E.ir, &E.mir}) {
                        g = g && fread(&n, 4, 1, f) == 1;
                        if (g) {
                            v->resize(2 * (size_t)n);
                            g = fread(v->data(), 4, 2 * (size_t)n, f) == 2 * (size_t)n;
                        }
                    }
                    E.has_room = g;
                }
                char r6[6];
                int nr = 0;
                bool got6 = ok && fread(r6, 1, 6, f) == 6;
                if (got6 && !memcmp(r6, "LROOMS", 6)) {
                    long long rl = 0;
                    std::vector<uint8_t> rb;
                    if (fread(&rl, 8, 1, f) == 1 && rl > 0) {
                        rb.resize((size_t)rl);
                        if (fread(rb.data(), 1, rb.size(), f) != rb.size())
                            rb.clear();
                    }
                    size_t at = 0;
                    auto i32 = [&]() { int v = 0; if (at + 4 <= rb.size()) memcpy(&v, &rb[at], 4); at += 4; return v; };
                    auto f64s = [&](int n) {
                        std::vector<double> v(n > 0 ? n : 0);
                        if (n > 0 && at + 8 * (size_t)n <= rb.size())
                            memcpy(v.data(), &rb[at], 8 * (size_t)n);
                        at += 8 * (size_t)(n > 0 ? n : 0);
                        return v;
                    };
                    if (!rb.empty()) {
                        int nf = i32(), per = 0;
                        for (int q = 0; q < nf; q++) {
                            int o = i32(), z = i32();
                            E.room_rng.push_back(std::make_pair(o, z));
                            per += z;
                        }
                        E.room_ncls = i32();
                        E.room_dev = f64s(i32());
                        int nrm = i32();
                        for (int q = 0; q < nrm && at <= rb.size(); q++) {
                            Export::RoomData rd;
                            int ln = i32();
                            if (ln > 0 && at + ln <= rb.size())
                                rd.name.assign((const char *)&rb[at], ln);
                            at += ln > 0 ? ln : 0;
                            rd.reflect = i32() != 0;
                            rd.spec = f64s(i32());
                            if (rd.reflect) {
                                size_t nb = (size_t)per * E.room_ncls;
                                if (at + nb <= rb.size())
                                    rd.fields.assign(rb.begin() + at, rb.begin() + at + nb);
                                at += nb;
                            }
                            E.rooms.push_back(std::move(rd));
                        }
                        if (at != rb.size()) {
                            fprintf(stderr, "nvlive: the export's rooms are not this build's: no room switching\n");
                            E.rooms.clear();
                        }
                    }
                    got6 = fread(r6, 1, 6, f) == 6;
                }
                if (got6 && !memcmp(r6, "LROUTE", 6) && fread(&nr, 4, 1, f) == 1)
                    for (int q = 0; q < nr; q++) {
                        std::array<int, 7> a;
                        if (fread(a.data(), 4, 7, f) != 7)
                            break;
                        E.routes.push_back(a);
                    }
                // LSTOP: each organ program's ranks' names and the panel's stop rows
                char s5[5];
                int no = 0;
                if (ok && fread(s5, 1, 5, f) == 5 && !memcmp(s5, "LSTOP", 5) && fread(&no, 4, 1, f) == 1)
                    for (int q = 0; q < no; q++) {
                        int pg = 0, nr = 0, nrow = 0;
                        if (fread(&pg, 4, 1, f) != 1 || fread(&nr, 4, 1, f) != 1 || pg < 0 || pg > 127)
                            break;
                        auto &so = E.stops[pg];
                        for (int i = 0; i < nr; i++) {
                            int len = 0;
                            if (fread(&len, 4, 1, f) != 1)
                                break;
                            std::string nm(len, ' ');
                            if (len && fread(&nm[0], 1, len, f) != (size_t)len)
                                break;
                            so.names.push_back(nm);
                        }
                        if (fread(&nrow, 4, 1, f) != 1)
                            break;
                        for (int r = 0; r < nrow; r++) {
                            int n = 0;
                            if (fread(&n, 4, 1, f) != 1)
                                break;
                            std::vector<int> row(n);
                            if (n && fread(row.data(), 4, n, f) != (size_t)n)
                                break;
                            so.rows.push_back(row);
                        }
                    }
                // LPROG: each program's strings, choirs and names
                if (ok && fread(s5, 1, 5, f) == 5 && !memcmp(s5, "LPROG", 5)) {
                    bool g = true;
                    for (int p = 0; g && p < 128; p++) {
                        Export::Prog &pr = E.prog[p];
                        int nc = 0, nb = 0;
                        g = fread(&pr.sid, 4, 1, f) == 1 && fread(&nc, 4, 1, f) == 1;
                        if (g && nc > 0) {
                            std::vector<long long> br(nc);
                            g = fread(br.data(), 8, nc, f) == (size_t)nc && fread(&pr.cross, 8, 1, f) == 1
                                && fread(&nb, 4, 1, f) == 1;
                            pr.cbr.assign(br.begin(), br.end());
                            if (g) {
                                pr.buffs.resize(2 * nb);
                                g = !nb || fread(pr.buffs.data(), 4, 2 * nb, f) == 2 * (size_t)nb;
                            }
                        }
                        for (std::string *nm : {&pr.name, &pr.kit}) {
                            int len = 0;
                            g = g && fread(&len, 4, 1, f) == 1;
                            if (g) {
                                nm->assign(len, ' ');
                                g = !len || fread(&(*nm)[0], 1, len, f) == (size_t)len;
                            }
                        }
                    }
                    E.has_prog = g;
                }
                // LP3D: live.pan_at's head (the 3D types')
                char s4[4];
                if (ok && fread(s4, 1, 4, f) == 4 && !memcmp(s4, "LP3D", 4))
                    E.has_p3d = fread(E.p3d, 8, 4, f) == 4;
            }
        }
    }
    fclose(f);
    return ok;
}


}  // namespace nvh

// ---- the live host (host step 2e: moved from nvlive.cpp whole) ----
#include "hostlive.h"
#include "host.h"

int nv_host::open(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: nvlive EXPORT.nvx [--program=N] [--midi=DEV] [--device=PCM] [--latency-ms=10]\n"
                        "       nvlive EXPORT.nvx --test IN.mid OUT.wav [--program=N] [--seconds=S]\n");
        return 1;
    }
    if (!read_export(argv[1], E) || !E.live) {
        fprintf(stderr, "nvlive: %s is not a live export of this build (native_export.py --live)\n", argv[1]);
        return 1;
    }
    // each class's organ, its table here (the export's pointer was the exporter's)
    for (size_t i = 0; i < E.classes.size(); i++)
        ((NoteClass *)E.classes[i].data())->organ = E.cls_organ[i] >= 0 ? &E.organs[E.cls_organ[i]] : nullptr;
    for (size_t i = 0; i < E.classes.size(); i++) {     // a struck layer's class (sl_idx)
        NoteClass *nc = (NoteClass *)E.classes[i].data();
        nc->sl = nc->sl_on && nc->sl_idx >= 0 && nc->sl_idx < (int)E.classes.size()
                 ? (const NoteClass *)E.classes[nc->sl_idx].data() : nullptr;
    }
    SR = E.k[K_SR];
    BLK = (long long)E.k[K_BLK];
    program = atoi(opt(argc, argv, "program", "0").c_str());
    // --drums: the part a DRUM PART (live.Patch(program, True)): the program
    // its drum set -- one velocity bucket, no wheel step, no dampers, no una
    // corda, every key (live.DRUM_RANGE), its exclusive classes, no register
    drums = false;
    for (int i = 1; i < argc; i++)
        drums = drums || !strcmp(argv[i], "--drums");
    static const int DRUM_PART[10] = {1, 1, 1, -1, -1, -1, -1, 0, 0, 0};
    // a part's live record: its variation's (VLIV), else its program's (LIVE)
    prec = [&](int prog, int var) -> const int * {
        for (size_t j = 0; var && j < E.vpv.size() && j < E.vpart.size(); j++)
            if (E.vpv[j][0] == (prog & 127) && E.vpv[j][1] == var)
                return E.vpart[j].data();
        for (const auto &d : E.vdrn)            // (a voice's own drone patch)
            if (var && d[0] == (prog & 127) && d[1] == var)
                return d.data() + 2;
        return E.part[prog & 127];
    };
    pp = drums ? DRUM_PART : prec(program, atoi(opt(argc, argv, "bank", "0").c_str()));
    if (!pp[0]) {
        fprintf(stderr, "nvlive: program %d is not native\n", program);
        return 1;
    }
    {
        // ...and its variation (--bank): refused where its slots are not the
        // engine's (an unbuilt bank is the capital tone, as live's Patch has it)
        const int bk = drums ? 0 : atoi(opt(argc, argv, "bank", "0").c_str());
        int en = 0;
        if ((bk & 0x7F) && !E.vgs.empty()) {
            int mp = bk >> 7, bs = 1 + 128 * (mp >= 1 && mp <= 4 ? mp : 0) + (bk & 0x7F);
            en = E.vgs[((size_t)((bs - 1) / 128) * 128 + (program & 127)) * 128 + (bs - 1) % 128];
        }
        bool nat = true;
        for (const auto &l : en > 0 ? E.vents[en].ls : std::vector<std::array<int, 4>>())
            for (int k = 0; k < 128 && nat; k++)
                nat = k + l[1] < 0 || k + l[1] > 127 || E.vmap[128 * (size_t)l[0] + k + l[1]] >= 0
                      || E.cmap[128 * (program & 127) + k] < 0;
        if (!nat || !pp[0]) {
            fprintf(stderr, "nvlive: program %d bank %d is not native\n", program, bk);
            return 1;
        }
    }
    // THE TUNER (native/tuner.cpp): --tuner=NAME in place of the export's (its
    // --tuner, else live's hybrid) -- any of midilib's, `hybrid@D:466`,
    // `raga:todi@c#` -- at --a=HZ or --c=HZ (tunelib.set_reference); the
    // free strings' bank built again at it (nv_strings, as live_bank does)
    tname = opt(argc, argv, "tuner", "");
    if (!tname.empty()) {
        std::string a = opt(argc, argv, "a", ""), c = opt(argc, argv, "c", "");
        int rn = !a.empty() ? 69 : !c.empty() ? 60 : -1;
        double rh = !a.empty() ? atof(a.c_str()) : !c.empty() ? atof(c.c_str()) : 0.0;
        double F[128];
        int have[128];
        int r = nv_tuning_table(tname.c_str(), rn, rh, F, have);
        if (r) {
            fprintf(stderr, "nvlive: tuner %s: %s\n", tname.c_str(),
                    r == -1 ? "no such tuner" : r == -2 ? "no such key" : r == -3 ? "a bad pitch"
                    : r == -4 ? "@KEY or :A4 on a tuner with no table to move" : "a bad raga spec");
            return 1;
        }
        for (int n = 0; n < 128; n++)
            E.freq[n] = have[n] ? F[n] : 0.0;
        fprintf(stderr, "nvlive: tuned %s%s\n", tname.c_str(), rn >= 0 ? (rn == 69 ? " at a=" + a : " at c=" + c).c_str() : "");
    }
    // A RAGA TUNER (T.raga_sa_note, T.raga_spec): its Sa and swaras, for the
    // templates' strings and the meend -- before a template is built
    raga_sa = -1; raga_nsw = 0;
    {
        std::string tl = tname;
        for (char &c : tl)
            c = (char)tolower((unsigned char)c);
        double rf[128];
        int rh[128];
        if (!(tl.compare(0, 5, "raga:") == 0 && nv_raga_info(tl.c_str(), 0.0, rf, rh, &raga_sa, raga_sw, &raga_nsw) == 0))
            raga_sa = -1;
    }
    // THE SECONDARY TUNING (live.tuner_for: --eastern=SPEC): a part whose
    // voice is an Indian instrument plays SPEC, Sa at its own tuner's pitch
    // for its key ("%s:%.6f") unless SPEC names one -- unless its own tuner is
    // a raga's already. Each program's table, and its raga, for its cache
    east = opt(argc, argv, "eastern", "");
    if (!east.empty()) {
        double rf[128], sw0[12];
        int rh[128], sa0 = -1, n0 = 0;
        if (nv_raga_info(east.c_str(), 0.0, rf, rh, &sa0, sw0, &n0)) {
            fprintf(stderr, "nvlive: eastern %s: a bad raga spec\n", east.c_str());
            return 1;
        }
    }
    ptab = std::vector<std::vector<double>>(128);
    psa = std::vector<int>(128, -1); pnsw = std::vector<int>(128, 0);
    psw = std::vector<std::array<double, 12>>(128);
    tune_for = [&](int prog, bool dr) -> const double * {
        int p = prog & 127;
        if (raga_sa >= 0 || east.empty() || dr)
            return E.freq.data();
        int cq = E.cmap[128 * p + 60];
        if (cq < 0 || !((const NoteClass *)E.classes[cq].data())->indian)
            return E.freq.data();
        if (ptab[p].empty()) {
            double rf[128], sw0[12];
            int rh[128], sa0 = -1, n0 = 0;
            nv_raga_info(east.c_str(), 0.0, rf, rh, &sa0, sw0, &n0);
            double f = sa0 >= 0 && sa0 < 128 ? E.freq[sa0] : 0.0, hz = 0.0;
            if (f != 0.0) {                     // ("%s:%.6f": its Sa's pitch, as the spec's text carries it)
                char b[64];
                snprintf(b, sizeof b, "%.6f", f);
                hz = strtod(b, nullptr);
            }
            ptab[p].resize(128);
            nv_raga_info(east.c_str(), hz, ptab[p].data(), rh, &psa[p], psw[p].data(), &pnsw[p]);
        }
        return ptab[p].data();
    };
    tl_ = tname;
    for (char &ch_ : tl_)
        ch_ = (char)tolower((unsigned char)ch_);
    raga_for = [&](void *c, int prog, bool dr) {
        int p = prog & 127;
        // ...and a gm2 patch: its tuner gm2's, not the secondary tuning's (live.tuner_for)
        nv_tcache_set_gm2(c, tl_ == "gm2" && !(!dr && psa[p] >= 0));
        if (raga_sa >= 0)
            nv_tcache_set_raga(c, raga_sa, raga_sw, raga_nsw);
        else if (!dr && psa[p] >= 0)
            nv_tcache_set_raga(c, psa[p], psw[p].data(), pnsw[p]);
    };
    // A PROGRAM's FREE STRINGS at nvlive's tuner: the export's bank, built
    // again (nv_strings, as live_bank does) where --tuner moved it -- once a
    // program, the first time it is asked for
    retuned = std::vector<char>(128, 0);
    retune = [&](int p) {
        Export::Reg &rr = E.reg[p & 127];
        if (tname.empty() || retuned[p & 127] || rr.M <= 0 || rr.cinit.empty())
            return;
        retuned[p & 127] = 1;
        int cap = 88 * 4 * 130;
        std::vector<StringMode> modes(cap), tmp(cap);
        int M = nv_strings((const VoiceInit *)rr.cinit.data(), (const VoiceSnap *)rr.csnap.data(), E.freq.data(),
                           0.0, 1.0, SR, modes.data(), tmp.data(), cap);
        if (M > 0) {
            modes.resize(M);
            rr.modes.swap(modes);
            rr.M = M;
        }
    };
    if (!drums)
        retune(program);
    // THE PART'S TEMPLATES (live.Patch.warm), built here
    // (K whole: the programs', the drum sets', the drones' and the variations' -- NV_K_VAR + 128 slot + key)
    kmap = std::vector<int>(E.cmap.begin(), E.cmap.begin() + 2 * NV_K_DRUMS);
    E.dmap.resize(256, -1);
    kmap.insert(kmap.end(), E.dmap.begin(), E.dmap.end());
    kmap.insert(kmap.end(), E.vmap.begin(), E.vmap.end());
    K = std::vector<const NoteClass *>(kmap.size(), nullptr);
    for (size_t q = 0; q < kmap.size(); q++)
        if (kmap[q] >= 0)
            K[q] = (const NoteClass *)E.classes[kmap[q]].data();
    if (!E.vgs.empty()) {
        // BANK SELECT's tables for live's templates (each entry's trim a file
        // not GS's: live's one-note file), each one-tone slot's organ (vents' pcls)
        std::vector<int> nls, ls;
        std::vector<double> vt;
        for (const auto &v : E.vents) {
            nls.push_back((int)v.ls.size());
            for (const auto &l : v.ls)
                ls.insert(ls.end(), l.begin(), l.end());
            vt.push_back(v.trim[0]);
        }
        std::vector<const OrganSpec *> so(E.vmap.size() / 128, nullptr);
        for (size_t en = 1; en < E.vents.size(); en++)
            if (E.vents[en].ls.size() == 1 && E.vents[en].pcls >= 0 && E.cls_organ[E.vents[en].pcls] >= 0)
                so[E.vents[en].ls[0][0]] = &E.organs[E.cls_organ[E.vents[en].pcls]];
        nv_live_vars((int)E.vents.size(), nls.data(), ls.data(), vt.data(), E.vgs.data(), E.vgm2.data(),
                     (int)so.size(), so.data(), (long long)K.size());
    }
    memset(&t, 0, sizeof t);
    t.sr = SR; t.retrigger_fade = E.k[K_RETRIGGER]; t.nyq_om = E.k[K_NYQ_OM];
    t.sv[1] = 1.0; t.sound_vib_depth_cents = E.k[K_SVDC]; t.gl[1] = 0.05; t.fx = -1.0;
    for (int i = 0; i < 9; i++)
        t.room_bands[i] = E.k[K_BANDS + i];
    t.reflect = E.k[K_REFLECT] != 0.0;
    t.fixed_touch = 1;                          // live builds its templates at fixed touch
    cache = nv_tcache_new(K.data(), &t, tune_for(program, drums), E.trim.data(), E.kind.data(), E.fin.data(), E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK, E.k[K_RING_FLOOR], E.k[K_RING_MAX], E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR);
    raga_for(cache, program, drums);
    // --bank=V: the part's variation (live.Patch's: map x 128 + bank, an unbuilt one the capital tone)
    bank = drums ? 0 : atoi(opt(argc, argv, "bank", "0").c_str());
    if (bank)
        nv_tcache_set_var(cache, bank);
    if (drums)
        nv_tcache_kits(cache, E.kit_f0.data(), E.kit_seat.data(), E.kit_choke.data(), E.kit_skind.data(),
                       E.kit_spar.data(), 100.0);       // (live.ONESHOT_FLOOR_DB)
    if (!E.les.empty())                         // a rotary voice's templates through its cabinet
        nv_tcache_leslie(cache, E.les.data(), (int)E.les.size());
    int speeds[3] = {pp[3], pp[4], pp[5]};
    built = drums ? nv_tcache_warm(cache, program, 0, 127, 1, speeds, 1) : nv_tcache_warm(cache, program, 21, 96, pp[1], speeds, pp[2]);
    fprintf(stderr, "nvlive: %s %d, %ld templates\n", drums ? "drum set" : "program", program, built);
    // THE SLAB'S SLOTS (--slots: live's capacity, 65536 -- a vibraslap's
    // strike is 16524 rows)
    slots = atol(opt(argc, argv, "slots", "65536").c_str());
    part = nv_part_new(cache, 1, 0.0, pp[1], pp[6], pp[7], pp[8], pp[9], SR, E.k[K_RETRIGGER], slots, E.headroom, E.pan.data(), E.beta);
    if (!E.les.empty())                         // the room's Leslie: its rotors, on chorale
        nv_part_leslie(part, E.les.data(), (int)E.les.size());
    if (E.k.size() > (size_t)K_EFX + 132)       // the module's insertion effect (an export with its tables)
        nv_part_efx(part, E.k.data() + K_EFX, SR);
    if (E.has_p3d)                              // (a 3D type's place: live.pan_at's head)
        nv_part_place3d(part, E.p3d);
    {                                           // the gm2 store's built-in tables at the tuner's reference
        std::string a_ = opt(argc, argv, "a", ""), c_ = opt(argc, argv, "c", "");
        if (!tname.empty() && (!a_.empty() || !c_.empty()))
            nv_part_mts_ref(part, !a_.empty() ? 69 : 60, atof((!a_.empty() ? a_ : c_).c_str()));
    }

    if (!E.scan.empty())                        // the Hammond's scanner: its circuit's tables
        nv_part_scan(part, E.scan.data(), (long)E.scan.size());
    if (drums)
        nv_part_drums(part, program, E.kit_choke.data());
    else
        nv_part_program(part, program);
    // THE DRUMS BESIDE THE PART (live's Parts on one slab): a drum set
    // (--drum-set=P, Standard's 0) on channel 10, the part on every other
    // (--no-drums: the part alone); and --split=N, on the keyboard's channel
    // (--split-channel, 1), its keys under N the drum set's, moved by
    // --split-transpose=T (the hand drums, 60-87, from a low split)
    nodrums = drums;
    for (int i = 1; i < argc; i++)
        nodrums = nodrums || !strcmp(argv[i], "--no-drums");
    split = atoi(opt(argc, argv, "split", "0").c_str());
    // THE PARTS A PROGRAM CHANGE REACHES (live._listens): each patch's index,
    // channel (-1 every one), whether it is a drum set, its program and its
    // strings' identity (live's _voice_class(60): -1 a drum set's none), and
    // the program posted to it, which is its own once the post has run
    bank0 = drums ? 0 : atoi(opt(argc, argv, "bank", "0").c_str());
    pats = std::vector<PartAt>{{0, -1, drums, program, drums ? -1 : E.prog[program & 127].sid, program, bank0, bank0}};
    // live._PATCHES: each program's templates (key p) and each drum set's
    // (128 + set), built once and kept -- a note struck from one may sound on
    // (keyed 256 x variation + (128 a drum set's) + program)
    caches[256 * bank0 + (drums ? 128 : 0) + (program & 127)] = cache;
    if (!drums && (!nodrums || split > 0)) {
        int dset = atoi(opt(argc, argv, "drum-set", "0").c_str()) & 127;
        void *dcache = nv_tcache_new(K.data(), &t, E.freq.data(), E.trim.data(), E.kind.data(), E.fin.data(),
                                     E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK,
                                     E.k[K_RING_FLOOR], E.k[K_RING_MAX], E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR);
        nv_tcache_kits(dcache, E.kit_f0.data(), E.kit_seat.data(), E.kit_choke.data(), E.kit_skind.data(),
                       E.kit_spar.data(), 100.0);
        int nsp[1] = {-1};
        long dbuilt = nv_tcache_warm(dcache, dset, 0, 127, 1, nsp, 1);      // (live.DRUM_RANGE)
        caches[128 + dset] = dcache;
        if (!nodrums) {
            nv_part_patch_range(part, 0, -1, 1u << 9, 0, 127, 0);
            int pi = nv_part_add_patch(part, dcache, 2, 0.0, 1, -1, 0, 0, 0, 1, dset, E.kit_choke.data(), 9, 0u, 0, 127, 0);
            pats.push_back(PartAt{pi, 9, true, dset, -1, dset});
            fprintf(stderr, "nvlive: drum set %d on channel 10 (%ld templates)\n", dset, dbuilt);
        }
        if (split > 0) {
            int sch = atoi(opt(argc, argv, "split-channel", "1").c_str()) - 1;
            int str = atoi(opt(argc, argv, "split-transpose", "0").c_str());
            int pi = nv_part_add_patch(part, dcache, 3, 0.0, 1, -1, 0, 0, 0, 1, dset, E.kit_choke.data(), sch & 15, 0u,
                                     0, split - 1, str);
            pats.push_back(PartAt{pi, sch & 15, true, dset, -1, dset});
            fprintf(stderr, "nvlive: drum set %d under key %d on channel %d (transposed %+d)\n", dset, split,
                    (sch & 15) + 1, str);
        }
    }
    nv_part_detune_wheel(part, pp[6] >= 0);       // the export's speed: a honky-tonk's wheel, else -1
    if (E.k.size() > K_BEND_RANGE)
        nv_part_post(part, E.k[K_THRESH], E.k[K_BEND_RANGE], 35.0);     // (the mod range: live's default)
    // THE ROOM'S LATE TAIL (the export's: the session's room), through live's
    // convolver -- unless --dry
    dry = false;
    for (int i = 1; i < argc; i++)
        dry = dry || !strcmp(argv[i], "--dry");
    conv_cn = nullptr; conv_cp = nullptr; conv_cf = nullptr;  // (live's convolver: a room switched to's too)
    if (E.has_room && !E.conv_lib.empty()) {
        void *ch = dlopen(E.conv_lib.c_str(), RTLD_NOW | RTLD_LOCAL);
        conv_cn = ch ? dlsym(ch, "conv_new") : nullptr;
        conv_cp = ch ? dlsym(ch, "conv_process") : nullptr;
        conv_cf = ch ? dlsym(ch, "conv_free") : nullptr;
    }
    nv_part_conv(part, conv_cn, conv_cp, conv_cf);   // (a bus's reverb: live's Convolver)
    if (!dry && E.has_room && !E.ir.empty()) {
        void *cn = conv_cn, *cp = conv_cp, *cf = conv_cf;
        if (cn && cp && cf) {
            nv_part_room(part, cn, cp, cf, E.ir.data(), (long)E.ir.size() / 2, E.mir.empty() ? nullptr : E.mir.data(),
                       (long)E.mir.size() / 2, (int)BLK);
            fprintf(stderr, "nvlive: the room's tail, %.2f s%s\n", E.ir.size() / 2 / SR,
                    E.mir.empty() ? "" : ", and its modes");
        } else {
            fprintf(stderr, "nvlive: no convolver (%s): dry\n", E.conv_lib.c_str());
        }
    }
    // the free strings (live's register, its worker answering in step)
    const Export::Reg &rg = E.reg[program & 127];
    rg0 = &rg;
    noreg = drums;  // (a drum has no free strings)
    for (int i = 1; i < argc; i++)
        noreg = noreg || !strcmp(argv[i], "--no-register");
    // ...ON WHEREVER A PROGRAM HAS STRINGS, as live's is: a part that starts
    // on a voice without (an organ) has an empty bank, and takes a piano's
    // at a program change
    anyreg = false;
    for (int p = 0; p < 128; p++)
        anyreg = anyreg || E.reg[p].M > 0;
    reg_on = anyreg && !noreg;
    if (reg_on && rg.M > 0) {
        nv_part_register(part, rg.modes.data(), rg.M, rg.d[0], rg.d[1], rg.d[2], rg.d[3], rg.i[0], rg.d[4], rg.i[1],
                       rg.d[5], rg.d[6], rg.d[7], rg.d[8], rg.i[2], rg.note);
        const Export::Prog &pr = E.prog[program & 127];
        if (!pr.cbr.empty())                    // a harpsichord's choirs
            nv_part_reg_choirs(part, (int)pr.cbr.size(), pr.cbr.data(), pr.cross, (int)pr.buffs.size() / 2,
                             pr.buffs.data());
        if (E.cmap[128 * (program & 127) + 60] >= 0)    // a dulcimer's bridges by key (its class at key 60's)
            nv_part_reg_keys(part, (const NoteClass *)E.classes[E.cmap[128 * (program & 127) + 60]].data());
        fprintf(stderr, "nvlive: the register: %d string modes%s\n", rg.M,
                pr.cbr.empty() ? "" : (", " + std::to_string(pr.cbr.size()) + " choirs").c_str());
    } else if (reg_on) {
        StringMode none[1];
        int nonote[128] = {0};
        nv_part_register(part, none, 0, 0.0, 0.0, 0.0, 0.0, 128, E.k[K_BETA], 0, 0.12 * SR, E.k[K_FULL],
                       E.k[K_RESIDUAL], E.k[K_LN10_20], BLK, nonote);
        fprintf(stderr, "nvlive: the register: none for this voice, ready for one with strings\n");
    }
    nv_part_damper(part, E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_KNEE], E.k[K_BETA], E.k[K_LN10_20]);
    nv_part_press_db(part, atof(opt(argc, argv, "press-db",
                                  std::to_string(E.k.size() > K_PRESS_DB ? E.k[K_PRESS_DB] : 8.0).c_str()).c_str()));
    // A MESSENGER's CHART on every part (live's Part.cc_map "messenger"):
    // --messenger, or --messenger=pre-1.0.7 for that firmware's; its knobs
    // built from the export's tables (set before the panel is sent by its chart)
    nv_moog_tables(E.mtab.size() > 1 ? E.mtab.data() : nullptr);
    for (int i = 1; i < argc; i++)
        if (!strcmp(argv[i], "--messenger") || !strcmp(argv[i], "--messenger=pre-1.0.7")) {
            nv_part_set(part, 8, 1.0);
            nv_part_set(part, 9, argv[i][11] == '=' ? 1.0 : 0.0);
        }
    // A MESSENGER TO SET (live.py --messenger): --messenger-out=/dev/snd/midiCxDy,
    // written by its own thread; --messenger-bend=SEMITONES its bend range
    // (2); in --test, --messenger-log=FILE what it would be sent, by block
    // (never destroyed: its detached thread waits on mo.cv, and glibc's
    // pthread_cond_destroy at exit would wait for it -- a hang on quitting)
    MsgrOut &mo = *new MsgrOut;
    {
        std::string md = opt(argc, argv, "messenger-out", ""), ml = opt(argc, argv, "messenger-log", "");
        double mb = atof(opt(argc, argv, "messenger-bend", "2").c_str());
        if (!ml.empty())
            mo.log = fopen(ml.c_str(), "w");
        else if (!md.empty() && md != "none") {
            mo.fd = ::open(md.c_str(), O_WRONLY);
            if (mo.fd < 0)
                fprintf(stderr, "nvlive: no Messenger on %s -- none set\n", md.c_str());
            else
                mo.start();
        }
        if (mo.log || mo.fd >= 0) {
            nv_part_messenger(part, MsgrOut::send, &mo, mb);
            if (mo.fd >= 0)
                fprintf(stderr, "nvlive: Messenger on %s: its Moog parts set\n", md.c_str());
        }
    }
    const char *FN[3] = {"synth_voice", "synth_voice_xdec", "synth_voice_damp"};
    for (int q = 0; q < 3; q++) {
        void *h = dlopen(E.libs[q].c_str(), RTLD_NOW | RTLD_LOCAL);
        fn[q] = h ? dlsym(h, FN[q]) : nullptr;
        if (!fn[q]) {
            fprintf(stderr, "nvlive: no %s in %s\n", FN[q], E.libs[q].c_str());
            return 1;
        }
        if (q == 0)                         // (the Moog's mod rows: the kernel library's own)
            nv_part_moog_kernel(part, dlsym(h, "moog_pitch_cells"), dlsym(h, "moog_shape_rows"));
    }
    master = E.k[K_MASTER];
    // THE GPU (live.GpuRenderer), by default (--cpu: none): the setup on the
    // CPU, the samples on OpenCL (--gpu=c: the C reference, voice_samples);
    // a block with fewer than --gpu-min busy slots (live's GPU_MIN) on the
    // CPU. One that cannot be had says why and plays on the CPU, as live
    // does. PIPELINED on OpenCL (--no-pipeline: not), as live's
    // TUNING_GPU_PIPELINE: a block late, the next block's setup while the
    // GPU renders this one
    gopt = "cl";
    pipe = true;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--gpu"))
            gopt = "cl";
        if (!strcmp(argv[i], "--cpu"))
            gopt = "";
        if (!strcmp(argv[i], "--no-pipeline"))
            pipe = false;
    }
    gopt = opt(argc, argv, "gpu", gopt.c_str());
    if (!gopt.empty()) {
        std::string why;
        void *gl = E.gpu ? dlopen(E.gpu_lib.c_str(), RTLD_NOW | RTLD_LOCAL) : nullptr;
        void *gd = E.gpu ? dlopen(E.gpu_damp_lib.c_str(), RTLD_NOW | RTLD_LOCAL) : nullptr;
        void *vb = gl ? dlsym(gl, "voice_block") : nullptr, *vs = gl ? dlsym(gl, "voice_samples") : nullptr;
        void *vz = gl ? dlsym(gl, "voice_sizes") : nullptr;
        void *vbd = gd ? dlsym(gd, "voice_block") : nullptr, *vds = gd ? dlsym(gd, "voice_damp_set") : nullptr;
        void *cl = nullptr;
        if (!E.gpu)
            why = "the export has no GPU section (native_export.py --live again)";
        else if (!vb || !vs || !vz || !vbd || !vds)
            why = "no voice_block in " + E.gpu_lib + " / " + E.gpu_damp_lib;
        else if (gopt != "c") {
            int sz[3];
            ((void (*)(int *))vz)(sz);
            char err[512] = "";
            cl = nv_cl_new(E.gpu_dir.c_str(), sz, err, sizeof err);
            if (!cl)
                why = err;
        }
        if (why.empty()) {
            // FROM 100 BUSY SLOTS, not live's GPU_MIN (1000, set against Python's
            // cost of a GPU block): natively a GPU block is ~0.35 ms however
            // many rows it has, and the CPU's took 1.4 ms on average under
            // 1000 (5.7 ms at p99) -- ondine.mid's 60 s, real-time, register
            // off the thread: 489 blocks over 2.67 ms at 1000, none at 100.
            // Each side's own threshold is checked by nvlive_check --gpu-min.
            long gmin = atol(opt(argc, argv, "gpu-min", "100").c_str());
            nv_part_gpu(part, vb, vbd, vds, vs, vz, cl, gmin, atoi(opt(argc, argv, "gpu-threads", "4").c_str()));
            nv_part_pipeline(part, cl && pipe);
            fprintf(stderr, "nvlive: the GPU (%s), from %ld busy slots%s\n", cl ? "OpenCL" : "the C reference", gmin,
                    cl && pipe ? ", pipelined" : "");
        } else {
            fprintf(stderr, "nvlive: no GPU (%s): the CPU\n", why.c_str());
        }
    }
    // THE ROUTES ahead of the part (live.Route, Live.on_midi): the session's,
    // from the export, and --pedal-key's -- a key held as the sustain pedal,
    // pushed into (aftertouch) to lower the dampers
    // ...or, once the panel has edited them, the routes kept beside the export
    routes_file = std::string(argv[1]) + ".routes";
    if (FILE *rf = fopen(routes_file.c_str(), "r")) {
        E.routes.clear();
        std::array<int, 7> a;
        while (fscanf(rf, "%d %d %d %d %d %d %d", &a[0], &a[1], &a[2], &a[3], &a[4], &a[5], &a[6]) == 7)
            E.routes.push_back(a);
        fclose(rf);
        fprintf(stderr, "nvlive: the routes kept in %s\n", routes_file.c_str());
    }
    router = nv_rt_new();
    for (auto &a : E.routes)
        nv_rt_add(router, a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
    pks = opt(argc, argv, "pedal-key", "");
    pedal_route = std::array<int, 7>{3, atoi(pks.c_str()), 64, 0, -1, 0, 1};
    if (!pks.empty()) {
        nv_rt_add(router, 3, atoi(pks.c_str()), 64, 0, -1, 0, 1);
        fprintf(stderr, "nvlive: key %d is the sustain pedal, pushed into to lower the dampers\n", atoi(pks.c_str()));
    }
    if (!E.routes.empty())
        fprintf(stderr, "nvlive: %zu route(s) from the session\n", E.routes.size());
    event = [&](int type, int ch, int a, int b) {
        int out[4 * 16];
        int n = nv_rt_feed(router, type, ch, a, b, out, 16);
        for (int q = 0; q < n; q++)
            nv_part_event(part, out[4 * q], out[4 * q + 1], out[4 * q + 2], out[4 * q + 3]);
    };
    // PROGRAM CHANGES (live.on_midi's program_change, its _patch_worker and
    // _swap_patch). With no bank selected (CC0 0: the capital tone, the
    // standard map's): a part listening on the channel changes voice, a drum
    // part its set. Notes sounding keep the templates they were struck from.
    // A voice not native here is refused (said, and the part plays on).
    //
    // build(): the program's templates (live.Patch.warm), made once -- on the
    // builder thread when playing, in step under --test
    // BANK SELECT, as live hears it: each channel's CC0 and CC32 latched until
    // a program change reads them, Rx.BANK SELECT (off after GM 1's System
    // On), the map CC32 0 reads in (blockrender.DEFAULT_MAP: TUNING_MAP)
    rxbank = true;
    tmap_ = getenv("TUNING_MAP");
    default_map = tmap_ && *tmap_ ? atoi(tmap_) : 0;
    latch = [&](int type, int ch, int a, int b) {
        if (type == 2 && a == 0)
            bmsb[ch] = b;
        else if (type == 2 && a == 32)
            blsb[ch] = b;
    };
    // ...and a reset's (GM System On, GM 2 On, GS Reset, SC mode): the latches
    // cleared, Rx.BANK SELECT off after GM 1's alone
    sys_reset = [&](const uint8_t *x, int n) {
        if (n > 0 && x[0] == 0xF0) {
            x++;
            n--;
        }
        int lvl = (n >= 4 && x[0] == 0x7E && x[2] == 0x09) ? (x[3] == 0x01 ? 1 : x[3] == 0x03 ? 2 : 0) : 0;
        bool gs = n >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12
                  && ((x[4] == 0x40 && x[5] == 0x00 && x[6] == 0x7F && x[7] == 0x00)
                      || (x[4] == 0x00 && x[5] == 0x00 && x[6] == 0x7F));
        if (!lvl && !gs)
            return;
        rxbank = lvl != 1;
        bmsb.clear();
        blsb.clear();
    };
    // the entry a variation key selects for a program (live.cpp's var_entry): 0 none
    var_entry_of = [&](int p, int v) -> int {
        if (!v || E.vgs.empty() || p < 0 || p > 127)
            return 0;
        int msb = v & 0x7F, mp = v >> 7;
        if (!msb)
            return 0;
        int bs = 1 + 128 * (mp >= 1 && mp <= 4 ? mp : 0) + msb;
        return E.vgs[((size_t)((bs - 1) / 128) * 128 + p) * 128 + (bs - 1) % 128];
    };
    // the class a program's variation sounds at key 60 (live's Patch pc)
    cls60 = [&](int prog, int var) -> const NoteClass * {
        int cq = -1;
        int en = var ? var_entry_of(prog & 127, var) : 0;
        if (en > 0 && en < (int)E.vents.size() && !E.vents[en].ls.empty()) {
            const auto &l = E.vents[en].ls[0];
            int k = 60 + l[1];
            cq = k >= 0 && k <= 127 ? E.vmap[128 * (size_t)l[0] + k] : -1;
        } else if (!var) {
            cq = E.cmap[128 * (prog & 127) + 60];
        }
        return cq >= 0 ? (const NoteClass *)E.classes[cq].data() : nullptr;
    };
    // THE PUNGI's DRONE PATCH (live's Patch.drone_note_patch): its own
    // variation's templates over the choices' range (drone_note_choices)
    build_drone = [&](int prog, const NoteClass *k) -> void * {
        const int dv = k->dchoice_var, key = 256 * dv + (prog & 127);
        {
            std::lock_guard<std::mutex> lk(cmu);
            auto it = caches.find(key);
            if (it != caches.end())
                return it->second;
        }
        const int *pq = prec(prog, dv);
        if (!pq[0] || var_entry_of(prog & 127, dv) <= 0)
            return nullptr;
        void *c = nv_tcache_new(K.data(), &t, tune_for(prog, false), E.trim.data(), E.kind.data(), E.fin.data(),
                                E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK, E.k[K_RING_FLOOR],
                                E.k[K_RING_MAX], E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR);
        raga_for(c, prog, false);
        nv_tcache_set_var(c, dv);
        int lo = 127, hi = 0;
        for (int q = 0; q < k->n_dchoice; q++) {
            lo = std::min(lo, k->dchoice[q]);
            hi = std::max(hi, k->dchoice[q]);
        }
        int sp[3] = {pq[3], pq[4], pq[5]};
        nv_tcache_warm(c, prog & 127, lo, hi, pq[1], sp, pq[2]);
        std::lock_guard<std::mutex> lk(cmu);
        caches[key] = c;
        return c;
    };
    // ...given to a part's patch (nvlive's start, swap): its record's buckets and speed
    attach_drone = [&](int pi, int prog, bool dr, int var) {
        const NoteClass *k = dr ? nullptr : cls60(prog, var);
        void *dc = nullptr;
        int nb = 1, sp = -1;
        if (k && k->n_dchoice && k->dchoice_var) {
            const int key = 256 * k->dchoice_var + (prog & 127);
            std::lock_guard<std::mutex> lk(cmu);
            auto it = caches.find(key);
            dc = it != caches.end() ? it->second : nullptr;
            const int *pq = prec(prog, k->dchoice_var);
            nb = pq[1];
            sp = pq[6];
        }
        nv_part_drone_patch(part, pi, dc, nb, sp);
    };
    build = [&](int prog, bool dr, int var) -> void * {
        int key = 256 * var + (dr ? 128 : 0) + (prog & 127);
        {
            std::lock_guard<std::mutex> lk(cmu);
            auto it = caches.find(key);
            if (it != caches.end())
                return it->second;
        }
        bool native = false;
        for (int k = 0; k < 128 && !native; k++)
            native = E.cmap[(dr ? NV_K_DRUMS : 0) + 128 * (prog & 127) + k] >= 0;
        if (var) {                              // (a variation's: its slots the engine's)
            int en = var_entry_of(prog & 127, var);
            native = en > 0;
            for (const auto &l : en > 0 ? E.vents[en].ls : std::vector<std::array<int, 4>>())
                for (int k = 0; k < 128; k++)
                    native = native && (k + l[1] < 0 || k + l[1] > 127 || E.vmap[128 * (size_t)l[0] + k + l[1]] >= 0
                                        || E.cmap[128 * (prog & 127) + k] < 0);
        }
        if (!dr && !prec(prog, var)[0])
            native = false;
        if (!native)
            return nullptr;
        void *c = nv_tcache_new(K.data(), &t, tune_for(prog, dr), E.trim.data(), E.kind.data(), E.fin.data(),
                                E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK, E.k[K_RING_FLOOR],
                                E.k[K_RING_MAX], E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR);
        raga_for(c, prog, dr);
        if (var)
            nv_tcache_set_var(c, var);
        if (dr) {
            nv_tcache_kits(c, E.kit_f0.data(), E.kit_seat.data(), E.kit_choke.data(), E.kit_skind.data(),
                           E.kit_spar.data(), 100.0);
            int nsp[1] = {-1};
            nv_tcache_warm(c, prog & 127, 0, 127, 1, nsp, 1);
        } else {
            if (!E.les.empty())
                nv_tcache_leslie(c, E.les.data(), (int)E.les.size());
            const int *pq = prec(prog, var);
            int sp[3] = {pq[3], pq[4], pq[5]};
            nv_tcache_warm(c, prog & 127, 21, 96, pq[1], sp, pq[2]);
            retune(prog);
        }
        if (!dr) {                              // A PUNGI's DRONE: its own patch, beside (Patch.warm's)
            const NoteClass *k60 = cls60(prog, var);
            if (k60 && k60->n_dchoice && k60->dchoice_var)
                build_drone(prog, k60);
        }
        std::lock_guard<std::mutex> lk(cmu);
        caches[key] = c;
        return c;
    };
    // swap(): a built program posted to its part (nv_part_swap, done after the
    // next block's events), and its strings where they are another voice's
    // (live._reg_forget: the new voice's bank, or none)
    shown_program = drums ? 128 + program : program;  // (what the panel shows)
    shown_var = drums ? 0 : bank0;  // (...its variation, 0 the capital tone)
    last_ctl_code = 0;  // (the panel's EFX learn)
    last_ctl_ns = 0;
    swap = [&](size_t i, int prog, bool dr, int var, void *c) {
        PartAt &pa = pats[i];
        static const int DRUM_P[10] = {1, 1, 1, -1, -1, -1, -1, 0, 0, 0};
        const int *pq = dr ? DRUM_P : prec(prog, var);
        int sid = dr ? -1 : E.prog[prog & 127].sid;
        const Export::Reg &rr = E.reg[prog & 127];
        bool regd = reg_on && pa.pi == 0;
        int nonote[128] = {0};
        const int *note = !dr && rr.M > 0 ? rr.note : nonote;
        if (regd && sid != pa.sid) {
            const Export::Prog &pr = E.prog[prog & 127];
            if (!dr && rr.M > 0) {
                double k6[6] = {rr.d[0], rr.d[1], rr.d[2], rr.d[3], rr.d[4], rr.d[5]};
                nv_part_swap_bank(part, rr.modes.data(), rr.M, k6, rr.i[0], rr.i[1], note, (int)pr.cbr.size(),
                                pr.cbr.empty() ? nullptr : pr.cbr.data(), pr.cbr.empty() ? 1.0 : pr.cross,
                                (int)pr.buffs.size() / 2, pr.buffs.empty() ? nullptr : pr.buffs.data());
                if (E.cmap[128 * (prog & 127) + 60] >= 0)
                    nv_part_swap_bank_keys(part, (const NoteClass *)E.classes[E.cmap[128 * (prog & 127) + 60]].data());
            } else {
                StringMode none[1];
                double k6[6] = {0.0, 0.0, 0.0, 0.0, E.k[K_BETA], 0.12 * SR};
                nv_part_swap_bank(part, none, 0, k6, 128, 0, nonote, 0, nullptr, 1.0, 0, nullptr);
            }
        }
        nv_part_swap(part, pa.pi, c, prog & 127, dr, pq[1], pq[6], pq[7], pq[8], pq[9], pq[6] >= 0,
                   dr ? E.kit_choke.data() : nullptr, regd ? note : nullptr);
        attach_drone(pa.pi, prog, dr, var);     // (a pungi's drone patch, built with it)
        pa.posted = prog & 127;
        pa.posted_var = var;
        pa.drums = dr;
        pa.sid = sid;
        if (pa.pi == 0) {
            shown_var = dr ? 0 : var;
            shown_program = (dr ? 128 : 0) + (prog & 127);
        }
    };
    if (!drums) {                               // the starting patch's pungi drone, as build() makes them
        const NoteClass *k0 = cls60(program, bank0);
        if (k0 && k0->n_dchoice && k0->dchoice_var)
            build_drone(program, k0);
        attach_drone(0, program, false, bank0);
    }
    // asked(): a program change heard -- each part listening that is not
    // already that voice asks for it (live's patch_reqs, in order)
    told_old = false;
    asked = [&](int ch, int prog) {
        // THE BANK it is read under (resolve_patch): the variation key its
        // entry's slot has, none after GM 1's System On (Rx.BANK SELECT off)
        int en = 0;
        auto mi = bmsb.find(ch), li = blsb.find(ch);
        int msb = mi != bmsb.end() ? mi->second : 0, lsb = li != blsb.end() ? li->second : 0;
        if (rxbank && msb && !E.vgs.empty()) {
            if (msb == 121)
                en = lsb ? E.vgm2[(size_t)(prog & 127) * 128 + lsb] : 0;
            else if (msb != 120) {
                int mp = lsb ? lsb : default_map;
                en = E.vgs[((size_t)(mp >= 1 && mp <= 4 ? mp : 0) * 128 + (prog & 127)) * 128 + msb];
            }
        }
        const int var = en > 0 && !E.vents[en].ls.empty() ? E.vslot_v[E.vents[en].ls[0][0]] : 0;
        if (!E.has_prog) {                      // (an export from before LPROG: no strings to tell apart)
            if (!told_old)
                fprintf(stderr, "nvlive: this export has no LPROG section: program changes ignored "
                                "(native_export.py --live again)\n");
            told_old = true;
            return;
        }
        for (size_t i = 0; i < pats.size(); i++) {
            const PartAt &pa = pats[i];
            if (pa.channel >= 0 && pa.channel != ch)
                continue;
            const int pv = pa.drums ? 0 : var;
            if (pa.program == (prog & 127) && pa.var == pv)
                continue;                       // (live: part.patch.key == want -- the patch it HAS)
            reqs.push_back(Req{i, prog & 127, pa.drums, pv});
        }
    };
    // ...and a GM System On or GS Reset the part heard: every part to program
    // 0 (live's patch requests at a reset), its drums its own
    reset_asked = [&]() {
        if (!nv_part_take_reset(part) || !E.has_prog)
            return;
        for (size_t i = 0; i < pats.size(); i++)
            if (pats[i].program != 0 || pats[i].var != 0)
                reqs.push_back(Req{i, 0, pats[i].drums, 0});
    };
    // ...and once a block has run its posts, the programs posted are the parts'
    landed = [&]() {
        for (PartAt &pa : pats) {
            pa.program = pa.posted;
            pa.var = pa.posted_var;
        }
    };
    // the requests so far, in order, the last of a part's run only (live's
    // coalescing): built and swapped in. Its count of swaps
    settle = [&](std::vector<Req> &rq) {
        int n = 0;
        for (size_t q = 0; q < rq.size(); q++) {
            bool later = false;
            for (size_t r = q + 1; r < rq.size() && !later; r++)
                later = rq[r].i == rq[q].i;
            if (later)
                continue;
            void *c = build(rq[q].prog, rq[q].dr, rq[q].var);
            if (!c) {
                fprintf(stderr, "nvlive: %s %d is not native here: the part plays on\n",
                        rq[q].dr ? "drum set" : "program", rq[q].prog);
                continue;
            }
            swap(rq[q].i, rq[q].prog, rq[q].dr, rq[q].var, c);
            n++;
        }
        rq.clear();
        return n;
    };
    // THE ROOM (live.set_room, _room_switch): any the export carries (LROOMS).
    // On the builder (in step under --test): the new room's tail drawn at the
    // stage's directivity from the templates the parts have now
    // (_room_band_q: native/roomtail.cpp, as roomtail.py draws it); the room
    // put on every class (its walls, its voice snapshot's room: dry, the
    // reflections off and the classes as they were); every built patch let go
    // (live's _PATCHES.clear() -- their notes keep the templates they were
    // struck from, so the caches are kept, not freed) and each part's built
    // again in it and swapped in; the tail crossfaded in after the swaps'
    // block's events (_room_install)
    room_now = E.room.empty() ? "hall" : E.room;
    room_band_q = [&](double *bq) {
        double acc[9][2] = {};
        bool seen[9] = {};
        std::vector<double> rq;
        for (const PartAt &pa : pats) {
            void *c = nullptr;
            {
                std::lock_guard<std::mutex> lk(cmu);
                auto it = caches.find(256 * (pa.drums ? 0 : pa.posted_var) + (pa.drums ? 128 : 0) + (pa.posted & 127));
                c = it != caches.end() ? it->second : nullptr;
            }
            if (!c)
                continue;
            long n = nv_tcache_room_q(c, nullptr, 0);
            rq.resize(27 * (size_t)n);
            nv_tcache_room_q(c, rq.data(), n);
            for (long t_ = 0; t_ < n; t_++)
                for (int i = 0; i < 9; i++) {
                    const double q = rq[27 * t_ + 3 * i + 1], e = rq[27 * t_ + 3 * i + 2];
                    if (e > 0.0) {
                        seen[i] = true;
                        acc[i][0] += e;
                        acc[i][1] += e / std::max(q, 1e-6);
                    }
                }
        }
        int has = 0;
        for (int i = 0; i < 9; i++) {
            bq[i] = seen[i] && acc[i][1] > 0.0 ? acc[i][0] / acc[i][1] : NAN;
            has = has || !std::isnan(bq[i]);
        }
        return has;
    };
    // its tail (live.room_irs, build_room_tail): the diffuse field and its
    // modes, or a device's; NULL none (dry, outdoors, --dry, no convolver)
    room_tail = [&](const Export::RoomData &rd, const double *bq, int has) -> void * {
        if (dry || !rd.reflect || rd.spec.empty() || !(conv_cn && conv_cp && conv_cf))
            return nullptr;
        const int kind = (int)rd.spec[1];
        if (kind < 0)
            return nullptr;
        double *ir = nullptr, *mir = nullptr;
        long n = kind == 0 ? nv_room_tail_ir(rd.spec.data(), bq, has, (int)SR, 0, &ir)
                           : nv_room_tail_device(rd.spec.data(), E.room_dev.data(), bq, has, (int)SR, &ir);
        if (n <= 0)
            return nullptr;
        std::vector<float> f(2 * (size_t)n), fm;
        for (long q = 0; q < 2 * n; q++)
            f[q] = (float)ir[q];
        nv_room_tail_free(ir);
        long m = 0;
        if (kind == 0) {
            int nm = 0;
            m = nv_room_tail_modes(rd.spec.data(), bq, has, (int)SR, &mir, &nm);
            if (nm > 0 && rd.spec[6] > 25.0 && m > 0) {         // (use_modes: some, and Schroeder over 25 Hz)
                fm.resize(2 * (size_t)m);
                for (long q = 0; q < 2 * m; q++)
                    fm[q] = (float)mir[q];
            } else {
                m = 0;
            }
            nv_room_tail_free(mir);
        }
        return nv_room_new(conv_cn, conv_cp, conv_cf, f.data(), n, m ? fm.data() : nullptr, m, (int)BLK);
    };
    // the switch: false if the room is not one the export has or the room
    // already; *tail the tail to install (NULL none); each part's new patch
    // handed to give (in step: swap now; playing: the audio thread's)
    room_switch = [&](const std::string &name, void **tail,
                           const std::function<void(size_t, int, bool, int, void *)> &give) -> bool {
        const Export::RoomData *rd = nullptr;
        for (const auto &r : E.rooms)
            if (r.name == name)
                rd = &r;
        if (!rd || name == room_now)
            return false;
        double bq[9];
        int has = room_band_q(bq);
        *tail = room_tail(*rd, bq, has);
        if (rd->reflect && E.room_ncls == (int)E.classes.size()) {
            int per = 0;
            for (const auto &rg : E.room_rng)
                per += rg.second;
            for (int c = 0; c < E.room_ncls; c++) {
                uint8_t *dst = E.classes[c].data();
                const uint8_t *src = rd->fields.data() + (size_t)per * c;
                for (const auto &rg : E.room_rng) {
                    memcpy(dst + rg.first, src, rg.second);
                    src += rg.second;
                }
            }
        }
        t.reflect = rd->reflect;
        room_now = name;
        {
            std::lock_guard<std::mutex> lk(cmu);
            for (auto &kv : caches)
                cache_grave.push_back(kv.second);
            caches.clear();
        }
        for (size_t i = 0; i < pats.size(); i++) {
            const PartAt &pa = pats[i];
            void *c = build(pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var);
            if (c)
                give(i, pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var, c);
        }
        return true;
    };
    // --room-at=S:NAME[,S:NAME...] (--test): a room switched to at the block
    // second S falls in, before its events -- live.set_room's, its builder in step
    {
        std::string ra = opt(argc, argv, "room-at", "");
        size_t a = 0;
        while (a < ra.size()) {
            size_t b = ra.find(',', a);
            std::string it = ra.substr(a, b == std::string::npos ? std::string::npos : b - a);
            size_t c = it.find(':');
            if (c != std::string::npos)
                room_at.push_back(std::make_pair((long long)(atof(it.substr(0, c).c_str()) * SR) / BLK,
                                                 it.substr(c + 1)));
            if (b == std::string::npos)
                break;
            a = b + 1;
        }
    }
    // WHAT THE PANEL POSTS, done between two blocks (live.post); what it
    // reads, handed over after each; and a key it is learning -- and the
    // block's counters, the governor, the master (render_block's, live
    // and in step)
    learning = 0;  // 1 armed, 2 got one
    learnt_ch = -1; learnt_note = -1;
    swallow = std::pair<int, int>(-1, -1);  // the learnt key's release (audio thread)
    underruns = 0; over = 0; blocks = 0;
    worst = 0.0; budget = 1000.0 * BLK / SR;
    govern = true;
    for (int i = 1; i < argc; i++)
        govern = govern && strcmp(argv[i], "--no-governor");
    master_now = master;
    rt_on = false;
    return -1;
}

// ONE BLOCK, the audio thread's: the panel's posts, the keyboard's events,
// the builder's patches swapped in, the render (into buf, interleaved),
// the governor and the panel's snapshot
void nv_host::render_block(long long n0, float *buf, bool step)
{
    long long t0 = rt::now_ns();
    rt::busy_since = t0;
    std::vector<std::function<void(long long)>> todo;
    {
        std::lock_guard<std::mutex> lk(pmu);
        todo.swap(posted);
    }
    for (auto &f : todo)
        f(n0);
    std::vector<Midi> evs;
    {
        std::lock_guard<std::mutex> lk(mu);
        evs.swap(q);
    }
    for (const Midi &m : evs) {
        // LEARNING A KEY (live._learn_take): the next press taken, and
        // neither it nor its release plays
        if (learning == 1 && m.type == 0) {
            learnt_ch = m.ch;
            learnt_note = m.a;
            learning = 2;
            swallow = std::make_pair(m.ch, m.a);
            continue;
        }
        if (m.type == 1 && swallow == std::make_pair(m.ch, m.a)) {
            swallow = std::make_pair(-1, -1);
            continue;
        }
        // the last controller the hardware moved: the EFX panel's learn
        // (live.on_midi's last_ctl: CC 1-95, aftertouch, the wheel past 1024)
        if ((m.type == 2 && m.a >= 1 && m.a <= 95) || m.type == 3 || (m.type == 4 && abs(m.a) > 1024)) {
            last_ctl_code = m.type == 2 ? m.a : m.type == 3 ? 0x60 : 0x61;
            last_ctl_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                              std::chrono::steady_clock::now().time_since_epoch()).count();
        }
        if (m.type == 5) {
            if (asks)
                asked(m.ch, m.a);
            continue;
        }
        if (m.type == 6) {
            sys_reset(m.x.data(), (int)m.x.size());
            nv_part_sysex(part, m.x.data(), (int)m.x.size());
            continue;
        }
        latch(m.type, m.ch, m.a, m.b);
        event(m.type, m.ch, m.a, m.b);
    }
    nv_part_block(part, n0, BLK);
    if (step) {                         // (the tail installed after the block's events, as live's post)
        if (step_room_go)
            nv_part_room_set(part, step_room, BLK);
        step_room = nullptr;
        step_room_go = false;
        nv_part_room_reap(part);
    }
    if (asks)
        reset_asked();
    else
        nv_part_take_reset(part);
    landed();
    if (step) {
        step_swaps += settle(reqs);     // (live's builder in step: for the next block)
    } else {
        // the programs asked for to the builder, and those it has built swapped in
        {
            std::unique_lock<std::mutex> lk(bmu, std::try_to_lock);
            if (lk.owns_lock()) {
                if (!reqs.empty()) {
                    breq.insert(breq.end(), reqs.begin(), reqs.end());
                    reqs.clear();
                    bcv.notify_one();
                }
                if (room_ready_go) {        // (the room's tail first, as live's posts run)
                    nv_part_room_set(part, room_ready, BLK);
                    room_ready = nullptr;
                    room_ready_go = false;
                }
                for (auto &d : bdone)
                    if (d.second)
                        swap(d.first.i, d.first.prog, d.first.dr, d.first.var, d.second);
                bdone.clear();
            }
        }
    }
    long long t1 = rt::now_ns();
    nv_part_output(part, n0, (long)BLK, L, R, fn[0], fn[1], fn[2], BLK, master_now);
    last_step_ms = (t1 - t0) / 1e6;
    last_out_ms = (rt::now_ns() - t1) / 1e6;
    rt::busy_since = 0;
    double ms = (rt::now_ns() - t0) / 1e6;
    if (govern)
        nv_part_govern(part, ms, budget, n0 + BLK);
    blocks++;
    over += ms > budget;
    worst = ms > worst ? ms : worst;
    float pk[2] = {0.0f, 0.0f};
    for (long long k = 0; k < BLK; k++) {
        buf[2 * k] = L[k];
        buf[2 * k + 1] = R[k];
        pk[0] = std::max(pk[0], fabsf(L[k]));
        pk[1] = std::max(pk[1], fabsf(R[k]));
    }
    {
        std::lock_guard<std::mutex> lk(pmu);
        snap.n0 = n0;
        snap.blocks = blocks;
        snap.over = over;
        snap.ms_max = std::max(snap.ms_max, ms);
        snap.ms_sum += ms;
        snap.ms_n++;
        snap.peak[0] = std::max(snap.peak[0], pk[0]);
        snap.peak[1] = std::max(snap.peak[1], pk[1]);
        if ((blocks & 7) == 0)
            nv_part_stats(part, snap.eng);
        // the insertion effect, when it changed (the panel's)
        const long er = nv_part_efx_rev(part);
        if (er != snap.efx_rev && er >= 0) {
            int o[512];
            const char *why = "";
            int no = nv_part_efx_state(part, o, 512, &why);
            snap.efx.assign(o, o + std::max(0, no));
            snap.efx_why = why ? why : "";
            snap.efx_rev = er;
        }
        snap.rt = rt_on && !rt::dropped;
        snap.rt_dropped = rt::dropped > 0;
    }
}

// THE ENGINE'S HALF OF PLAYING: the register's, the scanner's and the
// valve's workers (the register in step under --reg-sync), the builder's
// state and its thread -- what nvlive's live mode does before its audio
// thread, and nv_host_start
void nv_host::start()
{
    if (!rsync)
        nv_part_reg_async(part);
    nv_part_scan_async(part);                     // the scanner's data on its own thread, as live's builder
    nv_part_amp_async(part);                      // ...and the valve's passes, as live's workers
    // THE BUILDER (live's _patch_worker): the programs asked for, warmed off
    // the audio thread, handed back to be swapped in between two blocks
    // ...a ROOM asked for (the panel's), and the tail its switch drew, for
    // the audio thread to install ahead of the parts' new patches (live's
    // _room_install, posted before the swaps); the room now, by its index
    room_ready = nullptr;
    room_ready_go = false;
    room_idx = -1;
    for (size_t q = 0; q < E.rooms.size(); q++)
        if (E.rooms[q].name == room_now)
            room_idx = (int)q;
    note = [&](const std::string &m) {
        if (nopanel) {
            fprintf(stderr, "nvlive: %s\n", m.c_str());
            return;
        }
        std::lock_guard<std::mutex> lk(bmu);
        notes.push_back(m);
    };
    builder_loop = [&]() {
        while (!g_stop) {
            std::vector<Req> rq;
            {
                std::unique_lock<std::mutex> lk(bmu);
                bcv.wait_for(lk, std::chrono::milliseconds(100),
                             [&] { return !breq.empty() || !room_req.empty() || g_stop; });
                rq.swap(breq);
            }
            nv_part_room_reap(part);                    // (an old tail, let go off the audio thread)
            std::string rname;
            {
                std::lock_guard<std::mutex> lk(bmu);
                rname.swap(room_req);
            }
            if (!rname.empty()) {                       // A ROOM (live._room_switch, on its patch worker)
                auto t0 = std::chrono::steady_clock::now();
                void *tl = nullptr;
                int nb_ = 0;
                bool ok = room_switch(rname, &tl, [&](size_t i_, int p_, bool d_, int v_, void *c_) {
                    std::lock_guard<std::mutex> lk(bmu);
                    bdone.push_back(std::make_pair(Req{i_, p_, d_, v_}, c_));
                    nb_++;
                });
                if (ok) {
                    {
                        std::lock_guard<std::mutex> lk(bmu);
                        room_ready = tl;
                        room_ready_go = true;
                    }
                    for (size_t q = 0; q < E.rooms.size(); q++)
                        if (E.rooms[q].name == rname)
                            room_idx = (int)q;
                    note("room " + rname + ": " + std::to_string(nb_) + " patch(es) built in "
                         + std::to_string((int)std::chrono::duration<double, std::milli>(
                                              std::chrono::steady_clock::now() - t0).count()) + " ms");
                }
            }
            for (size_t q = 0; q < rq.size() && !g_stop; q++) {
                bool later = false;
                for (size_t r = q + 1; r < rq.size() && !later; r++)
                    later = rq[r].i == rq[q].i;
                if (later)
                    continue;                   // (only the last of a part's run)
                bool had;
                {
                    std::lock_guard<std::mutex> lk(cmu);
                    had = caches.count((rq[q].dr ? 128 : 0) + rq[q].prog) > 0;
                }
                auto t0 = std::chrono::steady_clock::now();
                void *c = build(rq[q].prog, rq[q].dr, rq[q].var);
                std::string nm = rq[q].dr ? E.prog[rq[q].prog].kit : E.prog[rq[q].prog].name;
                if (!c)
                    note((rq[q].dr ? "drum set " : "program ") + std::to_string(rq[q].prog) + " (" + nm
                         + ") is not native here: the part plays on");
                else if (!had)
                    note("built " + std::to_string(rq[q].prog) + " " + nm + " in "
                         + std::to_string((int)std::chrono::duration<double, std::milli>(
                                              std::chrono::steady_clock::now() - t0).count()) + " ms");
                std::lock_guard<std::mutex> lk(bmu);
                bdone.push_back(std::make_pair(rq[q], c));
            }
        }
    };
    builder = std::thread(builder_loop);
}

// ---- THE C API (host.h): over nv_host, as nvlive drives it ----
extern "C" {

nv_host *nv_host_open_args(int argc, char **argv, char *err, int errlen)
{
    nv_host *h = new nv_host();
    int rc = h->open(argc, argv);
    if (rc != -1) {
        if (err && errlen > 0)
            snprintf(err, errlen, "nvlive's open refused (%d): see stderr", rc);
        return nullptr;                     // (not freed: open may have started the Messenger's writer)
    }
    h->rsync = false;
    for (int i = 1; i < argc; i++)
        h->rsync = h->rsync || !strcmp(argv[i], "--reg-sync");
    h->nopanel = false;                     // (the builder's notes queued: nv_host_message)
    h->play_buf.assign(2 * h->BLK, 0.0f);
    return h;
}

void nv_host_start(nv_host *h) { h->start(); }

void nv_host_close(nv_host *h)
{
    g_stop = true;
    h->bcv.notify_one();
    if (h->builder.joinable())
        h->builder.join();
}

int nv_host_rate(const nv_host *h) { return (int)h->SR; }
int nv_host_block(const nv_host *h) { return (int)h->BLK; }

int nv_host_render(nv_host *h, float *L, float *R, int frames)
{
    if (frames != h->BLK)
        return -1;
    h->render_block(h->play_n0, h->play_buf.data());
    for (int k = 0; k < frames; k++) {
        L[k] = h->play_buf[2 * k];
        R[k] = h->play_buf[2 * k + 1];
    }
    h->play_n0 += h->BLK;
    return 0;
}

void nv_host_midi(nv_host *h, const uint8_t *msg, int n)
{
    std::lock_guard<std::mutex> lk(h->midi_in_mu);
    h->midi_in.feed(msg, n, [&](Midi &&m) {
        std::lock_guard<std::mutex> lq(h->mu);
        h->q.push_back(std::move(m));
    });
}

void nv_host_snapshot(nv_host *h, nv_host_snap *s)
{
    std::lock_guard<std::mutex> lk(h->pmu);
    const panel::Snap &p = h->snap;
    s->n0 = p.n0;
    s->blocks = p.blocks;
    s->over = p.over;
    s->underruns = p.underruns;
    s->ms_max = p.ms_max;
    s->ms_mean = p.ms_n ? p.ms_sum / p.ms_n : 0.0;
    s->budget_ms = h->budget;
    s->peak[0] = p.peak[0];
    s->peak[1] = p.peak[1];
    for (int i = 0; i < 15; i++)
        s->eng[i] = p.eng[i];
    s->rt = p.rt;
    s->rt_dropped = p.rt_dropped;
    s->on_gpu = (int)p.eng[4];
    s->efx_rev = p.efx_rev;
    h->snap.ms_max = h->snap.ms_sum = 0.0;  // (since the last read, as the panel's take)
    h->snap.ms_n = 0;
    h->snap.peak[0] = h->snap.peak[1] = 0.0f;
}

int nv_host_message(nv_host *h, char *buf, int cap)
{
    std::lock_guard<std::mutex> lk(h->bmu);
    if (h->notes.empty())
        return 0;
    std::string m = h->notes.front();
    h->notes.erase(h->notes.begin());
    if (buf && cap > 0)
        snprintf(buf, cap, "%s", m.c_str());
    return (int)m.size();
}

int nv_host_rooms(nv_host *h, char *names, int cap)
{
    std::string s;
    for (const auto &r : h->E.rooms)
        s += r.name + "\n";
    if (names && cap > 0)
        snprintf(names, cap, "%s", s.c_str());
    return (int)h->E.rooms.size();
}

const char *nv_host_room(const nv_host *h)
{
    int k = h->room_idx;
    return k >= 0 && k < (int)h->E.rooms.size() ? h->E.rooms[k].name.c_str() : "";
}

void nv_host_set_room(nv_host *h, const char *name)
{
    for (const auto &r : h->E.rooms)
        if (r.name == name) {
            {
                std::lock_guard<std::mutex> lk(h->bmu);
                h->room_req = r.name;
            }
            h->bcv.notify_one();
            return;
        }
}

}  // extern "C"
