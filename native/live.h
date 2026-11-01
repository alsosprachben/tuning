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

#endif
