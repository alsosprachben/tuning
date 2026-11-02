// channel.cpp -- the native engine's CHANNELS: a file's controller events
// and notes in, the questions a note asks of its channel answered.
//
// blockrender's channel passes for the pedals and the note list, as the
// note loop reads them:
//
//   damper pedal (CC64)   _prep_damper_pedal: its down/up spans (64 the
//                         switch point), and, where the channel ever stands
//                         between 0 and 127, its values (half-pedalling)
//   sostenuto (CC66)      _prep_sostenuto_soft: the keys down when it went
//                         down, held to its rise
//   soft pedal (CC67)     ...in at a note's onset or not
//   all sound off         _prep_sound_off: CC120, 126, 127
//   the next strike       _next_same: when this key is struck again
//
// and _note_pedal's arithmetic on them: a note's end once the pedals have
// had their say (Song::note_off). The half-pedal's contact law is damper.py's
// (band, contact). Events keep the file's order within a tick (in_order: a
// stable sort on the time alone).

#include <algorithm>
#include <array>
#include <cmath>
#include <map>
#include <set>
#include <tuple>
#include <utility>
#include <vector>

#include "pycompat.h"          // a stroke train's random.Random, sum()

namespace nv {

static double pymin(double a, double b) { return b < a ? b : a; }
static double pymax(double a, double b) { return b > a ? b : a; }

// damper.py
namespace damper {
const double BAND_TREBLE[2] = {24.0, 88.0};
const double BAND_BASS[2] = {40.0, 104.0};
const int LOW_KEY = 21;

static void band(int key, int top, double *lo, double *hi)
{
    double x = pymin(pymax((key - LOW_KEY) / (double)(top - LOW_KEY > 1 ? top - LOW_KEY : 1), 0.0), 1.0);
    *lo = BAND_BASS[0] + (BAND_TREBLE[0] - BAND_BASS[0]) * x;
    *hi = BAND_BASS[1] + (BAND_TREBLE[1] - BAND_BASS[1]) * x;
}

static double contact(int p, int key, int top)
{
    if (key >= top)
        return 0.0;
    double lo, hi;
    band(key, top, &lo, &hi);
    double x = pymin(pymax(((double)p - lo) / (hi - lo), 0.0), 1.0);
    return 1.0 - x * x * (3.0 - 2.0 * x);
}
}  // namespace damper

struct CC {
    double t;
    int cc, v;
};

typedef std::pair<double, double> Span;

// One channel's controllers, as the note loop asks of them.
struct Channel {
    std::vector<CC> ccs;                // in the file's order, then in_order
    std::vector<Span> ped, sost, soft;  // CC64, 66, 67 down/up spans
    std::vector<double> pv_t;           // a half-pedalled channel's CC64 times...
    std::vector<int> pv_v;              // ...and values (empty: a switch)
    std::vector<double> soff;           // all sound off, sorted

    std::vector<Span> spans(int cc, double total) const
    {
        std::vector<Span> segs;
        bool down = false;
        double dn = 0.0;
        for (const CC &e : ccs) {
            if (e.cc != cc)
                continue;
            if (e.v >= 64 && !down) {
                down = true;
                dn = e.t;
            } else if (e.v < 64 && down) {
                segs.push_back(Span(dn, e.t));
                down = false;
            }
        }
        if (down)
            segs.push_back(Span(dn, total));
        return segs;
    }

    void finish(double total)
    {
        std::stable_sort(ccs.begin(), ccs.end(), [](const CC &a, const CC &b) { return a.t < b.t; });
        ped = spans(64, total);
        sost = spans(66, total);
        soft = spans(67, total);
        bool half = false;
        for (const CC &e : ccs)
            if (e.cc == 64) {
                pv_t.push_back(e.t);
                pv_v.push_back(e.v);
                if (e.v > 0 && e.v < 127)
                    half = true;
            }
        if (!half) {
            pv_t.clear();
            pv_v.clear();
        }
        for (const CC &e : ccs)     // sorted() of the file-order times: the same set
            if (e.cc == 120 || e.cc == 126 || e.cc == 127)
                soff.push_back(e.t);
        std::sort(soff.begin(), soff.end());
    }

    // _damper_falls: when the damper lands for a key released at t
    double damper_falls(double t) const
    {
        // bisect_right(segs, (t, 1e18)) - 1: the last span starting at or before t
        int i = (int)(std::upper_bound(ped.begin(), ped.end(), Span(t, 1e18)) - ped.begin()) - 1;
        if (i >= 0 && ped[i].first <= t && t < ped[i].second)
            return ped[i].second;
        return t;
    }

    // _damper_lands: (when this key's damper lands, released at t; whether
    // the pedal stood in its band on the way)
    double damper_lands(double t, int key, int top, double total, bool *in_band) const
    {
        *in_band = false;
        int i = (int)(std::upper_bound(pv_t.begin(), pv_t.end(), t) - pv_t.begin()) - 1;
        double tt = t;
        int v = i >= 0 ? pv_v[i] : 0;
        for (int j = i;; j++) {
            if (j > i) {
                if (j >= (int)pv_t.size())
                    break;
                tt = pv_t[j];
                v = pv_v[j];
            }
            double k = damper::contact(v, key, top);
            if (k >= 1.0)
                return tt;
            if (k > 0.0)
                *in_band = true;
        }
        return pymax(total, t);
    }

    bool soft_at(double t) const
    {
        for (const Span &s : soft)
            if (s.first <= t && t < s.second)
                return true;
        return false;
    }

    // _sound_off: the first all-sound-off strictly after t (has: one exists)
    double sound_off(double t, bool *has) const
    {
        auto it = std::upper_bound(soff.begin(), soff.end(), t);
        *has = it != soff.end();
        return *has ? *it : 0.0;
    }
};

struct NoteKey {
    long long ch;
    int note;
    double on;
    bool operator<(const NoteKey &o) const
    {
        if (ch != o.ch)
            return ch < o.ch;
        if (note != o.note)
            return note < o.note;
        return on < o.on;
    }
};

struct Ev {
    long long ch;
    int note;
    double on, off;
    int vel;
    double v7, v11, pan, trim;          // the channel's CC7, CC11, CC10 at its onset; its program's trim
    int prog, drum;                     // its program, and whether a drum set's
    double ratio = 1.0;                 // a stroke's pitch (stroke_pitch: a bell tree's bar)
    int inner = 0;                      // a ridge after a scrape's first (inner_ridge: it chokes nothing)
};

// A file's channels and notes.
struct Song {
    std::map<long long, Channel> ch;
    std::vector<Ev> notes;
    std::map<NoteKey, double> next_same, sost_held;
    std::map<long long, int> vbase;     // each channel's median velocity (_vbase)
    double total = 0.0;
    // ITS TUNING: the file's table, a channel's MIDI Tuning Standard tables
    // from their times (_MTS_TL), its fixed bend (_BTUN) and octave tuning (_OTUN)
    std::vector<double> freq = std::vector<double>(128, 0.0);
    std::map<long long, std::vector<std::pair<double, std::vector<double>>>> mts;
    std::map<long long, double> btun;
    std::map<long long, std::vector<double>> otun;
    std::map<long long, int> fader;     // channels whose fader is a row (_LROW): their volume 1
    // THE DRUM SETS (percussion_for_note at kit_for_program): each drum
    // program's key, its pitch (0: no drum the engine knows) and its seat
    std::vector<double> kit_f0, kit_seat;
    // ...and its EXCLUSIVE CLASSES (percussion_map.choke_group): each drum
    // program's key, the keys a strike on it stops (bits, two words), and
    // from them (finish) each drum channel's key's later strikes that stop
    // it (_prep_exclusive_classes' choke_at)
    std::vector<unsigned long long> kit_choke;
    std::map<std::pair<long long, int>, std::vector<double>> choke_at;
    // ITS SLURS: _legato_ticks' (channel, key, k), and from them (finish)
    // each note's -- slurred, and a slur leaving it (_prep_slur_out)
    std::set<std::tuple<long long, int, int>> legato;
    std::vector<char> slurred, slur_out;

    bool in_group(int prog, int key, int k) const
    {
        const unsigned long long *m = &kit_choke[2 * (128 * prog + key)];
        return (m[k >> 6] >> (k & 63)) & 1ULL;
    }

    void exclusive_classes()
    {
        choke_at.clear();
        if (kit_choke.empty())
            return;
        // the notes in a choke group, by channel and key, and the set each
        // (channel, key) was last struck in
        std::map<std::pair<long long, int>, int> kit_on;
        std::map<std::pair<long long, int>, std::vector<double>> ons;
        for (const Ev &e : notes) {
            if (!e.drum || e.prog < 0 || e.prog > 127)
                continue;
            const unsigned long long *m = &kit_choke[2 * (128 * e.prog + e.note)];
            if (!(m[0] | m[1]))
                continue;
            auto k = std::make_pair(e.ch, e.note);
            kit_on[k] = e.prog;
            if (!e.inner)
                ons[k].push_back(e.on);
        }
        for (auto &a : ons) {
            int prog = kit_on[a.first];
            std::vector<double> later;
            for (auto &b : ons)
                if (b.first.first == a.first.first && in_group(prog, a.first.second, b.first.second))
                    later.insert(later.end(), b.second.begin(), b.second.end());
            std::sort(later.begin(), later.end());
            choke_at[a.first] = later;
        }
    }

    // The notes in the note loop's order (onset, channel, key), each key's
    // k-th a slur where legato has it; and a note a slurred onset on its
    // channel follows, sounding up to it or ending within 20 ms before
    void slurs()
    {
        size_t n = notes.size();
        slurred.assign(n, 0);
        slur_out.assign(n, 0);
        if (legato.empty())
            return;
        std::vector<int> idx(n);
        for (size_t i = 0; i < n; i++)
            idx[i] = (int)i;
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) {
            const Ev &x = notes[a], &y = notes[b];
            if (x.on != y.on) return x.on < y.on;
            if (x.ch != y.ch) return x.ch < y.ch;
            return x.note < y.note;
        });
        std::map<std::pair<long long, int>, int> occ;
        std::map<long long, std::vector<double>> sl_on;
        for (int i : idx) {
            int &k = occ[std::make_pair(notes[i].ch, notes[i].note)];
            if (legato.count(std::make_tuple(notes[i].ch, notes[i].note, k))) {
                slurred[i] = 1;
                sl_on[notes[i].ch].push_back(notes[i].on);
            }
            k++;
        }
        for (auto &v : sl_on)
            std::sort(v.second.begin(), v.second.end());
        for (size_t i = 0; i < n; i++) {
            auto it = sl_on.find(notes[i].ch);
            if (it == sl_on.end())
                continue;
            auto q = std::upper_bound(it->second.begin(), it->second.end(), notes[i].on);
            if (q != it->second.end() && notes[i].off >= *q - 0.02)
                slur_out[i] = 1;
        }
    }

    // A STRUCK OR SCRAPED GESTURE'S STROKES (percussion_map.rasp_strokes, as
    // _prep_strokes expands them): each drum note whose set's key has a
    // gesture (kind[q]: 1 a rasp, 2 a cascade, 3 an impact train, 4 a roll,
    // 5 a pattern; par[NV_SPAR q..])
    // replaced by its strokes -- each its own onset, end, velocity
    // (max(1, int(velocity x level))), pitch and, past the first, an inner
    // ridge. AND A KEY THAT ALSO STRIKES ANOTHER'S SOUND (key_layers:
    // par[NV_SPAR (q + 1) - 4] of them, the keys after): each struck as
    // the note is, before it, as _prep_strokes expands them
    void strokes(const int *kind, const double *par)
    {
        std::vector<Ev> out;
        for (const Ev &e : notes) {
            bool in = e.drum && e.prog >= 0 && e.prog < 128 && e.note >= 0 && e.note < 128;
            int q = 128 * e.prog + e.note;
            for (int l = 0; in && l < (int)par[NV_SPAR * (q + 1) - 4]; l++) {
                Ev x = e;
                x.note = (int)par[NV_SPAR * (q + 1) - 3 + l];
                out.push_back(x);
            }
            int kd = in ? kind[q] : 0;
            if (!kd) {
                out.push_back(e);
                continue;
            }
            const double *p = par + NV_SPAR * q;
            std::vector<std::array<double, 4>> st;     // (on, off, level, pitch)
            if (kd == 1)
                rasp(e.on, e.off, p, st);
            else if (kd == 2)
                cascade(e.on, e.off, p, st);
            else if (kd == 3)
                train(e.note, e.on, p, st);
            else if (kd == 4)
                roll(e.note, e.on, e.off, p, st);
            else
                pattern(e.on, p, st);
            for (size_t k = 0; k < st.size(); k++) {
                Ev x = e;
                x.on = st[k][0];
                x.off = st[k][1];
                long v = (long)(e.vel * st[k][2]);
                x.vel = (int)(v > 1 ? v : 1);
                x.ratio = st[k][3] != 1.0 ? st[k][3] : 1.0;
                x.inner = k > 0;
                out.push_back(x);
            }
        }
        notes.swap(out);
    }

    static double shape_db(const double *shape, int n, double frac)
    {
        double x = frac * n - 0.5;
        if (x <= 0.0)
            return shape[0];
        if (x >= n - 1)
            return shape[n - 1];
        int i = (int)x;
        return shape[i] + (shape[i + 1] - shape[i]) * (x - i);
    }

    // the guiro's ridges: (dur, n, shape's length, its dB...)
    static void rasp(double on, double off, const double *p, std::vector<std::array<double, 4>> &out)
    {
        double dur = p[0];
        int n = (int)p[1], ns = (int)p[2];
        double span = off > on ? pymax(dur, (off - on) * 0.5) : dur;
        if (n < 2) {
            out.push_back({on, on + span, 1.0, 1.0});
            return;
        }
        std::vector<double> w;
        for (int k = 0; k < n - 1; k++) {
            double frac = k / (double)(n - 1);
            double g = 1.260 - 0.330 * frac;
            if (frac > 0.80)
                g += 0.62 * (frac - 0.80) / 0.20;
            w.push_back(g);
        }
        double scale = span / pysum(w.data(), (int)w.size());
        double t = on;
        for (int k = 0; k < n; k++) {
            double frac = k / (double)(n - 1);
            double jitter = ((double)(((unsigned long long)k * 2654435761ULL) % 1000ULL) / 1000.0 - 0.5) * 0.05;
            double level = (0.318 + 0.400 * frac) / 0.638;
            if (frac > 0.80)
                level *= 1.0 - 0.30 * (frac - 0.80) / 0.20;
            if (ns)
                level *= pow(10.0, shape_db(p + 3, ns, frac) / 40.0);
            double step = (k < n - 1 ? w[k] : w.back()) * scale;
            out.push_back({t + step * jitter, t + step * 0.9, level, 1.0});
            t += step;
        }
    }

    // the bell tree's sweep: (span, n, semitones)
    static void cascade(double on, double off, const double *p, std::vector<std::array<double, 4>> &out)
    {
        double span = p[0], semis = p[2];
        int n = (int)p[1];
        if (off > on)
            span = pymax(span, (off - on) * 0.6);
        for (int k = 0; k < n; k++) {
            double frac = n > 1 ? k / (double)(n - 1) : 0.0;
            double t = on + span * pow(frac, 0.85);
            double jitter = ((double)(((unsigned long long)k * 2654435761ULL) % 1000ULL) / 1000.0 - 0.5) * 0.35
                            * (span / (n > 1 ? n : 1));
            double level = 0.55 + 0.45 * pow(1.0 - fabs(frac - 0.45) / 0.55, 2.0);
            double ratio = pow(2.0, semis * frac / 12.0);
            out.push_back({pymax(on, t + jitter), t + span / n, level, ratio});
        }
    }

    // a held roll (_snare_roll): (rate, bounces, bounce s, bounce dB, the
    // other hand's dB, jitter, scatter dB, the least span, the body's, the
    // first stroke's and the last's dB) -- every bounce a stroke, sorted
    static void roll(int note, double on, double off, const double *p, std::vector<std::array<double, 4>> &out)
    {
        double rate = p[0], bounce_s = p[2], bounce_db = p[3], hand_db = p[4], jit = p[5], sc = p[6];
        double body_db = p[8], first_db = p[9], last_db = p[10];
        int bounces = (int)p[1];
        PyRandom r;
        pyr_seed(&r, (long long)note * 7919LL + (long long)nearbyint(on * 1e4));
        double span = pymax(p[7], off - on);
        double last_t = span - 0.5 / rate;      // the last stroke lands as it ends
        size_t first = out.size();
        auto stroke = [&](double t, double base, int nb) {
            for (int b = 0; b < nb; b++) {
                double tb = t + b * bounce_s * (1.0 + pyr_uniform(&r, -0.15, 0.15));
                double db = base - bounce_db * b + pyr_uniform(&r, -sc, sc);
                out.push_back({on + tb, on + tb + 0.8 * bounce_s, pow(10.0, db / 40.0), 1.0});
            }
        };
        int k = 0;
        double t = 0.0;
        while (t < last_t) {
            double hand = k % 2 ? -hand_db : 0.0;
            stroke(t, k == 0 ? first_db : body_db + hand, bounces);
            k++;
            t = k / rate + pyr_uniform(&r, -jit, jit) / rate;
        }
        stroke(pymax(last_t, 0.0), last_db, 2);
        std::sort(out.begin() + first, out.end());
    }

    // a set's pattern (_pattern): (n, then each stroke's time, dB, semitones
    // and length -- NaN: to the next, the last 0.3 s)
    static void pattern(double on, const double *p, std::vector<std::array<double, 4>> &out)
    {
        int n = (int)p[0];
        for (int k = 0; k < n; k++) {
            const double *st = p + 1 + 4 * k;
            double end = !std::isnan(st[3]) ? st[0] + st[3] : k + 1 < n ? st[4] : st[0] + 0.3;
            out.push_back({on + st[0], on + end, pow(10.0, st[1] / 40.0), pow(2.0, st[2] / 12.0)});
        }
    }

    // the vibraslap's impacts (_impact_train): (rate, secs, fall dB, jitter,
    // scatter dB, the strike's dB, side_db set, side_db, side_slope)
    static void train(int note, double on, const double *p, std::vector<std::array<double, 4>> &out)
    {
        double rate = p[0], secs = p[1], fall = p[2], jit = p[3], sc = p[4], strike = p[5];
        bool has_side = p[6] != 0.0;
        double side_db = p[7], side_slope = p[8];
        PyRandom r;
        pyr_seed(&r, (long long)note * 1000003LL + (long long)nearbyint(on * 1e4));
        int n = (int)(rate * secs);
        for (int k = 0; k < n; k++) {
            double t = (k + pyr_uniform(&r, -jit, jit)) / rate;
            double swing = -fall * t / secs;
            double far = (has_side && k % 2) ? pymax(0.0, -swing - side_db) * side_slope : 0.0;
            double level = pow(10.0, (swing - far + pyr_uniform(&r, -sc, sc) + (k == 0 ? strike : 0.0)) / 20.0);
            double t0 = pymax(0.0, t);
            out.push_back({on + t0, on + t0 + 0.9 / rate, level, pow(2.0, pyr_uniform(&r, -0.1, 0.1))});
        }
    }

    void finish(double total_)
    {
        total = total_;
        exclusive_classes();
        slurs();
        for (auto &c : ch)
            c.second.finish(total);
        // _next_same: the notes by onset, latest first (stable), each key's
        // next strike the one seen before it
        std::vector<int> idx(notes.size());
        for (size_t i = 0; i < idx.size(); i++)
            idx[i] = (int)i;
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return -notes[a].on < -notes[b].on; });
        std::map<std::pair<long long, int>, double> seen;
        for (int i : idx) {
            const Ev &e = notes[i];
            auto k = std::make_pair(e.ch, e.note);
            auto it = seen.find(k);
            if (it != seen.end())
                next_same[NoteKey{e.ch, e.note, e.on}] = it->second;
            seen[k] = e.on;
        }
        // _vbase: each channel's median velocity, sorted()[len // 2]
        std::map<long long, std::vector<int>> vs;
        for (const Ev &e : notes)
            vs[e.ch].push_back(e.vel);
        for (auto &v : vs) {
            std::sort(v.second.begin(), v.second.end());
            vbase[v.first] = v.second[v.second.size() / 2];
        }
        // _SOST_HELD: each sostenuto span catches the keys down as it went down
        for (auto &c : ch)
            for (const Span &s : c.second.sost)
                for (const Ev &e : notes)
                    if (e.ch == c.first && e.on <= s.first && s.first < e.off) {
                        NoteKey k{e.ch, e.note, e.on};
                        auto it = sost_held.find(k);
                        sost_held[k] = pymax(s.second, it == sost_held.end() ? 0.0 : it->second);
                    }
    }

    // _F: this channel's 128-key table at t
    const std::vector<double> &table(long long c, double t) const
    {
        auto it = mts.find(c);
        if (it == mts.end() || it->second.empty())
            return freq;
        const auto &tl = it->second;
        int i = 0;
        for (int j = 0; j < (int)tl.size(); j++)        // bisect_right on the starts, of t + 1e-9
            if (tl[j].first <= t + 1e-9)
                i = j + 1;
        i -= 1;
        return tl[i > 0 ? i : 0].second;
    }

    // _note_class_and_pitch for a melodic note with none of its extras (no
    // per-note pitch, MPE, meend, sounding octaves, scale or brass law): f0
    double pitch(long long c, int note, double on) const
    {
        double f0 = table(c, on)[note];
        auto b = btun.find(c);
        if (b != btun.end() && b->second != 0.0)
            f0 *= b->second;
        auto o = otun.find(c);
        if (o != otun.end() && !o->second.empty())
            f0 *= pow(2.0, o->second[note % 12] / 1200.0);
        return f0;
    }

    const Channel *get(long long c) const
    {
        auto it = ch.find(c);
        return it == ch.end() ? nullptr : &it->second;
    }

    // _note_pedal, the sostenuto and all sound off on a note's key-up (the
    // one-shot extension and the choke are the caller's): its end.
    // damper_pedal: the voice has dampers; mcut: a mono note cut by the next.
    // *band: a half-pedalled note that meets the band (its damper track is
    // the caller's).
    double note_off(long long c, int note, double on, double off, bool damper_pedal, bool mcut,
                    double retrigger_fade, bool *band) const
    {
        *band = false;
        const Channel *C = get(c);
        auto nx_it = next_same.find(NoteKey{c, note, on});
        bool has_nx = nx_it != next_same.end();
        double nx = has_nx ? nx_it->second : 0.0;
        if (damper_pedal && !mcut && C && !C->pv_t.empty()) {
            const int top = 128;
            double land = C->damper_lands(off, note, top, total, band);
            if (has_nx && land > off)
                land = pymin(land, pymax(off, nx - retrigger_fade));
            if (!(land > off))
                *band = false;
            off = pymax(off, land);
        } else if (damper_pedal && !mcut) {
            double rel = C ? C->damper_falls(off) : off;
            if (rel > off) {
                if (has_nx)
                    rel = pymin(rel, pymax(off, nx - retrigger_fade));
                off = rel;
            }
        }
        auto sh = sost_held.find(NoteKey{c, note, on});
        if (sh != sost_held.end() && sh->second > off && damper_pedal && !mcut) {
            double h = sh->second;
            if (has_nx)
                h = pymin(h, pymax(off, nx - retrigger_fade));
            off = pymax(off, h);
        }
        bool has_sf = false;
        double sf = C ? C->sound_off(on, &has_sf) : 0.0;
        if (has_sf && sf < off)
            off = pymax(on + retrigger_fade, sf);
        return off;
    }
};

}  // namespace nv

extern "C" {

void *nv_song_new(void) { return new nv::Song(); }
void nv_song_free(void *s) { delete (nv::Song *)s; }

void nv_song_cc(void *s, long long ch, double t, int cc, int v)
{
    ((nv::Song *)s)->ch[ch].ccs.push_back(nv::CC{t, cc, v});
}

void nv_song_note(void *s, long long ch, int note, double on, double off, int vel, double v7, double v11,
                  double pan, double trim, int prog, int drum)
{
    ((nv::Song *)s)->notes.push_back(nv::Ev{ch, note, on, off, vel, v7, v11, pan, trim, prog, drum});
}

int nv_song_n_notes(void *s) { return (int)((nv::Song *)s)->notes.size(); }

// note i as given: (channel, key, velocity, program, drum) ints; (on, off) doubles
void nv_song_get_note(void *s, int i, long long *ch, int *iv, double *dv)
{
    const nv::Ev &e = ((nv::Song *)s)->notes[i];
    *ch = e.ch;
    iv[0] = e.note; iv[1] = e.vel; iv[2] = e.prog; iv[3] = e.drum;
    dv[0] = e.on; dv[1] = e.off;
}

// the held-key end the sostenuto gives this note, if it caught it
int nv_song_sost(void *s, long long ch, int note, double on, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    auto it = S->sost_held.find(nv::NoteKey{ch, note, on});
    if (it == S->sost_held.end())
        return 0;
    *out = it->second;
    return 1;
}

// _F: the channel's 128-key table at t
void nv_song_table(void *s, long long ch, double t, double *out)
{
    const std::vector<double> &tab = ((nv::Song *)s)->table(ch, t);
    for (int k = 0; k < 128; k++)
        out[k] = tab[k];
}

double nv_song_total(void *s) { return ((nv::Song *)s)->total; }

// the damper pedal's down/up spans (seconds), up to cap; the count
int nv_song_ped_spans(void *s, long long ch, double *out, int cap)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    if (!C)
        return 0;
    int n = (int)C->ped.size();
    for (int i = 0; i < n && i < cap; i++) {
        out[2 * i] = C->ped[i].first;
        out[2 * i + 1] = C->ped[i].second;
    }
    return n;
}

// a half-pedalled channel's CC64 (times, values), up to cap; 0 for a switch
int nv_song_pedal_values(void *s, long long ch, double *t, int *v, int cap)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    if (!C)
        return 0;
    int n = (int)C->pv_t.size();
    for (int i = 0; i < n && i < cap; i++) {
        t[i] = C->pv_t[i];
        v[i] = C->pv_v[i];
    }
    return n;
}

// damper.contact
double nv_damper_contact(int p, int key, int top) { return nv::damper::contact(p, key, top); }

// the channel's first value of controller cc in time order (in_order), if any
int nv_song_first_cc(void *s, long long ch, int cc, int *v)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    if (!C)
        return 0;
    for (const nv::CC &e : C->ccs)
        if (e.cc == cc) {
            *v = e.v;
            return 1;
        }
    return 0;
}

// the file's tuning (ch < 0, at 0) or a channel's MTS table from t
void nv_song_tuning(void *s, long long ch, double t, const double *freq)
{
    nv::Song *S = (nv::Song *)s;
    if (ch < 0)
        S->freq.assign(freq, freq + 128);
    else
        S->mts[ch].push_back(std::make_pair(t, std::vector<double>(freq, freq + 128)));
}

void nv_song_channel(void *s, long long ch, double btun, const double *otun, int fader)
{
    nv::Song *S = (nv::Song *)s;
    if (btun != 0.0)
        S->btun[ch] = btun;
    if (otun)
        S->otun[ch] = std::vector<double>(otun, otun + 12);
    if (fader)
        S->fader[ch] = 1;
}

// The drum sets' keys: f0[128 * program + key] (0 where the engine has no
// drum) and seat[...] (the drum's pan in its set)
void nv_song_kits(void *s, const double *f0, const double *seat)
{
    nv::Song *S = (nv::Song *)s;
    S->kit_f0.assign(f0, f0 + 16384);
    S->kit_seat.assign(seat, seat + 16384);
}

// A note's pitch and level as its channel gives them: f0, velocity, pan,
// channel volume ((CC7 CC11)^2, its program's trim; 1 under a fader row),
// effort (40 log10 of its velocity over the channel's median, +-12, where
// the voice has an effort tilt), and a drum's seat in its set. The note by
// its index in the song's notes (two can share a key, an onset and a
// key-up). 0 if there is no such note (or a drum the sets lack); 2 for a
// drum: its pitch its set's, not a tuning's.
int nv_song_pitch_level(void *s, int i, int effort_tilt, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->notes.size())
        return 0;
    long long ch = S->notes[i].ch;
    int note = S->notes[i].note;
    double on = S->notes[i].on;
    const nv::Ev &e = S->notes[i];
    int r = 1;
    out[5] = 0.0;
    if (e.drum) {
        int q = 128 * e.prog + note;
        if (S->kit_f0.empty() || e.prog < 0 || e.prog > 127 || S->kit_f0[q] == 0.0)
            return 0;
        out[0] = S->kit_f0[q] * e.ratio;
        out[5] = S->kit_seat[q];
        r = 2;
    } else {
        out[0] = S->pitch(ch, note, on);
    }
    out[1] = e.vel;
    out[2] = e.pan;
    double cv = pow(e.v7 * e.v11, 2.0);
    if (S->fader.count(ch))
        cv = 1.0;
    out[3] = cv * e.trim;
    double eff = 0.0;
    auto vb = S->vbase.find(ch);
    int b = vb != S->vbase.end() ? vb->second : 0;
    if (!b)
        b = e.vel;
    if (effort_tilt && e.vel && b)
        eff = nv::pymax(-12.0, nv::pymin(12.0, 40.0 * log10(e.vel / (double)b)));
    out[4] = eff;
    return r;
}

void nv_song_finish(void *s, double total) { ((nv::Song *)s)->finish(total); }

double nv_song_note_off(void *s, long long ch, int note, double on, double off, int damper_pedal, int mcut,
                        double retrigger_fade, int *band)
{
    bool b = false;
    double r = ((nv::Song *)s)->note_off(ch, note, on, off, damper_pedal, mcut, retrigger_fade, &b);
    *band = b;
    return r;
}

int nv_song_soft_at(void *s, long long ch, double t)
{
    const nv::Channel *C = ((nv::Song *)s)->get(ch);
    return C && C->soft_at(t);
}

// The drum sets' gestures expanded into their strokes (Song::strokes;
// before nv_song_finish, after the passes that read the notes as written)
void nv_song_strokes(void *s, const int *kind, const double *par)
{
    ((nv::Song *)s)->strokes(kind, par);
}

// Note i a stroke of a struck or scraped gesture (_prep_strokes): its pitch
// ratio, and whether it is a ridge after the scrape's first
void nv_song_note_stroke(void *s, int i, double ratio, int inner)
{
    nv::Song *S = (nv::Song *)s;
    if (i >= 0 && i < (int)S->notes.size()) {
        S->notes[i].ratio = ratio;
        S->notes[i].inner = inner;
    }
}

// A slurred note, as _legato_ticks found it: channel ch's key's k-th (before nv_song_finish)
void nv_song_legato(void *s, long long ch, int note, int k)
{
    ((nv::Song *)s)->legato.insert(std::make_tuple(ch, note, k));
}

// Note i's slurs: out[0] it is slurred, out[1] a slur leaves it. 0 past the notes
int nv_song_slur(void *s, int i, int *out)
{
    const nv::Song *S = (nv::Song *)s;
    if (i < 0 || i >= (int)S->slurred.size())
        return 0;
    out[0] = S->slurred[i];
    out[1] = S->slur_out[i];
    return 1;
}

// The drum sets' exclusive classes: choke[2 * (128 * program + key) + w],
// bit k of word w set where a strike on key stops key 64 w + k (before
// nv_song_finish)
void nv_song_chokes(void *s, const unsigned long long *choke)
{
    ((nv::Song *)s)->kit_choke.assign(choke, choke + 2 * 16384);
}

// Where a later strike in its exclusive class stops this note (the first
// past its onset): 1 and *out, else 0
int nv_song_choke(void *s, long long ch, int note, double on, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    auto it = S->choke_at.find(std::make_pair(ch, note));
    if (it == S->choke_at.end())
        return 0;
    for (double t : it->second)
        if (t > on + 1e-4) {
            *out = t;
            return 1;
        }
    return 0;
}

int nv_song_next_same(void *s, long long ch, int note, double on, double *out)
{
    const nv::Song *S = (nv::Song *)s;
    auto it = S->next_same.find(nv::NoteKey{ch, note, on});
    if (it == S->next_same.end())
        return 0;
    *out = it->second;
    return 1;
}

}  // extern "C"
