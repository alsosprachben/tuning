/* live.h -- the native engine's live types, shared by live.cpp (the template
 * cache) and slab.cpp (the slab and the piano's events). */
#ifndef NV_LIVE_H
#define NV_LIVE_H

#include <cstdint>
#include <vector>

namespace nv {
namespace live {

// a key's template as live's slab stamps it (live._raw_template's piano
// fields): its columns in live's groups (F8 om p0 p0R fmw fmp fmpR; F4 the
// 27; F4_NOTE gb gt gc vdl; I8 non noff; I4 gr cr br pl fx mk), hrel, fa_at
struct Template {
    long P = 0;
    std::vector<double> f8[6];
    std::vector<float> f4[27], f4n[4], hrel;
    std::vector<long long> i8[2];
    std::vector<int32_t> i4[6];
    std::vector<char> fa_at;
    long long dur = 0;
    int vel = 0;
};

}  // namespace live
}  // namespace nv

extern "C" const nv::live::Template *nv_tcache_lookup(void *cache, int note, int bucket, int speed);

// synthkernel.c's synth_voice (and synth_voice_xdec: the same arguments)
extern "C" typedef void (*nv_voice_fn)(
    float *outL, float *outR, long n0, long winlen, int BLK, int nblk, int P,
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
    float sfloor, float spow, float shmax, float shref, long CHUNK,
    const float *sendW, float *outSL, float *outSR);

// ...and synth_voice_damp (-DDAMP_KERNEL): those, then the rows' damper tracks
extern "C" typedef void (*nv_damp_fn)(
    float *outL, float *outR, long n0, long winlen, int BLK, int nblk, int P,
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
    float sfloor, float spow, float shmax, float shref, long CHUNK,
    const float *sendW, float *outSL, float *outSR,
    const int *dk, const float *dg, const float *DM, const long *DMO, const long *DMB, const long *DMN);

#endif
