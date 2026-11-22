// kernels.cpp -- the table of the built-in kernels (kernels.h). Each variant
// is a blockrender build (its -D flags in native.py's KVARIANTS) with the
// functions it defines; each is compiled at every rate in native.py's KRATES.
// A function added to the kernel goes in kprefix.h and in its variants here
// (a name missing here is not found; one listed but not built fails the link).
#include "kernels.h"

#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>

#if defined(__APPLE__)
#include <TargetConditionals.h>
#endif
#if !(defined(__APPLE__) && TARGET_OS_IPHONE)
#define NVK_DLOPEN 1
#include <dlfcn.h>
#endif

namespace {

struct KSym {
    const char *name;
    void *fn;
};
struct KLib {
    const char *name;                       // the library's name: "synthdamp_48000" (libsynthdamp_48000.so)
    const KSym *syms;
    int n;
    void *dl;                               // (a dlopened one's handle; the built-in: none)
};

}  // namespace

// every variant's functions: X(tag, name) for each
#define NVK_BASE(X, T) X(T, synth_voice) X(T, synth_organ) X(T, moog_coeff_rows) X(T, moog_pitch_cells) X(T, moog_shape_rows)
#define NVK_GPU(X, T) X(T, voice_block) X(T, voice_pack) X(T, voice_samples) X(T, voice_sizes) X(T, voice_team_set)
#define NVK_V_synth(X, T) NVK_BASE(X, T)
#define NVK_V_synthxdec(X, T) NVK_BASE(X, T) X(T, synth_voice_xdec)
#define NVK_V_synthdamp(X, T) NVK_BASE(X, T) X(T, synth_voice_damp)
#define NVK_V_synthmoogx(X, T) NVK_BASE(X, T) X(T, synth_voice_damp) X(T, synth_voice_moogx)
#define NVK_V_synthlobe(X, T) NVK_BASE(X, T) X(T, synth_voice_lobe)
#define NVK_V_synthcone(X, T) NVK_BASE(X, T) X(T, synth_voice_lobe) X(T, cone_table_set) X(T, synth_voice_cone_damp)
#define NVK_V_synthgpu(X, T) NVK_BASE(X, T) NVK_GPU(X, T) X(T, cone_table_set)
#define NVK_V_synthgpudamp(X, T) NVK_BASE(X, T) NVK_GPU(X, T) X(T, synth_voice_damp) X(T, voice_damp_set) X(T, cone_table_set)
#define NVK_V_synthgpumoogx(X, T) NVK_BASE(X, T) NVK_GPU(X, T) X(T, synth_voice_damp) X(T, voice_damp_set) \
    X(T, synth_voice_moogx) X(T, voice_moogx_set) X(T, cone_table_set)
#define NVK_V_convolver(X, T) X(T, conv_new) X(T, conv_process) X(T, conv_reset) X(T, conv_free)

#define NVK_VARIANTS(V, R) V(synth, R) V(synthxdec, R) V(synthdamp, R) V(synthmoogx, R) V(synthlobe, R) V(synthcone, R) \
    V(synthgpu, R) V(synthgpudamp, R) V(synthgpumoogx, R)

// the prefixed functions (their types are the callers' casts: an address is all this needs)
#define NVK_DECL(T, s) extern "C" void nvk_##T##_##s(void);
#define NVK_DECL_V(v, R) NVK_V_##v(NVK_DECL, v##_##R)
NVK_VARIANTS(NVK_DECL_V, 44100)
NVK_VARIANTS(NVK_DECL_V, 48000)
NVK_V_convolver(NVK_DECL, convolver)

#define NVK_ENT(T, s) {#s, (void *)&nvk_##T##_##s},
#define NVK_SYMS_V(v, R) static const KSym nvk_syms_##v##_##R[] = {NVK_V_##v(NVK_ENT, v##_##R)};
NVK_VARIANTS(NVK_SYMS_V, 44100)
NVK_VARIANTS(NVK_SYMS_V, 48000)
static const KSym nvk_syms_convolver[] = {NVK_V_convolver(NVK_ENT, convolver)};

#define NVK_LIB_V(v, R) {#v "_" #R, nvk_syms_##v##_##R, (int)(sizeof nvk_syms_##v##_##R / sizeof(KSym)), nullptr},
static KLib nvk_libs[] = {
    NVK_VARIANTS(NVK_LIB_V, 44100)
    NVK_VARIANTS(NVK_LIB_V, 48000)
    {"convolver", nvk_syms_convolver, (int)(sizeof nvk_syms_convolver / sizeof(KSym)), nullptr},
};

namespace nv {

// the library's name off its path: /x/libsynthdamp_48000.so -> synthdamp_48000
static std::string lib_name(const std::string &path)
{
    std::string b = path.substr(path.rfind('/') + 1);
    if (b.compare(0, 3, "lib") == 0)
        b = b.substr(3);
    size_t dot = b.find('.');
    return dot == std::string::npos ? b : b.substr(0, dot);
}

void *klib_open(const std::string &path)
{
    if (path.empty())
        return nullptr;
    static const bool force = [] {
        const char *e = getenv("NV_KERNEL_DLOPEN");
        return e && *e && strcmp(e, "0");
    }();
    if (!force) {
        const std::string nm = lib_name(path);
        for (KLib &l : nvk_libs)
            if (nm == l.name)
                return &l;
    }
#ifdef NVK_DLOPEN
    static std::mutex mu;
    static std::map<std::string, KLib *> opened;     // (one handle a path, kept for the process)
    std::lock_guard<std::mutex> lk(mu);
    auto it = opened.find(path);
    if (it != opened.end())
        return it->second;
    void *h = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!h)
        return nullptr;
    KLib *l = new KLib{nullptr, nullptr, 0, h};
    opened[path] = l;
    return l;
#else
    return nullptr;
#endif
}

void *klib_sym(void *lib, const char *name)
{
    const KLib *l = (const KLib *)lib;
    if (!l || !name)
        return nullptr;
#ifdef NVK_DLOPEN
    if (l->dl)
        return dlsym(l->dl, name);
#endif
    for (int i = 0; i < l->n; i++)
        if (!strcmp(l->syms[i].name, name))
            return l->syms[i].fn;
    return nullptr;
}

void *klib_beside(void *fn, const char *name)
{
    if (!fn)
        return nullptr;
    for (KLib &l : nvk_libs)
        for (int i = 0; i < l.n; i++)
            if (l.syms[i].fn == fn)
                return klib_sym(&l, name);
#ifdef NVK_DLOPEN
    Dl_info i;
    if (!dladdr(fn, &i) || !i.dli_fname)
        return nullptr;
    void *h = dlopen(i.dli_fname, RTLD_NOW | RTLD_NOLOAD);
    if (!h)
        return nullptr;
    void *s = dlsym(h, name);
    dlclose(h);
    return s;
#else
    return nullptr;
#endif
}

}  // namespace nv
