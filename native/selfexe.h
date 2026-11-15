// selfexe.h -- this program's own path: Linux's /proc/self/exe, macOS's
// _NSGetExecutablePath (no /proc there), resolved; "" if neither answers
#ifndef NV_SELFEXE_H
#define NV_SELFEXE_H

#include <climits>
#include <cstdlib>
#include <string>
#include <unistd.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

inline std::string nv_self_exe()
{
#ifdef __APPLE__
    char buf[4096];
    uint32_t n = sizeof buf;
    if (_NSGetExecutablePath(buf, &n) != 0)
        return "";
    char real[PATH_MAX];
    return realpath(buf, real) ? std::string(real) : std::string(buf);
#else
    char buf[4096];
    const ssize_t n = readlink("/proc/self/exe", buf, sizeof buf - 1);
    return n > 0 ? std::string(buf, (size_t)n) : std::string();
#endif
}

#endif
