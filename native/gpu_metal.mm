// gpu_metal.mm -- the GPU's sample pass on Metal (macOS now, iOS next, which
// has no OpenCL): native/gpu.cpp's Gpu, method for method, over
// gpukernel.metal -- the same voice_sample (voicedesc.h), the same
// work-groups, the same sums on the host in the same order. Chosen at
// nv_cl_new (gpu.cpp) by TUNING_GPU_API=metal; OpenCL stays the reference
// it is measured against on the same machine.
//
// APPLE SILICON SHARES ITS MEMORY: each table goes into a shared buffer (a
// memcpy, kept and grown per slot), the result is read where the GPU wrote
// it. The kernel is compiled at run time from gpukernel.metal with
// voicedesc.h's text in place of its #include (newLibraryWithSource cannot
// open files), the precise maths on (no fast-math approximations).

#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

struct VArgs {                  // gpukernel.metal's vargs
    int nd, per, frames, mg;
    unsigned long long n0;
    int send, pad;
};

struct Buf {                    // a shared buffer, grown as asked
    id<MTLBuffer> b = nil;
    size_t cap = 0;
};

struct MetalGpu {
    static const int LK = 16, LG = 8;
    id<MTLDevice> dev = nil;
    id<MTLCommandQueue> q = nil;
    id<MTLComputePipelineState> pv = nil, pw = nil;
    Buf tab[3], acc, wtab[4], wacc;
    struct Slot {
        Buf tab[3], acc;
        id<MTLCommandBuffer> cb = nil;
        int NG = 0, frames = 0;
        double t_commit = 0.0;
    } slot[3];                              // (three: a pipeline two deep, and the one being set up)
    // TUNING_METAL_TRACE: each pipelined block's time split -- committed to
    // the GPU's start (scheduling), the GPU's own run, its end to the wait's
    // return (waking) -- summarised on stderr when the GPU is let go
    bool trace = getenv("TUNING_METAL_TRACE") != nullptr;
    std::vector<double> t_sched, t_run, t_wake, t_total;
    static double now_s()
    {
        return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    static void stat(const char *what, std::vector<double> v)
    {
        if (v.empty())
            return;
        std::sort(v.begin(), v.end());
        double s = 0.0;
        for (double x : v)
            s += x;
        fprintf(stderr, "metal: %-10s %.3f ms mean, %.3f p99, %.3f worst (%zu)\n", what, 1e3 * s / v.size(),
                1e3 * v[v.size() * 99 / 100], 1e3 * v.back(), v.size());
    }
    static MetalGpu *&traced()
    {
        static MetalGpu *g = nullptr;
        return g;
    }
    void report()
    {
        if (trace && !t_total.empty()) {
            stat("scheduled", t_sched);
            stat("GPU run", t_run);
            stat("woken", t_wake);
            stat("total", t_total);
            t_total.clear();
        }
    }
    ~MetalGpu()
    {
        report();
        if (traced() == this)
            traced() = nullptr;
    }

    bool grow(Buf &b, size_t n)
    {
        if (b.b && b.cap >= n)
            return true;
        size_t c = n > 2 * b.cap ? n : 2 * b.cap;
        b.b = [dev newBufferWithLength:(c ? c : 16) options:MTLResourceStorageModeShared];
        b.cap = b.b ? c : 0;
        return b.b != nil;
    }
    bool put(Buf &b, const void *p, size_t n)
    {
        if (!grow(b, n ? n : 16))
            return false;
        if (n)
            memcpy([b.b contents], p, n);
        return true;
    }

    static std::string read_file(const std::string &path, bool &ok)
    {
        std::string s;
        ok = false;
        if (FILE *f = fopen(path.c_str(), "rb")) {
            char buf[4096];
            for (size_t n; (n = fread(buf, 1, sizeof buf, f)) > 0;)
                s.append(buf, n);
            fclose(f);
            ok = true;
        }
        return s;
    }

    bool open(const char *dir, const int *sizes, std::string &err)
    {
        if (trace) {                            // (nvlive exits without letting the GPU go: reported at exit)
            traced() = this;
            atexit([] {
                if (traced())
                    traced()->report();
            });
        }
        @autoreleasepool {
            dev = MTLCreateSystemDefaultDevice();
            if (!dev) {
                err = "no Metal device";
                return false;
            }
            bool ok1, ok2;
            std::string src = read_file(std::string(dir) + "/gpukernel.metal", ok1);
            std::string hdr = read_file(std::string(dir) + "/voicedesc.h", ok2);
            if (!ok1 || !ok2) {
                err = std::string("cannot read gpukernel.metal or voicedesc.h in ") + dir;
                return false;
            }
            const std::string inc = "#include \"voicedesc.h\"";
            size_t at = src.find(inc);
            if (at == std::string::npos) {
                err = "gpukernel.metal: no #include of voicedesc.h";
                return false;
            }
            src.replace(at, inc.size(), hdr);
            MTLCompileOptions *o = [MTLCompileOptions new];
            if (@available(macOS 15.0, iOS 18.0, *))
                o.mathMode = MTLMathModeSafe;
            else
                o.fastMathEnabled = NO;
            NSError *e = nil;
            id<MTLLibrary> lib = [dev newLibraryWithSource:[NSString stringWithUTF8String:src.c_str()]
                                                   options:o
                                                     error:&e];
            if (!lib) {
                err = std::string("gpukernel.metal: ") + (e ? [[e localizedDescription] UTF8String] : "?");
                return false;
            }
            auto pipe = [&](const char *name) -> id<MTLComputePipelineState> {
                id<MTLFunction> f = [lib newFunctionWithName:[NSString stringWithUTF8String:name]];
                if (!f)
                    return nil;
                NSError *pe = nil;
                return [dev newComputePipelineStateWithFunction:f error:&pe];
            };
            pv = pipe("voices");
            pw = pipe("voices_win");
            id<MTLComputePipelineState> ps = pipe("sizes");
            if (!pv || !pw || !ps) {
                err = "gpukernel.metal: a kernel would not build";
                return false;
            }
            q = [dev newCommandQueue];
            // the layout, as this compiler sees voicedesc.h
            id<MTLBuffer> b = [dev newBufferWithLength:3 * sizeof(int) options:MTLResourceStorageModeShared];
            id<MTLCommandBuffer> cb = [q commandBuffer];
            id<MTLComputeCommandEncoder> en = [cb computeCommandEncoder];
            [en setComputePipelineState:ps];
            [en setBuffer:b offset:0 atIndex:0];
            [en dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
            [en endEncoding];
            [cb commit];
            [cb waitUntilCompleted];
            const int *got = (const int *)[b contents];
            if (memcmp(got, sizes, 3 * sizeof(int))) {
                char m[160];
                snprintf(m, sizeof m, "Metal lays voicedesc.h out as (%d, %d, %d), the host as (%d, %d, %d)", got[0],
                         got[1], got[2], sizes[0], sizes[1], sizes[2]);
                err = m;
                return false;
            }
            if ((int)pv.maxTotalThreadsPerThreadgroup < LK * LG || (int)pw.maxTotalThreadsPerThreadgroup < LK * LG) {
                err = "Metal: a threadgroup of 128 is too many for the kernel";
                return false;
            }
            return true;
        }
    }

    // gpu.cpp's group arithmetic: per descriptors a group, groups padded to LG
    static void groups_of(int nd, int &per, int &groups)
    {
        per = nd / 1024 + (nd % 1024 != 0);
        per = per > 2 ? per : 2;
        groups = nd / per + (nd % per != 0);
        groups = groups > 1 ? groups : 1;
        groups = (groups / LG + (groups % LG != 0)) * LG;
    }

    // the sample pass encoded into cb: tables in t, the result into a
    id<MTLCommandBuffer> encode(Buf *t, Buf &a, int nd, long long n0, int frames, int send, int mg, int &NG)
    {
        int per, groups;
        groups_of(nd, per, groups);
        NG = groups / LG;
        if (!grow(a, (size_t)4 * NG * frames * sizeof(float)))
            return nil;
        VArgs A{nd, per, frames, mg, (unsigned long long)n0, send, 0};
        id<MTLCommandBuffer> cb = [q commandBuffer];
        id<MTLComputeCommandEncoder> en = [cb computeCommandEncoder];
        [en setComputePipelineState:pv];
        [en setBytes:&A length:sizeof A atIndex:0];
        for (int i = 0; i < 3; i++)
            [en setBuffer:t[i].b offset:0 atIndex:1 + i];
        [en setBuffer:a.b offset:0 atIndex:4];
        const int lk = frames % LK == 0 ? LK : 1;
        [en dispatchThreadgroups:MTLSizeMake(frames / lk, groups / LG, 1) threadsPerThreadgroup:MTLSizeMake(lk, LG, 1)];
        [en endEncoding];
        return cb;
    }

    // the work-groups' rows added up in order (numpy's res.sum(1)), as gpu.cpp
    static void sum_rows(const float *res, int NG, int frames, float *out)
    {
        for (int c = 0; c < 4; c++)
            for (int j = 0; j < frames; j++) {
                const float *r = res + (size_t)c * NG * frames + j;
                float v = r[0];
                for (int g = 1; g < NG; g++)
                    v += r[(size_t)g * frames];
                out[c * frames + j] = v;
            }
    }

    int samples(const void *D, size_t dn, const void *C, size_t cn, const void *S, size_t sn, int nd, long long n0,
                int frames, int send, int mg, float *out)
    {
        @autoreleasepool {
            if (!put(tab[0], D, dn) || !put(tab[1], C, cn) || !put(tab[2], S, sn))
                return -1;
            int NG = 0;
            id<MTLCommandBuffer> cb = encode(tab, acc, nd, n0, frames, send, mg, NG);
            if (!cb)
                return -1;
            [cb commit];
            [cb waitUntilCompleted];
            if (cb.status != MTLCommandBufferStatusCompleted)
                return -1;
            sum_rows((const float *)[acc.b contents], NG, frames, out);
            return 0;
        }
    }

    int launch(int s, const void *D, size_t dn, const void *C, size_t cn, const void *S, size_t sn, int nd,
               long long n0, int frames, int send, int mg)
    {
        @autoreleasepool {
            Slot &st = slot[s];
            if (st.cb)
                [st.cb waitUntilCompleted];         // (its last still running: its tables are about to change)
            st.cb = nil;
            if (!put(st.tab[0], D, dn) || !put(st.tab[1], C, cn) || !put(st.tab[2], S, sn))
                return -1;
            id<MTLCommandBuffer> cb = encode(st.tab, st.acc, nd, n0, frames, send, mg, st.NG);
            if (!cb)
                return -1;
            st.t_commit = now_s();
            [cb commit];                            // started now, collect waits
            st.cb = cb;
            st.frames = frames;
            return 0;
        }
    }

    int collect(int s, float *out)
    {
        Slot &st = slot[s];
        if (!st.cb)
            return -1;
        [st.cb waitUntilCompleted];
        const bool ok = st.cb.status == MTLCommandBufferStatusCompleted;
        if (trace && ok) {
            // (GPUStartTime/GPUEndTime: the host's mach clock in seconds, as
            // CACurrentMediaTime; kernelStart is the CPU's commit, in the same)
            const double back = now_s(), gs = st.cb.GPUStartTime, ge = st.cb.GPUEndTime;
            const double ks = st.cb.kernelStartTime;
            t_sched.push_back(gs - ks);
            t_run.push_back(ge - gs);
            t_total.push_back(back - st.t_commit);
            t_wake.push_back((back - st.t_commit) - (ge - ks));
        }
        st.cb = nil;
        if (!ok)
            return -1;
        sum_rows((const float *)[st.acc.b contents], st.NG, st.frames, out);
        return 0;
    }

    int win(const void *G, size_t gn, const void *D, size_t dn, const void *C, size_t cn, const void *S, size_t sn,
            int ng, int frames, int mg, long long n0, int send, float *res)
    {
        @autoreleasepool {
            const void *p[4] = {G, D, C, S};
            size_t n[4] = {gn, dn, cn, sn};
            for (int i = 0; i < 4; i++)
                if (!put(wtab[i], p[i], n[i]))
                    return -1;
            const int nwg = ng / LG;
            const size_t need = (size_t)4 * nwg * frames;
            if (!grow(wacc, need * sizeof(float)))
                return -1;
            VArgs A{0, 0, frames, mg, (unsigned long long)n0, send, 0};
            id<MTLCommandBuffer> cb = [q commandBuffer];
            id<MTLComputeCommandEncoder> en = [cb computeCommandEncoder];
            [en setComputePipelineState:pw];
            [en setBytes:&A length:sizeof A atIndex:0];
            for (int i = 0; i < 4; i++)
                [en setBuffer:wtab[i].b offset:0 atIndex:1 + i];
            [en setBuffer:wacc.b offset:0 atIndex:5];
            [en dispatchThreadgroups:MTLSizeMake(frames / LK, ng / LG, 1) threadsPerThreadgroup:MTLSizeMake(LK, LG, 1)];
            [en endEncoding];
            [cb commit];
            [cb waitUntilCompleted];
            if (cb.status != MTLCommandBufferStatusCompleted)
                return -1;
            memcpy(res, [wacc.b contents], need * sizeof(float));
            return 0;
        }
    }
};

}  // namespace

extern "C" {

void *nv_mtl_new(const char *dir, const int *sizes, char *err, int errlen)
{
    MetalGpu *g = new MetalGpu();
    std::string e;
    if (!g->open(dir, sizes, e)) {
        if (err && errlen > 0)
            snprintf(err, errlen, "%s", e.c_str());
        delete g;
        return nullptr;
    }
    return g;
}

int nv_mtl_samples(void *h, const void *D, long dn, const void *C, long cn, const void *S, long sn, int nd,
                   long long n0, int frames, int send, int mg, float *out)
{
    return ((MetalGpu *)h)->samples(D, (size_t)dn, C, (size_t)cn, S, (size_t)sn, nd, n0, frames, send, mg, out);
}

int nv_mtl_launch(void *h, int slot, const void *D, long dn, const void *C, long cn, const void *S, long sn, int nd,
                  long long n0, int frames, int send, int mg)
{
    return ((MetalGpu *)h)->launch(slot, D, (size_t)dn, C, (size_t)cn, S, (size_t)sn, nd, n0, frames, send, mg);
}

int nv_mtl_collect(void *h, int slot, float *out) { return ((MetalGpu *)h)->collect(slot, out); }

void nv_mtl_free(void *h) { delete (MetalGpu *)h; }

int nv_mtl_win(void *h, const void *G, long gn, const void *D, long dn, const void *C, long cn, const void *S, long sn,
               int ng, int frames, int mg, long long n0, int send, float *res)
{
    return ((MetalGpu *)h)->win(G, (size_t)gn, D, (size_t)dn, C, (size_t)cn, S, (size_t)sn, ng, frames, mg, n0, send,
                                res);
}

}  // extern "C"
