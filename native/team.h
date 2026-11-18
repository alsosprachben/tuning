// team.h -- THE ENGINE's OWN THREADS, in OpenMP's place (iOS ships no
// OpenMP; the kernels' pragmas are Python's alone). A Team is n members: the
// caller, and n-1 workers that wait for its run(). run(f) calls f(member) on
// every member and returns when all have; the work inside f is TAKEN, by a
// shared count, never dealt -- so a member that starts late (or a run that
// finds the team busy and goes alone) still leaves nothing undone, and the
// result is the same however many members took part.
//
// Workers spin for spin_ns after a job before sleeping on a semaphore, as
// libgomp's do, so a team woken every audio block wakes at once. A team made
// on the audio thread inherits its priority (as libgomp's did); rt set, each
// worker also joins the audio device's workgroup (rtjoin.h: macOS, iOS).
#ifndef NV_TEAM_H
#define NV_TEAM_H

#include <atomic>
#include <chrono>
#include <dlfcn.h>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

#include "rtjoin.h"
#include "rtsem.h"

#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>
#define NV_TEAM_RELAX() _mm_pause()
#elif defined(__aarch64__)
#define NV_TEAM_RELAX() __asm__ __volatile__("yield")
#else
#define NV_TEAM_RELAX() do { } while (0)
#endif

namespace nv {

class Team {
    struct alignas(64) Worker {
        RtSem sem;
        std::atomic<bool> sleeping{false};
        std::thread th;
    };
    int n_;
    long long spin_ns_;
    bool rt_;
    std::vector<std::unique_ptr<Worker>> w_;
    alignas(64) std::atomic<unsigned> gen_{0};
    alignas(64) std::atomic<int> left_{0};
    void (*fn_)(void *, int) = nullptr;
    void *ctx_ = nullptr;
    bool quit_ = false;
    std::mutex busy_;

    static long long now_ns()
    {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
                   std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    void work(int k)
    {
        Worker &me = *w_[k];
        unsigned seen = 0;
        for (;;) {
            unsigned g;
            long long t0 = now_ns();
            while ((g = gen_.load(std::memory_order_acquire)) == seen) {
                if (now_ns() - t0 < spin_ns_) {
                    NV_TEAM_RELAX();
                    continue;
                }
                me.sleeping.store(true);                // (seq_cst: run's gen_, then sleeping;
                if (gen_.load() == seen)                //  here sleeping, then gen_ -- one sees the other)
                    me.sem.wait();
                me.sleeping.store(false, std::memory_order_relaxed);
                t0 = now_ns();
            }
            seen = g;
            if (quit_)
                return;
            if (rt_)
                NV_RT_HELPER();
            fn_(ctx_, k + 1);
            left_.fetch_sub(1, std::memory_order_release);
        }
    }

public:
    explicit Team(int n, long long spin_ns = 0, bool rt = false) : n_(n < 1 ? 1 : n), spin_ns_(spin_ns), rt_(rt)
    {
        for (int k = 0; k < n_ - 1; k++)
            w_.emplace_back(new Worker);
        for (int k = 0; k < n_ - 1; k++)
            w_[k]->th = std::thread([this, k] { work(k); });
    }
    ~Team()
    {
        quit_ = true;
        gen_.fetch_add(1);
        for (auto &w : w_)
            w->sem.signal();
        for (auto &w : w_)
            w->th.join();
    }
    Team(const Team &) = delete;
    Team &operator=(const Team &) = delete;
    int size() const { return n_; }

    template <class F> void run(F &&f)
    {
        std::unique_lock<std::mutex> lk(busy_, std::try_to_lock);
        if (n_ <= 1 || !lk.owns_lock()) {
            f(0);                                       // (alone: the work is taken, so it all gets done)
            return;
        }
        using Fn = typename std::remove_reference<F>::type;
        fn_ = [](void *c, int t) { (*(Fn *)c)(t); };
        ctx_ = (void *)&f;
        left_.store(n_ - 1, std::memory_order_relaxed);
        gen_.fetch_add(1);
        for (auto &w : w_)
            if (w->sleeping.load())
                w->sem.signal();
        f(0);
        while (left_.load(std::memory_order_acquire) > 0)
            NV_TEAM_RELAX();
    }
};

// THE FILE RENDERS' TEAM: every core, made on first use, kept for the process
inline Team &file_team()
{
    static Team t((int)(std::thread::hardware_concurrency() ? std::thread::hardware_concurrency() : 4));
    return t;
}

// a kernel library's other function, found beside one of its functions (the
// GPU builds' voice_team_set, beside their voice_block); NULL if none
inline void *sym_beside(void *fn, const char *name)
{
    Dl_info i;
    if (!fn || !dladdr(fn, &i) || !i.dli_fname)
        return nullptr;
    void *h = dlopen(i.dli_fname, RTLD_NOW | RTLD_NOLOAD);
    if (!h)
        return nullptr;
    void *s = dlsym(h, name);
    dlclose(h);
    return s;
}

// VOICE_BLOCK ON A TEAM (synthkernel.c's voice_team_set): call(nthr) is the
// voice_block call; with the library's set function, every member runs it
// with the team's shared counts and counts[0..1] are set from them after;
// without one (an older build), the one call with nthr OpenMP threads.
template <class Call> int vblock_team(Team *team, void *set_fn, int nthr, int *counts, Call &&call)
{
    if (!set_fn || !team)
        return call(nthr);
    auto set = (void (*)(int *, long *))set_fn;
    int sh[3] = {0, 0, 0};
    long next = 0;
    team->run([&](int) {
        set(sh, &next);
        call(1);
        set(nullptr, nullptr);
    });
    counts[0] = sh[0];
    counts[1] = sh[1];
    return sh[2] ? -1 : 0;
}

}  // namespace nv

#endif
