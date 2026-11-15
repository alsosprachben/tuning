// lfqueue.h -- a bounded lock-free queue, any number of threads pushing and
// popping (Dmitry Vyukov's bounded MPMC queue): each cell carries a sequence
// number, a push or pop claims its cell with one compare-and-swap and
// publishes it with a release store. No thread ever waits on another: a push
// to a full queue, a pop of an empty one, returns false at once. What the
// audio thread takes from the window and the keyboard comes through these
// (host.cpp: the MIDI, the stamped MIDI, the posted work -- and their trash,
// so nothing is freed on the audio thread).
#ifndef NV_LFQUEUE_H
#define NV_LFQUEUE_H

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>

namespace nv {

template <class T> class LfQueue {
    struct Cell {
        std::atomic<size_t> seq;
        T v;
    };
    std::unique_ptr<Cell[]> buf;
    size_t mask;
    alignas(64) std::atomic<size_t> head{0};
    alignas(64) std::atomic<size_t> tail{0};

public:
    explicit LfQueue(size_t cap_pow2) : buf(new Cell[cap_pow2]), mask(cap_pow2 - 1)
    {
        for (size_t i = 0; i < cap_pow2; i++)
            buf[i].seq.store(i, std::memory_order_relaxed);
    }
    LfQueue(const LfQueue &) = delete;
    LfQueue &operator=(const LfQueue &) = delete;

    bool push(const T &v)
    {
        size_t pos = tail.load(std::memory_order_relaxed);
        for (;;) {
            Cell &c = buf[pos & mask];
            const size_t s = c.seq.load(std::memory_order_acquire);
            const intptr_t d = (intptr_t)s - (intptr_t)pos;
            if (d == 0) {
                if (tail.compare_exchange_weak(pos, pos + 1, std::memory_order_relaxed)) {
                    c.v = v;
                    c.seq.store(pos + 1, std::memory_order_release);
                    return true;
                }
            } else if (d < 0) {
                return false;                       // (full)
            } else {
                pos = tail.load(std::memory_order_relaxed);
            }
        }
    }

    bool pop(T &v)
    {
        size_t pos = head.load(std::memory_order_relaxed);
        for (;;) {
            Cell &c = buf[pos & mask];
            const size_t s = c.seq.load(std::memory_order_acquire);
            const intptr_t d = (intptr_t)s - (intptr_t)(pos + 1);
            if (d == 0) {
                if (head.compare_exchange_weak(pos, pos + 1, std::memory_order_relaxed)) {
                    v = c.v;
                    c.seq.store(pos + mask + 1, std::memory_order_release);
                    return true;
                }
            } else if (d < 0) {
                return false;                       // (empty)
            } else {
                pos = head.load(std::memory_order_relaxed);
            }
        }
    }

    // (how many are in it, as near as two loads can say: a bound on a drain)
    size_t size_approx() const
    {
        const size_t t = tail.load(std::memory_order_acquire), h = head.load(std::memory_order_acquire);
        return t > h ? t - h : 0;
    }
};

}  // namespace nv

#endif
