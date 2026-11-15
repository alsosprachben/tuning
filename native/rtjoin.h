// rtjoin.h -- a helper thread in the audio's workgroup (macOS, iOS).
//
// Apple's way for an audio app's helper threads (since macOS 11 / iOS 14):
// each joins the output device's AUDIO WORKGROUP (os_workgroup), so the
// scheduler wakes it promptly on a fast core and the performance controller
// counts its work with the audio thread's. A helper the audio thread waits
// on -- the room's body, the GPU setup's team -- woke slowly from sleep at
// ordinary priority with the Mac busy: a click every few seconds (the M3).
//
// The host is handed the device's workgroup (nv_host_join_output_workgroup:
// CoreAudio's kAudioOutputUnitProperty_OSWorkgroup); each helper calls
// sync() at the top of its loop and joins it -- again when it changes (the
// output device changed). Elsewhere these are nothing.
#ifndef NV_RTJOIN_H
#define NV_RTJOIN_H

#include <atomic>

#ifdef __APPLE__
#include <os/workgroup.h>
namespace nv {
namespace rtj {
inline std::atomic<void *> g_wg{nullptr};
inline std::atomic<unsigned> g_gen{0};

// the device's workgroup (retained by the caller; an old one is not
// released: a helper may still be leaving it)
inline void set(void *wg)
{
    g_wg.store(wg);
    g_gen.fetch_add(1);
}

struct Member {
    os_workgroup_t joined = nullptr;
    unsigned gen = ~0u;
    os_workgroup_join_token_s tok;
    void sync()
    {
        const unsigned g = g_gen.load(std::memory_order_acquire);
        if (g == gen)
            return;
        gen = g;
        if (joined) {
            os_workgroup_leave(joined, &tok);
            joined = nullptr;
        }
        os_workgroup_t w = (os_workgroup_t)g_wg.load();
        if (w && os_workgroup_join(w, &tok) == 0)
            joined = w;
    }
    ~Member()
    {
        if (joined)
            os_workgroup_leave(joined, &tok);
    }
};
}  // namespace rtj
}  // namespace nv
#define NV_RT_HELPER() do { static thread_local nv::rtj::Member nv_wgm_; nv_wgm_.sync(); } while (0)
#else
namespace nv {
namespace rtj {
inline std::atomic<void *> g_wg{nullptr};
inline std::atomic<unsigned> g_gen{0};
inline void set(void *) {}
}  // namespace rtj
}  // namespace nv
#define NV_RT_HELPER() do { } while (0)
#endif

#endif
