// rtsem.h -- a counting semaphore with a deadline, for the audio thread to
// wait on a helper and give up in time (the rubato path, host.cpp): Mach's
// semaphore on macOS / iOS (what Core Audio's own threads use: no lock, no
// allocation, a wait that ends at its deadline), POSIX's elsewhere.
#ifndef NV_RTSEM_H
#define NV_RTSEM_H

#include <cerrno>
#include <ctime>

#ifdef __APPLE__
#include <mach/mach.h>
#include <mach/semaphore.h>
#include <mach/task.h>
#else
#include <semaphore.h>
#endif

namespace nv {

class RtSem {
#ifdef __APPLE__
    semaphore_t s;
#else
    sem_t s;
#endif
public:
    RtSem()
    {
#ifdef __APPLE__
        semaphore_create(mach_task_self(), &s, SYNC_POLICY_FIFO, 0);
#else
        sem_init(&s, 0, 0);
#endif
    }
    ~RtSem()
    {
#ifdef __APPLE__
        semaphore_destroy(mach_task_self(), s);
#else
        sem_destroy(&s);
#endif
    }
    RtSem(const RtSem &) = delete;
    RtSem &operator=(const RtSem &) = delete;

    void signal()
    {
#ifdef __APPLE__
        semaphore_signal(s);
#else
        sem_post(&s);
#endif
    }
    void wait()
    {
#ifdef __APPLE__
        while (semaphore_wait(s) == KERN_ABORTED) {
        }
#else
        while (sem_wait(&s) == -1 && errno == EINTR) {
        }
#endif
    }
    // wait at most `ns` nanoseconds; true if signalled
    bool wait_for_ns(long long ns)
    {
        if (ns <= 0)
            ns = 0;
#ifdef __APPLE__
        mach_timespec_t t{(unsigned)(ns / 1000000000LL), (clock_res_t)(ns % 1000000000LL)};
        return semaphore_timedwait(s, t) == KERN_SUCCESS;
#else
        timespec t;
        clock_gettime(CLOCK_REALTIME, &t);
        long long n = t.tv_nsec + ns % 1000000000LL;
        t.tv_sec += (time_t)(ns / 1000000000LL + n / 1000000000LL);
        t.tv_nsec = (long)(n % 1000000000LL);
        int r;
        while ((r = sem_timedwait(&s, &t)) == -1 && errno == EINTR) {
        }
        return r == 0;
#endif
    }
};

}  // namespace nv

#endif
