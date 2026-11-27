// eucseq.h -- THE EUCLIDEAN SEQUENCER (the SEQ card's; Ben 2026-11-26: "a card
// that is a sequencer that is a Euclidean sequencer"): eight lanes, each a
// drum key struck on HITS of its STEPS spread as evenly as they go
// (Bjorklund's E(hits, steps), Toussaint's "Euclidean rhythms"), turned by
// ROTATE -- each lane its own length, so 16 against 12 against 7 cycle
// apart. The state as the host keeps it (and the session, "seq"); the
// patterns are worked out here, off the audio thread, and handed to the
// slab as bits (slab.cpp's seq_tick steps them at their samples).
#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>

namespace nv {

enum { SEQ_LANES = 8, SEQ_MAX_STEPS = 32 };

struct SeqLane {
    int key = -1;           // the drum key (-1: none)
    int steps = 16;         // its length, 1..32
    int hits = 0;           // 0..steps
    int rot = 0;            // its pattern turned later by this many steps
    int vel = 100;          // 1..127
    int accent = 0;         // every nth hit +20 (0 none)
    int mute = 0;
    uint32_t pat = 0;       // (bit i: step i struck -- euclid's, filled by seq_patterns)
};
struct Seq {
    int on = 0;             // running
    double bpm = 120.0;     // the tempo (the metronome's too: the interface keeps them one)
    int spb = 4;            // steps a beat (4: sixteenths)
    double swing = 50.0;    // 50 straight .. 75: the second step of each pair this far through the pair
    int ch = 9;             // the channel it plays (the drum part's)
    SeqLane lane[SEQ_LANES];
};

// E(k, n) as Bjorklund lays it out (x..x..x. for E(3,8)), bit i step i,
// turned later by rot
inline uint32_t euclid(int k, int n, int rot)
{
    n = std::max(1, std::min((int)SEQ_MAX_STEPS, n));
    k = std::max(0, std::min(n, k));
    std::vector<std::vector<int>> a((size_t)k, std::vector<int>{1}), b((size_t)(n - k), std::vector<int>{0});
    // (grouped at least once: E(3,4) is x.xx, not xxx.)
    for (bool first = true; !a.empty() && (b.size() > 1 || (first && b.size() == 1)); first = false) {
        const size_t m = std::min(a.size(), b.size());
        std::vector<std::vector<int>> na, rest;
        for (size_t i = 0; i < m; i++) {
            std::vector<int> s = a[i];
            s.insert(s.end(), b[i].begin(), b[i].end());
            na.push_back(s);
        }
        if (a.size() > m)
            rest.assign(a.begin() + (long)m, a.end());
        else
            rest.assign(b.begin() + (long)m, b.end());
        a.swap(na);
        b.swap(rest);
    }
    std::vector<int> seq;
    for (const auto &s : a)
        seq.insert(seq.end(), s.begin(), s.end());
    for (const auto &s : b)
        seq.insert(seq.end(), s.begin(), s.end());
    rot = ((rot % n) + n) % n;
    uint32_t p = 0;
    for (int i = 0; i < n; i++)
        if (seq[(size_t)((i - rot + n) % n)])
            p |= 1u << i;
    return p;
}

// every lane's bits from its numbers (each clamped to its range)
inline void seq_patterns(Seq &s)
{
    s.spb = std::max(1, std::min(8, s.spb));
    s.bpm = std::max(20.0, std::min(300.0, s.bpm));
    s.swing = std::max(50.0, std::min(75.0, s.swing));
    for (SeqLane &l : s.lane) {
        l.steps = std::max(1, std::min((int)SEQ_MAX_STEPS, l.steps));
        l.hits = std::max(0, std::min(l.steps, l.hits));
        l.rot = ((l.rot % l.steps) + l.steps) % l.steps;
        l.vel = std::max(1, std::min(127, l.vel));
        l.accent = std::max(0, std::min(16, l.accent));
        l.pat = euclid(l.hits, l.steps, l.rot);
    }
}

// a new pattern's lanes: the kick on the beats, the snare on two and four,
// the closed hat's eleven of sixteen, a free lane (GM keys)
inline Seq seq_default()
{
    Seq s;
    const int K[SEQ_LANES][4] = {{36, 16, 4, 0}, {38, 16, 2, 4}, {42, 16, 11, 0}, {-1, 16, 0, 0},
                                 {-1, 16, 0, 0}, {-1, 16, 0, 0}, {-1, 16, 0, 0}, {-1, 16, 0, 0}};
    for (int i = 0; i < SEQ_LANES; i++) {
        s.lane[i].key = K[i][0];
        s.lane[i].steps = K[i][1];
        s.lane[i].hits = K[i][2];
        s.lane[i].rot = K[i][3];
    }
    s.lane[2].vel = 80;
    seq_patterns(s);
    return s;
}

}  // namespace nv
