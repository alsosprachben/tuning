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

#endif
