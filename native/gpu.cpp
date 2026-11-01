// gpu.cpp -- the GPU's sample pass for a live block (gpurender.Gpu.samples):
// voice_block's descriptors (the block's setup, on the CPU) through
// gpukernel.cl's `voices` on an OpenCL GPU, and the work-groups' sums added
// up on the host as numpy's res.sum(1) does. OpenCL is loaded at run time
// (libOpenCL.so.1), so nothing needs its headers and a machine without it
// still runs the rest: nv_cl_new says why it could not.
//
// The tables are not copied: a buffer over page-aligned host memory
// (CL_MEM_USE_HOST_PTR) is read where voice_block wrote it, as gpurender's
// are, and made again only when a table moves or grows.

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <dlfcn.h>
#include <string>
#include <vector>

namespace nv {
namespace gpu {

// OpenCL 1.2's types and the few constants used, as cl.h declares them
typedef int32_t cl_int;
typedef uint32_t cl_uint;
typedef uint64_t cl_ulong;
typedef cl_ulong cl_bitfield;
typedef cl_bitfield cl_device_type, cl_mem_flags, cl_command_queue_properties;
typedef intptr_t cl_context_properties;
typedef cl_uint cl_program_build_info;
typedef struct _cl_platform_id *cl_platform_id;
typedef struct _cl_device_id *cl_device_id;
typedef struct _cl_context *cl_context;
typedef struct _cl_command_queue *cl_command_queue;
typedef struct _cl_mem *cl_mem;
typedef struct _cl_program *cl_program;
typedef struct _cl_kernel *cl_kernel;
typedef struct _cl_event *cl_event;

static const cl_device_type CL_DEVICE_TYPE_GPU = 1 << 2;
static const cl_mem_flags CL_MEM_WRITE_ONLY = 1 << 1, CL_MEM_READ_ONLY = 1 << 2, CL_MEM_USE_HOST_PTR = 1 << 3;
static const cl_program_build_info CL_PROGRAM_BUILD_LOG = 0x1183;
static const cl_uint CL_TRUE = 1;

struct Api {
    void *h = nullptr;
    cl_int (*GetPlatformIDs)(cl_uint, cl_platform_id *, cl_uint *);
    cl_int (*GetDeviceIDs)(cl_platform_id, cl_device_type, cl_uint, cl_device_id *, cl_uint *);
    cl_context (*CreateContext)(const cl_context_properties *, cl_uint, const cl_device_id *, void *, void *,
                                cl_int *);
    cl_command_queue (*CreateCommandQueue)(cl_context, cl_device_id, cl_command_queue_properties, cl_int *);
    cl_program (*CreateProgramWithSource)(cl_context, cl_uint, const char **, const size_t *, cl_int *);
    cl_int (*BuildProgram)(cl_program, cl_uint, const cl_device_id *, const char *, void *, void *);
    cl_int (*GetProgramBuildInfo)(cl_program, cl_device_id, cl_program_build_info, size_t, void *, size_t *);
    cl_kernel (*CreateKernel)(cl_program, const char *, cl_int *);
    cl_mem (*CreateBuffer)(cl_context, cl_mem_flags, size_t, void *, cl_int *);
    cl_int (*SetKernelArg)(cl_kernel, cl_uint, size_t, const void *);
    cl_int (*EnqueueNDRangeKernel)(cl_command_queue, cl_kernel, cl_uint, const size_t *, const size_t *,
                                   const size_t *, cl_uint, const cl_event *, cl_event *);
    cl_int (*EnqueueReadBuffer)(cl_command_queue, cl_mem, cl_uint, size_t, size_t, void *, cl_uint,
                                const cl_event *, cl_event *);
    cl_int (*ReleaseMemObject)(cl_mem);
    cl_int (*ReleaseKernel)(cl_kernel);
    cl_int (*ReleaseProgram)(cl_program);
    cl_int (*ReleaseCommandQueue)(cl_command_queue);
    cl_int (*ReleaseContext)(cl_context);

    bool load()
    {
        h = dlopen("libOpenCL.so.1", RTLD_NOW | RTLD_LOCAL);
        if (!h)
            h = dlopen("libOpenCL.so", RTLD_NOW | RTLD_LOCAL);
        if (!h)
            return false;
        bool ok = true;
#define SYM(n)                                                    \
    do {                                                          \
        *(void **)&n = dlsym(h, "cl" #n);                         \
        ok = ok && n != nullptr;                                  \
    } while (0)
        SYM(GetPlatformIDs); SYM(GetDeviceIDs); SYM(CreateContext); SYM(CreateCommandQueue);
        SYM(CreateProgramWithSource); SYM(BuildProgram); SYM(GetProgramBuildInfo); SYM(CreateKernel);
        SYM(CreateBuffer); SYM(SetKernelArg); SYM(EnqueueNDRangeKernel); SYM(EnqueueReadBuffer);
        SYM(ReleaseMemObject); SYM(ReleaseKernel); SYM(ReleaseProgram); SYM(ReleaseCommandQueue);
        SYM(ReleaseContext);
#undef SYM
        return ok;
    }
};

struct Held {                   // a buffer over a host table: made again when the table moves or grows
    const void *p = nullptr;
    size_t n = 0;
    cl_mem m = nullptr;
};

struct Gpu {
    static const int LK = 16, LG = 8;       // gpurender.Gpu's work-group: 16 samples by 8 groups
    Api cl;
    cl_device_id dev = nullptr;
    cl_context ctx = nullptr;
    cl_command_queue q = nullptr;
    cl_program prg = nullptr;
    cl_kernel k = nullptr;
    Held tab[3];
    cl_mem acc = nullptr;
    size_t acc_cap = 0;                     // floats
    std::vector<float> res;
    std::string name;

    ~Gpu()
    {
        for (Held &t : tab)
            if (t.m)
                cl.ReleaseMemObject(t.m);
        if (acc)
            cl.ReleaseMemObject(acc);
        if (k)
            cl.ReleaseKernel(k);
        if (prg)
            cl.ReleaseProgram(prg);
        if (q)
            cl.ReleaseCommandQueue(q);
        if (ctx)
            cl.ReleaseContext(ctx);
    }

    // the first GPU of the first platform that has one (pyopencl's
    // get_platforms() order), its context, queue and gpukernel.cl built with
    // -I DIR; the compiler's layout of voicedesc.h checked against `sizes`
    bool open(const char *dir, const int *sizes, std::string &err)
    {
        if (!cl.load()) {
            err = "no OpenCL (libOpenCL.so.1)";
            return false;
        }
        cl_uint np = 0;
        if (cl.GetPlatformIDs(0, nullptr, &np) != 0 || !np) {
            err = "no OpenCL platform";
            return false;
        }
        std::vector<cl_platform_id> ps(np);
        cl.GetPlatformIDs(np, ps.data(), nullptr);
        for (cl_platform_id p : ps) {
            cl_uint nd = 0;
            if (cl.GetDeviceIDs(p, CL_DEVICE_TYPE_GPU, 1, &dev, &nd) == 0 && nd)
                break;
            dev = nullptr;
        }
        if (!dev) {
            err = "no OpenCL GPU (is intel-opencl-icd installed?)";
            return false;
        }
        cl_int e = 0;
        ctx = cl.CreateContext(nullptr, 1, &dev, nullptr, nullptr, &e);
        if (e == 0)
            q = cl.CreateCommandQueue(ctx, dev, 0, &e);
        if (e != 0) {
            err = "OpenCL context: " + std::to_string(e);
            return false;
        }
        std::string path = std::string(dir) + "/gpukernel.cl";
        FILE *f = fopen(path.c_str(), "rb");
        if (!f) {
            err = "cannot read " + path;
            return false;
        }
        std::string src;
        char buf[4096];
        for (size_t n; (n = fread(buf, 1, sizeof buf, f)) > 0;)
            src.append(buf, n);
        fclose(f);
        const char *s = src.c_str();
        size_t sl = src.size();
        prg = cl.CreateProgramWithSource(ctx, 1, &s, &sl, &e);
        std::string opts = std::string("-I ") + dir;
        if (e == 0 && cl.BuildProgram(prg, 1, &dev, opts.c_str(), nullptr, nullptr) != 0) {
            size_t ln = 0;
            cl.GetProgramBuildInfo(prg, dev, CL_PROGRAM_BUILD_LOG, 0, nullptr, &ln);
            std::string log(ln, '\0');
            cl.GetProgramBuildInfo(prg, dev, CL_PROGRAM_BUILD_LOG, ln, &log[0], nullptr);
            err = "gpukernel.cl: " + log;
            return false;
        }
        // the layout, as this compiler sees voicedesc.h
        cl_kernel ks = cl.CreateKernel(prg, "sizes", &e);
        cl_mem b = e == 0 ? cl.CreateBuffer(ctx, CL_MEM_WRITE_ONLY, 3 * sizeof(int), nullptr, &e) : nullptr;
        int got[3] = {0, 0, 0};
        if (e == 0) {
            size_t one = 1;
            cl.SetKernelArg(ks, 0, sizeof(cl_mem), &b);
            e = cl.EnqueueNDRangeKernel(q, ks, 1, nullptr, &one, nullptr, 0, nullptr, nullptr);
            if (e == 0)
                e = cl.EnqueueReadBuffer(q, b, CL_TRUE, 0, sizeof got, got, 0, nullptr, nullptr);
        }
        if (b)
            cl.ReleaseMemObject(b);
        if (ks)
            cl.ReleaseKernel(ks);
        if (e != 0 || memcmp(got, sizes, sizeof got)) {
            char m[160];
            snprintf(m, sizeof m, "the GPU compiler lays voicedesc.h out as (%d, %d, %d), the host as (%d, %d, %d)",
                     got[0], got[1], got[2], sizes[0], sizes[1], sizes[2]);
            err = m;
            return false;
        }
        k = cl.CreateKernel(prg, "voices", &e);
        if (e != 0) {
            err = "no kernel `voices`";
            return false;
        }
        cl.SetKernelArg(k, 10, 4 * LG * LK * sizeof(float), nullptr);     // local: the work-group's sums
        return true;
    }

    bool over(int i, const void *p, size_t n)
    {
        Held &t = tab[i];
        if (t.m && t.p == p && t.n == n)
            return true;
        if (t.m)
            cl.ReleaseMemObject(t.m);
        cl_int e = 0;
        t.m = cl.CreateBuffer(ctx, CL_MEM_READ_ONLY | CL_MEM_USE_HOST_PTR, n, const_cast<void *>(p), &e);
        t.p = p;
        t.n = n;
        if (e != 0) {
            t.m = nullptr;
            return false;
        }
        return cl.SetKernelArg(k, 6 + i, sizeof(cl_mem), &t.m) == 0;
    }

    // Gpu.samples: (L, R, SL, SR) into out[4 * frames], each the sum over the
    // work-groups' rows in order (numpy's res.sum(1): the first, then each
    // added) -- 0 on success
    int samples(const void *D, size_t dn, const void *C, size_t cn, const void *S, size_t sn, int nd,
                long long n0, int frames, int send, int mg, float *out)
    {
        if (!over(0, D, dn) || !over(1, C, cn) || !over(2, S, sn))
            return -1;
        int per = nd / 1024 + (nd % 1024 != 0);
        per = per > 2 ? per : 2;
        int groups = nd / per + (nd % per != 0);
        groups = groups > 1 ? groups : 1;
        groups = (groups / LG + (groups % LG != 0)) * LG;
        int NG = groups / LG;
        size_t need = (size_t)4 * NG * frames;
        if (acc_cap < need) {
            if (acc)
                cl.ReleaseMemObject(acc);
            acc_cap = need > 2 * acc_cap ? need : 2 * acc_cap;
            cl_int e = 0;
            acc = cl.CreateBuffer(ctx, CL_MEM_WRITE_ONLY, acc_cap * sizeof(float), nullptr, &e);
            if (e != 0) {
                acc = nullptr;
                acc_cap = 0;
                return -1;
            }
            res.resize(acc_cap);
        }
        cl_ulong u0 = (cl_ulong)n0;
        cl.SetKernelArg(k, 0, sizeof(int), &nd);
        cl.SetKernelArg(k, 1, sizeof(int), &per);
        cl.SetKernelArg(k, 2, sizeof(int), &frames);
        cl.SetKernelArg(k, 3, sizeof(int), &mg);
        cl.SetKernelArg(k, 4, sizeof(cl_ulong), &u0);
        cl.SetKernelArg(k, 5, sizeof(int), &send);
        cl.SetKernelArg(k, 9, sizeof(cl_mem), &acc);
        size_t gs[2] = {(size_t)frames, (size_t)groups}, ls[2] = {(size_t)(frames % LK == 0 ? LK : 1), (size_t)LG};
        if (cl.EnqueueNDRangeKernel(q, k, 2, nullptr, gs, ls, 0, nullptr, nullptr) != 0)
            return -1;
        if (cl.EnqueueReadBuffer(q, acc, CL_TRUE, 0, need * sizeof(float), res.data(), 0, nullptr, nullptr) != 0)
            return -1;
        for (int c = 0; c < 4; c++)
            for (int j = 0; j < frames; j++) {
                const float *r = res.data() + (size_t)c * NG * frames + j;
                float s = r[0];
                for (int g = 1; g < NG; g++)
                    s += r[(size_t)g * frames];
                out[c * frames + j] = s;
            }
        return 0;
    }
};

}  // namespace gpu
}  // namespace nv

extern "C" {

// The GPU (gpukernel.cl in DIR, voicedesc.h beside it) for descriptors of
// sizes[3] bytes (voice_sizes), or NULL and why in err
void *nv_cl_new(const char *dir, const int *sizes, char *err, int errlen)
{
    nv::gpu::Gpu *g = new nv::gpu::Gpu();
    std::string e;
    if (!g->open(dir, sizes, e)) {
        if (err && errlen > 0)
            snprintf(err, errlen, "%s", e.c_str());
        delete g;
        return nullptr;
    }
    return g;
}

int nv_cl_samples(void *h, const void *D, long dn, const void *C, long cn, const void *S, long sn, int nd,
                  long long n0, int frames, int send, int mg, float *out)
{
    return ((nv::gpu::Gpu *)h)->samples(D, (size_t)dn, C, (size_t)cn, S, (size_t)sn, nd, n0, frames, send, mg, out);
}

void nv_cl_free(void *h) { delete (nv::gpu::Gpu *)h; }

}  // extern "C"
