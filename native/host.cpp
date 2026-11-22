// host.cpp -- the native live host in libnative (host.h): today the
// export's reader, moved from nvlive.cpp whole; nvlive's main() follows.
#include "nvenv.h"
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
#include <cstdarg>
#include <unistd.h>
#include <vector>
#include "relocate.h"
#include "panel.h"
#include "pycompat.h"
#include <sys/mman.h>
#include <sys/stat.h>
#include "hostint.h"
#include "rtjoin.h"
#ifdef __APPLE__
#include <mach/mach.h>
#endif

// THE THREAD's OWN CPU TIME, user and system, ms (macOS: thread_info): set
// against a slow block's wall time it says whether the thread was computing
// slowly (cpu ~ wall: user a slow core, system memory faults) or not
// running at all (cpu << wall: preempted, demoted)
static void thread_cpu_ms(double *user, double *sys)
{
#ifdef __APPLE__
    thread_basic_info_data_t info;
    mach_msg_type_number_t n = THREAD_BASIC_INFO_COUNT;
    mach_port_t th = mach_thread_self();
    if (thread_info(th, THREAD_BASIC_INFO, (thread_info_t)&info, &n) == KERN_SUCCESS) {
        *user = info.user_time.seconds * 1e3 + info.user_time.microseconds * 1e-3;
        *sys = info.system_time.seconds * 1e3 + info.system_time.microseconds * 1e-3;
    } else {
        *user = *sys = 0.0;
    }
    mach_port_deallocate(mach_task_self(), th);
#else
    *user = *sys = 0.0;
#endif
}

namespace nvh {

bool read_export(const char *path, Export &E)
{
    FILE *f = fopen(path, "rb");
    // THE FILE MAPPED, copy on write: the classes and organs (nine tenths of
    // it) used where they lie, only the pages a session touches in memory
    if (f) {
        struct stat st;
        if (fstat(fileno(f), &st) == 0 && st.st_size > 0) {
            void *m = mmap(nullptr, (size_t)st.st_size, PROT_READ | PROT_WRITE, MAP_PRIVATE, fileno(f), 0);
            if (m != MAP_FAILED) {
                E.map = m;
                E.map_n = (size_t)st.st_size;
            }
        }
    }
    auto in_map = [&](long off, size_t n) -> unsigned char * {
        return E.map && off >= 0 && (size_t)off + n <= E.map_n ? (unsigned char *)E.map + off : nullptr;
    };
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
        {
            const long c0 = ftell(f);
            unsigned char *b = in_map(c0, (size_t)ncls * (size_t)csz);
            ok = ok && b && fseek(f, (long)ncls * csz, SEEK_CUR) == 0;
            for (int i = 0; ok && i < ncls; i++)
                E.classes.push_back(Mapped{b + (size_t)i * csz, (size_t)csz});
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
        // ORGA: the registered organs' tables (after their pad), each class's organ, each program's
        char om[4];
        int norg = 0, osz = 0, opad = 0;
        ok = ok && fread(om, 1, 4, f) == 4 && !memcmp(om, "ORGA", 4) && fread(&norg, 4, 1, f) == 1
             && fread(&osz, 4, 1, f) == 1 && osz == (int)sizeof(OrganSpec) && fread(&opad, 4, 1, f) == 1
             && fseek(f, opad, SEEK_CUR) == 0;
        if (ok) {
            const long o0 = ftell(f);
            unsigned char *b = in_map(o0, (size_t)norg * sizeof(OrganSpec));
            ok = b && (o0 % alignof(OrganSpec)) == 0 && fseek(f, (long)norg * (long)sizeof(OrganSpec), SEEK_CUR) == 0;
            E.organs.p = (OrganSpec *)b;
            E.organs.n = ok ? (size_t)norg : 0;
            E.cls_organ.resize(ncls);
            E.prog_organ.resize(128);
            ok = ok && fread(E.cls_organ.data(), 4, ncls, f) == (size_t)ncls && fread(E.prog_organ.data(), 4, 128, f) == 128;
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
            // ...THE SPECTRA-TONE's numbers and cone table (native.spectra_constants), its kernel's library
            if (ok) {
                int ns = 0, nc = 0;
                ok = fread(&ns, 4, 1, f) == 1 && ns >= 0 && ns < (1 << 24);
                if (ok) {
                    E.spec.resize((size_t)ns);
                    ok = fread(E.spec.data(), 8, (size_t)ns, f) == (size_t)ns && fread(&nc, 4, 1, f) == 1;
                }
                if (ok) {
                    E.cone_lib.resize((size_t)nc);
                    ok = fread(&E.cone_lib[0], 1, (size_t)nc, f) == (size_t)nc;
                }
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
                // ...THE CABINET CHOICES' SPEAKERS, last (native.cab_terms: 36
                // doubles a choice -- nv_cab_terms), where the export has them
                if (ok && ftell(f) < vp + 8 + vl) {
                    int nc = 0;
                    ok = fread(&nc, 4, 1, f) == 1;
                    E.cabt.resize(ok ? 36 * (size_t)nc : 0);
                    ok = ok && fread(E.cabt.data(), 8, E.cabt.size(), f) == E.cabt.size();
                }
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
                // the maps' own drum sets: their ids, keys' classes, and their
                // tables after the 128 sets' (set 128 + j's: nvrender's reading)
                int nm = 0;
                ok = fread(&nm, 4, 1, f) == 1 && nm >= 0 && nm <= 64;
                const size_t n = 128 * (size_t)(ok ? nm : 0);
                E.mk_ids.resize(ok ? nm : 0);
                E.mk_map.resize(n);
                std::vector<double> f0(n), seat(n), spar(NV_SPAR * n);
                std::vector<unsigned long long> chk(2 * n);
                std::vector<int> sk(n);
                ok = ok && fread(E.mk_ids.data(), 4, nm, f) == (size_t)nm && fread(E.mk_map.data(), 4, n, f) == n
                     && fread(f0.data(), 8, n, f) == n && fread(seat.data(), 8, n, f) == n
                     && fread(chk.data(), 8, 2 * n, f) == 2 * n && fread(sk.data(), 4, n, f) == n
                     && fread(spar.data(), 8, NV_SPAR * n, f) == NV_SPAR * n;
                E.kit_f0.insert(E.kit_f0.end(), f0.begin(), f0.end());
                E.kit_seat.insert(E.kit_seat.end(), seat.begin(), seat.end());
                E.kit_choke.insert(E.kit_choke.end(), chk.begin(), chk.end());
                E.kit_skind.insert(E.kit_skind.end(), sk.begin(), sk.end());
                E.kit_spar.insert(E.kit_spar.end(), spar.begin(), spar.end());
            } else if (!memcmp(tt, "MKNM", 4)) {
                for (size_t j = 0; ok && j < E.mk_ids.size(); j++) {
                    int ln = 0;
                    ok = fread(&ln, 4, 1, f) == 1 && ln >= 0 && ln < 256;
                    std::string s(ok ? ln : 0, '\0');
                    ok = ok && (ln == 0 || fread(&s[0], 1, ln, f) == (size_t)ln);
                    E.mk_names.push_back(s);
                }
            } else if (!memcmp(tt, "EFXU", 4)) {
                E.efxu.resize(tl);
                ok = fread(&E.efxu[0], 1, tl, f) == (size_t)tl;
            } else if (!memcmp(tt, "DKEY", 4)) {
                E.dkey.resize(tl);
                ok = tl == 0 || fread(&E.dkey[0], 1, tl, f) == (size_t)tl;
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
                    // (the block where it lies in the map -- the rooms' class ranges,
                    // 65 MB, read in place -- else read into E.rooms_buf)
                    struct RB {
                        const uint8_t *p = nullptr;
                        size_t n = 0;
                        size_t size() const { return n; }
                        const uint8_t &operator[](size_t i) const { return p[i]; }
                        bool empty() const { return n == 0; }
                    } rb;
                    if (fread(&rl, 8, 1, f) == 1 && rl > 0) {
                        const long at0 = ftell(f);
                        if (const unsigned char *m = in_map(at0, (size_t)rl)) {
                            rb.p = m;
                            rb.n = (size_t)rl;
                            if (fseek(f, rl, SEEK_CUR) != 0)
                                rb.n = 0;
                        } else {
                            E.rooms_buf.resize((size_t)rl);
                            if (fread(E.rooms_buf.data(), 1, E.rooms_buf.size(), f) == E.rooms_buf.size()) {
                                rb.p = E.rooms_buf.data();
                                rb.n = E.rooms_buf.size();
                            }
                        }
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
                                    rd.fields = rb.p + at;
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
                        int pg = 0, var = 0, nr = 0, nrow = 0;
                        if (fread(&pg, 4, 1, f) != 1 || fread(&var, 4, 1, f) != 1 || fread(&nr, 4, 1, f) != 1
                            || pg < 0 || pg > 127)
                            break;
                        auto &so = var ? E.vstops[std::make_pair(pg, var)] : E.stops[pg];
                        for (int pass = 0; pass < 2; pass++)        // (its names, then their labels)
                            for (int i = 0; i < nr; i++) {
                                int len = 0;
                                if (fread(&len, 4, 1, f) != 1)
                                    break;
                                std::string nm(len, ' ');
                                if (len && fread(&nm[0], 1, len, f) != (size_t)len)
                                    break;
                                (pass ? so.labels : so.names).push_back(nm);
                            }
                        if (fread(&nrow, 4, 1, f) != 1)
                            break;
                        for (int r = 0; r < nrow; r++) {
                            int n = 0;
                            if (fread(&n, 4, 1, f) != 1)
                                break;
                            std::vector<int> got(n), row, brk;
                            if (n && fread(got.data(), 4, n, f) != (size_t)n)
                                break;
                            for (int x : got) {         // (-1: the voice's line break, not a stop)
                                if (x < 0) {
                                    if (!row.empty())
                                        brk.push_back((int)row.size());
                                } else {
                                    row.push_back(x);
                                }
                            }
                            so.rows.push_back(row);
                            so.breaks.push_back(brk);
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
#include "kernels.h"             // (the kernels, linked in: no dlopen of our own)

#ifdef __GLIBC__
#include <malloc.h>
#endif
// A ROOM's KEY (nv_host::key_room's): 1 + its index in the export's rooms, 0 none
int nv_host::room_key_of(const std::string &name) const
{
    for (size_t q = 0; q < E.rooms.size(); q++)
        if (E.rooms[q].name == name)
            return (int)q + 1;
    return 0;
}

// A FILE PLAYED's REPORT (A5): its notes missed (none, its octaves right) and its patches' size
void nv_host::file_report()
{
    double mb = 0;
    int n = 0;
    {
        std::lock_guard<std::mutex> lk(cmu);
        for (const auto &kv : caches) {
            mb += nv_tcache_bytes(kv.second) / 1048576.0;
            n++;
        }
    }
    fprintf(stderr, "nvlive: the file: %ld note(s) asked of a template not built, %ld struck late, %ld on a stand-in; "
            "%d patch(es), %.1f MB\n", nv_part_misses(part), late_n.load(), stand_n.load(), n, mb);
}

// A FILE's NOTES SCANNED (A5): each room's masks, by the room's key; the
// room it starts in the room now (the user's, over none)
void nv_host::file_octaves(void *m, bool merged)
{
    std::map<int, std::array<unsigned, 256>> by_macro;
    file_octave_masks(m, by_macro, merged);
    std::lock_guard<std::mutex> lk(oct_mu);
    oct_rooms.clear();
    oct_any.fill(0u);
    for (const auto &kv : by_macro) {
        const std::string nm = kv.first >= 0 && kv.first < 8 ? GS_ROOM[kv.first] : !user_room.empty() ? user_room : room_now;
        auto &o = oct_rooms[room_key_of(nm)];
        for (int i = 0; i < 256; i++) {
            // (two macros on one room: both rooms' octaves -- OCT_NONE only where neither plays)
            const unsigned a = o[(size_t)i] & ~OCT_NONE, b = kv.second[(size_t)i] & ~OCT_NONE;
            o[(size_t)i] = (a | b) ? (a | b) : (o[(size_t)i] | kv.second[(size_t)i]);
            oct_any[(size_t)i] |= b;
        }
    }
    oct_on = true;
}


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
    // (the libraries and kernel sources it records: an app's own copies where it carries them)
    for (std::string *lp : {&E.libs[0], &E.libs[1], &E.libs[2], &E.gpu_lib, &E.gpu_damp_lib, &E.conv_lib, &E.lobe_lib,
                            &E.cone_lib})
        *lp = nv_reloc_lib(*lp);
    E.gpu_dir = nv_reloc_kernels(E.gpu_dir);
    // each class's organ, its table here (the export's pointer was the exporter's),
    // and a struck layer's class (sl_idx) -- WRITTEN ONLY WHERE IT CHANGES: the
    // classes lie in the mapped export, and a page written is the process's own
    // from then on (copy on write: iOS counts it); most classes have neither
    for (size_t i = 0; i < E.classes.size(); i++) {
        NoteClass *nc = (NoteClass *)E.classes[i].data();
        const OrganSpec *org = E.cls_organ[i] >= 0 ? &E.organs[E.cls_organ[i]] : nullptr;
        if (nc->organ != org)
            nc->organ = org;
        const NoteClass *sl = nc->sl_on && nc->sl_idx >= 0 && nc->sl_idx < (int)E.classes.size()
                              ? (const NoteClass *)E.classes[nc->sl_idx].data() : nullptr;
        if (nc->sl != sl)
            nc->sl = sl;
    }
    key_room = room_key_of(E.room.empty() ? "hall" : E.room);     // (the export's room: its patches' key)
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
        var &= 4095;                            // (a cabinet variant's record its variation's: one template serves every speaker)
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
    // --tuner, else live's gm2) -- any of midilib's, `hybrid@D:466`,
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
    tuner_now = tname.empty() ? "gm2" : tname;      // (the export's: live's gm2, unless --tuner)
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
    // ...and the maps' own drum sets' (a drum program 128 + j), after them
    // (nvrender's mapk_base), for live's caches and its templates' song
    const int mapk_base = (int)kmap.size();
    kmap.insert(kmap.end(), E.mk_map.begin(), E.mk_map.end());
    nv_tcache_mapk(mapk_base, (int)E.mk_ids.size(), E.mk_ids.data());
    // (the reader's too: a file's -- and a template's -- CC32 selects them, kit_in_map)
    nv_midi_map_kits(E.mk_ids.data(), (int)E.mk_ids.size());
    nv_midi_map_kits_play(!E.mk_ids.empty());
    nv_song_mapk_base(mapk_base);
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
        // (as nvrender gives its song them: each slot its entry's program
        // class's organ, and every organ the entry brings -- voice_classes:
        // its class's, then each layer's at key 60 -- for the recalls)
        const int ns = (int)(E.vmap.size() / 128);
        std::vector<const OrganSpec *> so(ns, nullptr);
        std::vector<std::vector<const OrganSpec *>> per(ns);
        for (size_t en = 1; en < E.vents.size(); en++) {
            const OrganSpec *o = E.vents[en].pcls >= 0 && E.cls_organ[E.vents[en].pcls] >= 0
                                 ? &E.organs[E.cls_organ[E.vents[en].pcls]] : nullptr;
            std::vector<const OrganSpec *> eo;
            if (o)
                eo.push_back(o);
            for (const auto &l : E.vents[en].ls) {   // (K's class there: the live export's cmap stops
                const long long kq = NV_K_VAR + 128LL * l[0] + 60;     // at the drum sets)
                if (l[0] >= 0 && kq < (long long)K.size() && K[kq] && K[kq]->organ)
                    eo.push_back(K[kq]->organ);
            }
            for (const auto &l : E.vents[en].ls)
                if (l[0] >= 0 && l[0] < ns) {
                    if (o)
                        so[l[0]] = o;
                    per[l[0]] = eo;
                }
        }
        std::vector<int> soff(1, 0);
        std::vector<const OrganSpec *> sog;
        for (int i = 0; i < ns; i++) {
            sog.insert(sog.end(), per[i].begin(), per[i].end());
            soff.push_back((int)sog.size());
        }
        nv_live_vars((int)E.vents.size(), nls.data(), ls.data(), vt.data(), E.vgs.data(), E.vgm2.data(),
                     ns, so.data(), soff.data(), sog.data(), (long long)K.size());
        nv_cab_terms((int)(E.cabt.size() / 36), E.cabt.data());
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
    if (!E.spec.empty())                        // ...a Spectra-Tone's, their cone rows
        nv_tcache_spectra(cache, E.spec.data(), (int)E.spec.size());
    int speeds[3] = {pp[3], pp[4], pp[5]};
    built = drums ? nv_tcache_warm(cache, program, 0, 127, 1, speeds, 1) : nv_tcache_warm(cache, program, 21, 108, pp[1], speeds, pp[2]);   // (MELODIC_RANGE: A0 to C8)
    fprintf(stderr, "nvlive: %s %d, %ld templates\n", drums ? "drum set" : "program", program, built);
    // THE SLAB'S SLOTS (--slots: live's capacity, 65536 -- a vibraslap's
    // strike is 16524 rows)
    slots = atol(opt(argc, argv, "slots", "65536").c_str());
    miss_swap.reserve(256);
    gval[14] = 20.0;                            // (a held note's stand-in after 20 ms: the Setup card's, the session's)
    part = nv_part_new(cache, 1, 0.0, pp[1], pp[6], pp[7], pp[8], pp[9], SR, E.k[K_RETRIGGER], slots, E.headroom, E.pan.data(), E.beta);
    if (!E.les.empty())                         // the room's Leslie: its rotors, on chorale
        nv_part_leslie(part, E.les.data(), (int)E.les.size());
    if (!E.spec.empty() && !E.cone_lib.empty()) {   // ...and the console's Spectra-Tone: its rotor, its kernel
        void *hc = nv::klib_open(E.cone_lib);
        void *sc = hc ? nv::klib_sym(hc, "synth_voice_lobe") : nullptr;
        if (sc && nv_cone_table(hc, E.spec))
            nv_part_spectra(part, E.spec.data(), (int)E.spec.size(), sc);
    }
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
    pats.reserve(64);                           // (parts added while the builder reads them: never moved)
    // live._PATCHES: each program's templates (key p) and each drum set's
    // (128 + set), built once and kept -- a note struck from one may sound on
    // (keyed 256 x variation + (128 a drum set's) + program)
    caches[ckey(program, drums, bank0)] = cache;
    if (!drums && (!nodrums || split > 0)) {
        int dset = atoi(opt(argc, argv, "drum-set", "0").c_str()) & 127;
        void *dcache = nv_tcache_new(K.data(), &t, E.freq.data(), E.trim.data(), E.kind.data(), E.fin.data(),
                                     E.k[K_REG_SCALE], E.k[K_FULL], E.k[K_RESIDUAL], E.k[K_BETA], BLK,
                                     E.k[K_RING_FLOOR], E.k[K_RING_MAX], E.k[K_KNEE], E.k[K_LN10_20], E.k[K_XDEC], SR);
        nv_tcache_kits(dcache, E.kit_f0.data(), E.kit_seat.data(), E.kit_choke.data(), E.kit_skind.data(),
                       E.kit_spar.data(), 100.0);
        int nsp[1] = {-1};
        long dbuilt = nv_tcache_warm(dcache, dset, 0, 127, 1, nsp, 1);      // (live.DRUM_RANGE)
        caches[ckey(dset, true, 0)] = dcache;
        if (!nodrums) {
            nv_part_patch_range(part, 0, -1, 1u << 9, 0, 127, 0);
            pats[0].excl = 1u << 9;
            int pi = nv_part_add_patch(part, dcache, 2, 0.0, 1, -1, 0, 0, 0, 1, dset, E.kit_choke.data(), 9, 0u, 0, 127, 0);
            pats.push_back(PartAt{pi, 9, true, dset, -1, dset});
            pats.back().pid = 2;
            fprintf(stderr, "nvlive: drum set %d on channel 10 (%ld templates)\n", dset, dbuilt);
        }
        if (split > 0) {
            int sch = atoi(opt(argc, argv, "split-channel", "1").c_str()) - 1;
            int str = atoi(opt(argc, argv, "split-transpose", "0").c_str());
            int pi = nv_part_add_patch(part, dcache, 3, 0.0, 1, -1, 0, 0, 0, 1, dset, E.kit_choke.data(), sch & 15, 0u,
                                     0, split - 1, str);
            pats.push_back(PartAt{pi, sch & 15, true, dset, -1, dset});
            pats.back().pid = 3;
            pats.back().hi = split - 1;
            pats.back().tr = str;
            // ...and the part from the split up (live: Part(lo=split)) -- a key
            // under it, every patch that claims it sounding, is the drums' alone
            nv_part_patch_range(part, 0, -1, nodrums ? 0u : 1u << 9, split, 127, 0);
            pats[0].lo = split;
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
        void *ch = nv::klib_open(E.conv_lib);
        conv_cn = ch ? nv::klib_sym(ch, "conv_new") : nullptr;
        conv_cp = ch ? nv::klib_sym(ch, "conv_process") : nullptr;
        conv_cf = ch ? nv::klib_sym(ch, "conv_free") : nullptr;
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
            msgr_reads = true;
            msgr_pre107 = argv[i][11] == '=';
        }
    // A MESSENGER TO SET (live.py --messenger): --messenger-out=/dev/snd/midiCxDy,
    // written by its own thread; --messenger-bend=SEMITONES its bend range
    // (2); in --test, --messenger-log=FILE what it would be sent, by block
    // (never destroyed: its detached thread waits on mo.cv, and glibc's
    // pthread_cond_destroy at exit would wait for it -- a hang on quitting)
    MsgrOut &mo = *new MsgrOut;
    msgr = &mo;
    {
        // ...OR FOUND BY ITSELF (live.messenger_watch): with no --messenger-out
        // (or =auto), a raw MIDI device named "Moog Messenger" is set when it is
        // plugged in and let go when it is unplugged; =none (the session's
        // "none") never. Not under --test: a check never writes to a device
        bool testing = false;
        for (int i = 1; i < argc; i++)
            testing = testing || !strcmp(argv[i], "--test");
        std::string md = opt(argc, argv, "messenger-out", ""), ml = opt(argc, argv, "messenger-log", "");
        double mb = atof(opt(argc, argv, "messenger-bend", "2").c_str());
        msgr_auto = !testing && ml.empty() && (md.empty() || md == "auto");
        if (!ml.empty())
            mo.log = fopen(ml.c_str(), "w");
        else if (!md.empty() && md != "none" && md != "auto") {
            msgr_connect(md, md);
            if (mo.fd.load() < 0)
                fprintf(stderr, "nvlive: no Messenger on %s -- none set\n", md.c_str());
        } else if (msgr_auto) {
            std::string pa, nm;
            if (find_messenger(pa, nm))
                msgr_connect(pa, nm);
        }
        if (mo.log || mo.fd.load() >= 0 || msgr_auto) {
            nv_part_messenger(part, MsgrOut::send, &mo, mb);
            if (mo.fd.load() >= 0)
                fprintf(stderr, "nvlive: Messenger on %s (%s): its Moog parts set\n", mo.where().c_str(),
                        mo.ident.empty() ? "no identity reply" : mo.ident.c_str());
            msgr_out = mo.log ? "a log" : "";
        }
        if (msgr_auto)
            std::thread([this, mb] {
                MsgrOut &o = *msgr;
                while (!g_stop) {
                    usleep(2000000);
                    if (o.fd.load() >= 0) {
                        std::string pa;
                        {
                            std::lock_guard<std::mutex> lk(o.mu);
                            pa = o.path;
                        }
                        if (!midi_exists(pa))
                            o.drop();               // (unplugged)
                        continue;
                    }
                    std::string pa, nm;
                    bool found = find_messenger(pa, nm), asked = false;
                    if (!found) {               // (...else one found by its answer: behind a USB MIDI interface)
                        std::lock_guard<std::mutex> lk(msgr_id_mu);
                        if (!msgr_id_path.empty() && midi_exists(msgr_id_path)) {
                            pa = msgr_id_path;
                            nm = msgr_id_name;
                            found = asked = true;
                        }
                    }
                    if (found && msgr_connect(pa, nm)) {
                        if (asked) {
                            std::lock_guard<std::mutex> lk(o.mu);
                            o.ident = "it answered as a Messenger";
                        }
                        fprintf(stderr, "nvlive: Messenger on %s: its Moog parts set\n", nm.c_str());
                        post([this, mb](long long) { nv_part_messenger(part, MsgrOut::send, msgr, mb); });
                    }
                }
            }).detach();
    }
    const char *FN[3] = {"synth_voice", "synth_voice_xdec", "synth_voice_damp"};
    for (int q = 0; q < 3; q++) {
        void *h = nv::klib_open(E.libs[q]);
        fn[q] = h ? nv::klib_sym(h, FN[q]) : nullptr;
        if (!fn[q]) {
            fprintf(stderr, "nvlive: no %s in %s\n", FN[q], E.libs[q].c_str());
            return 1;
        }
        if (q == 0)                         // (the Moog's mod rows: the kernel library's own)
            nv_part_moog_kernel(part, nv::klib_sym(h, "moog_pitch_cells"), nv::klib_sym(h, "moog_shape_rows"),
                                nv::klib_sym(h, "moog_coeff_rows"));
    }
    // THE MOOG EXTENSIONS' KERNELS (a note's loops, its contours' age, its
    // filter contour's depth: blockrender.ensure_moogx_lib, which the export
    // builds), beside the damper's: none, and those rows play as they were
    auto beside = [](const std::string &p, const char *was, const char *now) {
        size_t at = p.rfind(was);
        return at == std::string::npos ? std::string() : p.substr(0, at) + now + p.substr(at + strlen(was));
    };
    {
        std::string ml = beside(E.libs[2], "libsynthdamp_", "libsynthmoogx_");
        void *h = ml.empty() ? nullptr : nv::klib_open(ml);
        void *smx = h ? nv::klib_sym(h, "synth_voice_moogx") : nullptr;
        if (!smx)
            fprintf(stderr, "nvlive: no synth_voice_moogx in %s: a Moog's loops do not loop\n", ml.c_str());
        nv_part_moogx(part, smx, nullptr, nullptr, nullptr);
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
    if (gopt == "metal" || gopt == "opencl") {  // (macOS: --gpu=metal, the default, or --gpu=opencl, its reference)
        setenv("TUNING_GPU_API", gopt.c_str(), 1);
        gopt = "cl";
    }
    if (!gopt.empty()) {
        std::string why;
        void *gl = E.gpu ? nv::klib_open(E.gpu_lib) : nullptr;
        void *gd = E.gpu ? nv::klib_open(E.gpu_damp_lib) : nullptr;
        void *vb = gl ? nv::klib_sym(gl, "voice_block") : nullptr, *vs = gl ? nv::klib_sym(gl, "voice_samples") : nullptr;
        void *vz = gl ? nv::klib_sym(gl, "voice_sizes") : nullptr;
        void *vbd = gd ? nv::klib_sym(gd, "voice_block") : nullptr, *vds = gd ? nv::klib_sym(gd, "voice_damp_set") : nullptr;
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
            gpu_nthr = atoi(opt(argc, argv, "gpu-threads", "4").c_str());
            nv_part_gpu(part, vb, vbd, vds, vs, vz, cl, gmin, gpu_nthr);
            {                               // (the Moog extensions' build of the setup)
                std::string gm = beside(E.gpu_damp_lib, "libsynthgpudamp_", "libsynthgpumoogx_");
                void *hm = gm.empty() ? nullptr : nv::klib_open(gm);
                void *smx = nullptr;
                {
                    std::string ml = beside(E.libs[2], "libsynthdamp_", "libsynthmoogx_");
                    void *h = ml.empty() ? nullptr : nv::klib_open(ml);
                    smx = h ? nv::klib_sym(h, "synth_voice_moogx") : nullptr;
                }
                nv_part_moogx(part, smx, hm ? nv::klib_sym(hm, "voice_block") : nullptr,
                              hm ? nv::klib_sym(hm, "voice_damp_set") : nullptr, hm ? nv::klib_sym(hm, "voice_moogx_set") : nullptr);
            }
            nv_part_pipeline(part, cl && pipe);
            // (--gpu-depth=2: two blocks in flight -- an app's on macOS; 1, live's and nvlive's)
            nv_part_gpu_depth(part, atoi(opt(argc, argv, "gpu-depth", "1").c_str()));
            // (--gpu-span=N: a GPU block's descriptors set up for N samples -- a
            // held moment's partials ringing on; 0, the block's own)
            // (live's default 2048, so rubato's holds ring on -- rubato on by
            //  default; --test's 0, its checks' blocks as they were)
            bool test_ = false;
            for (int q = 1; q < argc; q++)
                test_ = test_ || !strcmp(argv[q], "--test");
            nv_part_gpu_span(part, atol(opt(argc, argv, "gpu-span", test_ ? "0" : "2048").c_str()));
            fprintf(stderr, "nvlive: the GPU (%s), from %ld busy slots%s\n", cl ? nv_cl_api(cl) : "the C reference", gmin,
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
    if (session_routes_set) {                   // (the session's, as live's: they win)
        E.routes = session_routes;
        fprintf(stderr, "nvlive: the routes from the session\n");
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
            engine_event(out[4 * q], out[4 * q + 1], out[4 * q + 2], out[4 * q + 3]);
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
    tmap_ = nv_env("TUNING_MAP");
    default_map = tmap_ && *tmap_ ? atoi(tmap_) : 0;
    latch = [&](int type, int ch, int a, int b) {
        if (type == 2 && a == 0)
            bmsb[ch] = b;
        else if (type == 2 && a == 32)
            blsb[ch] = b;
        else if (type == 2 && (a == 83 || a == 85) && E.has_prog) {
            // THE CABINET (CC83) or THE PICKUP (CC85) of the parts on the
            // channel, at once (live's on_midi): the program on its way, if one
            // is -- a program change puts it back to the voice's own
            for (size_t i = 0; i < pats.size(); i++) {
                PartAt &pa = pats[i];
                if (pa.gone || pa.drums || (pa.channel >= 0 && pa.channel != ch))
                    continue;
                {
                    std::lock_guard<std::mutex> lk(parts_mu);
                    (a == 83 ? pa.cab : pa.pk) = b ? b : -1;
                }
                const bool w = pa.want >= 0;
                const int p = w ? pa.want : pa.program, v = with_cab(p, w ? pa.want_var : pa.var, std::max(0, pa.cab),
                                                                     std::max(0, pa.pk));
                if (!pa.is(p, false, v))
                    ask(i, p, false, v);
            }
        }
    };
    // ...and a reset's (GM System On, GM 2 On, GS Reset, SC mode): the latches
    // cleared, Rx.BANK SELECT off after GM 1's alone; true where it was one
    sys_reset = [&](const uint8_t *x, int n) -> bool {
        if (n > 0 && x[0] == 0xF0) {
            x++;
            n--;
        }
        int lvl = (n >= 4 && x[0] == 0x7E && x[2] == 0x09) ? (x[3] == 0x01 ? 1 : x[3] == 0x03 ? 2 : 0) : 0;
        bool gs = n >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12
                  && ((x[4] == 0x40 && x[5] == 0x00 && x[6] == 0x7F && x[7] == 0x00)
                      || (x[4] == 0x00 && x[5] == 0x00 && x[6] == 0x7F));
        if (!lvl && !gs)
            return false;
        rxbank = lvl != 1;
        bmsb.clear();
        blsb.clear();
        for (int c = 0; c < 16; c++) {
            chdr[c] = c == 9;
            hn_msb[c] = hn_lsb[c] = 127;
        }
        hdedit.clear();
        hrmap.clear();
        for (int c = 0; c < 16; c++) {
            hvol[c] = 100;
            hexpr[c] = 127;
        }
        return true;
    };
    // the entry a variation key selects for a program (live.cpp's var_entry): 0 none
    var_entry_of = [&](int p, int v) -> int {
        v &= 4095;                              // (a cabinet choice over bit 12: the variation's entry -- its voice the cache's)
        if (!v || E.vgs.empty() || p < 0 || p > 127)
            return 0;
        int msb = v & 0x7F, mp = v >> 7;
        if (!msb)
            return 0;
        int bs = 1 + 128 * (mp >= 1 && mp <= 4 ? mp : 0) + msb;
        return E.vgs[((size_t)((bs - 1) / 128) * 128 + p) * 128 + (bs - 1) % 128];
    };
    // the cabinets a program's variation offers a part (its key-60 class's cab_mask)
    cab_mask_of = [&](int p, int v) -> int {
        const NoteClass *k = cls60(p & 127, v & 4095);
        return k ? k->cab_mask : 0;
    };
    pk_mask_of = [&](int p, int v) -> int {
        const NoteClass *k = cls60(p & 127, v & 4095);
        return k ? k->pk_mask : 0;
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
        const int dv = k->dchoice_var;
        const long long key = ckey(prog & 127, false, dv);
        {
            std::lock_guard<std::mutex> lk(cmu);
            auto it = caches.find(key);
            if (it != caches.end()) {
                cache_used[key] = ++cache_tick;
                return it->second;
            }
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
        cache_used[key] = ++cache_tick;
        return c;
    };
    // ...given to a part's patch (nvlive's start, swap): its record's buckets and speed
    attach_drone = [&](int pi, int prog, bool dr, int var) {
        const NoteClass *k = dr ? nullptr : cls60(prog, var);
        void *dc = nullptr;
        int nb = 1, sp = -1;
        if (k && k->n_dchoice && k->dchoice_var) {
            const long long key = ckey(prog & 127, false, k->dchoice_var);
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
        // (a map's own drum set, 128 + j, a key past every program's and variation's)
        const bool mapk = dr && prog >= 128;
        long long key = ckey(prog, dr, var);
        {
            std::lock_guard<std::mutex> lk(cmu);
            auto it = caches.find(key);
            if (it != caches.end()) {
                cache_used[key] = ++cache_tick;
                return it->second;
            }
        }
        bool native = false;
        if (mapk) {
            const size_t j = (size_t)(prog - 128);
            for (int k = 0; k < 128 && !native && j < E.mk_ids.size(); k++)
                native = E.mk_map[128 * j + k] >= 0;
        } else {
            for (int k = 0; k < 128 && !native; k++)
                native = E.cmap[(dr ? NV_K_DRUMS : 0) + 128 * (prog & 127) + k] >= 0;
        }
        if (var & 4095) {                       // (a variation's: its slots the engine's -- a cabinet choice alone over bit 12 is the capital's)
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
        // ITS ROOM (A5): with a budget, the patches no part plays let go first;
        // the bytes left are this one's to take
        long long limit = 0;
        if (patch_budget > 0) {
            // (the least recently used let go, as far as this one took when last built)
            long long want_ = 0;
            {
                std::lock_guard<std::mutex> lk(cmu);
                auto wb = built_bytes.find(key);
                want_ = wb != built_bytes.end() ? wb->second : 0;
            }
            trim_to = std::max(0LL, patch_budget - want_);
            cache_trim({});
            trim_to = -1;
            long long held_ = 0;
            {
                std::lock_guard<std::mutex> lk(cmu);
                for (const auto &kv : caches) {
                    auto b = cache_bytes.find(kv.second);
                    if (b == cache_bytes.end())
                        b = cache_bytes.emplace(kv.second, nv_tcache_bytes(kv.second)).first;
                    held_ += b->second;
                }
            }
            limit = std::max(1LL, patch_budget - held_);
        }
        // ...and A FILE's OCTAVES, while one plays (0: every octave)
        unsigned oct = 0;
        {
            std::lock_guard<std::mutex> lk(oct_mu);
            if (oct_on) {
                const size_t ix = (size_t)((dr ? 128 : 0) + (prog & 127));
                auto ro = oct_rooms.find(key_room);
                oct = ro != oct_rooms.end() ? ro->second[ix] : oct_any[ix];     // (a room it did not name: every room's)
            }
        }
        if (getenv("NV_PATCH_SIZES"))
            fprintf(stderr, "nvlive: building %s %d var %d in room key %d: octaves %03x%s\n", dr ? "drum set" : "program",
                    prog & 127, var, key_room, oct & 0xFFFu, oct == OCT_NONE ? " (none)" : oct_on ? "" : " (no file)");
        long long got = 0;
        bool thin = false;                      // (over the budget: its middle octaves only, the rest on demand)
        const auto t_build = std::chrono::steady_clock::now();
        // ...THE WARM: whole, or a file's octaves; under a budget, the middle
        // octaves out as far as they fit (none fits: refused)
        auto warm = [&](int p_, int lo, int hi, int nb, const int *sp, int nsp) -> bool {
            if (limit <= 0 || oct)
                return nv_tcache_warm_b(c, p_, lo, hi, nb, sp, nsp, &bp_done, oct, limit, &got) >= 0;
            static const int ORD[11] = {4, 5, 3, 6, 2, 7, 1, 8, 0, 9, 10};
            const long step_ = (long)(hi - lo + 1) * nb * nsp / 11;
            for (int o : ORD) {
                const long long left = limit - got;
                long long g = 0;
                if (left <= 0) {
                    thin = true;
                    break;
                }
                const long r = nv_tcache_warm_b(c, p_, lo, hi, nb, sp, nsp, nullptr, 1u << o, left, &g);
                __atomic_fetch_add(&bp_done, step_, __ATOMIC_RELAXED);
                if (r < 0) {
                    thin = true;
                    got = nv_tcache_bytes(c);      // (what that octave kept of itself too)
                    break;
                }
                got += g;
            }
            long nt = 0;
            long long rows_ = 0;
            nv_tcache_shape(c, &nt, &rows_);
            return !thin || nt > 0;
        };
        auto refuse = [&]() -> void * {
            nv_tcache_free(c);
            char b_[160];
            snprintf(b_, sizeof b_, "needs more than the %.0f MB left of the patches' %.0f MB: the part plays on as it was",
                     limit / 1048576.0, patch_budget / 1048576.0);
            refused = std::string(dr ? "drum set " : "program ") + std::to_string(prog & 127) + " " + b_;
            __atomic_store_n(&bp_total, 0L, __ATOMIC_RELEASE);
            return nullptr;
        };
        // (its progress, for the panel: every key, bucket and speed it warms)
        auto begin = [&](long total) {
            std::lock_guard<std::mutex> lk(bmu);
            bp_name = (dr ? "drum set " : "program ") + std::to_string(prog & 127) + " "
                      + (dr ? kit_name(prog) : E.prog[prog & 127].name);
            __atomic_store_n(&bp_done, 0L, __ATOMIC_RELAXED);
            __atomic_store_n(&bp_total, total, __ATOMIC_RELEASE);
        };
        if (dr) {
            nv_tcache_kits(c, E.kit_f0.data(), E.kit_seat.data(), E.kit_choke.data(), E.kit_skind.data(),
                           E.kit_spar.data(), 100.0);
            int nsp[1] = {-1};
            begin(128);
            if (!warm(prog, 0, 127, 1, nsp, 1))
                return refuse();
        } else {
            if (!E.les.empty())
                nv_tcache_leslie(c, E.les.data(), (int)E.les.size());
            if (!E.spec.empty())
                nv_tcache_spectra(c, E.spec.data(), (int)E.spec.size());
            {                                   // (a note that borrows a kit key's strokes: the sets' tables)
                const NoteClass *k60 = cls60(prog, var);
                if (k60 && k60->sfx_prog >= 0)
                    nv_tcache_stroke_kits(c, E.kit_f0.data(), E.kit_seat.data(), E.kit_choke.data(),
                                          E.kit_skind.data(), E.kit_spar.data());
            }
            const int *pq = prec(prog, var);
            int sp[3] = {pq[3], pq[4], pq[5]};
            begin(76L * pq[1] * pq[2]);
            if (!warm(prog & 127, 21, 108, pq[1], sp, pq[2]))     // (MELODIC_RANGE)
                return refuse();
            retune(prog);
        }
        __atomic_store_n(&bp_total, 0L, __ATOMIC_RELEASE);
        if (getenv("NV_PATCH_SIZES"))
            fprintf(stderr, "nvlive: built %s %d var %d: %.1f MB in %.0f ms\n", dr ? "drum set" : "program", prog & 127, var,
                    got / 1048576.0,
                    std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t_build).count());
        if (!dr) {                              // A PUNGI's DRONE: its own patch, beside (Patch.warm's)
            const NoteClass *k60 = cls60(prog, var);
            if (k60 && k60->n_dchoice && k60->dchoice_var)
                build_drone(prog, k60);
        }
        if (thin) {
            char b_[200];
            snprintf(b_, sizeof b_, "%s: more than the %.0f MB left of the patches' %.0f MB -- its middle octaves "
                     "built (%.0f MB), the rest as they are played", tone_name(prog, dr, var).c_str(),
                     limit / 1048576.0, patch_budget / 1048576.0, got / 1048576.0);
            tell(b_);
        }
        std::lock_guard<std::mutex> lk(cmu);
        caches[key] = c;
        cache_used[key] = ++cache_tick;
        if (oct || thin)
            partial.insert(key);
        else
            built_bytes[key] = got;
        return c;
    };
    // PATCHES LET GO (off the audio thread): to the part with their
    // templates, at the next hand-off (the caller holds neither lock)
    retire = [&](const std::vector<void *> &cs) {
        if (cs.empty())
            return;
        std::vector<std::pair<void *, std::vector<const void *>>> rs;
        for (void *c : cs) {
            std::vector<const void *> ts((size_t)nv_tcache_templates(c, nullptr, 0));
            nv_tcache_templates(c, ts.data(), (long)ts.size());
            std::sort(ts.begin(), ts.end());
            rs.emplace_back(c, std::move(ts));
        }
        {
            std::lock_guard<std::mutex> lk(cmu);
            for (void *c : cs)
                cache_bytes.erase(c);
        }
        std::lock_guard<std::mutex> lk(bmu);
        for (auto &r : rs)
            retire_req.push_back(std::move(r));
    };
    // THE LRU (live's patch_for): over the cap, the least recently used
    // patch no part plays or wants, nor one just built (fresh) or built and
    // not yet swapped in, is let go -- until under it, or every patch left is
    // in use (a rig playing sixteen voices keeps all sixteen)
    cache_trim = [&](const std::set<long long> &fresh) {
        std::set<long long> pins(fresh.begin(), fresh.end());
        std::set<void *> pinc;
        {
            std::lock_guard<std::mutex> lk(oct_mu);
            if (oct_on) {                       // (a file's patches, every room's, kept while it plays)
                std::lock_guard<std::mutex> lc(cmu);
                pins.insert(partial.begin(), partial.end());
            }
        }
        {
            std::lock_guard<std::mutex> lk(bmu);
            pins.insert(pin_keys.begin(), pin_keys.end());
            for (const auto &d : bdone)
                pinc.insert(d.second);
            for (const auto &d : add_done)
                pinc.insert(d.second);
        }
        std::vector<void *> out;
        {
            std::lock_guard<std::mutex> lk(cmu);
            long long tot = 0;
            for (const auto &kv : caches) {
                auto b = cache_bytes.find(kv.second);
                if (b == cache_bytes.end()) {
                    b = cache_bytes.emplace(kv.second, nv_tcache_bytes(kv.second)).first;
                    static const bool say = getenv("NV_PATCH_SIZES") != nullptr;     // (each patch's size, once: mem_measure)
                    if (say)
                        fprintf(stderr, "nvlive: patch key %lld: %.1f MB\n", kv.first, b->second / 1048576.0);
                }
                tot += b->second;
            }
            const long long cap = trim_to >= 0 ? trim_to : patch_budget > 0 ? std::min(cache_cap, patch_budget) : cache_cap;
            while (tot > cap) {
                long long drop = -1;
                long long oldest = LLONG_MAX;
                for (const auto &kv : caches) {
                    if (pins.count(kv.first) || pinc.count(kv.second))
                        continue;
                    auto u = cache_used.find(kv.first);
                    const long long at = u != cache_used.end() ? u->second : 0;
                    if (at < oldest) {
                        oldest = at;
                        drop = kv.first;
                    }
                }
                if (drop < 0)
                    break;                      // (every patch left is in use)
                void *c = caches[drop];
                tot -= cache_bytes[c];
                caches.erase(drop);
                cache_used.erase(drop);
                out.push_back(c);
            }
        }
        retire(out);
    };
    // THE KEYS IN USE (on the audio thread, bmu held): each part's patch,
    // the one it asked for, and a pungi's drone beside each
    pin_keys.reserve(256);
    pins_update = [&]() {
        pin_keys.clear();
        auto pin = [&](int prog, bool dr, int var) {
            pin_keys.push_back(ckey(prog, dr, var));
            const NoteClass *k = dr ? nullptr : cls60(prog, var);
            if (k && k->n_dchoice && k->dchoice_var)
                pin_keys.push_back(256 * k->dchoice_var + (prog & 127));
        };
        for (const PartAt &pa : pats) {
            if (pa.gone)
                continue;
            pin(pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var);
            if (pa.want >= 0)
                pin(pa.want, pa.want_dr, pa.want_dr ? 0 : pa.want_var);
        }
    };
    if (const char *mb = getenv("NV_PATCH_CACHE_MB"))
        cache_cap = (long long)atof(mb) * (1LL << 20);
    // THE PATCHES' BUDGET (A5): --patch-budget-mb=N, NV_PATCH_BUDGET_MB (0: none)
    {
        std::string pb = opt(argc, argv, "patch-budget-mb", getenv("NV_PATCH_BUDGET_MB") ? getenv("NV_PATCH_BUDGET_MB") : "0");
        patch_budget = (long long)(atof(pb.c_str()) * 1048576.0);
        if (patch_budget > 0)
            fprintf(stderr, "nvlive: the patches' budget, %.0f MB\n", patch_budget / 1048576.0);
    }
    // swap(): a built program posted to its part (nv_part_swap, done after the
    // next block's events), and its strings where they are another voice's
    // (live._reg_forget: the new voice's bank, or none)
    shown_program = drums ? 128 + program : program;  // (what the panel shows)
    shown_var = drums ? 0 : bank0;  // (...its variation, 0 the capital tone)
    last_ctl_code = 0;  // (the panel's EFX learn)
    last_ctl_ns = 0;
    swap = [&](size_t i, int prog, bool dr, int var, void *c) {
        if (i >= pats.size() || pats[i].gone)
            return;                             // (a part taken away meanwhile)
        if (recording)
            rec("s %lld part %zu program %d var %d drums %d", snap.n0, i, prog, var, (int)dr);
        PartAt &pa = pats[i];
        static const int DRUM_P[10] = {1, 1, 1, -1, -1, -1, -1, 0, 0, 0};
        const int *pq = dr ? DRUM_P : prec(prog, var);
        int sid = dr ? -1 : E.prog[prog & 127].sid;
        const Export::Reg &rr = E.reg[prog & 127];
        bool regd = reg_on && pa.pi == 0;
        int nonote[128] = {0};
        const int *note = !dr && rr.M > 0 ? rr.note : nonote;
        if (regd && (sid != pa.sid || retune_bank.exchange(false))) {
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
        nv_part_swap(part, pa.pi, c, dr ? prog : prog & 127, dr, pq[1], pq[6], pq[7], pq[8], pq[9], pq[6] >= 0,
                   dr ? E.kit_choke.data() : nullptr, regd ? note : nullptr);
        attach_drone(pa.pi, prog, dr, var);     // (a pungi's drone patch, built with it)
        // A PRESET's STOPS, for this organ -- again at each swap of it (the
        // preset's tuner rebuilds it after its program: live builds the two
        // as one patch), until another program or a stop drawn by hand
        // (a swap BEFORE the organ's -- the old program rebuilt for the
        // preset's tuner, on its way already -- leaves them waiting: only one
        // after the organ has come in is "another program")
        if (pa.pi == 0 && !dr && prog == pending_drawn_prog) {
            std::vector<const char *> nm;
            for (const auto &x : pending_drawn)
                nm.push_back(x.c_str());
            nv_part_set_drawn_names(part, 0, nm.data(), (int)nm.size());
            pending_drawn_in = true;
        } else if (pa.pi == 0 && pending_drawn_in) {
            pending_drawn_prog = -1;
        }
        pa.posted = dr ? prog : prog & 127;
        pa.posted_var = var;
        pa.drums = dr;
        if (dr) {
            // A DRUM SET's OWN KEYS, asked as it comes in (live's _swap_patch):
            // its channels' NRPN pitch/pan keys and a user set's keys, whose
            // settings may have come before the program (moved to dreq where
            // the builder's lock is held)
            for (int ch = 0; ch < 16; ch++) {
                if (pa.channel >= 0 && pa.channel != ch)
                    continue;
                std::set<int> keys;
                auto d = hdedit.find(ch);
                if (d != hdedit.end())
                    for (auto &kv : d->second)
                        keys.insert(kv.first);
                if (prog == 64 || prog == 65)
                    for (auto &kv : huset)
                        if (kv.first.first == prog - 64)
                            keys.insert(kv.first.second);
                for (int k : keys) {
                    DReq rq{nullptr, prog, 0, -1};
                    if (drum_req(prog, ch, k, pa.tr, c, rq))
                        dreq_swap.push_back(rq);
                }
            }
        }
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
                int mp = lsb ? lsb : (int)default_map;
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
            if (pa.gone || (pa.channel >= 0 && pa.channel != ch))
                continue;
            // (its cabinet and pickup back to the voice's own -- live's on_midi:
            //  a program change is another instrument; CC83, CC85 after it choose again)
            if (pa.cab >= 0 || pa.pk >= 0) {
                std::lock_guard<std::mutex> lk(parts_mu);
                pats[i].cab = pats[i].pk = -1;
            }
            const int pv = pa.drums ? 0 : with_cab(prog & 127, var, 0, 0);
            // a drum set in the map, where it has its own (live's kit_in_map:
            // CC32's map, else the standard's -- not GM 2's drum bank)
            const int pp = pa.drums && msb != 120 ? kit_in_map(prog & 127, lsb ? lsb : (int)default_map)
                                                  : prog & 127;
            if (pa.is(pp, pa.drums, pv))
                continue;                       // (live: part.patch.key == want -- but the patch it WILL have)
            ask(i, pp, pa.drums, pv);
        }
    };
    // ...and a GM System On or GS Reset: every part to program 0 (live's
    // patch requests at a reset, its drums its own) -- asked where it falls
    // among the block's events, as live's _sysex asks, so a program change
    // after it in the same block is the one built (a file's GS Reset, then
    // its drum set: the set was lost to the reset's program 0)
    reset_asked = [&]() {
        if (!E.has_prog)
            return;
        for (size_t i = 0; i < pats.size(); i++) {
            if (pats[i].gone)
                continue;
            if (pats[i].cab >= 0 || pats[i].pk >= 0) {      // (its cabinet and pickup the voice's own)
                std::lock_guard<std::mutex> lk(parts_mu);
                pats[i].cab = pats[i].pk = -1;
            }
            if (!pats[i].is(0, pats[i].drums, 0))
                ask(i, 0, pats[i].drums, 0);
        }
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
                answered(rq[q].i, rq[q].prog, rq[q].dr, rq[q].var);
                continue;
            }
            swap(rq[q].i, rq[q].prog, rq[q].dr, rq[q].var, c);
            answered(rq[q].i, rq[q].prog, rq[q].dr, rq[q].var);
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
                auto it = caches.find(ckey(pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var));
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
    room_tail = [&](const Export::RoomData &rd, const double *bq, int has, const double *tl) -> void * {
        if (dry || !rd.reflect || rd.spec.empty() || !(conv_cn && conv_cp && conv_cf))
            return nullptr;
        const int kind = (int)rd.spec[1];
        if (kind < 0)
            return nullptr;
        // (a GS reverb's time: the spec's T60s scaled, roomtail's T60_SCALE)
        std::vector<double> sp(rd.spec);
        if (tl)
            nv_room_spec_scale(sp.data(), tl[1]);
        double *ir = nullptr, *mir = nullptr;
        long n = kind == 0 ? nv_room_tail_ir(sp.data(), bq, has, (int)SR, 0, &ir)
                           : nv_room_tail_device(sp.data(), E.room_dev.data(), bq, has, (int)SR, &ir,
                                                 tl ? tl[1] : 1.0, tl ? tl[2] : -1.0);
        if (n <= 0)
            return nullptr;
        std::vector<float> f(2 * (size_t)n), fm;
        for (long q = 0; q < 2 * n; q++)
            f[q] = (float)(tl ? ir[q] * tl[0] : ir[q]);     // (its level: the diffuse tail's gain)
        nv_room_tail_free(ir);
        long m = 0;
        if (kind == 0) {
            int nm = 0;
            m = nv_room_tail_modes(sp.data(), bq, has, (int)SR, &mir, &nm);
            if (nm > 0 && sp[6] > 25.0 && m > 0) {         // (use_modes: some, and Schroeder over 25 Hz)
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
    // A ROOM's FIELDS into every class (its reflections: what a template is
    // built from), and the build's reflect flag
    room_fields = [&](const Export::RoomData *rd) {
        if (rd->reflect && E.room_ncls == (int)E.classes.size()) {
            int per = 0;
            for (const auto &rg : E.room_rng)
                per += rg.second;
            for (int c = 0; c < E.room_ncls; c++) {
                uint8_t *dst = E.classes[c].data();
                const uint8_t *src = rd->fields + (size_t)per * c;
                for (const auto &rg : E.room_rng) {
                    memcpy(dst + rg.first, src, rg.second);
                    src += rg.second;
                }
            }
        }
        t.reflect = rd->reflect;
    };
    // A FILE's PATCHES IN ITS OTHER ROOMS (A5), built ahead: each patch
    // built for it in the room now, built again in each other room it plays
    // in -- that room's octaves -- for its switch to swap them in at its block
    prebuild_rooms = [&]() {
        std::vector<int> rooms_;
        {
            std::lock_guard<std::mutex> lk(oct_mu);
            if (!oct_on)
                return 0;
            for (const auto &kv : oct_rooms)
                if (kv.first > 0 && kv.first != key_room && kv.first <= (int)E.rooms.size())
                    rooms_.push_back(kv.first);
        }
        if (rooms_.empty())
            return 0;
        const int home = key_room;
        std::vector<long long> keys;
        {
            std::lock_guard<std::mutex> lk(cmu);
            for (long long k_ : partial)
                if ((k_ >> KEY_ROOM_SHIFT) == home)
                    keys.push_back(k_ & ((1LL << KEY_ROOM_SHIFT) - 1));
        }
        const Export::RoomData *hr = home > 0 ? &E.rooms[(size_t)home - 1] : nullptr;
        int nb_ = 0;
        for (int r : rooms_) {
            room_fields(&E.rooms[(size_t)r - 1]);
            key_room = r;
            for (long long k_ : keys) {
                const int v_ = (int)((k_ >> 8) & 0x3FFF), cb_ = (int)((k_ >> KEY_CAB_SHIFT) & 255);
                const bool dr_ = (k_ & 128) != 0;
                const int pr_ = v_ >= 4096 ? v_ - 4096 : (int)(k_ & 127);
                refused.clear();
                if (build(pr_, dr_ || v_ >= 4096, v_ >= 4096 || dr_ ? 0 : v_ | (cb_ << 12)))
                    nb_++;
                else if (!refused.empty())
                    note(refused);
            }
        }
        key_room = home;
        if (hr)
            room_fields(hr);
        return nb_;
    };
    room_switch = [&](const std::string &name, const double *tl, void **tail,
                           const std::function<void(size_t, int, bool, int, void *)> &give) -> bool {
        const Export::RoomData *rd = nullptr;
        for (const auto &r : E.rooms)
            if (r.name == name)
                rd = &r;
        const bool same_tl = tl ? room_tl_on && tl[0] == room_tl[0] && tl[1] == room_tl[1] && tl[2] == room_tl[2]
                                : !room_tl_on;
        if (!rd || (name == room_now && same_tl))
            return false;
        double bq[9];
        int has = room_band_q(bq);
        room_tl_on = tl != nullptr;
        for (int q = 0; q < 3; q++)
            room_tl[q] = tl ? tl[q] : (q == 2 ? -1.0 : 1.0);
        *tail = room_tail(*rd, bq, has, tl);
        if (name == room_now)
            return true;                        // (the same room, a GS reverb's other tail: live's _room_switch)
        room_fields(rd);
        room_now = name;
        // EACH PART's PATCH IN THE NEW ROOM: a file's, built there ahead
        // (file_rooms_prebuild), swapped in at once; else built now, one at a
        // time, each old patch let go as its part's new one lands -- never
        // every patch twice. A file's own (partial) are kept for its next
        // switch; the rest let go once nothing plays them.
        const int old_room = key_room;
        key_room = room_key_of(name);
        bool file_on;
        {
            std::lock_guard<std::mutex> lk(oct_mu);
            file_on = oct_on;
        }
        auto old_key = [&](const PartAt &pa) {
            const long long k = ckey(pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var);
            return k - ((long long)key_room << KEY_ROOM_SHIFT) + ((long long)old_room << KEY_ROOM_SHIFT);
        };
        for (size_t i = 0; i < pats.size(); i++) {
            const PartAt &pa = pats[i];
            if (pa.gone)
                continue;
            void *c = build(pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var);
            if (c)
                give(i, pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var, c);
            if (file_on || !c)
                continue;
            const long long ok_ = old_key(pa);
            bool later = false;                 // (a part still to switch plays it too: let go after it)
            for (size_t j = i + 1; j < pats.size() && !later; j++)
                later = !pats[j].gone && old_key(pats[j]) == ok_;
            if (later)
                continue;
            std::vector<void *> old_;
            {
                std::lock_guard<std::mutex> lk(cmu);
                auto it = caches.find(ok_);
                if (it != caches.end()) {
                    old_.push_back(it->second);
                    caches.erase(it);
                    cache_used.erase(ok_);
                }
            }
            retire(old_);
            if (room_async) {                   // (playing: freed once the part has the new one and no note holds the old)
                for (int w = 0; w < 200 && !g_stop; w++) {
                    {
                        std::lock_guard<std::mutex> lk(bmu);
                        if (bdone.empty() && retire_req.empty())
                            break;
                    }
                    std::this_thread::sleep_for(std::chrono::milliseconds(1));
                }
                if (int fr = nv_part_cache_reap(part)) {
                    cache_freed += fr;
#ifdef __GLIBC__
                    malloc_trim(0);
#endif
                }
            }
        }
        if (!file_on) {                         // (the old room's left, that no part played)
            std::vector<void *> old_;
            {
                std::lock_guard<std::mutex> lk(cmu);
                for (auto it = caches.begin(); it != caches.end();) {
                    if ((it->first >> KEY_ROOM_SHIFT) == old_room && old_room != key_room) {
                        old_.push_back(it->second);
                        cache_used.erase(it->first);
                        it = caches.erase(it);
                    } else
                        ++it;
                }
            }
            retire(old_);
        }
        return true;
    };
    user_room = room_now;
    gs_rx_reset();                              // (every part on its own channel: live._gs_rx_reset)
    gs_reverb = [&](int kind, int value) {
        if (E.rooms.empty())
            return;                             // (no room on this rig)
        if (kind < 0)
            gs_rev.clear();
        else if (kind == 0x30) {                // (a macro resets the rest)
            gs_rev.clear();
            gs_rev[kind] = value;
        } else
            gs_rev[kind] = value;
        // blockrender.GS_REVERB_ROOM, GS_REVERB_TIME, GS_REVERB_DELAY_FB
        static const char *ROOM[8] = {"studio", "chamber", "large_chamber", "hall", "grand_hall", "plate", "delay",
                                      "pan_delay"};
        static const int TIME[8] = {80, 56, 64, 72, 64, 88, 32, 64};
        auto mc = gs_rev.find(0x30);
        const int macro = mc != gs_rev.end() ? mc->second : -1;
        std::string room = macro >= 0 && macro < 8 ? ROOM[macro] : !user_room.empty() ? user_room : room_now;
        double tl[3] = {1.0, 1.0, -1.0};
        bool on = false;
        if (!gs_rev.empty()) {
            auto lv = gs_rev.find(0x33), tm = gs_rev.find(0x34), fb = gs_rev.find(0x35);
            tl[0] = (lv != gs_rev.end() ? lv->second : 64) / 64.0;
            tl[1] = tm != gs_rev.end()
                        ? pow(2.0, (double)(tm->second - (macro >= 0 && macro < 8 ? TIME[macro] : 64)) / 64.0)
                        : 1.0;
            if (macro == 6 || macro == 7)
                tl[2] = fb != gs_rev.end() ? fb->second : (macro == 6 ? 40 : 32);
            on = !(tl[0] == 1.0 && tl[1] == 1.0 && tl[2] < 0.0);
        }
        const bool same_tl = on ? room_tl_on && tl[0] == room_tl[0] && tl[1] == room_tl[1] && tl[2] == room_tl[2]
                                : !room_tl_on;
        if (room != room_now || !same_tl) {
            gs_want = true;
            gs_want_room = room;
            gs_want_tl_on = on;
            for (int q = 0; q < 3; q++)
                gs_want_tl[q] = tl[q];
        }
    };
    gs_eq_apply = [&]() {
        auto at = [&](int k, int d) { auto it = gs_eq.find(k); return it != gs_eq.end() ? it->second : d; };
        const bool on = at(1, 0x40) != 0x40 || at(3, 0x40) != 0x40;
        unsigned off = 0;
        for (const auto &kv : gs_eq_sw)
            if (!kv.second && kv.first >= 0 && kv.first < 16)
                off |= 1u << kv.first;
        nv_part_gs_eq(part, on, at(0, 0) ? 400.0 : 200.0, at(2, 0) ? 6000.0 : 3000.0,
                      (double)std::max(-12, std::min(12, at(1, 0x40) - 0x40)),
                      (double)std::max(-12, std::min(12, at(3, 0x40) - 0x40)), off);
    };
    tuner_switch = [&](const std::string &name,
                       const std::function<void(size_t, int, bool, int, void *)> &give) -> bool {
        double F[128];
        int have[128];
        if (name == tuner_now || nv_tuning_table(name.c_str(), -1, 0.0, F, have))
            return false;
        for (int n = 0; n < 128; n++)
            E.freq[n] = have[n] ? F[n] : 0.0;
        tname = name;
        tl_ = name;
        for (char &ch_ : tl_)
            ch_ = (char)tolower((unsigned char)ch_);
        double rf[128];                         // (a raga tuner's Sa and swaras, as at the start)
        int rh[128];
        raga_sa = -1;
        raga_nsw = 0;
        if (!(tl_.compare(0, 5, "raga:") == 0 && nv_raga_info(tl_.c_str(), 0.0, rf, rh, &raga_sa, raga_sw, &raga_nsw) == 0))
            raga_sa = -1;
        ptab.assign(128, std::vector<double>());    // (the secondary tuning's Sa: at the new pitches)
        psa.assign(128, -1);
        pnsw.assign(128, 0);
        retuned.assign(128, 0);                 // (each program's free strings, at the new pitches)
        std::vector<void *> old_;               // (the old patches: let go once nothing plays them)
        {
            std::lock_guard<std::mutex> lk(cmu);
            for (auto &kv : caches)
                old_.push_back(kv.second);
            caches.clear();
            cache_used.clear();
        }
        retire(old_);
        {
            std::lock_guard<std::mutex> lk(bmu);
            tuner_now = name;
        }
        retune_bank = true;
        for (size_t i = 0; i < pats.size(); i++) {
            const PartAt &pa = pats[i];
            if (pa.gone)
                continue;
            void *c = build(pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var);
            if (c)
                give(i, pa.posted, pa.drums, pa.drums ? 0 : pa.posted_var, c);
        }
        return true;
    };
    // THE EASTERN TUNING, switched (live.set_eastern): a bad spec refused
    // before anything moves; each Indian voice's table and cache let go, and
    // the parts playing one built again
    east_now = east;
    east_switch = [&](const std::string &spec,
                      const std::function<void(size_t, int, bool, int, void *)> &give) -> bool {
        if (spec == east)
            return false;
        if (!spec.empty()) {
            double rf[128], sw0[12];
            int rh[128], sa0 = -1, n0_ = 0;
            if (nv_raga_info(spec.c_str(), 0.0, rf, rh, &sa0, sw0, &n0_))
                return false;
        }
        auto indian = [&](int p) {
            int cq = E.cmap[128 * (p & 127) + 60];
            return cq >= 0 && ((const NoteClass *)E.classes[cq].data())->indian;
        };
        east = spec;
        ptab.assign(128, std::vector<double>());
        psa.assign(128, -1);
        pnsw.assign(128, 0);
        {
            std::vector<void *> old_;
            {
                std::lock_guard<std::mutex> lk(cmu);
                for (auto it = caches.begin(); it != caches.end();) {
                    if (!(it->first & 128) && indian((int)(it->first & 127))) {
                        old_.push_back(it->second);
                        cache_used.erase(it->first);
                        it = caches.erase(it);
                    } else
                        ++it;
                }
            }
            retire(old_);
        }
        {
            std::lock_guard<std::mutex> lk(bmu);
            east_now = spec;
        }
        for (size_t i = 0; i < pats.size(); i++) {
            const PartAt &pa = pats[i];
            if (pa.gone || pa.drums || !indian(pa.posted))
                continue;
            void *c = build(pa.posted, false, pa.posted_var);
            if (c)
                give(i, pa.posted, false, pa.posted_var, c);
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
    // (the audio thread's lists, reserved once: lfqueue.h's take never grows them)
    evs_rt.reserve(1 << 14);
    tpend.reserve(1 << 14);
    due_rt.reserve(1 << 14);
    mstash.reserve(1 << 14);
    pstash.reserve(1 << 13);
    rx_store.reserve(64);
    rxo_p.reserve(64);
    learnt_ch = -1; learnt_note = -1;
    swallow = std::pair<int, int>(-1, -1);  // the learnt key's release (audio thread)
    underruns = 0; over = 0; blocks = 0;
    worst = 0.0; budget = 1000.0 * BLK / SR;
    govern = true;
    // (--govern-at=F: the governor's budget a fraction of the block's -- an
    // app's 0.7: it sheds once blocks run past ~2/3 of their time, leaving
    // room for the next burst, where at 1 it waited for the limit)
    govern_at = std::max(0.2, std::min(1.0, atof(opt(argc, argv, "govern-at", "1").c_str())));
    for (int i = 1; i < argc; i++)
        govern = govern && strcmp(argv[i], "--no-governor");
    master_now = master;
    rt_on = false;
    return -1;
}

void nv_host::rec(const char *fmt, ...)
{
    char line[256];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    std::lock_guard<std::mutex> lk(rec_mu);
    recq.emplace_back(line);
}

// ONE BLOCK, the audio thread's: the panel's posts, the keyboard's events,
// the builder's patches swapped in, the render (into buf, interleaved),
// the governor and the panel's snapshot
void nv_host::render_block(long long n0, float *buf, bool step)
{
    // (an allocation watcher preloaded -- tests/live/allocwatch.c, alloc_check.py -- told when
    // each block starts and ends; none: the lookup finds nothing, and nothing is called)
    static void (*rt_watch)(int) = (void (*)(int))dlsym(RTLD_DEFAULT, "nv_rt_alloc_watch");
    struct RtWatch {
        void (*f)(int);
        explicit RtWatch(void (*g)(int)) : f(g) { if (f) f(1); }
        ~RtWatch() { if (f) f(0); }
    } rt_watch_on(rt_watch);
    // (No OpenMP here: a block is one kernel chunk, on this thread -- handed
    // to a worker that slept, a coupled harpsichord's chord ran 10-25 ms a
    // block -- and the GPU setup's team is the engine's own, team.h, its
    // members in the audio workgroup themselves.)
    double cu0 = 0.0, cs0 = 0.0;
    if (soft_locks)
        thread_cpu_ms(&cu0, &cs0);
    long long t0 = rt::now_ns();
    if (!rub_on)                        // (rubato: the callback is the guarded thread, not the blocks')
        rt::busy_since = t0;
    // WHAT WAS QUEUED FOR THIS BLOCK (posted work, the MIDI) -- taken under
    // the locks the other threads write them under. NEVER WAITED FOR where
    // the host plays in real time (nv_host_set_realtime: an app's audio
    // callback): a lock held by a thread the system has paused (the
    // window's, ten times a second) stalled the block -- a click with the
    // machine busy, however lightly played (Ben, on the M3). Busy: taken
    // next block. (Not in a check's render: there it waits, so the blocks
    // stay the same whatever the threads' timing.)
    // (now lock-free: lfqueue.h -- what is in the queues when the block
    // looks is all taken, whatever the other threads are doing; a post a
    // post makes runs next block)
    {
        Post *p;
        for (size_t n = pq.size_approx(); n > 0 && pq.pop(p); n--) {
            p->f(n0);
            posted_n.fetch_sub(1, std::memory_order_relaxed);
            trash(p);
        }
    }
    const long long t_ev = rt::now_ns();        // (the onset's split: the queued work, the events, the step)
    evs_rt.clear();
    {
        Midi *m;
        for (size_t n = mq.size_approx(); n > 0 && mq.pop(m); n--)
            evs_rt.push_back(m);
    }
    evs_rt.insert(evs_rt.end(), due_rt.begin(), due_rt.end());     // (the stamped MIDI due in this block: timed_due)
    due_rt.clear();
    if (recording)
        for (const Midi *m : evs_rt)
            rec("e %lld %d %d %d %d", n0, m->type, m->ch, m->a, m->b);
    if (m2b.on && !m2b.pending.empty() && m2_held != std::chrono::steady_clock::time_point{}
        && std::chrono::steady_clock::now() - m2_held > std::chrono::microseconds(5000)) {
        std::vector<nv::ump::Ev> out;           // (a lone data entry held past live's M2_HOLD_S: sent)
        m2b.flush_all(out);
        m2_hold_mark();
        m2_out(out);
    }
    for (Midi *mp0 : evs_rt) {
      const Midi &m0 = *mp0;
      // A CHANNEL MESSAGE AS THE PARTS RECEIVE IT (live._gs_rx): to each part
      // listening on its channel, dropped by an Rx switch, a CC10 by master pan
      // (staged copies of a channel message -- no exclusive's bytes to copy;
      // anything else as it came)
      rx_store.clear();
      rxo_p.clear();
      if (m0.type != 6 && m0.ch >= 0 && m0.ch < 16) {
          gs_rx_stage(m0, rx_store);
          for (const Midi &x : rx_store)
              rxo_p.push_back(&x);
      } else {
          rxo_p.push_back(&m0);
      }
      for (const Midi *mpp : rxo_p) {
        const Midi &m = *mpp;
        if (m.type == 8 || !std::isnan(m.v)) {  // MIDI 2.0's own (live.on_ump: past the routes, learn, latch)
            engine_raw(m.type, m.ch, m.a, m.b, m.v);
            continue;
        }
        if (m.ump && m.type != 5 && m.type != 6) {   // (a MIDI 2.0 source's: past the routes and the bridge)
            latch(m.type, m.ch, m.a, m.b);
            engine_raw(m.type, m.ch, m.a, m.b, m.v);
            continue;
        }
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
        if (m.type == 5 && m.ch >= 0 && m.ch < 16 && nv_part_mpe_member(part, m.ch))
            continue;                   // (an MPE member's program change: ignored, 2.3.3 -- live._mpe_route)
        if (m.type == 5) {
            // the channel's drums state as live resolves it (resolve_patch: GM
            // 2's banks under Rx.BANK SELECT, else as it was), to the part
            // (its drum keys' own settings go with a drum set change)
            if (m.ch >= 0 && m.ch < 16) {
                auto bi = bmsb.find(m.ch);
                const int bm = bi != bmsb.end() ? bi->second : 0;
                if (rxbank && bm == 120)
                    chdr[m.ch] = 1;
                else if (rxbank && bm == 121)
                    chdr[m.ch] = 0;
                if (chdr[m.ch])
                    hdedit.erase(m.ch);
                if (m2b.on && !m.ump) {         // (the bridge: a held data entry and the bank select first)
                    std::vector<nv::ump::Ev> out;
                    m2b.feed(5, m.ch, m.a, chdr[m.ch], out);
                    m2_hold_mark();
                    m2_out(out);
                } else
                    nv_part_event(part, 5, m.ch, m.a, chdr[m.ch]);
            }
            if (asks)
                asked(m.ch, m.a);
            continue;
        }
        if (m.type == 6) {
            const uint8_t *x = m.x.data();
            int xn = (int)m.x.size();
            if (xn > 0 && x[0] == 0xF0) {
                x++;
                xn--;
            }
            if (xn >= 4 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12)
                nv_part_gs_seen(part);          // (the session speaks GS: live's gs_on)
            if (xn >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12 && x[4] == 0x40) {
                // a part's receive setting or master pan (live._gs_rx_part)
                if (x[5] == 0x00 && x[6] == 0x06) {
                    gs_mpan = std::max(1, std::min(127, (int)x[7]));
                    for (int p = 0; p < 16; p++) {      // (every part's pan again, by the new offset)
                        auto pr = gs_pan_raw.find(p);
                        const int v = std::max(0, std::min(127, (pr != gs_pan_raw.end() ? pr->second : 64) + gs_mpan - 64));
                        latch(2, p, 10, v);
                        event(2, p, 10, v);
                    }
                    continue;
                }
                const int a6 = x[6];
                if ((x[5] >> 4) == 1 && (a6 == 0x02 || (a6 >= 0x03 && a6 <= 0x12) || a6 == 0x14 || a6 == 0x1F
                                         || a6 == 0x20)) {
                    const int blk = x[5] & 0x0F;
                    const int ch = blk == 0 ? 9 : blk <= 9 ? blk - 1 : blk;
                    const int v = x[7];
                    if (a6 == 0x02)
                        gs_rx[ch] = v < 16 ? v : 16;
                    else if (a6 == 0x14) {
                        gs_assign[ch] = v;
                        nv_part_sysex(part, m.x.data(), (int)m.x.size());   // (ASSIGN MODE: the slab's restrike)
                    }
                    else if (a6 == 0x1F || a6 == 0x20) {
                        gs_ccnum[std::make_pair(ch, a6)] = v;
                        nv_part_sysex(part, m.x.data(), (int)m.x.size());   // (the controller matrix's CC1/CC2: the slab's)
                    }
                    else if (v)
                        gs_rxsw[ch].erase(a6);
                    else
                        gs_rxsw[ch].insert(a6);
                    continue;
                }
            }
            if (xn >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12 && x[4] == 0x40 && x[5] == 0x01
                && x[6] >= 0x38 && x[6] <= 0x40) {
                nv_part_gs_chorus(part, x[6], x[7]);    // (the GS chorus: live's _sysex, and nothing else)
                continue;
            }
            if (xn >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12 && x[4] == 0x40 && x[5] == 0x01
                && x[6] >= 0x50 && x[6] <= 0x5A) {
                nv_part_gs_delay(part, x[6], x[7]);     // (the GS delay: live's _sysex, and nothing else)
                continue;
            }
            if (xn >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12 && x[4] == 0x40 && x[5] == 0x01
                && (x[6] == 0x30 || x[6] == 0x33 || x[6] == 0x34 || x[6] == 0x35)) {
                gs_reverb(x[6], x[7]);          // (live's _sysex: blockrender.parse_gs_reverb's, and nothing else)
                continue;
            }
            if (xn >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12) {     // THE GS EQ (parse_gs_eq)
                if (x[4] == 0x40 && x[5] == 0x02 && x[6] <= 3) {
                    gs_eq[x[6]] = x[7];
                    gs_eq_apply();
                    continue;
                }
                if ((x[4] == 0x40 || x[4] == 0x50) && (x[5] >> 4) == 4 && x[6] == 0x20) {
                    const int blk = x[5] & 0x0F;
                    const int ch = (blk == 0 ? 9 : blk <= 9 ? blk - 1 : blk) + (x[4] == 0x50 ? 16 : 0);
                    if (ch < 16)
                        gs_eq_sw[ch] = x[7] != 0;
                    gs_eq_apply();
                    continue;
                }
            }
            if (xn >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12 && x[4] == 0x40 && (x[5] >> 4) == 1
                && x[6] == 0x15) {              // (use for rhythm part: the channel's drums state, live's ch_drums)
                const int blk = x[5] & 0x0F, rc = blk == 0 ? 9 : (blk <= 9 ? blk - 1 : blk);
                chdr[rc] = x[7] != 0;
                if (x[7])
                    hrmap[rc] = x[7] - 1;
                // ...AND A PART ON THAT CHANNEL FOLLOWS (live._sysex's): a kit,
                // or melodic again, its program kept -- an omni part is the
                // player's own, as at GM 2's bank 120
                for (size_t i = 0; i < pats.size() && asks; i++) {
                    const PartAt &pa = pats[i];
                    if (pa.gone || pa.channel != rc)
                        continue;
                    const bool dr = x[7] != 0;
                    const int pv = dr ? 0 : pa.var;
                    if (!pa.is(pa.program, dr, pv))
                        ask(i, pa.program, dr, pv);
                }
            }
            if (xn >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12 && x[4] == 0x21 && (x[5] >> 4) <= 1
                && (x[5] & 0x0F) >= 1 && (x[5] & 0x0F) <= 0x0C) {   // (a user drum set's key: its template asked)
                huset[std::make_pair(x[5] >> 4, (int)x[6])][x[5] & 0x0F] = x[7];
                drum_warm(9, x[6], x[5] >> 4);
            }
            if (xn >= 8 && x[0] == 0x41 && x[2] == 0x42 && x[3] == 0x12 && x[4] == 0x41 && (x[5] >> 4) <= 1
                && ((x[5] & 0x0F) == 1 || (x[5] & 0x0F) == 4))   // (drum setup: a key's PLAY NOTE or pan)
                for (int c = 0; c < 16; c++) {
                    auto rm = hrmap.find(c);
                    if (chdr[c] && (rm == hrmap.end() ? 0 : rm->second) == (x[5] >> 4))
                        drum_set(c, x[6], (x[5] & 0x0F) == 1 ? 0 : 1, (x[5] & 0x0F) == 1 ? x[7] - x[6] : x[7]);
                }
            const bool rs = sys_reset(m.x.data(), (int)m.x.size());
            if (rs && (!gs_rev.empty() || room_tl_on || (!user_room.empty() && room_now != user_room)))
                gs_reverb(-1, 0);               // (the panel's room again: the sequencer's override ends)
            if (rs) {                           // (and the EQ flat, every part's switch on; Chorus 3 again)
                gs_eq.clear();
                gs_eq_sw.clear();
                gs_eq_apply();
                const bool gm1 = xn >= 4 && x[0] == 0x7E && x[2] == 0x09 && x[3] == 0x01;
                nv_part_gs_chorus_reset(part, gm1);
                gs_rx_reset();                  // (every part on its own channel, every Rx on, master pan centre)
            }
            if (rs && asks)
                reset_asked();
            nv_part_sysex(part, m.x.data(), (int)m.x.size());
            continue;
        }
        if (m.ch >= 0 && m.ch < 16) {                  // (each channel's activity: the panel's 16 bars)
            if (m.type == 0 && m.b > 0) {               // (...and its keys': the drum pads)
                key_vel[(size_t)m.ch][(size_t)(m.a & 127)] = (unsigned char)m.b;
                key_hits[(size_t)m.ch][(size_t)(m.a & 127)].fetch_add(1, std::memory_order_relaxed);
            }
            if (m.type == 2 && m.a == 7)
                hvol[m.ch] = m.b;
            else if (m.type == 2 && m.a == 11)
                hexpr[m.ch] = m.b;
            else if (m.type == 2 && m.a == 121)
                hexpr[m.ch] = 127;
            else if (m.type == 0 && m.b > 0)
                meter[m.ch] = std::make_pair(m.b / 127.0 * (hvol[m.ch] / 127.0) * (hexpr[m.ch] / 127.0),
                                             std::chrono::duration<double>(
                                                 std::chrono::steady_clock::now().time_since_epoch()).count());
        }
        if (m.type == 2 && m.ch >= 0 && m.ch < 16) {   // (a drum key's pitch or pan: its templates asked)
            if (m.a == 99 || m.a == 98)
                (m.a == 99 ? hn_msb : hn_lsb)[m.ch] = m.b;
            else if (m.a == 101 || m.a == 100)
                hn_msb[m.ch] = hn_lsb[m.ch] = 127;
            else if (m.a == 6 && (hn_msb[m.ch] == 0x18 || hn_msb[m.ch] == 0x1C))
                drum_set(m.ch, hn_lsb[m.ch], hn_msb[m.ch] == 0x18 ? 0 : 1, hn_msb[m.ch] == 0x18 ? m.b - 64 : m.b);
        }
        latch(m.type, m.ch, m.a, m.b);
        event(m.type, m.ch, m.a, m.b);
      }
    }
    for (Midi *mp0 : evs_rt)            // (done with: to be freed elsewhere)
        trash(mp0);
    evs_rt.clear();
    if (gs_want && !step) {             // (a sequencer's GS reverb, playing: the builder's, as live.set_room --
                                        //  never waited for: the builder busy, asked next block)
        std::unique_lock<std::mutex> lk(bmu, std::try_to_lock);
        if (lk.owns_lock()) {
            room_req = gs_want_room;
            room_req_tl_on = gs_want_tl_on;
            for (int q = 0; q < 3; q++)
                room_req_tl[q] = gs_want_tl[q];
            gs_want = false;
            lk.unlock();
            bcv.notify_one();
        }
    }
    const long long t_blk = rt::now_ns();
    nv_part_late(part, !step || late_test);    // (a note with no template held for it: live's, --late's)
    nv_part_block(part, n0, BLK);
    {                                   // (the templates its held notes asked: to the builder, below)
        void *ac[256];
        int ap[256], ad[256], an[256], ab[256], ax[256];
        const int na = nv_part_asks(part, ac, ap, ad, an, ab, ax, 256);
        for (int q = 0; q < na && miss_swap.size() < 256; q++)
            miss_swap.push_back(MissReq{ac[q], ap[q], ad[q], an[q], ab[q], ax[q]});
        long lc[4];
        nv_part_late_counts(part, lc);
        lost_n.store(lc[3], std::memory_order_relaxed);
        late_n.store(lc[0], std::memory_order_relaxed);
        stand_n.store(lc[1], std::memory_order_relaxed);
        held_n.store(lc[2], std::memory_order_relaxed);
    }
    last_split[0] = (t_ev - t0) / 1e6;
    last_split[1] = (t_blk - t_ev) / 1e6;
    last_split[2] = (rt::now_ns() - t_blk) / 1e6;
    if (step) {                         // (the tail installed after the block's events, as live's post)
        if (step_room_go)
            nv_part_room_set(part, step_room, BLK);
        step_room = nullptr;
        step_room_go = false;
        nv_part_room_reap(part);
    }
    nv_part_take_reset(part);           // (its reset asked at its place, above)
    landed();
    if (step) {
        step_swaps += settle(reqs);     // (live's builder in step: for the next block)
        if (!miss_swap.empty() || !fills.empty()) {     // (a held note's template, and its octaves, in step)
            on_demand(miss_swap);
            while (fill_step()) {
            }
        }
        {                               // ...and an edited drum key's templates (patchsync.fill's)
            std::vector<DReq> dq;
            {
                std::lock_guard<std::mutex> lk(bmu);
                dq.swap(dreq);
            }
            dq.insert(dq.end(), dreq_swap.begin(), dreq_swap.end());
            dreq_swap.clear();
            drum_build(dq);
        }
        std::vector<PartSpec> adds;     // ...and the parts added (the session's), built and added in step
        {
            std::lock_guard<std::mutex> lk(bmu);
            adds.swap(add_req);
        }
        for (const PartSpec &sp : adds)
            part_added(sp, build(sp.program, sp.drums, sp.var));
        std::string tn;                 // ...and a tuner asked for (a preset's), switched in step
        {
            std::lock_guard<std::mutex> lk(bmu);
            tn.swap(tuner_req);
        }
        if (!tn.empty())
            tuner_switch(tn, [&](size_t i_, int p_, bool d_, int v_, void *c_) { swap(i_, p_, d_, v_, c_); });
        {                               // ...and patches let go (a room's, a tuner's), freed once unreached
            std::lock_guard<std::mutex> lk(bmu);
            for (auto &r : retire_req)
                nv_part_cache_retire(part, r.first, r.second.data(), (long)r.second.size());
            retire_req.clear();
        }
        cache_freed += nv_part_cache_reap(part);
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
                for (auto &d : bdone) {
                    if (d.second)
                        swap(d.first.i, d.first.prog, d.first.dr, d.first.var, d.second);
                    answered(d.first.i, d.first.prog, d.first.dr, d.first.var);
                }
                bdone.clear();
                if (!miss_swap.empty()) {               // (a held note's template: to the builder)
                    miss_req.insert(miss_req.end(), miss_swap.begin(), miss_swap.end());
                    miss_swap.clear();
                    bcv.notify_one();
                }
                if (!dreq_swap.empty()) {               // (a drum set's own keys: to the builder)
                    dreq.insert(dreq.end(), dreq_swap.begin(), dreq_swap.end());
                    dreq_swap.clear();
                    bcv.notify_one();
                }
                for (auto &d : add_done)                // (the parts built: added)
                    part_added(d.first, d.second);
                add_done.clear();
                for (auto &r : retire_req)              // (patches let go: the part frees none it still reaches)
                    nv_part_cache_retire(part, r.first, r.second.data(), (long)r.second.size());
                retire_req.clear();
                pins_update();
            }
        }
    }
    long long t1 = rt::now_ns();
    nv_part_output(part, n0, (long)BLK, L, R, fn[0], fn[1], fn[2], BLK, master_now);
    last_step_ms = (t1 - t0) / 1e6;
    last_out_ms = (rt::now_ns() - t1) / 1e6;
    if (!rub_on)
        rt::busy_since = 0;
    double ms = (rt::now_ns() - t0) / 1e6;
    if (govern)
        nv_part_govern(part, ms, budget * govern_at, n0 + BLK);
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
    if (recording && (blocks % 24 == 0 || ms > budget)) {
        double st[15];
        nv_part_stats(part, st);
        rec("b %lld %.3f busy %.0f keys %.0f shed %.0f peak %.5f pedal %.0f mono %.0f gpu %.0f", n0, ms, st[0], st[1],
            st[2], pk[0], st[7], st[9], st[4]);
    }
    // ...AND WHAT THE WINDOW READS, published under its lock -- not waited
    // for either: busy, this block's figures carried to the next publish
    if (ms > pend_max) {
        pend_step = last_step_ms;
        pend_out = last_out_ms;
        if (soft_locks) {
            double cu1, cs1;
            thread_cpu_ms(&cu1, &cs1);
            pend_cpu[0] = cu1 - cu0;
            pend_cpu[1] = cs1 - cs0;
        }
        double st[15];
        nv_part_stats(part, st);
        pend_st[0] = st[0];
        pend_st[1] = st[4];
        pend_st[2] = st[5];
        pend_st[3] = st[6];
        for (int i = 0; i < 3; i++)
            pend_split[i] = last_split[i];
    }
    pend_max = std::max(pend_max, ms);
    pend_sum += ms;
    pend_n++;
    pend_pk[0] = std::max(pend_pk[0], pk[0]);
    pend_pk[1] = std::max(pend_pk[1], pk[1]);
    std::unique_lock<std::mutex> plk(pmu, std::try_to_lock);
    if (plk.owns_lock()) {
        snap.n0 = n0;
        snap.blocks = blocks;
        snap.over = over;
        if (pend_max > snap.ms_max) {
            snap_step = pend_step;
            snap_out = pend_out;
            for (int i = 0; i < 4; i++)
                snap_st[i] = pend_st[i];
            for (int i = 0; i < 3; i++)
                snap_split[i] = pend_split[i];
            snap_cpu[0] = pend_cpu[0];
            snap_cpu[1] = pend_cpu[1];
        }
        snap.ms_max = std::max(snap.ms_max, pend_max);
        snap.ms_sum += pend_sum;
        snap.ms_n += pend_n;
        snap.peak[0] = std::max(snap.peak[0], pend_pk[0]);
        snap.peak[1] = std::max(snap.peak[1], pend_pk[1]);
        pend_max = pend_sum = 0.0;
        pend_n = 0;
        pend_pk[0] = pend_pk[1] = 0.0f;
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
    nv_part_rt_prepare(part, BLK);                // (the block's scratch reserved: none allocated playing)
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
                             [&] { return !breq.empty() || !room_req.empty() || !tuner_req.empty() || east_req_set
                                          || !add_req.empty() || !dreq.empty() || fill_req || prebuild_req || g_stop
                                          || !miss_req.empty() || !fills.empty(); });
                rq.swap(breq);
                builder_busy = !rq.empty() || !room_req.empty() || !tuner_req.empty() || east_req_set || !add_req.empty()
                               || prebuild_req || fill_req;
            }
            {                                           // A HELD NOTE's TEMPLATE (A5's on demand), first
                std::vector<MissReq> mq;
                {
                    std::lock_guard<std::mutex> lk(bmu);
                    mq.swap(miss_req);
                }
                if (!mq.empty())
                    on_demand(mq);
            }
            {                                           // AN EDITED DRUM KEY's TEMPLATES (live._fill_misses)
                std::vector<DReq> dq;
                {
                    std::lock_guard<std::mutex> lk(bmu);
                    dq.swap(dreq);
                }
                drum_build(dq);
            }
            nv_part_room_reap(part);                    // (an old tail, let go off the audio thread)
            if (int fr = nv_part_cache_reap(part)) {    // (old patches nothing plays now)
                cache_freed += fr;
#ifdef __GLIBC__
                malloc_trim(0);                         // (their pages back to the system: else only reused)
#endif
                long long held = 0;
                int nc = 0;
                {
                    std::lock_guard<std::mutex> lk(cmu);
                    for (const auto &kv : caches) {
                        auto b = cache_bytes.find(kv.second);
                        held += b != cache_bytes.end() ? b->second : 0;
                        nc++;
                    }
                }
                note("let go " + std::to_string(fr) + " old patch(es): " + std::to_string(nc) + " kept, "
                     + std::to_string((int)(held >> 20)) + " MB");
            }
            std::set<long long> fresh;                        // (the patches this pass builds: not the LRU's)
            std::string rname;
            double rtl[3];
            bool rtl_on;
            {
                std::lock_guard<std::mutex> lk(bmu);
                rname.swap(room_req);
                rtl_on = room_req_tl_on;
                for (int q = 0; q < 3; q++)
                    rtl[q] = room_req_tl[q];
            }
            if (!rname.empty()) {                       // A ROOM (live._room_switch, on its patch worker)
                auto t0 = std::chrono::steady_clock::now();
                void *tl = nullptr;
                int nb_ = 0;
                room_async = true;              // (playing: each old patch freed as its part's new one lands)
                bool ok = room_switch(rname, rtl_on ? rtl : nullptr, &tl, [&](size_t i_, int p_, bool d_, int v_, void *c_) {
                    std::lock_guard<std::mutex> lk(bmu);
                    bdone.push_back(std::make_pair(Req{i_, p_, d_, v_}, c_));
                    nb_++;
                });
                room_async = false;
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
            bool pre = false;                           // A FILE's OTHER ROOMS (A5): its patches built there ahead
            {
                std::lock_guard<std::mutex> lk(bmu);
                pre = prebuild_req;
                prebuild_req = false;
            }
            if (pre) {
                auto t0 = std::chrono::steady_clock::now();
                const int nb_ = prebuild_rooms();
                if (nb_)
                    note("the file's rooms: " + std::to_string(nb_) + " patch(es) built ahead in "
                         + std::to_string((int)std::chrono::duration<double, std::milli>(
                                              std::chrono::steady_clock::now() - t0).count()) + " ms");
            }
            std::string tn;                             // A TUNER (livetui's TUNER column), after a room
            {
                std::lock_guard<std::mutex> lk(bmu);
                tn.swap(tuner_req);
            }
            if (!tn.empty()) {
                auto t0 = std::chrono::steady_clock::now();
                int nb_ = 0;
                bool ok = tuner_switch(tn, [&](size_t i_, int p_, bool d_, int v_, void *c_) {
                    std::lock_guard<std::mutex> lk(bmu);
                    bdone.push_back(std::make_pair(Req{i_, p_, d_, v_}, c_));
                    nb_++;
                });
                if (ok)
                    note("tuner " + tn + ": " + std::to_string(nb_) + " patch(es) built in "
                         + std::to_string((int)std::chrono::duration<double, std::milli>(
                                              std::chrono::steady_clock::now() - t0).count()) + " ms");
                else if (tn != tuner_now)
                    note("tuner " + tn + ": not one nvlive can make");
            }
            std::string es;                             // THE EASTERN TUNING (livetui's E), after a tuner
            bool eset = false;
            {
                std::lock_guard<std::mutex> lk(bmu);
                if (east_req_set) {
                    es.swap(east_req);
                    east_req_set = false;
                    eset = true;
                }
            }
            if (eset) {
                auto t0 = std::chrono::steady_clock::now();
                int nb_ = 0;
                bool ok = east_switch(es, [&](size_t i_, int p_, bool d_, int v_, void *c_) {
                    std::lock_guard<std::mutex> lk(bmu);
                    bdone.push_back(std::make_pair(Req{i_, p_, d_, v_}, c_));
                    nb_++;
                });
                if (ok)
                    note("eastern " + (es.empty() ? std::string("off") : es) + ": " + std::to_string(nb_)
                         + " part(s) built again in "
                         + std::to_string((int)std::chrono::duration<double, std::milli>(
                                              std::chrono::steady_clock::now() - t0).count()) + " ms");
            }
            std::vector<PartSpec> adds;                 // PARTS ADDED (layer, split, the session's)
            {
                std::lock_guard<std::mutex> lk(bmu);
                adds.swap(add_req);
            }
            for (const PartSpec &sp : adds) {
                fresh.insert(ckey(sp.program, sp.drums, sp.var));
                refused.clear();
                void *c = build(sp.program, sp.drums, sp.var);
                if (!c)
                    note(!refused.empty() ? refused : std::string(sp.drums ? "drum set " : "program ") + std::to_string(sp.program)
                         + " is not native here: no part added");
                std::lock_guard<std::mutex> lk(bmu);
                add_done.push_back(std::make_pair(sp, c));
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
                    had = caches.count(ckey(rq[q].prog, rq[q].dr, rq[q].dr ? 0 : rq[q].var)) > 0;
                }
                auto t0 = std::chrono::steady_clock::now();
                fresh.insert(ckey(rq[q].prog, rq[q].dr, rq[q].var));
                refused.clear();
                void *c = build(rq[q].prog, rq[q].dr, rq[q].var);
                std::string nm = rq[q].dr ? kit_name(rq[q].prog) : E.prog[rq[q].prog].name;
                if (!c)
                    note(!refused.empty() ? refused
                                          : (rq[q].dr ? "drum set " : "program ") + std::to_string(rq[q].prog) + " (" + nm
                                                + ") is not native here: the part plays on");
                else if (!had)
                    note("built " + std::to_string(rq[q].prog) + " " + nm + " in "
                         + std::to_string((int)std::chrono::duration<double, std::milli>(
                                              std::chrono::steady_clock::now() - t0).count()) + " ms");
                std::lock_guard<std::mutex> lk(bmu);
                bdone.push_back(std::make_pair(rq[q], c));
            }
            if (!fresh.empty())
                cache_trim(fresh);
            if (!fills.empty())                         // (an octave on demand: a key of it, then the asks again)
                fill_step();
            builder_busy = false;
        }
    };
    builder = std::thread(builder_loop);
}

// AN EVENT PAST THE ROUTES, into the part -- and a captured control's last
// value latched as it goes (live._see: CAPTURE_CC, what a scene keeps; CC121
// resets the ones it resets). The audio thread's
static const int CAPTURE_CC[] = {0, 32, 1, 5, 7, 10, 11, 43, 44, 45, 65, 91, 93};
void nv_host::engine_event(int type, int ch, int a, int b, double v)
{
    if (m2b.on && type != 8 && std::isnan(v) && type != 5 && type != 6) {
        // THE BRIDGE (live._bridge): the keyboard's MIDI 1.0, past its routes,
        // to the engine as MIDI 2.0 -- what the engine receives of it
        std::vector<nv::ump::Ev> out;
        m2b.feed(type, ch, a, b, out);
        m2_hold_mark();
        m2_out(out);
        return;
    }
    engine_raw(type, ch, a, b, v);
}

// the bridge's events to the engine (a program change the host's own, its drums state)
void nv_host::m2_out(const std::vector<nv::ump::Ev> &out)
{
    for (const auto &e : out) {
        if (e.type == 5)
            nv_part_event(part, 5, e.ch, e.a, e.ch >= 0 && e.ch < 16 ? chdr[e.ch] : 0);
        else
            engine_raw(e.type, e.ch, e.a, e.b, e.v);
    }
}

// (when the bridge began holding a data entry: its timeout, live's M2_HOLD_S)
void nv_host::m2_hold_mark()
{
    if (m2b.pending.empty())
        m2_held = {};
    else if (m2_held == std::chrono::steady_clock::time_point{})
        m2_held = std::chrono::steady_clock::now();
}

void nv_host::engine_raw(int type, int ch, int a, int b, double v)
{
    if (type == 8 || !std::isnan(v)) {          // (MIDI 2.0's own: nothing latched)
        nv_part_event_x(part, type, ch, a, b, v);
        return;
    }
    if (type == 2) {
        for (int c : CAPTURE_CC)
            if (a == c)
                chanlatch[std::make_pair(ch, a)] = b;
        if (a == 121)
            for (int c : {1, 11, 65})
                chanlatch.erase(std::make_pair(ch, c));
    }
    nv_part_event(part, type, ch, a, b);
}

// a tuner asked for (the panel's): built on the builder, as a room is
void nv_host::set_tuner(const std::string &name)
{
    {
        std::lock_guard<std::mutex> lk(bmu);
        tuner_req = name;
        tuner_asked = name;
    }
    bcv.notify_one();
}

// the Eastern tuning asked for (the panel's E, a preset's): built on the
// builder, as a tuner is -- a bad spec said and refused there
void nv_host::set_eastern(const std::string &spec)
{
    {
        std::lock_guard<std::mutex> lk(bmu);
        east_req = spec;
        east_req_set = true;
        east_asked = spec;
    }
    bcv.notify_one();
}

// does a part on this voice play the Eastern tuning now (live.tuner_for's
// test: an Indian instrument, not a drum set, the rig's tuner no raga)
bool nv_host::east_part(int prog, bool drums)
{
    std::string e;
    {
        std::lock_guard<std::mutex> lk(bmu);
        e = east_now;
    }
    if (e.empty() || drums || raga_sa >= 0)
        return false;
    int cq = E.cmap[128 * (prog & 127) + 60];
    return cq >= 0 && ((const NoteClass *)E.classes[cq].data())->indian;
}

// ---- what the panel and a GUI change (the panel's hooks call these) ----
// THE MESSENGER SET ON A DEVICE (live.messenger_connect): asked who it is
// first (probe_messenger: before it is opened to write), then opened
bool nv_host::msgr_connect(const std::string &path, const std::string &name)
{
    MsgrOut &o = *msgr;
    bool is = false;
    std::string id = probe_messenger(path, &is);
    int f = midi_open(path, O_WRONLY | O_NONBLOCK);
    if (f < 0)
        return false;
    {
        std::lock_guard<std::mutex> lk(o.mu);
        o.path = path;
        o.name = name;
        o.ident = id.empty() ? "" : is ? "it answered as a Messenger" : id;
        o.q.clear();
    }
    o.fd.store(f);
    o.start();
    return true;
}

// A DRUM KEY's PITCH (which 0) OR PAN (1) set (live's dedit, _drum_warm):
// kept, and its template asked of each drum part listening on the channel
void nv_host::drum_set(int ch, int key, int which, int v)
{
    if (key < 0 || key > 127)
        return;
    auto &e = hdedit[ch].emplace(key, std::array<int, 2>{INT_MIN, INT_MIN}).first->second;
    e[which] = v;
    drum_warm(ch, key, -1);
}

// live._drum_warm: a drum key's own template asked of each drum part
// listening on ch (only_set >= 0: each part playing that user set) -- its
// NRPN pitch and pan, a user set key's settings with them
// drum_req: one key's request on drum set prog (c its cache) -- false when
// the key has nothing of its own there
bool nv_host::drum_req(int prog, int ch, int key, int tr, void *c, DReq &rq)
{
    int pitch = INT_MIN, pan = INT_MIN;
    {
        auto d = hdedit.find(ch);
        if (d != hdedit.end()) {
            auto k = d->second.find(key);
            if (k != d->second.end()) {
                pitch = k->second[0];
                pan = k->second[1];
            }
        }
    }
    const int sn = key + tr;
    if (sn < 0 || sn > 127 || !c)
        return false;
    rq = DReq{c, prog, sn, -1};
    rq.pitch = pitch;
    rq.pan = pan;
    if (prog == 64 || prog == 65) {
        auto u = huset.find(std::make_pair(prog - 64, key));
        if (u != huset.end()) {
            static const int CODE[4] = {0x01, 0x04, 0x0B, 0x0C};
            for (int i = 0; i < 4; i++) {
                auto f = u->second.find(CODE[i]);
                rq.ud[i] = f != u->second.end() ? f->second : -1;
                rq.has_ud = rq.has_ud || rq.ud[i] >= 0;
            }
        }
    }
    if (rq.has_ud)
        rq.axis = nv_drum_axis_ud(pitch, pan, rq.ud, prog - 64);
    else if (pitch != INT_MIN || pan != INT_MIN)
        rq.axis = nv_drum_axis(pitch, pan);
    else
        return false;
    return true;
}

void nv_host::drum_warm(int ch, int key, int only_set)
{
    std::lock_guard<std::mutex> lk(bmu);
    for (const PartAt &pa : pats) {
        if (pa.gone || !pa.drums)
            continue;
        const int prog = pa.posted;
        if (only_set >= 0 ? prog != 64 + only_set : (pa.channel >= 0 && pa.channel != ch))
            continue;
        const long long ck = ckey(prog, true, 0);
        void *c = nullptr;
        {
            std::lock_guard<std::mutex> lc(cmu);
            auto it = caches.find(ck);
            if (it != caches.end())
                c = it->second;
        }
        DReq rq{nullptr, prog, 0, -1};
        if (drum_req(prog, only_set >= 0 ? 9 : ch, key, pa.tr, c, rq))
            dreq.push_back(rq);
    }
    bcv.notify_one();
}

// ...built (one bucket: a drum set's), on the builder or in step
void nv_host::drum_build(std::vector<DReq> &q)
{
    for (const DReq &r : q) {
        if (r.has_ud)
            nv_tcache_build_var_ud(r.c, r.prog, r.note, 0, 1, r.axis, r.pitch, r.pan, r.ud);
        else
            nv_tcache_build_var(r.c, r.prog, r.note, 0, 1, r.axis);
    }
    q.clear();
}

// a builder's note: the panel's (playing), stderr's (in step: no panel)
void nv_host::tell(const std::string &m)
{
    static const bool say = getenv("NV_MISS_TRACE") != nullptr;
    if (note)
        note(m);
    if (!note || say)
        fprintf(stderr, "nvlive: %s\n", m.c_str());
}

// a tone's name: a variation's own, a drum set's, else the program's
std::string nv_host::tone_name(int prog, bool dr, int var) const
{
    if (dr)
        return kit_name(prog);
    for (size_t j = 0; j < E.vpv.size() && var; j++)
        if (E.vpv[j][0] == (prog & 127) && E.vpv[j][1] == var)
            return E.vnames[j];
    return E.prog[prog & 127].name;
}

// (a patch still in the cache: not let go since the note asked)
bool nv_host::cache_alive(void *c)
{
    std::lock_guard<std::mutex> lk(cmu);
    for (const auto &kv : caches)
        if (kv.second == c)
            return true;
    return false;
}

// A5's ON DEMAND, on the builder (in step after the block): each held
// note's template built first, then its octave queued (the front of the
// fills), unless the octave is there already or on its way
void nv_host::on_demand(std::vector<MissReq> &q)
{
    for (const MissReq &r : q) {
        if (!cache_alive(r.c))
            continue;
        long long b = 0;
        if (nv_tcache_add(r.c, r.prog, r.note, r.bucket, r.axis, &b) > 0) {
            std::lock_guard<std::mutex> lk(cmu);
            auto cb = cache_bytes.find(r.c);
            if (cb != cache_bytes.end())
                cb->second += b;
        }
        const int o = r.note / 12;
        bool queued = false;
        for (const Fill &f : fills)
            queued = queued || (f.c == r.c && f.oct == o);
        if (!queued)
            fills.push_front(Fill{r.c, r.prog, r.drums, o, -1, true, 0, std::chrono::steady_clock::now()});
    }
    q.clear();
    fill_n.store((long)fills.size(), std::memory_order_relaxed);
}

// ...ONE KEY of the front octave (every bucket and wheel step), within the
// budget; its octave done, the two either side queued behind (the played
// one's only). False: nothing left to fill
bool nv_host::fill_step()
{
    while (!fills.empty()) {
        Fill &f = fills.front();
        int nb = 0, sp[8];
        const int nsp = cache_alive(f.c) ? nv_tcache_slots(f.c, &nb, sp) : 0;
        const int lo = std::max(f.oct * 12, f.drums ? 0 : 21), hi = std::min(f.oct * 12 + 11, f.drums ? 127 : 108);
        if (nsp <= 0 || lo > hi) {
            fills.pop_front();
            continue;
        }
        if (f.next < 0) {                       // (begun: an octave already whole is passed over)
            bool whole = true;
            for (int k = lo; k <= hi && whole; k++)
                for (int b = 0; b < nb && whole; b++)
                    for (int s = 0; s < nsp && whole; s++)
                        whole = nv_tcache_has(f.c, k, b, sp[s]) != 0;
            if (whole) {
                fills.pop_front();
                continue;
            }
            f.next = 0;                         // (the template's index in the octave: key x bucket x step)
            f.t0 = std::chrono::steady_clock::now();
            std::lock_guard<std::mutex> lk(bmu);
            fill_name = "OCT " + std::to_string(f.oct);     // (the display's: FILL OCT 5; the tone in the note)
        }
        if (patch_budget > 0) {                 // (the budget: the unused patches let go first, else stop here)
            long long held_ = 0;
            {
                std::lock_guard<std::mutex> lk(cmu);
                for (const auto &kv : caches) {
                    auto b = cache_bytes.find(kv.second);
                    if (b == cache_bytes.end())
                        b = cache_bytes.emplace(kv.second, nv_tcache_bytes(kv.second)).first;
                    held_ += b->second;
                }
            }
            if (held_ >= patch_budget) {
                trim_to = patch_budget / 2 > 0 ? patch_budget - patch_budget / 16 : 0;
                cache_trim({});
                trim_to = -1;
                if (!cache_alive(f.c)) {
                    fills.pop_front();
                    continue;
                }
                held_ = 0;
                std::lock_guard<std::mutex> lk(cmu);
                for (const auto &kv : caches) {
                    auto b = cache_bytes.find(kv.second);
                    held_ += b != cache_bytes.end() ? b->second : 0;
                }
            }
            if (held_ >= patch_budget) {
                if (unfilled.insert(std::make_pair(f.c, f.oct)).second)     // (said once an octave)
                    tell(tone_name(f.prog, f.drums != 0, nv_tcache_var(f.c)) + ": octave " + std::to_string(f.oct)
                     + " left unfilled, the patches' " + std::to_string((int)(patch_budget >> 20))
                     + " MB full: its notes build one at a time");
                fills.pop_front();
                continue;
            }
        }
        // (templates for ~5 ms, then back for the asks: a key of a big
        //  tone is 60 ms, too long for a held note to wait behind)
        long long kb = 0;
        const auto ts = std::chrono::steady_clock::now();
        const int per = nb * nsp;
        bool more = true;
        while (more) {
            const int k = f.next / per, r = f.next % per;
            long long t = 0;
            if (nv_tcache_add(f.c, f.prog, lo + k, r / nsp, sp[r % nsp], &t) > 0)
                kb += t;
            f.next++;
            more = lo + f.next / per <= hi;
            if (std::chrono::steady_clock::now() - ts > std::chrono::milliseconds(5))
                break;
        }
        f.bytes += kb;
        {
            std::lock_guard<std::mutex> lk(cmu);
            auto cb = cache_bytes.find(f.c);
            if (cb != cache_bytes.end())
                cb->second += kb;
        }
        if (more)
            return true;
        const Fill done = f;                    // (the octave whole)
        fills.pop_front();
        tell(tone_name(done.prog, done.drums != 0, nv_tcache_var(done.c)) + ": octave " + std::to_string(done.oct)
             + " built as played (" + std::to_string((int)std::lround(done.bytes / 1048576.0)) + " MB in "
             + std::to_string((int)std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - done.t0)
                                  .count())
             + " ms)");
        if (done.first)
            for (int o : {done.oct - 1, done.oct + 1})
                if (o >= 0 && o <= 10)
                    fills.push_back(Fill{done.c, done.prog, done.drums, o, -1, false, 0, std::chrono::steady_clock::now()});
        fill_n.store((long)fills.size(), std::memory_order_relaxed);
        if (fills.empty()) {
            std::lock_guard<std::mutex> lk(bmu);
            fill_name.clear();
        }
        return !fills.empty();
    }
    fill_n.store(0, std::memory_order_relaxed);
    {
        std::lock_guard<std::mutex> lk(bmu);
        fill_name.clear();
    }
    return false;
}

// THE AUDIO THREAD's QUEUES (lfqueue.h): pushed here, on the caller's
// thread -- allocated here, and what the block is done with freed here too
void nv_host::reclaim()
{
    Midi *m;
    while (mtrash.pop(m))
        delete m;
    Post *p;
    while (ptrash.pop(p))
        delete p;
}

void nv_host::enqueue(Midi &&m)
{
    reclaim();
    Midi *p = new Midi(std::move(m));
    while (!mq.push(p))                         // (full: 16384 waiting -- the block will take them)
        std::this_thread::yield();
}

void nv_host::post(std::function<void(long long)> f)
{
    reclaim();
    Post *p = new Post{std::move(f)};
    posted_n.fetch_add(1, std::memory_order_relaxed);
    while (!pq.push(p))
        std::this_thread::yield();
}

// ...and handed back by the audio thread: the trash full (no one pushing for
// a long while), kept in a stash reserved at the start, handed back later
void nv_host::trash(Midi *m)
{
    while (!mstash.empty() && mtrash.push(mstash.back()))
        mstash.pop_back();
    if (!mtrash.push(m))
        mstash.push_back(m);
}

void nv_host::trash(Post *p)
{
    while (!pstash.empty() && ptrash.push(pstash.back()))
        pstash.pop_back();
    if (!ptrash.push(p))
        pstash.push_back(p);
}

// the globals where they start (the panel's g: master dB, headroom dB, the
// limiter's knee, the wheel's range, mod cents, aftertouch dB, the GPU, the
// room's tail, the room)
void nv_host::globals_init()
{
    double st[15];
    nv_part_stats(part, st);
    gval[0] = 20.0 * log10(std::max(master, 1e-12));
    gval[1] = std::round(-20.0 * log10(std::max(E.headroom, 1e-12)) * 1e9) / 1e9;    // (4.0, not 3.9999999999999996)
    gval[2] = E.k.size() > K_THRESH ? E.k[K_THRESH] : 0.70;
    gval[3] = E.k.size() > K_BEND_RANGE ? E.k[K_BEND_RANGE] : 2.0;
    gval[4] = 35.0;
    gval[5] = E.k.size() > K_PRESS_DB ? E.k[K_PRESS_DB] : 8.0;
    gval[6] = st[12] > 0.5 ? 1.0 : 0.0;
    gval[7] = st[11] > 0.5 ? 1.0 : 0.0;
    gval[8] = room_idx;
    gval[9] = 0.25;                             // live.mod_rate: the wheel's vibrato +25% faster at full
    // (10-12, the metronome: off, no bell, 0 dB -- kept as they are: its own)
    gval[13] = default_map;
}

void nv_host::set_global(int i, double v)
{
    if (i < 0 || i >= NV_G_N)
        return;
    if (i == NV_G_STAND_IN) {                   // A HELD NOTE's STAND-IN after this many ms (0: none, it waits)
        gval[i] = std::max(0.0, std::min(200.0, v));
        const double ms = gval[i];
        post([this, ms](long long) { nv_part_stand_in(part, ms); });
        return;
    }
    if (i == 13) {                              // THE STANDARD (live.std_map): read at the next program change
        gval[i] = std::max(0.0, std::min(4.0, std::round(v)));
        default_map = (int)gval[i];
        return;
    }
    if (i == 10 || i == 11) {                   // THE METRONOME (livetui.metronome): built the first time it is on
        gval[i] = v;
        const double bpm = gval[10];
        const int ring = (int)gval[11];
        if (metro_pi >= 0) {
            post([this, bpm, ring](long long) { nv_part_metronome(part, -1, bpm, ring); });
        } else if (bpm > 0.0 && !metro_building) {
            metro_building = true;              // (one build: it starts on the tempo and ring of its arrival)
            PartSpec sp;
            sp.drums = true;
            sp.channel = 9;
            sp.level = gval[12];
            sp.metro = true;
            part_add(sp);
        }
        return;
    }
    if (i == 12) {                              // ...its level (live.set_metro_level: its part's)
        gval[i] = v;
        if (metro_pi >= 0) {
            const int pi = metro_pi;
            post([this, pi, v](long long) { nv_part_patch_level(part, pi, v, 0); });
        }
        return;
    }
    if (i == 8) {                               // THE ROOM: the builder's (live.set_room)
        int k = (int)v;
        if (k >= 0 && k < (int)E.rooms.size()) {
            std::lock_guard<std::mutex> lk(bmu);
            room_req = E.rooms[k].name;
            room_req_tl_on = false;             // (the panel's: the user's room, over a sequencer's reverb)
            user_room = room_req;
            gs_rev.clear();
            room_asked = k;
        }
        bcv.notify_one();
        return;
    }
    gval[i] = v;
    post([this, i, v](long long) {
        switch (i) {
        case 0: master_now = pow(10.0, v / 20.0); break;     // T.master_gain
        case 1: nv_part_set(part, 0, v); break;
        case 2: nv_part_set(part, 2, v); break;
        case 3: nv_part_set(part, 3, v); break;
        case 4: nv_part_set(part, 4, v); break;
        case 5: nv_part_set(part, 1, v); break;
        case 6: nv_part_set(part, 5, v); break;
        case 7: nv_part_set(part, 6, v); break;
        case 9: nv_part_set(part, 7, v); break;     // live.mod_rate
        }
    });
}

// THE PICKER's: every program and set, which are native; the variations
// (VNAM), native where every key of their slots the capital plays is one
// the engine plays too
void nv_host::patches_init()
{
    pnames.assign(256, "");
    pnative.assign(256, 0);
    for (int sp = 0; sp < 256; sp++) {
        pnames[sp] = sp < 128 ? E.prog[sp].name : E.prog[sp & 127].kit;
        bool nat = false;
        for (int k = 0; k < 128 && !nat; k++)
            nat = E.cmap[(sp >= 128 ? NV_K_DRUMS : 0) + 128 * (sp & 127) + k] >= 0;
        pnative[sp] = nat && (sp >= 128 ? !pnames[sp].empty() : E.part[sp][0] != 0);
    }
    // GS's two USER SETS (programs 65, 66: live's patch tree): each key
    // another set's, as the panel's U sets them -- native where the drums are
    for (int u = 0; u < 2; u++) {
        pnames[128 + 64 + u] = "User Set " + std::to_string(u + 1);
        pnative[128 + 64 + u] = pnative[128];
    }
    vnative.assign(E.vpv.size(), 0);
    for (size_t j = 0; j < E.vpv.size(); j++) {
        int p = E.vpv[j][0], en = var_entry_of(p, E.vpv[j][1]);
        bool nat = en > 0 && (j < E.vpart.size() ? E.vpart[j][0] : E.part[p][0]) != 0;
        for (const auto &l : en > 0 ? E.vents[en].ls : std::vector<std::array<int, 4>>())
            for (int k = 0; k < 128 && nat; k++)
                nat = k + l[1] < 0 || k + l[1] > 127 || E.vmap[128 * (size_t)l[0] + k + l[1]] >= 0
                      || E.cmap[128 * p + k] < 0;
        vnative[j] = nat;
    }
}

// a patch for the part, asked for between two blocks (live's change_patch)
void nv_host::pick(int sp) { pick_row(0, sp); }

// ...for any part (livetui's PATCH column)
int nv_host::kit_in_map(int prog, int mp) const
{
    if (mp) {
        for (size_t j = 0; j < E.mk_ids.size(); j++)
            if (E.mk_ids[j] == 128 * mp + prog)
                return 128 + (int)j;
        if (mp == 1 || mp == 2)
            for (size_t j = 0; j < E.mk_ids.size(); j++)
                if (E.mk_ids[j] == 3 * 128 + prog)
                    return 128 + (int)j;
    }
    return prog;
}

std::string nv_host::kit_name(int prog) const
{
    if (prog >= 128) {
        const size_t j = (size_t)(prog - 128);
        return j < E.mk_names.size() && !E.mk_names[j].empty() ? E.mk_names[j] : "drum set";
    }
    if (prog == 64 || prog == 65)               // (GS's user sets: built from other sets' keys)
        return prog == 64 ? "User Set 1" : "User Set 2";
    return prog >= 0 && E.prog[prog].kit.size() ? E.prog[prog].kit : "drum set";
}

void nv_host::pick_row(size_t row, int sp)
{
    if (!E.has_prog)
        return;
    post([this, row, sp](long long) {
        if (row >= pats.size() || pats[row].gone)
            return;
        {                                       // (a pick is a program change: its cabinet and pickup the voice's own)
            std::lock_guard<std::mutex> lk(parts_mu);
            pats[row].cab = pats[row].pk = -1;
        }
        const PartAt &pa = pats[row];
        if (sp >= 256) {                        // (a variation: its program under its bank)
            int p = E.vpv[sp - 256][0], v = with_cab(E.vpv[sp - 256][0], E.vpv[sp - 256][1], 0, 0);
            if (!pa.is(p, false, v))
                ask(row, p, false, v);
        } else {
            const int p = sp >= 128 ? kit_in_map(sp & 127, (int)default_map) : sp;    // (livetui's pick)
            const int v = sp >= 128 ? 0 : with_cab(p, 0, 0, 0);
            if (!pa.is(p, sp >= 128, v))
                ask(row, p, sp >= 128, v);
        }
    });
}

// ---- A MOOG PART's KNOBS (livetui's synth pane) ----

// its panel on a layer, read on the audio thread between two blocks (or
// here, when no blocks are coming): its layers, 0 not a Moog
int nv_host::synth_state(size_t row, int layer, double *pn, char *own)
{
    int pi;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone || pats[row].drums)
            return 0;
        pi = pats[row].pi;
    }
    struct Got {
        double pn[NV_MK_N];
        char own[NV_MK_N];
        int n = 0;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [this, got, pi, layer](long long) {
        got->n = nv_part_synth_get(part, pi, layer, got->pn, got->own);
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    std::lock_guard<std::mutex> lk(synth_mu);
    const size_t key = row * 2 + (size_t)layer;
    if (got->done) {                            // (read: kept, for a save the audio cannot answer -- a quit's)
        SynthRead &c = synth_cache[key];
        c.n = got->n;
        memcpy(c.pn, got->pn, sizeof c.pn);
        memcpy(c.own, got->own, sizeof c.own);
    }
    auto it = synth_cache.find(key);
    if (it == synth_cache.end())
        return -1;                              // (never read: unknown)
    if (!it->second.n)
        return 0;
    memcpy(pn, it->second.pn, sizeof it->second.pn);
    memcpy(own, it->second.own, sizeof it->second.own);
    return it->second.n;
}

// AN ORGAN's DRAWN STOPS, patch pi's, read between two blocks (a swap may
// be replacing them); read here when the audio does not answer (stopped)
bool nv_host::drawn_of(int pi, std::vector<char> &out)
{
    struct Got {
        std::vector<char> d;
        int n = 0;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [this, got, pi](long long) {
        got->d.assign(512, 0);
        got->n = nv_part_drawn(part, pi, got->d.data(), (int)got->d.size());
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done) {                           // (no blocks to come -- the way out: read here, as before)
        std::vector<char> d(512, 0);
        const int n = nv_part_drawn(part, pi, d.data(), (int)d.size());
        out.assign(d.begin(), d.begin() + n);
        return true;
    }
    out.assign(got->d.begin(), got->d.begin() + got->n);
    return true;
}

static int part_pi(nv_host &h, size_t row)
{
    std::lock_guard<std::mutex> lk(h.parts_mu);
    return row < h.pats.size() && !h.pats[row].gone ? h.pats[row].pi : -1;
}

void nv_host::synth_set(size_t row, int layer, int knob, double v)
{
    const int pi = part_pi(*this, row);
    if (pi >= 0)
        post([this, pi, layer, knob, v](long long) { nv_part_synth_set(part, pi, layer, knob, v); });
}

void nv_host::synth_forget(size_t row, int layer, int knob)
{
    const int pi = part_pi(*this, row);
    if (pi >= 0)
        post([this, pi, layer, knob](long long) { nv_part_synth_forget(part, pi, layer, knob); });
}

int nv_host::synth_send(size_t row)
{
    const int pi = part_pi(*this, row);
    if (pi < 0 || !msgr || (!msgr->log && msgr->fd.load() < 0))
        return 0;                               // (none plugged in)
    auto sent = std::make_shared<std::atomic<int>>(-1);
    post([this, pi, sent](long long) { *sent = nv_part_synth_send(part, pi); });
    for (int i = 0; i < 200 && *sent < 0 && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    return std::max(0, sent->load());
}

// ---- THE PARTS (livetui's PARTS pane) ----

// A PART's FIXED TOUCH (livetui.toggle_touch): the host's copy now, the
// patch's between two blocks
void nv_host::part_touch(size_t row, int fixed)
{
    int pi;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return;
        pats[row].fixed = fixed;
        pi = pats[row].pi;
    }
    post([this, pi, fixed](long long) { nv_part_patch_touch(part, pi, fixed); });
}

// A PART's ROTARY HEARD (live.set_rotary): an organ's cabinet in the room or
// two mics round it, a Rotary type's likewise -- the host's copy now, the
// patch's between two blocks (the notes struck after it)
// A PART's CABINET (live.set_cabinet): its patch rebuilt through CAB_CHOICES
// [choice] (-1 none: the voice's own), as a pick rebuilds one -- the program
// on its way, if one is; a program change puts it back to -1
void nv_host::set_cabinet(size_t row, int choice)
{
    if (!E.has_prog)
        return;
    post([this, row, choice](long long) {
        if (row >= pats.size() || pats[row].gone)
            return;
        {
            std::lock_guard<std::mutex> lk(parts_mu);
            pats[row].cab = choice < 0 ? -1 : choice;
        }
        const PartAt &pa = pats[row];
        if (pa.drums)
            return;
        const bool w = pa.want >= 0;
        const int p = w ? pa.want : pa.program, v = with_cab(p, w ? pa.want_var : pa.var, std::max(0, choice),
                                                             std::max(0, pa.pk));
        if (!pa.is(p, false, v))
            ask(row, p, false, v);
    });
}

// A PART's PICKUP (live.set_pickup): its patch rebuilt through
// PICKUP_CHOICES[choice] (-1 none: the voice's own) -- what that is, its
// instrument's (patch_map.PICKUP_FAMILIES) -- its cabinet kept; a program
// change puts it back to -1, as the cabinet
void nv_host::set_pickup(size_t row, int choice)
{
    if (!E.has_prog)
        return;
    post([this, row, choice](long long) {
        if (row >= pats.size() || pats[row].gone)
            return;
        {
            std::lock_guard<std::mutex> lk(parts_mu);
            pats[row].pk = choice < 0 ? -1 : choice;
        }
        const PartAt &pa = pats[row];
        if (pa.drums)
            return;
        const bool w = pa.want >= 0;
        const int p = w ? pa.want : pa.program, v = with_cab(p, w ? pa.want_var : pa.var, std::max(0, pa.cab),
                                                             std::max(0, choice));
        if (!pa.is(p, false, v))
            ask(row, p, false, v);
    });
}

void nv_host::part_rotary(size_t row, int mode, double sep)
{
    int pi;
    mode = mode < 0 ? -1 : mode != 0;
    sep = sep < 0.0 ? -1.0 : std::min(M_PI, sep);
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return;
        pats[row].rot_mode = mode;
        pats[row].rot_sep = sep;
        pi = pats[row].pi;
    }
    post([this, pi, mode, sep](long long) { nv_part_rotary(part, pi, mode, sep); });
}

// ...the host's copies brought up to the parts' (a file's or a keyboard's CC82
// switches them on the audio thread): read between two blocks, at most every
// 100 ms (the cards ask each poll)
void nv_host::rotary_refresh()
{
    const auto now = std::chrono::steady_clock::now();
    if (now - rotary_read < std::chrono::milliseconds(100))
        return;
    rotary_read = now;
    std::vector<int> pis;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        for (const PartAt &pa : pats)
            pis.push_back(pa.gone ? -1 : pa.pi);
    }
    struct Got {
        std::vector<double> o;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    got->o.assign(2 * pis.size(), -2.0);
    auto take = [this, got, pis](long long) {
        for (size_t i = 0; i < pis.size(); i++)
            if (pis[i] >= 0)
                nv_part_rotary_get(part, pis[i], got->o.data() + 2 * i);
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 50 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return;
    std::lock_guard<std::mutex> lk(parts_mu);
    for (size_t i = 0; i < pis.size() && i < pats.size(); i++)
        if (pis[i] >= 0 && pats[i].pi == pis[i] && got->o[2 * i] > -2.0) {
            pats[i].rot_mode = (int)got->o[2 * i];
            pats[i].rot_sep = got->o[2 * i + 1];
        }
}

// AN ORGAN's DRIVE KNOB (live.set_drive): the host's copy now (a session's),
// the patch's between two blocks
void nv_host::part_drive(size_t row, double v)
{
    int pi;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return;
        pats[row].drive = v < 0.0 ? -1.0 : v;
        pi = pats[row].pi;
    }
    post([this, pi, v](long long) { nv_part_drive(part, pi, v); });
}

// A PART's ROTOR SPEED (the AMP card's: live.set_rotor_speed), between two blocks
void nv_host::part_rotor(size_t row, int v)
{
    int pi;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return;
        pi = pats[row].pi;
    }
    post([this, pi, v](long long) { nv_part_rotor(part, pi, v); });
}

// ...and what it is, read between two blocks (nv_part_drive_get's out)
// ...THE AMP CARD's: nv_part_amp_get's eight, read between two blocks
int nv_host::amp_state(size_t row, double *out)
{
    const int pi = part_pi(*this, row);
    if (pi < 0)
        return 0;
    struct Got {
        double o[8];
        int r = 0;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [this, got, pi](long long) {
        got->r = nv_part_amp_get(part, pi, got->o);
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return -1;
    memcpy(out, got->o, sizeof got->o);
    return got->r;
}

int nv_host::drive_state(size_t row, double *out)
{
    const int pi = part_pi(*this, row);
    if (pi < 0)
        return 0;
    struct Got {
        double o[3];
        int r = 0;
        std::atomic<bool> done{false};
    };
    auto got = std::make_shared<Got>();
    auto take = [this, got, pi](long long) {
        got->r = nv_part_drive_get(part, pi, got->o);
        got->done = true;
    };
    if (scene_inline)
        take(0);
    else
        post(take);
    for (int i = 0; i < 200 && !got->done && !g_stop; i++)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!got->done)
        return -1;
    memcpy(out, got->o, sizeof got->o);
    return got->r;
}

// A MESSENGER's CHART read on every part (livetui's M, live's cc_map
// "messenger": nvlive's for all its parts at once, --messenger's)
// AN INPUT OPENED (MidiIns::opened, the reader's thread): a MESSENGER --
// its name its own USB port's, "Moog Messenger" -- turns its knobs' reading on
// (its chart over GM's, so SUB WAVE is the sub wave and not CC71's timbre),
// unless the player switched the reading this run. Behind a USB MIDI
// interface its name is the interface's ("USB Midi"): then it is ASKED who
// it is -- MIDI's Device Inquiry out of the same device (its output, a
// handle of its own) -- and its Identity Reply, back through the input,
// says (input_identity)
void nv_host::input_opened(const std::string &path, const std::string &name)
{
    if (msgr_reads || msgr_reads_set)
        return;
    std::string l = name;
    for (char &c : l)
        c = (char)tolower((unsigned char)c);
    if (l.find("messenger") != std::string::npos) {
        messenger_reading(true);
        fprintf(stderr, "nvlive: %s is a Messenger: its knobs read as its own (Setup: READ ITS KNOBS)\n", name.c_str());
        return;
    }
    int f = midi_open(path, O_WRONLY | O_NONBLOCK);
    if (f < 0)
        return;                             // (no output beside it: nothing to ask)
    static const uint8_t rq[6] = {0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7};
    if (::write(f, rq, sizeof rq) != (ssize_t)sizeof rq)
        fprintf(stderr, "nvlive: %s: its identity not asked (%s)\n", name.c_str(), strerror(errno));
    midi_close(f);
}

// ...AN IDENTITY REPLY through an input (MidiIns::identity: F0 7E dev 06 02
// maker family model version): a Messenger's -- Moog (04), family 49, model
// 153 (probe_messenger's) -- turns its knobs' reading on, as its name would,
// and is the device its Moog parts' patches go out of (the Messenger
// watcher's, when no device's name says Messenger)
void nv_host::input_identity(const std::string &path, const std::string &name, const std::vector<uint8_t> &x)
{
    size_t j = 4;
    const int mk = x.size() > j ? x[j] : -1;
    j += mk == 0 ? 3 : 1;
    if (x.size() < j + 4)
        return;
    const int fam = x[j] | x[j + 1] << 7, mod = x[j + 2] | x[j + 3] << 7;
    if (!(mk == 0x04 && fam == 49 && mod == 153))
        return;
    {
        std::lock_guard<std::mutex> lk(msgr_id_mu);
        msgr_id_path = path;
        msgr_id_name = name;
    }
    if (msgr_reads || msgr_reads_set)
        return;
    messenger_reading(true);
    fprintf(stderr, "nvlive: %s answered as a Messenger: its knobs read as its own (Setup: READ ITS KNOBS)\n", name.c_str());
}

void nv_host::messenger_reading(bool on)
{
    msgr_reads = on;
    const double v = on ? 1.0 : 0.0;
    post([this, v](long long) { nv_part_set(part, 8, v); });
}

// AN ON-SCREEN CONTROL SENT (livetui.send_control, live.control_message):
// past the routes, to every channel or its own -- mono on as CC126 1, off as
// CC127 0 (both carry an All Sounds Off: switching it stops what the channel holds)
void nv_host::control_send(int key, int value, int channel)
{
    int type, a, b;
    if (key == -1) {                            // the pitch wheel
        type = 4;
        a = std::max(-8192, std::min(8191, value));
        b = 0;
    } else if (key == -2) {                     // aftertouch
        type = 3;
        a = std::max(0, std::min(127, value));
        b = 0;
    } else if (key == -3) {                     // mono
        type = 2;
        a = value >= 64 ? 126 : 127;
        b = value >= 64 ? 1 : 0;
    } else {
        type = 2;
        a = key;
        b = std::max(0, std::min(127, value));
    }
    post([this, type, a, b, channel](long long) {
        for (int ch = 0; ch < 16; ch++)
            if (channel < 0 || channel == ch)
                engine_event(type, ch, a, b);
    });
}

// what the panel shows of each part still there (its index the host's)
std::vector<panel::PartRow> nv_host::part_rows()
{
    std::vector<panel::PartRow> out;
    std::lock_guard<std::mutex> lk(parts_mu);
    for (size_t i = 0; i < pats.size(); i++) {
        const PartAt &pa = pats[i];
        if (pa.gone)
            continue;
        panel::PartRow r;
        r.index = (int)i;
        r.program = pa.program & 127;
        r.var = pa.drums ? 0 : pa.var;
        r.drums = pa.drums;
        r.channel = pa.channel;
        r.lo = pa.lo;
        r.hi = pa.hi;
        r.tr = pa.tr;
        r.level = pa.level;
        r.muted = pa.muted;
        r.solo = pa.solo ? 1 : solo_n.load() > 0 ? 2 : 0;
        r.touch_fixed = pa.fixed < 0 ? !nv_part_patch_touch_sensitive(part, pa.pi) : pa.fixed != 0;
        r.name = pa.drums ? kit_name(r.program) : E.prog[r.program].name;
        for (size_t j = 0; j < E.vpv.size() && r.var; j++)
            if (E.vpv[j][0] == r.program && E.vpv[j][1] == r.var)
                r.name = E.vnames[j];
        out.push_back(r);
    }
    return out;
}

// a part's channel (-1 every one), keys, transpose, level and mute: the
// host's copy now, the patch's between two blocks (read as a note is struck)
void nv_host::part_set(size_t row, int channel, int lo, int hi, int tr, double level, bool muted)
{
    int pi;
    unsigned excl;
    bool psolo;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return;
        PartAt &pa = pats[row];
        pa.channel = channel;
        pa.lo = lo;
        pa.hi = hi;
        pa.tr = tr;
        pa.level = level;
        pa.muted = muted;
        pi = pa.pi;
        psolo = pa.solo;
        excl = channel >= 0 ? 0u : pa.excl;
    }
    const bool out = muted || (solo_n.load() > 0 && !psolo);           // (a solo elsewhere: silent too)
    post([this, pi, channel, excl, lo, hi, tr, level, out](long long) {
        nv_part_patch_range(part, pi, channel, excl, lo, hi, tr);
        nv_part_patch_level(part, pi, level, out);
    });
}

// A PART INTO THE SOLO, OR OUT (live.toggle_solo): while any part is
// soloed, every other is silent as a muted one is; the session keeps none
void nv_host::part_solo(size_t row)
{
    std::vector<std::tuple<int, double, bool>> lv;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return;
        pats[row].solo = !pats[row].solo;
        int n = 0;
        for (const PartAt &pa : pats)
            n += !pa.gone && pa.solo;
        solo_n.store(n);
        for (const PartAt &pa : pats)
            if (!pa.gone)
                lv.push_back(std::make_tuple(pa.pi, pa.level, pa.muted || (n > 0 && !pa.solo)));
    }
    post([this, lv](long long) {
        for (const auto &x : lv)
            nv_part_patch_level(part, std::get<0>(x), std::get<1>(x), std::get<2>(x));
    });
}

// A PART ADDED (livetui's a and s): its program built on the builder (as a
// program change's), then the patch added between two blocks
void nv_host::part_add(const PartSpec &sp)
{
    {
        std::lock_guard<std::mutex> lk(bmu);
        add_req.push_back(sp);
    }
    bcv.notify_one();
}

static const int HOST_DRUM_P[10] = {1, 1, 1, -1, -1, -1, -1, 0, 0, 0};    // (a drum set's live record)

// ...on the audio thread, between two blocks: the patch added last (it takes
// the notes it claims), the host's row with it
void nv_host::part_added(const PartSpec &sp, void *c)
{
    if (!c)
        return;
    if (sp.metro) {                             // THE METRONOME's part (live.build_metro_part): Standard's kit, hidden
        int pi = nv_part_add_patch(part, c, 4, gval[12], HOST_DRUM_P[1], HOST_DRUM_P[6], HOST_DRUM_P[7],
                                   HOST_DRUM_P[8], HOST_DRUM_P[9], 1, 0, E.kit_choke.data(), 9, 0u, 0, 127, 0);
        nv_part_patch_level(part, pi, gval[12], 0);
        nv_part_metronome(part, pi, gval[10], (int)gval[11]);
        metro_pi = pi;
        return;
    }
    const int *pq = sp.drums ? HOST_DRUM_P : prec(sp.program, sp.var);
    const long long pid = next_pid++;
    int pi = nv_part_add_patch(part, c, pid, sp.level, pq[1], pq[6], pq[7], pq[8], pq[9], sp.drums, sp.program,
                               sp.drums ? E.kit_choke.data() : nullptr, sp.channel, sp.channel >= 0 ? 0u : sp.excl,
                               sp.lo, sp.hi, sp.tr);
    nv_part_patch_level(part, pi, sp.level, sp.muted || solo_n.load() > 0);    // (a solo elsewhere: silent)
    nv_part_patch_touch(part, pi, sp.fixed);
    nv_part_rotary(part, pi, sp.rot_mode, sp.rot_sep);
    if (sp.drive >= 0.0)
        nv_part_drive(part, pi, sp.drive);
    attach_drone(pi, sp.program, sp.drums, sp.var);
    for (int layer = 0; layer < 2; layer++)    // (its knobs: once the patch is in)
        for (const auto &kv : sp.syn[layer])
            nv_part_synth_set_later(part, pi, layer, kv.first, kv.second);
    if (!sp.drawn.empty() && !sp.drums) {      // (its stops, by name: the organ's own matched in the post)
        std::vector<const char *> nm;
        for (const auto &x : sp.drawn)
            nm.push_back(x.c_str());
        if (!nm.empty())
            nv_part_set_drawn_names(part, pi, nm.data(), (int)nm.size());
    }
    PartAt pa{pi, sp.channel, sp.drums, sp.program, sp.drums ? -1 : E.prog[sp.program & 127].sid, sp.program,
              sp.var, sp.var};
    pa.excl = sp.excl;
    pa.lo = sp.lo;
    pa.hi = sp.hi;
    pa.tr = sp.tr;
    pa.level = sp.level;
    pa.muted = sp.muted;
    pa.pid = pid;
    pa.fixed = sp.fixed;
    pa.rot_mode = sp.rot_mode;
    pa.rot_sep = sp.rot_sep;
    pa.drive = sp.drive;
    pa.cab = sp.cab;
    pa.pk = sp.pk;
    std::lock_guard<std::mutex> lk(parts_mu);
    pats.push_back(pa);                         // (reserved: the builder may be reading the rest)
}

static nv_host::PartSpec spec_of(const nv_host::PartAt &pa)
{
    nv_host::PartSpec sp;
    sp.program = pa.program & 127;
    sp.var = pa.drums ? 0 : pa.var;
    sp.drums = pa.drums;
    sp.channel = pa.channel;
    sp.excl = pa.excl;
    sp.lo = pa.lo;
    sp.hi = pa.hi;
    sp.tr = pa.tr;
    sp.level = pa.level;
    sp.muted = pa.muted;
    sp.fixed = pa.fixed;
    sp.rot_mode = pa.rot_mode;
    sp.rot_sep = pa.rot_sep;
    sp.drive = pa.drive;
    sp.cab = pa.cab;
    sp.pk = pa.pk;
    return sp;
}

// livetui.add_part: the part copied -- same keys, same channel
bool nv_host::part_layer(size_t row)
{
    PartSpec sp;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return false;
        sp = spec_of(pats[row]);
    }
    part_add(sp);
    return true;
}

// livetui.split_here: the part's keys cut in two, the upper half a new part
bool nv_host::part_split(size_t row, std::string &why)
{
    PartSpec sp;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return false;
        sp = spec_of(pats[row]);
    }
    const int mid = (sp.lo + sp.hi) / 2;
    if (mid <= sp.lo || mid >= sp.hi) {
        why = "range too small to split";
        return false;
    }
    part_set(row, sp.channel, sp.lo, mid, sp.tr, sp.level, sp.muted);
    sp.lo = mid + 1;
    part_add(sp);
    return true;
}

// livetui.del_part: the part taken away, its notes let go (its index kept);
// never the first -- the part itself, its free strings with it
bool nv_host::part_delete(size_t row, std::string &why)
{
    int pi;
    {
        std::lock_guard<std::mutex> lk(parts_mu);
        if (row >= pats.size() || pats[row].gone)
            return false;
        if (pats[row].pi == 0) {
            why = "the first part carries the free strings: it stays (change its patch or mute it)";
            return false;
        }
        pi = pats[row].pi;
    }
    post([this, row, pi](long long n0) {
        nv_part_patch_gone(part, pi, n0);
        std::lock_guard<std::mutex> lk(parts_mu);
        pats[row].gone = true;
    });
    return true;
}

// the build under way: templates done of its total, and its name; false none
bool nv_host::progress(long *done, long *total, std::string *name)
{
    long t = __atomic_load_n(&bp_total, __ATOMIC_ACQUIRE);
    if (t <= 0)
        return false;
    *total = t;
    *done = std::min(t, __atomic_load_n(&bp_done, __ATOMIC_RELAXED));
    std::lock_guard<std::mutex> lk(bmu);
    *name = bp_name;
    return true;
}

void nv_host::panic()
{
    post([this](long long n) { nv_part_panic(part, n); });
}

// what is still to land: posts not yet run, builds asked for, being built,
// built and not yet swapped in, a room asked for
int nv_host::building()
{
    int n = builder_busy ? 1 : 0;
    {
        std::lock_guard<std::mutex> lk(pmu);
        n += posted_n.load(std::memory_order_relaxed);
    }
    std::lock_guard<std::mutex> lk(bmu);
    return n + (int)breq.size() + (int)bdone.size() + (room_req.empty() ? 0 : 1) + (tuner_req.empty() ? 0 : 1)
           + (prebuild_req ? 1 : 0) + (fill_req ? 1 : 0) + (int)miss_req.size() + (int)fill_n.load()
           + (east_req_set ? 1 : 0) + (int)add_req.size() + (int)add_done.size();
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
    h->globals_init();
    h->patches_init();
    return h;
}

void nv_host_start(nv_host *h) { h->start(); }

void nv_host_stamped(nv_host *h, unsigned mask) { nv_part_stamped(h->part, mask); }
// (a file's stamped channels by the export's rule: STAMP_S, STAMPED_SHARE)
unsigned nv_host_stamp_rule(nv_host *h, void *midi) { return nv_midi_stamped(midi, h->E.k[K_STAMP_S], h->E.k[K_STAMPED_SHARE]); }

void nv_host_set_realtime(nv_host *h, int on)
{
    h->soft_locks = on != 0;
    nv_room_inline(on);                         // (the room's body on the audio thread: no worker to wake)
}

void nv_host_room_inline(nv_host *, int on) { nv_room_inline(on); }

int nv_host_join_output_workgroup(nv_host *, void *audio_unit)
{
#ifdef __APPLE__
    os_workgroup_t wg = nullptr;
    UInt32 size = sizeof wg;
    if (!audio_unit || AudioUnitGetProperty((AudioUnit)audio_unit, kAudioOutputUnitProperty_OSWorkgroup,
                                            kAudioUnitScope_Global, 0, &wg, &size) != noErr || !wg)
        return -1;
    nv::rtj::set(wg);                           // (kept: the helpers join it at their next pass)
    return 0;
#else
    (void)audio_unit;
    return -1;
#endif
}

void nv_host_close(nv_host *h)
{
    g_stop = true;
    h->bcv.notify_one();
    if (h->builder.joinable())
        h->builder.join();
    nv_host_set_rubato(h, 0, h->rub_frac);   // (its render thread stopped first: it renders through the part)
    if (h->part)
        nv_part_stop_workers(h->part);          // (none left running into the app's exit)
}

int nv_host_rate(const nv_host *h) { return (int)h->SR; }
int nv_host_block(const nv_host *h) { return (int)h->BLK; }

int nv_host_render(nv_host *h, float *L, float *R, int frames)
{
    return nv_host_render_step(h, L, R, frames, 0);
}

// the stamped MIDI whose sample falls in the block from n0 (nv_host_midi_at),
// into the queue the block reads -- in their samples' order, a sample's in
// the order given
// the stamped MIDI (nv_host_midi_at) due in the block at n0: the queue
// drained into the audio thread's own list, sorted by sample (one stamped
// alike after the one before it), and those under the block's end handed to
// the block (due_rt) -- no lock, no allocation (the lists reserved)
static void timed_due(nv_host *h, long long n0)
{
    Midi *m;
    while (h->tq.pop(m)) {
        auto it = std::upper_bound(h->tpend.begin(), h->tpend.end(), m,
                                   [](const Midi *a, const Midi *b) { return a->at < b->at; });
        h->tpend.insert(it, m);
    }
    size_t k = 0;
    while (k < h->tpend.size() && h->tpend[k]->at < n0 + h->BLK)
        h->due_rt.push_back(h->tpend[k++]);
    if (k)
        h->tpend.erase(h->tpend.begin(), h->tpend.begin() + (long)k);
}

int nv_host_render_step(nv_host *h, float *L, float *R, int frames, int step)
{
    if (frames != h->BLK)
        return -1;
    timed_due(h, h->play_n0);
    h->render_block(h->play_n0, h->play_buf.data(), step != 0);
    for (int k = 0; k < frames; k++) {
        L[k] = h->play_buf[2 * k];
        R[k] = h->play_buf[2 * k + 1];
    }
    h->play_n0 += h->BLK;
    return 0;
}

// ANY NUMBER OF FRAMES (an app's callback: AVAudioEngine's, an Audio Unit's
// -- 256, 512, 471 ...): whole blocks rendered as they are needed, the frames
// of the last one not handed out kept for the next call. The samples are the
// blocks' own, in order, whatever the sizes asked
int nv_host_pull_step(nv_host *h, float *L, float *R, int frames, int step)
{
    const int B = (int)h->BLK;
    const long long t_in = rt::now_ns();
    int done = 0;
    while (done < frames) {
        if (h->pull_pos < 0 || h->pull_pos >= B) {
            timed_due(h, h->play_n0);
            h->render_block(h->play_n0, h->play_buf.data(), step != 0);
            h->play_n0 += B;
            h->pull_pos = 0;
        }
        const int k = std::min(B - h->pull_pos, frames - done);
        const float *src = h->play_buf.data() + 2 * h->pull_pos;
        for (int i = 0; i < k; i++) {
            L[done + i] = src[2 * i];
            R[done + i] = src[2 * i + 1];
        }
        h->pull_pos += k;
        done += k;
    }
    // A COLD START's WARM-UP (nv_host_set_cold_start): while the phrase's
    // first note waits its block, the thread kept busy -- this callback's
    // spare time up to warm_frac of its length -- so the core is up to speed
    // when the note's first real block comes (a slowed core ran 544 slots in
    // 4.4 ms after a pause, warm ~0.3: the underrun Ben heard after a rest)
    if (h->cold_blocks > 0 && h->play_n0 <= h->warm_until.load(std::memory_order_relaxed)) {
        const long long until = t_in + (long long)(h->warm_frac * 1e9 * frames / h->SR);
        while (rt::now_ns() < until) {
        }
    }
    return 0;
}

// A COLD START (an app's real time): a note-on after cold_s with no MIDI
// begins a phrase whose events all come one block (cold_blocks) later -- the
// same shift for every note of it, so its intervals stay as played (Ben: the
// differences are heard, not the absolute time) -- and the waiting block
// warms the core (nv_host_pull_step). The next cold note-on sets it again
void nv_host_set_cold_start(nv_host *h, int blocks, double cold_seconds, double warm_fraction)
{
    h->cold_blocks = std::max(0, std::min(4, blocks));
    h->cold_frames = (long long)(std::max(0.05, cold_seconds) * h->SR);
    h->warm_frac = std::max(0.0, std::min(0.9, warm_fraction));
}

// ---- RUBATO: borrowed time instead of a click (Ben's) ----
//
// A block that runs past its callback's deadline was a click: the device got
// silence for it. With rubato on there are two timelines: the LOGICAL -- the
// music, rendered on its own thread (in the audio workgroup) into a ring and
// handed out in order -- and the PHYSICAL -- the device's frames. The
// callback waits for the music only until its deadline (rub_frac of its
// length); on time -- nearly always -- the two run together and it hands out
// the same samples as nv_host_pull_step. Late, the physical runs on while the
// logical waits -- a hold, filled by the waiting moment's partials ringing
// on from their GPU block (--gpu-span; or the replay of what was just heard)
// -- and then the logical goes on from where it waited: the late block whole,
// after the ringing, time bent. The difference is the time borrowed, given
// back by cuts that let the logical catch up. MIDI comes in physical time
// and is placed in logical (nv_host_midi_at), every event alike, so what is
// played keeps its shape.

void nv_host::rub_loop()
{
    if (rub_rt_prio > 0) {                  // (as the audio thread: the music is made here now -- beside the guard's)
        const std::string why = rt::promote_aux(rub_rt_prio);
        if (!why.empty())
            fprintf(stderr, "nvlive: the render thread not real-time (%s)\n", why.c_str());
    }
    long long ran_since = rt::now_ns();     // (its last block on a wait: the kernel's real-time budget counts from it)
    while (!rub_stop.load()) {
        rub_go.wait();
        ran_since = rt::now_ns();
        if (rub_stop.load())
            break;
        NV_RT_HELPER();                         // (the audio workgroup's, where there is one)
        while (rub_made.load(std::memory_order_relaxed) < rub_want.load(std::memory_order_acquire)
               && !rub_stop.load(std::memory_order_relaxed)) {
            const long long made = rub_made.load(std::memory_order_relaxed);
            if (made + BLK - rub_took.load(std::memory_order_acquire) > rub_cap)
                break;                          // (the ring full: never, at a callback's want)
            bool ev;
            if (rub_block) {
                ev = rub_block(play_n0, play_buf.data());
            } else {
                timed_due(this, play_n0);
                ev = !due_rt.empty() || mq.size_approx() > 0;
                render_block(play_n0, play_buf.data(), false);
            }
            if (ev) {
                // (where its sound comes out: the block set up, plus the pipeline's lag)
                const unsigned k = rub_evn.load(std::memory_order_relaxed);
                rub_evr[k % RUB_EVN].store(play_n0 + (part ? nv_part_out_lag(part) : 0), std::memory_order_relaxed);
                rub_evn.store(k + 1, std::memory_order_release);
            }
            if (rub_stall_every > 0 && (play_n0 / BLK) % rub_stall_every == rub_stall_every - 1)
                std::this_thread::sleep_for(std::chrono::nanoseconds((long long)(rub_stall_ms * 1e6)));
            float *dst = rub_ring.data() + 2 * (made % rub_cap);
            std::memcpy(dst, play_buf.data(), sizeof(float) * 2 * BLK);   // (rub_cap a multiple of BLK)
            play_n0 += BLK;
            rub_made.store(made + BLK, std::memory_order_release);
            rub_done.signal();
            // (behind for a while -- never waiting -- a moment's sleep: a
            // real-time thread that runs RTTIME_SOFT_US without blocking is
            // demoted by the kernel; this one is allowed to be late, not that)
            if (rub_rt_prio > 0 && rt::now_ns() - ran_since > 50000000LL) {
                std::this_thread::sleep_for(std::chrono::microseconds(50));
                ran_since = rt::now_ns();
            }
        }
    }
}

bool nv_host::rub_events_in(long long a, long long b) const
{
    // (the newest first: an event block older than a ends the search -- they
    // are recorded in order; more than RUB_EVN since the oldest kept: say yes)
    const unsigned n = rub_evn.load(std::memory_order_acquire);
    for (unsigned j = 0; j < n && j < (unsigned)RUB_EVN; j++) {
        const long long n0 = rub_evr[(n - 1 - j) % RUB_EVN].load(std::memory_order_relaxed);
        if (n0 + BLK <= a)
            return false;
        if (n0 < b)
            return true;
    }
    return n > (unsigned)RUB_EVN;
}

// A SPLICE MATCHED BY ITS WAVEFORM (WSOLA's): of the starts lo..hi in the
// ring, the one whose next n frames best match ref's (the normalised
// correlation of the two ears' sums) -- so a crossfade from ref into it joins
// two waves in step, where two at different points of a low note's cycle
// cancelled in part (a dip in the bass, heard as a thud: Ben). Every other
// start, then its neighbours. -1: no room to look
extern "C++" {
template <class At>
static long long splice_best(const float *rl, const float *rr, int n, At at, long long lo, long long hi)
{
    if (lo < 0)                                 // (nothing before the music's start: a hold ending in its first moments)
        lo = 0;
    if (hi < lo || n <= 0)
        return -1;
    long long best = hi;
    double bc = -2.0;
    auto score = [&](long long s) {
        double c = 0.0, e = 0.0, e0 = 0.0;
        for (int i = 0; i < n; i++) {
            const float *q = at(s + i);
            const double a = (double)rl[i] + rr[i], b = (double)q[0] + q[1];
            c += a * b;
            e += b * b;
            e0 += a * a;
        }
        return (e > 1e-20 && e0 > 1e-20) ? c / std::sqrt(e * e0) : -2.0;
    };
    for (long long s = hi; s >= lo; s -= 2) {
        const double c = score(s);
        if (c > bc) {
            bc = c;
            best = s;
        }
    }
    for (long long s = best - 1; s <= best + 1; s += 2)
        if (s >= lo && s <= hi) {
            const double c = score(s);
            if (c > bc) {
                bc = c;
                best = s;
            }
        }
    return best;
}
}  // extern "C++"

static int nv_host_pull_rubato(nv_host *h, float *L, float *R, int frames)
{
    const long long t_in = rt::now_ns();
    const long long until = t_in + (long long)(h->rub_frac * 1e9 * frames / h->SR);
    const int XF = nv::RubFill::XF, LOOK = nv_host::RUB_LOOK, SEEK = nv_host::RUB_SEEK;
    const long long lg = h->rub_took.load(std::memory_order_relaxed);     // the logical timeline
    const long long ph = h->rub_phys.load(std::memory_order_relaxed);     // the physical
    const long long owed = ph - lg;                                       // borrowed
    // (the render thread asked for this callback's music -- and, while time is
    // owed, as much past it as a return's cut needs)
    const long long want = lg + frames + (h->rub_return && owed > 0 ? owed + LOOK + frames : 0);
    if (want > h->rub_want.load(std::memory_order_relaxed))
        h->rub_want.store(want, std::memory_order_release);
    h->rub_go.signal();
    while (h->rub_made.load(std::memory_order_acquire) < lg + frames) {
        const long long left = until - rt::now_ns();
        if (left <= 0)
            break;
        h->rub_done.wait_for_ns(left);          // (a block made, or the deadline)
    }
    const long long made = h->rub_made.load(std::memory_order_acquire);
    auto at = [h](long long k) { return h->rub_ring.data() + 2 * (k % h->rub_cap); };
    auto copy = [&](long long from, int n, int to) {
        for (int i = 0; i < n; i++) {
            const float *s = at(from + i);
            L[to + i] = s[0];
            R[to + i] = s[1];
        }
    };
    // 1. THE TIME RETURNED: the logical catches up -- a cut of what is owed
    // (made, and no event in it nor in an attack's first 20 ms before it),
    // placed up to SEEK/2 short of it where the waveform after matches the
    // one it leaves (WSOLA's; what is left returned at the next)
    // (A CEILING: past RUB_MAX_OWED the time is returned at the next chance
    // even beside an event -- a note a little early, not latency that grows
    // while the machine stays behind)
    const bool over = owed > (long long)(nv_host::RUB_MAX_OWED_S * h->SR);
    if (h->rub_return && owed > 0 && !h->rub_hold && made - lg >= owed + std::max(frames + XF, LOOK)
        && (over || !h->rub_events_in(lg - h->SR / 50, lg + owed + XF))) {
        for (int i = 0; i < LOOK; i++) {
            const float *q = at(lg + i);
            h->rub_rl[i] = q[0];
            h->rub_rr[i] = q[1];
        }
        const long long s = splice_best(h->rub_rl, h->rub_rr, LOOK, at, lg + std::max<long long>(XF, owed - SEEK / 2), lg + owed);
        const long long cut = s >= 0 ? s - lg : owed;
        for (int i = 0; i < frames; i++) {
            const float *b = at(lg + cut + i);
            if (i < XF) {
                const float *a = at(lg + i);
                const float w = 0.5f - 0.5f * std::cos(3.14159265f * (i + 0.5f) / XF);
                L[i] = w * b[0] + (1.0f - w) * a[0];
                R[i] = w * b[1] + (1.0f - w) * a[1];
            } else {
                L[i] = b[0];
                R[i] = b[1];
            }
        }
        h->rub_fill.heard(L, R, frames);
        h->rub_took.store(lg + cut + frames, std::memory_order_release);
        h->rub_phys.store(ph + frames, std::memory_order_release);
        h->rub_returned.fetch_add(cut, std::memory_order_relaxed);
        h->rub_returns.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    long long pos = lg;
    int have = 0;
    if (h->rub_hold && made > pos) {
        // 2. THE HOLD ENDS: the logical goes on from where it waited -- the
        // late block whole, whatever began in it heard from its start. After
        // the ringing, at the start at or just before the wait (within SEEK)
        // whose waveform matches the ringing's next frames, and crossed from
        // them; after the replay, its own crossing (rubfill.h)
        if (h->rub_ringing) {
            const long long s = splice_best(h->rub_xl, h->rub_xr, LOOK, at, std::max({pos - SEEK, made - h->rub_cap + 2 * LOOK, 0LL}),
                                            std::min(pos, made - LOOK));
            if (s >= 0) {
                h->rub_held.fetch_add(pos - s, std::memory_order_relaxed);
                pos = s;                        // (a little further back: borrowed, as the hold was)
            }
            have = (int)std::max<long long>(0, std::min<long long>(made - pos, frames));
            copy(pos, have, 0);
            const int m = std::min(have, XF);
            for (int i = 0; i < m; i++) {
                const float w = 0.5f - 0.5f * std::cos(3.14159265f * (i + 0.5f) / m);
                L[i] = w * L[i] + (1.0f - w) * h->rub_xl[i];
                R[i] = w * R[i] + (1.0f - w) * h->rub_xr[i];
            }
            h->rub_fill.heard(L, R, have);
        } else {
            have = (int)std::max<long long>(0, std::min<long long>(made - pos, frames));
            copy(pos, have, 0);
            h->rub_fill.resume(L, R, have);
        }
        h->rub_hold = h->rub_ringing = false;
    } else {
        have = (int)std::max<long long>(0, std::min<long long>(made - pos, frames));
        copy(pos, have, 0);
        h->rub_fill.resume(L, R, have);         // (heard)
    }
    pos += have;
    h->rub_took.store(pos, std::memory_order_release);
    if (have < frames) {
        // 3. A HOLD: the physical runs on, the logical waits at pos. Filled by
        // the music's state there run on -- its GPU block's partials ringing
        // (nv_part_extend: from pos, as far as the hold has rung) -- or, where
        // no block reaches, by the replay of what was just heard (rubfill.h)
        const int n = frames - have;
        const bool first = !h->rub_hold;
        if (first) {
            h->rub_holds.fetch_add(1, std::memory_order_relaxed);
            h->rub_run = 0;
            h->rub_ringing = true;
        }
        bool rung = false;
        if (h->rub_ringing && !h->rub_silent && h->part)
            rung = nv_part_extend(h->part, pos + h->rub_run, n, L + have, R + have, first ? 1 : 0, LOOK, h->rub_xl,
                                  h->rub_xr) == n;
        if (rung) {
            h->rub_fill.heard(L + have, R + have, n);
            h->rub_ext_n.fetch_add(n, std::memory_order_relaxed);
        } else {
            h->rub_ringing = false;             // (from here the replay: it joins what was heard)
            h->rub_fill.gen(L + have, R + have, n);
            if (h->rub_silent)
                for (int i = have; i < frames; i++)
                    L[i] = R[i] = 0.0f;
        }
        h->rub_run += n;
        h->rub_held.fetch_add(n, std::memory_order_relaxed);
        h->rub_hold = true;
    }
    h->rub_phys.store(ph + frames, std::memory_order_release);
    return 0;
}

int nv_host_set_rubato(nv_host *h, int on, double wait_fraction)
{
    h->rub_frac = std::max(0.05, std::min(1000.0, wait_fraction));   // (over 1: longer than the callback -- a test's)
    if (!on == !h->rub_on)
        return 0;
    if (on) {
        // (from where the plain pull left off: its last block's frames not yet
        // handed out would be skipped -- turned on before the first callback)
        if (h->play_buf.size() < 2 * (size_t)h->BLK)
            h->play_buf.assign(2 * h->BLK, 0.0f);   // (nvlive --test's host is not opened through nv_host_open_args)
        h->rub_cap = 512 * h->BLK;          // (1.4 s at 128: room for the most that may be owed, and a cut past it)
        h->rub_ring.assign(2 * h->rub_cap, 0.0f);
        h->rub_made = h->rub_took = h->rub_want = 0;
        h->rub_phys = 0;
        h->rub_hold = h->rub_ringing = false;
        h->rub_evn = 0;
        h->rub_fill = nv::RubFill();
        h->rub_fill.set_rate(h->SR);
        h->rub_stop = false;
        h->rub_on = true;
        h->rub_thread = std::thread([h] { h->rub_loop(); });
    } else {
        h->rub_stop = true;
        h->rub_go.signal();
        if (h->rub_thread.joinable())
            h->rub_thread.join();
        h->rub_on = false;
    }
    return 0;
}

void nv_host_rubato_stats(const nv_host *h, long long *out)
{
    out[0] = h->rub_holds.load();
    out[1] = h->rub_held.load();
    out[2] = h->rub_owed_now();
    out[3] = h->rub_made.load();
    out[4] = h->rub_took.load();
    out[5] = h->rub_returns.load();
    out[6] = h->rub_returned.load();
    out[7] = h->rub_ext_n.load();
}

void nv_host_set_rubato_return(nv_host *h, int on) { h->rub_return = on != 0; }

int nv_host_pull(nv_host *h, float *L, float *R, int frames)
{
    if (h->rub_on)
        return nv_host_pull_rubato(h, L, R, frames);
    return nv_host_pull_step(h, L, R, frames, 0);
}

// MIDI bytes stamped with the sample they belong to (from the start of the
// render: nv_host_snapshot's n0 counts them): heard at the start of the block
// that sample falls in -- as nvlive --test places a file's events -- or at
// the next block if that one is gone
void nv_host_midi_at(nv_host *h, const uint8_t *msg, int n, long long frame)
{
    // (rubato: the device frames ahead of the render by what is borrowed --
    // the event heard that much later, as everything since the hold)
    if (h->rub_on && frame > 0)
        frame -= h->rub_owed_now();
    if (h->cold_blocks > 0 && n > 0) {
        // (a cold start's shift: a phrase's events one block later, the note-on
        // that begins it after cold_s of no MIDI setting it)
        const long long f = frame > 0 ? frame : h->play_n0;
        const long long last = h->last_midi_f;
        const bool on = n >= 3 && (msg[0] & 0xF0) == 0x90 && msg[2] > 0;
        if (last < 0 || f - last >= h->cold_frames) {
            h->phrase_shift = on ? (long long)h->cold_blocks * h->BLK : 0;
            if (on)
                h->warm_until.store(f + h->phrase_shift, std::memory_order_relaxed);
        }
        h->last_midi_f = f;
        frame = f + h->phrase_shift;
    }
    h->reclaim();
    std::lock_guard<std::mutex> lk(h->timed_mu);     // (the parse's running status: the stamping threads')
    h->timed_parse.feed(msg, n, [&](Midi &&m) {
        if (h->module_on.load(std::memory_order_acquire) && h->module_feed_at)
            h->module_feed_at(h, std::move(m), frame);      // (the module mode's reading of it, at its frame)
        else
            h->push_timed(std::move(m), frame);
    });
}

// a message heard at the start of the block FRAME falls in (nv_host_midi_at's)
void nv_host::push_timed(Midi &&m, long long frame)
{
    Midi *p = new Midi(std::move(m));
    p->at = frame;
    while (!tq.push(p))
        std::this_thread::yield();
}

void nv_host_midi(nv_host *h, const uint8_t *msg, int n)
{
    std::lock_guard<std::mutex> lk(h->midi_in_mu);   // (the parse's running status: the callers')
    h->midi_in.feed(msg, n, [&](Midi &&m) { h->input(std::move(m)); });
}

void nv_host_snapshot(nv_host *h, nv_host_snap *s)
{
    h->reclaim();                               // (the window's poll: the block's trash freed here too)
    std::lock_guard<std::mutex> lk(h->pmu);
    const panel::Snap &p = h->snap;
    s->n0 = p.n0;
    s->blocks = p.blocks;
    s->over = p.over;
    s->underruns = p.underruns;
    s->ms_max = p.ms_max;
    s->max_step_ms = h->snap_step;
    s->max_out_ms = h->snap_out;
    s->max_busy = h->snap_st[0];
    s->max_gpu = h->snap_st[1];
    s->max_gpu_setup_ms = h->snap_st[2];
    s->max_gpu_samples_ms = h->snap_st[3];
    for (int i = 0; i < 3; i++)
        s->max_split_ms[i] = h->snap_split[i];
    s->max_cpu_user_ms = h->snap_cpu[0];
    s->max_cpu_sys_ms = h->snap_cpu[1];
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
    h->snap_step = h->snap_out = 0.0;
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
                h->room_req_tl_on = false;      // (the user's room, over a sequencer's reverb: live.set_room)
                h->user_room = r.name;
                h->gs_rev.clear();
            }
            h->bcv.notify_one();
            return;
        }
}

int nv_host_global_count(void) { return NV_G_N; }

void nv_host_set_global(nv_host *h, int which, double v) { h->set_global(which, v); }

double nv_host_global(const nv_host *h, int which)
{
    if (which < 0 || which >= NV_G_N)
        return 0.0;
    return which == 8 ? (double)h->room_idx : h->gval[which];
}

int nv_host_patches(nv_host *h, nv_host_patch *out, int cap)
{
    if (h->pnames.empty())
        h->patches_init();
    int n = 0;
    for (int sp = 0; sp < 256; sp++) {
        if (h->pnames[sp].empty())
            continue;
        if (out && n < cap) {
            nv_host_patch &o = out[n];
            o.program = sp & 127;
            o.variation = 0;
            o.drums = sp >= 128;
            o.native = h->pnative[sp];
            o.pick = sp;
            snprintf(o.name, sizeof o.name, "%s", h->pnames[sp].c_str());
        }
        n++;
    }
    for (size_t j = 0; j < h->E.vpv.size(); j++) {
        if (out && n < cap) {
            nv_host_patch &o = out[n];
            o.program = h->E.vpv[j][0];
            o.variation = h->E.vpv[j][1];
            o.drums = 0;
            o.native = h->vnative[j];
            o.pick = 256 + (int)j;
            snprintf(o.name, sizeof o.name, "%s", j < h->E.vnames.size() ? h->E.vnames[j].c_str() : "");
        }
        n++;
    }
    return n;
}

void nv_host_pick(nv_host *h, int pick) { h->pick(pick); }

void nv_host_patch_now(const nv_host *h, int *program, int *variation, int *drums)
{
    const int sp = h->shown_program;
    if (program)
        *program = sp & 127;
    if (drums)
        *drums = sp >= 128;
    if (variation)
        *variation = sp >= 128 ? 0 : h->shown_var.load();
}

void nv_host_panic(nv_host *h) { h->panic(); }

int nv_host_building(nv_host *h) { return h->building(); }
int nv_host_progress(nv_host *h, long *done, long *total, char *name, int cap)
{
    std::string nm;
    if (!h->progress(done, total, &nm))
        return 0;
    if (name && cap > 0)
        snprintf(name, (size_t)cap, "%s", nm.c_str());
    return 1;
}
void *nv_host_part(nv_host *h) { return h->part; }

}  // extern "C"
