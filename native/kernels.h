// kernels.h -- THE VOICE KERNELS, LINKED IN (iOS loads no code of its own at
// run time): every build of synthkernel.c that blockrender makes as a
// library (libsynth*_<rate>.so: a variant at a rate) and live's convolver
// (libconvolver.so) are compiled into libnative too, their names prefixed
// (kprefix.h), and found here by the library's name. An export records the
// libraries' paths; klib_open takes the name off the path and hands back the
// built-in copy -- the same source under the same flags, so the same bits --
// whether or not the file is there.
//
// A library not built in (a rate other than 44.1 and 48 kHz) is dlopened
// from its path as before, except on iOS. NV_KERNEL_DLOPEN=1: every one
// dlopened (Python's own builds; an A/B of the two).
#ifndef NV_KERNELS_H
#define NV_KERNELS_H

#include <string>

namespace nv {

// the library at path: its built-in copy, else (not iOS) dlopened; NULL if neither
void *klib_open(const std::string &path);
// a function of an opened library; NULL if it has none
void *klib_sym(void *lib, const char *name);
// a library's other function, found beside one of its functions (the GPU
// builds' voice_team_set, beside their voice_block); NULL if none
void *klib_beside(void *fn, const char *name);

}  // namespace nv

#include <mutex>
#include <vector>

// THE SPECTRA-TONE's TABLE into a cone kernel's library h (synthkernel.c
// cone_table_set; blockrender.ensure_cone_lib's): spec native.spectra_constants'
// -- [0] bins, [1] angles, [4..5] the cones' radii, [6] c, then CA and CK.
// The table is the build's, one for every export: copied to float32 once for
// the process and set on each library it is asked for. false: h has no
// cone_table_set, or spec is short
inline bool nv_cone_table(void *h, const std::vector<double> &spec)
{
    typedef void (*Set)(const float *, const float *, int, int, float, float, float);
    Set set = h ? (Set)nv::klib_sym(h, "cone_table_set") : nullptr;
    if (!set || spec.size() < 11)
        return false;
    const size_t nb = (size_t)spec[0], na = (size_t)spec[1], nca = nb * na * 2, nck = 2 * nb * 2;
    if (spec.size() < 11 + nca + nck)
        return false;
    static std::mutex mu;
    static std::vector<float> CA, CK;
    std::lock_guard<std::mutex> lk(mu);
    if (CA.empty()) {
        CA.assign(spec.begin() + 11, spec.begin() + 11 + (long)nca);
        CK.assign(spec.begin() + 11 + (long)nca, spec.begin() + 11 + (long)(nca + nck));
    }
    set(CA.data(), CK.data(), (int)nb, (int)na, (float)spec[4], (float)spec[5], (float)spec[6]);
    return true;
}

#endif
