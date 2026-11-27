// eucseq.h -- THE EUCLIDEAN SEQUENCER (the SEQ card's; Ben 2026-11-26: "a card
// that is a sequencer that is a Euclidean sequencer"): eight lanes, each a
// drum key struck on HITS of its STEPS spread as evenly as they go
// (Bjorklund's E(hits, steps), Toussaint's "Euclidean rhythms"), turned by
// ROTATE -- each lane its own length, so 16 against 12 against 7 cycle
// apart; NUDGE sets it ahead of or behind the beat by part of a step, DRIFT
// runs it a little faster or slower than the tempo (Reich's phasing: it
// slides against the others until SYNC puts it back on the beat). The state as the host keeps it (and the session, "seq"); the
// patterns are worked out here, off the audio thread, and handed to the
// slab as bits (slab.cpp's seq_tick steps them at their samples).
#pragma once
#include <algorithm>
#include <cmath>
#include <string>
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
    int nudge = 0;          // its notes this far off its steps, % of a step (-50..50: ahead, behind)
    int drift = 0;          // its own tempo, tenths of a % faster (-50..50: +-5 %) -- Reich's phasing:
                            //  it slides against the other lanes, a step's lap at a time
    uint32_t pat = 0;       // (bit i: step i struck -- euclid's, filled by seq_patterns)
};
struct Seq {
    int on = 0;             // running
    double bpm = 120.0;     // the tempo (the metronome's too: the interface keeps them one)
    int spb = 4;            // steps a beat (4: sixteenths)
    double swing = 50.0;    // 50 straight .. 75: the second step of each pair this far through the pair
    int ch = 9;             // the channel it plays (the drum part's)
    int sync = 0;           // (counted up: every lane back on the beat, at the next step)
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
        l.nudge = std::max(-50, std::min(50, l.nudge));
        l.drift = std::max(-50, std::min(50, l.drift));
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

// A STANDARD MIDI FILE of the pattern (the SEQ card's SAVE MIDI): BARS bars of
// BEATS beats, at 960 ticks a beat, format 0 -- its name, the tempo, the time
// signature (BEATS/4), the kit (program on the channel; a user set's settings
// as GS 21 exclusives, exs, before it), then each lane's notes where the engine
// plays them: swing, NUDGE, ACCENT and DRIFT as seq_tick has them, all lanes
// from the start; a note let go at its lane's next step. A note nudged over the
// loop's edge is wrapped round to the other end (the file loops as it plays).
inline std::vector<uint8_t> seq_midi(const Seq &s0, int bars, int beats, int program,
                                     const std::vector<std::vector<uint8_t>> &exs, const std::string &name)
{
    Seq s = s0;
    seq_patterns(s);
    bars = std::max(1, std::min(999, bars));
    beats = std::max(1, std::min(32, beats));
    const double PPQ = 960.0, step = PPQ / s.spb, total = (double)bars * beats * PPQ;
    const double swf = s.swing / 100.0 * 2.0 - 1.0;
    const bool swings = s.spb % 2 == 0;
    struct E {
        long t;
        int order;                      // (at one tick: a let-go before a strike)
        std::vector<uint8_t> b;
    };
    std::vector<E> ev;
    const uint8_t ch = (uint8_t)(s.ch & 15);
    for (int l = 0; l < SEQ_LANES; l++) {
        const SeqLane &L = s.lane[l];
        if (L.mute || L.key < 0 || L.key > 127 || L.steps <= 0 || !L.pat)
            continue;
        const double pl = step / (1.0 + L.drift / 1000.0), nud = L.nudge / 100.0 * pl;
        for (long k = 0; k * pl < total - 1e-9; k++) {
            const int pos = (int)(k % L.steps);
            if (!((L.pat >> pos) & 1u))
                continue;
            double t = k * pl + ((k & 1) && swings ? swf * pl : 0.0) + nud;
            t = std::fmod(std::fmod(t, total) + total, total);
            int v = L.vel;
            if (L.accent > 0 && __builtin_popcount(L.pat & ((1u << pos) - 1u)) % L.accent == 0)
                v = std::min(127, v + 20);
            const long on = std::lround(t), off = std::min(std::lround(total), std::lround(t + pl));
            ev.push_back({on, 1, {(uint8_t)(0x90 | ch), (uint8_t)L.key, (uint8_t)v}});
            ev.push_back({std::max(on + 1, off), 0, {(uint8_t)(0x80 | ch), (uint8_t)L.key, 64}});
        }
    }
    std::stable_sort(ev.begin(), ev.end(), [](const E &a, const E &b) { return a.t != b.t ? a.t < b.t : a.order < b.order; });
    std::vector<uint8_t> tr;
    auto vlq = [&](unsigned long v) {
        uint8_t b[5];
        int n = 0;
        b[n++] = v & 0x7F;
        while (v >>= 7)
            b[n++] = (uint8_t)(0x80 | (v & 0x7F));
        while (n)
            tr.push_back(b[--n]);
    };
    auto meta = [&](uint8_t type, const std::vector<uint8_t> &d) {
        vlq(0);
        tr.push_back(0xFF);
        tr.push_back(type);
        vlq(d.size());
        tr.insert(tr.end(), d.begin(), d.end());
    };
    meta(0x03, std::vector<uint8_t>(name.begin(), name.end()));
    const unsigned long us = (unsigned long)std::lround(60000000.0 / s.bpm);
    meta(0x51, {(uint8_t)(us >> 16), (uint8_t)(us >> 8), (uint8_t)us});
    meta(0x58, {(uint8_t)beats, 2, 24, 8});
    for (const auto &x : exs) {                 // (a user set's settings: F0 x.. F7)
        vlq(0);
        tr.push_back(0xF0);
        vlq(x.size() + 1);
        tr.insert(tr.end(), x.begin(), x.end());
        tr.push_back(0xF7);
    }
    if (program >= 0) {
        vlq(0);
        tr.push_back((uint8_t)(0xC0 | ch));
        tr.push_back((uint8_t)(program & 127));
    }
    long now = 0;
    for (const E &e : ev) {
        vlq((unsigned long)(e.t - now));
        now = e.t;
        tr.insert(tr.end(), e.b.begin(), e.b.end());
    }
    vlq((unsigned long)std::max(0L, std::lround(total) - now));
    tr.push_back(0xFF);
    tr.push_back(0x2F);
    tr.push_back(0);
    std::vector<uint8_t> f = {'M', 'T', 'h', 'd', 0, 0, 0, 6, 0, 0, 0, 1, (uint8_t)(960 >> 8), (uint8_t)(960 & 255),
                              'M', 'T', 'r', 'k'};
    const uint32_t n = (uint32_t)tr.size();
    f.push_back((uint8_t)(n >> 24));
    f.push_back((uint8_t)(n >> 16));
    f.push_back((uint8_t)(n >> 8));
    f.push_back((uint8_t)n);
    f.insert(f.end(), tr.begin(), tr.end());
    return f;
}

}  // namespace nv
