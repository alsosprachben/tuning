// relocate.h -- where the engine's own files are: an export records the
// absolute paths of the kernel libraries and of the GPU kernel's sources as
// they were where it was made (the repo); an app carries its own copies. A
// recorded file is taken from beside libnative itself when a file of that
// name is there (the app's Frameworks), the kernel sources from beside it or
// its ../Resources (the app's) -- so a bundle never loads the repo's -- else
// as recorded. In the repo libnative sits beside them all: nothing moves.
#ifndef NV_RELOCATE_H
#define NV_RELOCATE_H

#include <string>
#include <sys/stat.h>

extern "C" const char *nv_native_dir(void);     // (libnative's directory: hostsession.cpp)

inline bool nv_file_is(const std::string &p)
{
    struct stat st;
    return !p.empty() && stat(p.c_str(), &st) == 0;
}

// a library recorded at `path`: beside libnative, if one of its name is there
inline std::string nv_reloc_lib(const std::string &path)
{
    const char *d = nv_native_dir();
    if (!d || !*d || path.empty())
        return path;
    const std::string here = std::string(d) + "/" + path.substr(path.rfind('/') + 1);
    return nv_file_is(here) ? here : path;
}

// the GPU kernel's sources (gpukernel.cl, gpukernel.metal, voicedesc.h),
// recorded in `dir`: beside libnative, else its ../Resources, else as recorded
inline std::string nv_reloc_kernels(const std::string &dir)
{
    const char *d = nv_native_dir();
    if (d && *d) {
        const std::string a = d, b = std::string(d) + "/../Resources";
        for (const std::string &c : {a, b})
            if (nv_file_is(c + "/voicedesc.h") && (nv_file_is(c + "/gpukernel.metal") || nv_file_is(c + "/gpukernel.cl")))
                return c;
    }
    return dir;
}

#endif
