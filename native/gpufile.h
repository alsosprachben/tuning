// gpufile.h -- nvrender's --gpu: gpurender.FileRenderer, a window of the
// stream's table on the GPU. The setup is voice_block from blockrender's GPU
// build (libsynthgpu_SR.so, or its damper build for a table with damper
// tracks), the samples gpukernel.cl's voices_win through native/gpu.cpp
// (nv_cl_win). Not bit for bit the CPU's render -- the phasors are evaluated,
// not turned, and summed in another order -- but FileRenderer's, step for
// step: each row's audible end (RETIRE_FLOOR), the active set swept by
// onset, a window of 32 blocks cut to DESC_BUDGET, voice_pack's packing,
// the groups and their work-groups, each block's sums in order.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <string>
#include <thread>
#include <vector>

extern "C" {
void *nv_cl_new(const char *dir, const int *sizes, char *err, int errlen);
void nv_cl_free(void *h);
int nv_cl_win(void *h, const void *G, long gn, const void *D, long dn, const void *C, long cn, const void *S, long sn,
              int ng, int frames, int mg, long long n0, int send, float *res);
}

typedef int (*gf_vblock_fn)(
    long n0, int BLK, int nblk, int P,
    const double *omega, const double *ph0L, const double *ph0R,
    const float *ampL, const float *ampR, const float *nomfreq,
    const long *non, const long *noff, const float *fadeS, const float *relS, const float *chiffS,
    const float *logr, const float *logrA, const float *aftL, const float *susL,
    const float *chVol, const float *chCyc, const float *chRel, const float *susJit, const float *chScale,
    const float *chBW, const float *tbav, const float *tau, const float *tcut,
    const float *gbav, const float *gtau, const float *gcut,
    const float *vdep, const float *vrate, const float *vph, const float *vdl,
    const float *delL, const float *delR,
    const int *grow, const int *crow, const float *G, const float *S,
    const int *brow, const float *BR, const double *BC, const float *BL,
    const int *fxr, const float *FT, const float *KN, long knk, long kb0,
    const float *ampLp, const float *ampRp, const int *mkr,
    const int *MPI, const double *MPC, const float *MPR, const int *MKI, const float *MPK,
    const double *fmw, const double *fmp, const double *fmpR,
    float sfloor, float spow, float shmax, float shref,
    const int *lsr, const float *lph, const float *lfl, const float *lsh, const float *lnm,
    const float *LANG, long lgn,
    const int *fsr, const int *fty, const float *fpa, const float *fpb, const float *fpc,
    const float *FCT, long fgn,
    const float *sendW, int send,
    const long *idx, int nact, void *D, void *C, int ccap, void *SB, int sbcap,
    int nthr, int *counts, int nb);
typedef void (*gf_vdamp_fn)(const int *drow, const float *dwt, const float *DM, const long *DMO, const long *DMB,
                            const long *DMN);
typedef void (*gf_vsizes_fn)(int *out);
typedef void (*gf_vpack_fn)(void *D, int nact, int nb, int *m);

// a window's table, by column (prepare's final types), as the stream gathers it
struct GfTable {
    long long P = 0;
    const double *d[3];                     // om p0 p0R
    const float *f[29];                     // VF order (render.cpp's F_*), f[28] the damper weight
    const long *l[2];                       // non noff
    const int *i[4];                        // gr cr br dk
    const int *fx = nullptr, *mk = nullptr; // a Moog's, NULL none
    const float *FT = nullptr, *KN = nullptr;
    long knk = 1, kb0 = 0;
    const int *MPI = nullptr, *MKI = nullptr;
    const double *MPC = nullptr;
    const float *MPR = nullptr, *MPK = nullptr;
    const double *fm[3] = {nullptr, nullptr, nullptr};
    const int *lsr = nullptr;               // a rotor's lobe columns, NULL none
    const float *lob[4] = {nullptr, nullptr, nullptr, nullptr};     // lph lfl lsh lnm
};

struct GpuFile {
    enum { F_aL, F_aR, F_nf, F_fa, F_re, F_ch, F_logr, F_logrA, F_aft, F_sus, F_cv, F_cc, F_crl, F_sj, F_csc, F_cbw,
           F_tbav, F_tau, F_tcut, F_gb, F_gt, F_gc, F_vd, F_vr, F_vp, F_vdl, F_delL, F_delR, F_dg };
    static const int LK = 16, LG = 8, W = 32;
    static constexpr double RETIRE_FLOOR = 1e-6, BEND_RETIRE_FLOOR = 3e-7;
    // THE WINDOW's BUDGET (FileRenderer's DESC_BUDGET: "memory bounded however
    // dense the file"), counted at what a descriptor really costs: its own
    // bytes, and the result it brings -- at most BLK bytes on the host and as
    // many on the GPU (groups of 2 or more, LG to a work-group, 4 floats a
    // sample), and its group's 8 -- FileRenderer's count, 384 MB of everything,
    // beside the stream's own under a 3.5 GB cap. NV_GPU_DESC_MB sets it
    long long DESC_BUDGET = 384LL << 20;
    void *cl = nullptr;
    gf_vblock_fn vb = nullptr, vbd = nullptr;
    gf_vdamp_fn vds = nullptr;
    gf_vpack_fn vpack = nullptr;
    int sz[3] = {0, 0, 0};                  // vdesc, vcell, vsb
    int nthr = 4;
    struct Tab {                            // gpurender.aligned_zeros: whole pages and whole records
        void *p = nullptr;
        long n = 0, size = 0;
        ~Tab() { free(p); }
        void room(long want, long sz_, long cap = 0)        // (contents not kept: each fill writes its own)
        {
            if (p && want <= n)
                return;
            long grow = n ? (cap ? std::min(2 * n, cap) : 2 * n) : want;
            long m0 = std::max(want, grow);
            long a = 4096, b = sz_;
            while (b) {
                long t = a % b;
                a = b;
                b = t;
            }
            long per = 4096 / a;
            long m = std::max((std::max(m0, 1L) + per - 1) / per * per, per);
            free(p);
            p = aligned_alloc(4096, (size_t)(m * sz_));
            memset(p, 0, (size_t)(m * sz_));
            n = m;
            size = sz_;
        }
        long bytes() const { return n * size; }
    } D, C, SB, G;
    std::vector<float> res;
    // the bend rows' level from each block on (_audible_end's sm), made once a song
    std::vector<float> BLmax;
    long BLrows = 0, BLcols = 0;

    ~GpuFile()
    {
        if (cl)
            nv_cl_free(cl);
    }

    // the GPU (OpenCL, gpukernel.cl in dir) and the setup's builds in dir (SR's): "" or why not
    std::string open(const std::string &dir, int SR)
    {
        std::string lib = dir + "/libsynthgpu_" + std::to_string(SR) + ".so";
        std::string dlib = dir + "/libsynthgpudamp_" + std::to_string(SR) + ".so";
        void *h = dlopen(lib.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!h)
            return "no " + lib + " (blockrender.ensure_gpu_lib builds it)";
        vb = (gf_vblock_fn)dlsym(h, "voice_block");
        vpack = (gf_vpack_fn)dlsym(h, "voice_pack");
        gf_vsizes_fn vz = (gf_vsizes_fn)dlsym(h, "voice_sizes");
        if (!vb || !vpack || !vz)
            return "no voice_block / voice_pack / voice_sizes in " + lib;
        vz(sz);
        void *hd = dlopen(dlib.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (hd) {
            vbd = (gf_vblock_fn)dlsym(hd, "voice_block");
            vds = (gf_vdamp_fn)dlsym(hd, "voice_damp_set");
        }
        char err[512] = {0};
        cl = nv_cl_new(dir.c_str(), sz, err, sizeof err);
        if (!cl)
            return std::string("the GPU: ") + err;
        const char *db = getenv("NV_GPU_DESC_MB");
        if (db && atoll(db) > 0)
            DESC_BUDGET = atoll(db) << 20;
        unsigned hc = std::thread::hardware_concurrency();
        nthr = hc ? (int)hc : 4;            // (every core for the descriptors: os.cpu_count())
        D.room(1 << 16, sz[0]);
        C.room(1 << 12, sz[1]);
        SB.room(1 << 14, sz[2]);
        G.room(1 << 12, 16);
        return "";
    }

    // _audible_end's sm: each bend row's level, the most it meets from each block on
    void bend_levels(const float *BL, long nr, long ncol)
    {
        BLrows = nr;
        BLcols = ncol;
        BLmax.assign(BL ? (size_t)(nr * ncol) : 0, 0.0f);
        if (!BL)
            return;
        for (long r = 0; r < nr; r++) {
            float m = -INFINITY;
            for (long c = ncol - 1; c >= 0; c--) {
                m = std::max(m, BL[r * ncol + c]);
                BLmax[r * ncol + c] = m;
            }
        }
    }

    // FileRenderer.render(N = n0 + wn, send_w, n0): the selected rows (sel NULL: all)
    // into out[4][wn] (L, R, SL, SR, unscaled, zeroed here); sendW per row or NULL.
    // 0, or -1 where the GPU failed
    int render(const GfTable &t, const unsigned char *sel, long long n0, long long wn, const float *sendW,
               int BLK, int nblk, const float *Gt, const float *St, const float *BR, const double *BC,
               const float *BL, const float *sh, const float *LANG, long lgn, const float *DM, const long *DMO,
               const long *DMB, const long *DMN, double SR, float *out)
    {
        memset(out, 0, sizeof(float) * 4 * wn);
        // the rows, by onset (stable), and each one's end: as voice_partial.inc
        // ends it, or its last sample above the floor, the sooner
        std::vector<long> ord;
        for (long long r = 0; r < t.P; r++)
            if (!sel || sel[r])
                ord.push_back((long)r);
        std::stable_sort(ord.begin(), ord.end(), [&](long a, long b) { return t.l[0][a] < t.l[0][b]; });
        std::vector<long long> end(t.P, 0);
        const long long big = INT64_MAX / 4;
        for (long r : ord) {
            float dl32 = std::max(0.0f, std::max(t.f[F_delL][r], t.f[F_delR][r]));
            long long cdl = (long long)std::ceil(dl32);
            long long e = (long long)t.l[1][r] + (long long)t.f[F_re][r] + cdl + BLK;
            // _audible_end
            double a = std::max(std::fabs((double)t.f[F_aL][r]), std::fabs((double)t.f[F_aR][r]));
            double lift = 1.0, F = RETIRE_FLOOR;
            const int br = t.i[2][r];
            if (br >= 0) {
                F = BEND_RETIRE_FLOOR;
                if (BL && !BLmax.empty()) {
                    long bb = std::min((long)(t.l[0][r] / BLK), BLcols - 1);
                    lift = std::max((double)BLmax[(size_t)br * BLcols + bb], 0.0);
                }
            }
            if (LANG && t.lsr && t.lsr[r] >= 0)
                lift = lift * (double)t.lob[3][r];
            a = a * lift;
            const double sl = t.f[F_sus][r], af = t.f[F_aft][r], lr = t.f[F_logr][r], lrA = t.f[F_logrA][r];
            auto t_to = [&](double c, double rate) -> double {
                if (rate < 0.0)
                    return INFINITY;
                if (c <= F)
                    return 0.0;
                if (rate > 0.0)
                    return std::log(std::max(c, F) / F) / rate;
                return INFINITY;
            };
            double tt = std::max(t_to((1.0 - sl) * (1.0 - af) * a, lr), t_to((1.0 - sl) * af * a, lrA));
            if (sl * a > F)
                tt = INFINITY;
            if ((t.fx && t.fx[r] >= 0) || t.i[0][r] >= 0)
                tt = INFINITY;
            long long ae = std::isfinite(tt)
                ? (long long)t.l[0][r] + (long long)(std::min(tt, 1e6) * SR) + cdl + 2LL * BLK : big;
            end[r] = std::min(e, ae);
        }
        const int mg = (BLK % 128 == 0 && BLK / 128 <= 64) ? 128 : BLK;
        const long long N = n0 + wn;
        const long nb = (long)((N + BLK - 1) / BLK);
        std::vector<long> active;
        size_t ptr = 0;
        long wb = (long)(n0 / BLK);
        int counts[2];
        while (wb < nb) {
            long b0 = wb, b1 = std::min(nb, wb + (long)W);
            long long w0 = (long long)b0 * BLK, w1 = (long long)b1 * BLK;
            while (ptr < ord.size() && (long long)t.l[0][ord[ptr]] < w1)
                active.push_back(ord[ptr++]);
            {
                size_t k = 0;
                for (size_t q = 0; q < active.size(); q++)
                    if (end[active[q]] > w0)
                        active[k++] = active[q];
                active.resize(k);
            }
            const long nact = (long)active.size();
            if (!nact) {
                wb = b1;
                continue;
            }
            long nbk = b1 - b0;
            const long cap = std::max(nact, (long)(DESC_BUDGET / (sz[0] + 2L * BLK + 8)));
            if (nact * nbk > cap) {
                nbk = std::max(1L, cap / nact);
                b1 = b0 + nbk;
            }
            D.room(nact * nbk, sz[0], cap);
            bool damp = false;
            if (DM && t.i[3])
                for (long r : active)
                    damp = damp || t.i[3][r] >= 0;
            gf_vblock_fn fn = vb;
            if (damp) {
                if (!vbd || !vds)
                    return -1;
                vds(t.i[3], t.f[F_dg], DM, DMO, DMB, DMN);
                fn = vbd;
            }
            for (;;) {
                int r = fn((long)w0, BLK, nblk, (int)t.P, t.d[0], t.d[1], t.d[2], t.f[F_aL], t.f[F_aR], t.f[F_nf],
                           t.l[0], t.l[1], t.f[F_fa], t.f[F_re], t.f[F_ch], t.f[F_logr], t.f[F_logrA], t.f[F_aft],
                           t.f[F_sus], t.f[F_cv], t.f[F_cc], t.f[F_crl], t.f[F_sj], t.f[F_csc], t.f[F_cbw],
                           t.f[F_tbav], t.f[F_tau], t.f[F_tcut], t.f[F_gb], t.f[F_gt], t.f[F_gc], t.f[F_vd],
                           t.f[F_vr], t.f[F_vp], t.f[F_vdl], t.f[F_delL], t.f[F_delR], t.i[0], t.i[1], Gt, St,
                           t.i[2], BR, BC, BL, t.fx, t.fx ? t.FT : nullptr, t.fx ? t.KN : nullptr, t.knk, t.kb0,
                           nullptr, nullptr, t.fx ? t.mk : nullptr, t.MPI, t.MPI ? t.MPC : nullptr,
                           t.MPI ? t.MPR : nullptr, t.MKI, t.MKI ? t.MPK : nullptr, t.fx ? t.fm[0] : nullptr,
                           t.fx ? t.fm[1] : nullptr, t.fx ? t.fm[2] : nullptr, sh[0], sh[1], sh[2], sh[3],
                           LANG ? t.lsr : nullptr, LANG ? t.lob[0] : nullptr, LANG ? t.lob[1] : nullptr,
                           LANG ? t.lob[2] : nullptr, LANG ? t.lob[3] : nullptr, LANG, LANG ? lgn : 0, nullptr,
                           nullptr, nullptr, nullptr, nullptr, nullptr, 0, sendW ? sendW : &zero_, sendW ? 1 : 0,
                           active.data(), (int)nact, D.p, C.p, (int)C.n, SB.p, (int)SB.n, nthr, counts, (int)nbk);
                if (r == 0)
                    break;
                if (counts[0] > C.n)
                    C.room(2L * counts[0], sz[1]);
                if (counts[1] > SB.n)
                    SB.room(2L * counts[1], sz[2]);
            }
            std::vector<int> m(nbk);
            vpack(D.p, (int)nact, (int)nbk, m.data());
            if (getenv("NV_GPU_STATS")) {           // (the tables' sizes, a window at a time)
                static long last = -1;
                long sec = (long)(w0 / SR);
                if (sec != last) {
                    last = sec;
                    FILE *f = fopen("/proc/self/status", "r");
                    char ln[256];
                    long kb = 0;
                    while (f && fgets(ln, sizeof ln, f))
                        if (!strncmp(ln, "VmRSS:", 6))
                            kb = atol(ln + 6);
                    if (f)
                        fclose(f);
                    fprintf(stderr, "GPUSTAT %5ld s  rows %7lld  active %7ld x %2ld blocks  D %5ld MB  C %5ld MB (%d)  "
                                    "SB %5ld MB (%d)  G %4ld MB  res %5ld MB  RSS %ld MB\n",
                            sec, t.P, nact, nbk, D.bytes() >> 20, C.bytes() >> 20, counts[0], SB.bytes() >> 20,
                            counts[1], G.bytes() >> 20, (long)(res.capacity() * 4) >> 20, kb >> 10);
                }
            }
            std::vector<long> per(nbk), gn(nbk);
            long ng = 0;
            for (long j = 0; j < nbk; j++) {
                long mj = m[j];
                per[j] = std::max(2L, (mj + 255) / 256);
                long g = (mj + per[j] - 1) / per[j];
                gn[j] = (g + LG - 1) / LG * LG;
                ng += gn[j];
            }
            if (ng) {
                G.room(ng, 16);
                int32_t *gp = (int32_t *)G.p;
                long q = 0;
                for (long j = 0; j < nbk; j++)
                    for (long g = 0; g < gn[j]; g++, q++) {
                        gp[4 * q] = (int32_t)(j * nact + std::min((long)m[j], g * per[j]));
                        gp[4 * q + 1] = (int32_t)(j * nact + std::min((long)m[j], (g + 1) * per[j]));
                        gp[4 * q + 2] = (int32_t)(j * BLK);
                        gp[4 * q + 3] = 0;
                    }
                const long nwg = ng / LG;
                res.resize((size_t)4 * nwg * BLK);
                if (nv_cl_win(cl, G.p, G.bytes(), D.p, D.bytes(), C.p, C.bytes(), SB.p, SB.bytes(), (int)ng, BLK, mg,
                              (long long)wb * BLK, sendW ? 1 : 0, res.data()) != 0)
                    return -1;
                // each block's work-groups summed (res.sum(1): the first, then each added)
                long s0 = 0;
                for (long j = 0; j < nbk; j++) {
                    const long n = gn[j] / LG;
                    if (n) {
                        const long long a = (long long)(wb + j) * BLK - n0;
                        const long long e = std::min(N - n0, a + BLK);
                        for (int c = 0; c < 4; c++)
                            for (long long k = 0; k < e - a; k++) {
                                const float *rr = res.data() + ((size_t)c * nwg + s0) * BLK + k;
                                float v = rr[0];
                                for (long g = 1; g < n; g++)
                                    v += rr[(size_t)g * BLK];
                                out[(size_t)c * wn + a + k] += v;
                            }
                    }
                    s0 += n;
                }
            }
            wb = b1;
        }
        return 0;
    }
    float zero_ = 0.0f;
};
