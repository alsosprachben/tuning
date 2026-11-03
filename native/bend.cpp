// bend.cpp -- the file renderer's bend passes, for the notes the engine plays:
// blockrender's _prep_pitch_bend and _prep_channel_fader over the native
// reading (midi.cpp's pitch stream and controllers) and its song's notes.
//
// A CHANNEL'S PITCH RATIO (_pitch_stream): the wheel over its range (RPN 0),
// the channel's coarse and fine tuning (RPN 2, 1), GM System On or GS Reset
// putting them back -- in the order the file sent them, ties at one tick by
// the message's place -- as tonelib.channel_pitch_ratio makes it (no master
// tuning: the reader refuses its exclusive). The ratio in force at the
// channel's first note is its TUNING, folded into every note's f0 (_BTUN);
// what moves after is a gesture, which only a voice that can be bent takes
// -- and no piano class can (pitch_bendable), so here it goes nowhere, as in
// blockrender.
//
// THE CHANNEL FADER (_prep_channel_fader): a channel whose CC7 or CC11 moves
// while one of its notes sounds (its release with it, FADER_TAIL) has its
// level as a row -- its notes at unity, the level (CC7 x CC11, squared) at
// each block edge, glided over TAU (onepole_edges) -- unless it is a stamped
// channel (mt32mux: a CC7 a tick before nearly every note).

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <vector>

extern "C" {
int nv_midi_n_pitch(void *p);
void nv_midi_pitch(void *p, int i, int *iv, long *seq, double *t, double *v);
int nv_midi_n_ccs(void *p);
void nv_midi_cc(void *p, int i, int *iv, double *t);
int nv_midi_n_notes(void *p);
void nv_midi_note(void *p, int i, int *iv, double *dv);
}

namespace nv {
namespace bend {

struct P {
    double t;
    long seq;
    int kind;
    double v;
};

}  // namespace bend
}  // namespace nv

// EACH CHANNEL'S PITCH STREAM (_pitch_stream): (t, ratio) at each of its
// events, for the channels with a wheel or an RPN; and each channel's first
// note (the notes as the file wrote them -- before a gesture's strokes, as
// blockrender's passes read them)
static void streams(void *midi, double bend_range, std::map<int, std::vector<std::pair<double, double>>> &out,
                    std::map<long long, double> &first_on)
{
    using nv::bend::P;
    int nn = nv_midi_n_notes(midi);
    for (int i = 0; i < nn; i++) {
        int iv[5];
        double dv[5];
        nv_midi_note(midi, i, iv, dv);
        long long ch = iv[0];
        auto it = first_on.find(ch);
        if (it == first_on.end() || dv[0] < it->second)
            first_on[ch] = dv[0];
    }
    // the channels with a wheel or an RPN (pws, rpns), and every channel's stream
    std::map<int, std::vector<P>> by;
    std::vector<P> gmon;
    std::set<int> chans;
    int np = nv_midi_n_pitch(midi);
    for (int i = 0; i < np; i++) {
        int iv[2];
        long seq;
        double t, v;
        nv_midi_pitch(midi, i, iv, &seq, &t, &v);
        if (iv[0] < 0) {
            gmon.push_back(P{t, seq, 9, 0.0});
            continue;
        }
        chans.insert(iv[0]);
        if (iv[1] <= 3)                     // the wheel, range, fine, coarse
            by[iv[0]].push_back(P{t, seq, iv[1], v});
    }
    for (int c : chans) {
        std::vector<P> ev = by[c];
        ev.insert(ev.end(), gmon.begin(), gmon.end());
        std::stable_sort(ev.begin(), ev.end(), [](const P &a, const P &b) {
            return a.t < b.t || (a.t == b.t && a.seq < b.seq);
        });
        double range = bend_range, wheel = 0.0, coarse = 0.0, fine = 0.0;
        bool hr = false, hw = false, hc = false, hf = false;
        std::vector<std::pair<double, double>> &o = out[c];
        for (const P &e : ev) {
            if (e.kind == 9) {
                hr = hw = hc = hf = false;
            } else if (e.kind == 0) {
                wheel = e.v;
                hw = true;
            } else if (e.kind == 1) {
                range = e.v;
                hr = true;
            } else if (e.kind == 2) {
                fine = e.v;
                hf = true;
            } else {
                coarse = e.v;
                hc = true;
            }
            // tonelib.channel_pitch_ratio, master tuning 0
            double st = (hr ? range : bend_range) * (hw ? wheel : 0.0) / 8192.0 + (hc ? coarse : 0.0)
                        + (hf ? fine : 0.0) / 100.0 + 0.0 + 0.0 / 100.0;
            o.push_back(std::make_pair(e.t, pow(2.0, st / 12.0)));
        }
    }
}

// the ratio in force at the channel's first note (the last event at or
// before it): its TUNING; 1 where it has none
static double tuning_of(const std::vector<std::pair<double, double>> &ev, double first)
{
    double tun = 1.0;
    for (auto &e : ev)
        if (e.first <= first + 1e-6)
            tun = e.second;
    return tun;
}

extern "C" {

// _BTUN: each channel's tuning (out[256]; 0 where it has none), from the
// reader's pitch stream and its first notes; the bend range a channel
// starts at, GM's
int nv_bend_btun(void *midi, void *song, double bend_range, double *out)
{
    (void)song;
    for (int c = 0; c < 256; c++)
        out[c] = 0.0;
    std::map<int, std::vector<std::pair<double, double>>> st;
    std::map<long long, double> first_on;
    streams(midi, bend_range, st, first_on);
    int n = 0;
    for (auto &kv : st) {
        auto f = first_on.find(kv.first);
        if (f == first_on.end() || kv.second.empty())
            continue;                       // tuning a silent channel
        double tun = tuning_of(kv.second, f->second);
        if (fabs(tun - 1.0) > 1e-12) {
            out[kv.first & 255] = tun;
            n++;
        }
    }
    return n;
}

// _BGEST and bend_blocks for channel ch: 1 if its pitch MOVES while it
// sounds -- the stream after its first note, over its tuning -- and then,
// BR and BC not NULL, its row: each block's mean ratio (float32) and the
// extra phase in samples at its start, the running sum of those same means
// (C[b+1] = C[b] + (r[b]-1) BLK by construction); else 0
int nv_bend_gesture(void *midi, void *song, double bend_range, int ch, long nblk, int blk, double sr, float *BR,
                    double *BC)
{
    (void)song;
    std::map<int, std::vector<std::pair<double, double>>> st;
    std::map<long long, double> first_on;
    streams(midi, bend_range, st, first_on);
    auto s = st.find(ch);
    auto f = first_on.find(ch);
    if (s == st.end() || f == first_on.end() || s->second.empty())
        return 0;
    double tun = tuning_of(s->second, f->second);
    std::vector<std::pair<double, double>> ev;
    bool moves = false;
    for (auto &e : s->second)
        if (e.first > f->second + 1e-6) {
            double r = e.second / tun;
            ev.push_back(std::make_pair(e.first, r));
            moves = moves || fabs(r - 1.0) > 1e-9;
        }
    if (!moves)
        return 0;
    if (!BR)
        return 1;
    std::sort(ev.begin(), ev.end());
    size_t m = ev.size() + 1;
    std::vector<double> ts(m), rs(m), acc(m + 1);
    ts[0] = 0.0;
    rs[0] = 1.0;
    for (size_t k = 0; k < ev.size(); k++) {
        ts[k + 1] = ev[k].first;
        rs[k + 1] = ev[k].second;
    }
    double e_last = (double)nblk * blk / sr;
    double app = (ts[m - 1] > e_last ? ts[m - 1] : e_last) + 1.0;          // max(edges[-1], ts[-1]) + 1
    acc[0] = 0.0;
    for (size_t k = 0; k < m; k++) {
        double seg = (k + 1 < m ? ts[k + 1] : app) - ts[k];
        acc[k + 1] = acc[k] + (rs[k] - 1.0) * seg;                         // np.cumsum, in order
    }
    std::vector<double> C(nblk + 1);
    for (long j = 0; j <= nblk; j++) {
        double e = (double)j * blk / sr;
        size_t i = (size_t)(std::upper_bound(ts.begin(), ts.end(), e) - ts.begin()) - 1;
        C[j] = (acc[i] + (rs[i] - 1.0) * (e - ts[i])) * sr;
    }
    for (long j = 0; j < nblk; j++) {
        BR[j] = (float)(1.0 + (C[j + 1] - C[j]) / (double)blk);
        BC[j] = C[j];
    }
    return 1;
}

// _prep_channel_fader for channel ch: 1 and its level at the nblk + 1 block
// edges in L if its fader is a row, else 0. The reader's notes give the spans
// (each to its key-up plus fader_tail); the reader's controllers, in time
// order (in_order), the level; tau the glide
int nv_bend_fader(void *midi, void *song, int ch, long nblk, int blk, double sr, double tau, double fader_tail,
                  double stamp_s, double stamped_share, int vol0, int expr0, float *L)
{
    std::vector<std::pair<double, double>> spans;
    std::vector<double> ons;
    int nn = nv_midi_n_notes(midi);
    for (int i = 0; i < nn; i++) {
        int iv[5];
        double dv[5];
        nv_midi_note(midi, i, iv, dv);
        if (iv[0] != ch)
            continue;
        spans.push_back(std::make_pair(dv[0], dv[1] + fader_tail));
        ons.push_back(dv[0]);
    }
    if (spans.empty())
        return 0;
    struct E {
        double t;
        int cc, v;
    };
    std::vector<E> ccs;
    int nc = nv_midi_n_ccs(midi);
    for (int i = 0; i < nc; i++) {
        int iv[3];
        double t;
        nv_midi_cc(midi, i, iv, &t);
        if (iv[0] == ch)
            ccs.push_back(E{t, iv[1], iv[2]});
    }
    std::stable_sort(ccs.begin(), ccs.end(), [](const E &a, const E &b) { return a.t < b.t; });
    // ...NOT A STAMPED CHANNEL: a CC7 within stamp_s before nearly every note
    std::vector<double> t7;
    for (const E &e : ccs)
        if (e.cc == 7)
            t7.push_back(e.t);
    std::sort(t7.begin(), t7.end());
    std::sort(ons.begin(), ons.end());
    if (!t7.empty()) {
        long hit = 0;
        for (double o : ons) {
            long k = (long)(std::upper_bound(t7.begin(), t7.end(), o + 1e-9) - t7.begin()) - 1;
            hit += k >= 0 && (o - t7[std::max(k, 0L)]) <= stamp_s;
        }
        if ((double)hit / (double)ons.size() >= stamped_share)
            return 0;
    }
    double v7 = vol0, v11 = expr0;
    double lv = pow((v7 / 127.0) * (v11 / 127.0), 2.0);
    bool moves = false;
    std::vector<std::pair<double, double>> fev;
    for (const E &e : ccs) {
        if (e.cc == 7)
            v7 = e.v;
        else if (e.cc == 11)
            v11 = e.v;
        else if (e.cc == 121)
            v11 = 127;                      // reset: expression back up, volume kept
        else
            continue;
        double g = pow((v7 / 127.0) * (v11 / 127.0), 2.0);
        if (g != lv)
            for (auto &s : spans)
                if (s.first < e.t && e.t < s.second) {
                    moves = true;
                    break;
                }
        fev.push_back(std::make_pair(e.t, g));
        lv = g;
    }
    if (!moves)
        return 0;
    // onepole_edges: each segment's target approached over tau, edge by edge
    double dflt = pow(((double)vol0 / 127.0) * ((double)expr0 / 127.0), 2.0);
    std::vector<std::pair<double, double>> segs;
    segs.push_back(std::make_pair(0.0, dflt));
    segs.insert(segs.end(), fev.begin(), fev.end());
    double v = dflt;
    for (size_t k = 0; k < segs.size(); k++) {
        double t0 = segs[k].first, target = segs[k].second;
        double t1 = k + 1 < segs.size() ? segs[k + 1].first : 1e18;
        for (long q = 0; q <= nblk; q++) {
            double te = (double)(q * (long)blk) / sr;
            if (te >= t0 && te < t1)
                L[q] = (float)(target + (v - target) * exp(-(te - t0) / tau));
        }
        if (t1 < 1e17)
            v = target + (v - target) * exp(-(t1 - t0) / tau);
    }
    return 1;
}

}  // extern "C"
