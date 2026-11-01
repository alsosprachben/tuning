// slab.cpp -- the native engine's LIVE SLAB: live.Slab's core for a piano.
//
// The slab is live's partial table: a fixed capacity of slots, each a row of
// the kernel's columns, the free ones in a queue. A press stamps its key's
// template into free slots (Slab.stamp_cols): the template's columns, each
// partial's onset moved to the press with its phase moved to match, its end
// left open (IDLE) until the key comes up, its level scaled by the velocity
// and the headroom. A key-up releases them (Slab.release: noff at the key-up,
// plus its own delay); once a release has rung out, reap frees the slots.
// Bit for bit live.Slab's columns (numpy's float32 arithmetic, its pairwise
// mean), checked by examples/slab_check.py.
//
// Not here yet (refused by the caller): a section's onset scatter, a
// contact's, grain's or stroke's offsets, a catch's own end, the taps, the
// Moog's rows, Leslie, filters and the damper tracks.

#include <cmath>
#include <cstdint>
#include <cstring>
#include <deque>
#include <map>
#include <tuple>
#include <set>
#include <utility>
#include <vector>

#include "live.h"

extern "C" double nv_damper_contact(int p, int key, int top);

namespace nv {
namespace slab {

static const long long IDLE = 1LL << 62;        // live.IDLE

// live's column groups, in live.py's order
static const char *F8[] = {"om", "p0", "p0R", "fmw", "fmp", "fmpR"};
static const char *F4[] = {"aL", "aR", "nf", "fa", "re", "ch", "logr", "logrA", "aft", "sus", "cv", "cc", "crl",
                           "sj", "csc", "cbw", "tbav", "tau", "tcut", "vd", "vr", "vp", "delL", "delR", "az", "rdl",
                           "nfr"};
static const char *F4N[] = {"gb", "gt", "gc", "vdl"};
static const char *I8[] = {"non", "noff"};
static const char *I4[] = {"gr", "cr", "br", "pl", "fx", "mk"};
enum { NF8 = 6, NF4 = 27, NF4N = 4, NI8 = 2, NI4 = 6 };
enum { F4_aL = 0, F4_aR = 1, F4_nf = 2, F4_re = 4, F4_cbw = 15, F4_vd = 19, F4_vr = 20, F4_delL = 22, F4_delR = 23, F4_rdl = 25 };
enum { F8_om = 0, F8_p0 = 1, F8_p0R = 2, F8_fmw = 3 };
enum { I4_gr = 0, I4_cr = 1, I4_br = 2, I4_fx = 4 };

// numpy's pairwise sum of a float32 array (its float accumulator), as np.mean takes it
static float pairwise(const float *a, long n)
{
    if (n < 8) {
        float res = 0.0f;
        for (long i = 0; i < n; i++)
            res += a[i];
        return res;
    }
    if (n <= 128) {
        float r[8];
        for (int k = 0; k < 8; k++)
            r[k] = a[k];
        long i;
        for (i = 8; i < n - (n % 8); i += 8)
            for (int k = 0; k < 8; k++)
                r[k] += a[i + k];
        float res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++)
            res += a[i];
        return res;
    }
    long n2 = n / 2;
    n2 -= n2 % 8;
    return pairwise(a, n2) + pairwise(a + n2, n - n2);
}

typedef std::tuple<long long, long long, long long, long long> Key;    // (part, channel, note, layer)

struct Slab {
    long cap;
    std::vector<std::vector<double>> f8;
    std::vector<std::vector<float>> f4, f4n;
    std::vector<std::vector<long long>> i8;
    std::vector<std::vector<int32_t>> i4;
    std::vector<float> sw, aL0, aR0, sg, sre, hrel, vbase, vrbase, vsc;
    std::vector<int32_t> dk, slot_ch;
    std::vector<float> aLp, aRp;            // pressure's columns: none on a piano, still the kernel's
    std::vector<char> busy;
    std::deque<long> free;
    // the keys sounding and their slots, in the order first stamped (a
    // Python dict: a key released and stamped again goes to the end) --
    // the order a pedal's release takes them in, so the free queue's order
    std::vector<std::pair<Key, std::vector<long>>> live;
    std::map<Key, int> oneshot;
    std::vector<std::pair<std::vector<long>, long long>> retiring;
    std::vector<long> last_slots;
    double send[256];
    float headroom = 1.0f;
    double headroom_d = 1.0;

    explicit Slab(long capacity) : cap(capacity)
    {
        f8.assign(NF8, std::vector<double>(cap, 0.0));
        f4.assign(NF4, std::vector<float>(cap, 0.0f));
        f4n.assign(NF4N, std::vector<float>(cap, 0.0f));
        i8.assign(NI8, std::vector<long long>(cap, IDLE));
        i4.assign(NI4, std::vector<int32_t>(cap, 0));
        // live.Slab's rest: no gate, bend row or Moog filter row (-1); unit
        // gains, harmonic ratio and vibrato scale; the vibrato at 5.5 Hz
        for (int c : {I4_gr, I4_br, I4_fx})
            i4[c].assign(cap, -1);
        f4[F4_cbw].assign(cap, 100000.0f);      // the wash's width: blockrender.RAND_GRAN, never 0
        sw.assign(cap, 1.0f);
        aL0.assign(cap, 0.0f); aR0.assign(cap, 0.0f); sg.assign(cap, 1.0f); sre.assign(cap, 1.0f);
        hrel.assign(cap, 1.0f); vbase.assign(cap, 0.0f); vsc.assign(cap, 1.0f);
        vrbase.assign(cap, 1.0f * 5.5f);
        dk.assign(cap, -1); slot_ch.assign(cap, -1);
        aLp.assign(cap, 0.0f); aRp.assign(cap, 0.0f);
        busy.assign(cap, 0);
        for (long i = 0; i < cap; i++)
            free.push_back(i);
        for (int c = 0; c < 256; c++)
            send[c] = 1.0;
    }

    // Slab.stamp_cols for a template with none of the offsets (scatter,
    // contact, grain, stroke, a catch's own end): t_* the template's columns
    // (n rows), key, n0, vel_scale, hrel, dur, oneshot, the template's send
    // (NAN: none). False if the slab is full.
    bool stamp(const double *const *tf8, const float *const *tf4, const long long *const *ti8,
               const int32_t *const *ti4, const float *threl, long n, Key key, long long n0, double vel_scale,
               long long dur, bool one, double tsend, long long ch)
    {
        if (n == 0)
            return true;
        if ((long)free.size() < n)
            return false;
        std::vector<long> idx(n);
        for (long q = 0; q < n; q++) {
            idx[q] = free.front();
            free.pop_front();
        }
        for (long q = 0; q < n; q++) {
            long s = idx[q];
            busy[s] = 1;
            dk[s] = -1;
            for (int c = 0; c < NF4; c++)
                f4[c][s] = tf4[c][q];
            for (int c = 0; c < NI4; c++)
                i4[c][s] = ti4[c][q];
            for (int c = 0; c < NF4N; c++)
                f4n[c][s] = 0.0f;
            i4[I4_gr][s] = -1;
            i4[I4_br][s] = -1;
            i4[I4_cr][s] = 0;
            f8[F8_om][s] = tf8[F8_om][q];
            f8[F8_fmw][s] = 0.0;
            long long rd = (long long)tf4[F4_rdl][q];        // rdl.astype(int64): toward zero
            long long newnon = n0 + rd;
            double sh = tf8[F8_om][q] * (double)(ti8[0][q] - newnon);
            f8[F8_p0][s] = tf8[F8_p0][q] + sh;
            f8[F8_p0R][s] = tf8[F8_p0R][q] + sh;
            i8[0][s] = newnon;
            i8[1][s] = one ? n0 + dur + rd : IDLE;
            if (vel_scale != 1.0) {
                f4[F4_aL][s] = tf4[F4_aL][q] * (float)vel_scale;
                f4[F4_aR][s] = tf4[F4_aR][q] * (float)vel_scale;
            }
            if (headroom_d != 1.0) {
                f4[F4_aL][s] *= headroom;
                f4[F4_aR][s] *= headroom;
            }
            aL0[s] = f4[F4_aL][s];
            aR0[s] = f4[F4_aR][s];
            sg[s] = 1.0f;
            sre[s] = 1.0f;
            hrel[s] = threl[q];
            slot_ch[s] = (int32_t)ch;
            vbase[s] = tf4[F4_vd][q];
            vrbase[s] = tf4[F4_vr][q];
        }
        // the vibrato's scale: vd over its mean (np.mean: float32, pairwise)
        std::vector<float> vd(n);
        for (long q = 0; q < n; q++)
            vd[q] = tf4[F4_vd][q];
        float mv = pairwise(vd.data(), n) / (float)n;
        for (long q = 0; q < n; q++)
            vsc[idx[q]] = (double)mv > 1e-12 ? vd[q] / mv : 1.0f;
        double swv = (ch >= 0 && ch < 256) ? send[ch] : 1.0;
        if (!std::isnan(tsend) && ch >= 0)
            swv = tsend;
        for (long q = 0; q < n; q++)
            sw[idx[q]] = (float)swv;
        if (one) {
            long long m = 0;
            retiring.push_back(std::make_pair(idx, n0 + dur));
            (void)m;
            oneshot[key] = 1;
        }
        std::vector<long> &lv = live_of(key);
        lv.insert(lv.end(), idx.begin(), idx.end());
        for (long s : idx)
            i4[I4_fx][s] = -1;                  // _moog_stamp: not a Moog note
        last_slots = idx;
        return true;
    }

    // stamp_cols with a cached template (its own columns, hrel, dur)
    bool stamp_t(const nv::live::Template &T, Key key, long long n0, double vel_scale, long long ch)
    {
        const double *f8p[6];
        const float *f4p[27];
        const long long *i8p[2];
        const int32_t *i4p[6];
        for (int c = 0; c < 6; c++)
            f8p[c] = T.f8[c].data();
        for (int c = 0; c < 27; c++)
            f4p[c] = T.f4[c].data();
        for (int c = 0; c < 2; c++)
            i8p[c] = T.i8[c].data();
        for (int c = 0; c < 6; c++)
            i4p[c] = T.i4[c].data();
        return stamp(f8p, f4p, i8p, i4p, T.hrel.data(), T.P, key, n0, vel_scale, T.dur, false, NAN, ch);
    }

    // THE PAN TABLE (live.pan_table: CC10 -> left and right shadow alpha, half
    // the interaural delay) and the head's beta, from the caller
    double pan_tab[128][3];
    double pan_beta = 0.0;

    // Slab.repan: CC10 was -> cc on these slots; the head shadow's ratio at
    // each partial's frequency (float32), and with itd the ears' delays and
    // the phases that follow them
    void repan(const std::vector<long> &slots, int cc, int was, double rate, bool itd)
    {
        if (slots.empty() || cc == was)
            return;
        auto clamp = [](int v) { return v < 0 ? 0 : (v > 127 ? 127 : v); };
        const double *t1 = pan_tab[clamp(cc)], *t0 = pan_tab[clamp(was)];
        double b2 = pan_beta * pan_beta;
        for (long sidx : slots) {
            double om = 2.0 * M_PI * (double)f4[2][sidx];
            auto shelf = [&](double al) { double x = al * om; return sqrt(x * x + b2); };
            float rl = (float)(shelf(t1[0]) / shelf(t0[0]));
            float rr = (float)(shelf(t1[1]) / shelf(t0[1]));
            aL0[sidx] *= rl; aR0[sidx] *= rr;
            f4[F4_aL][sidx] *= rl; f4[F4_aR][sidx] *= rr;
        }
        if (itd) {
            float dl = (float)((t1[2] - t0[2]) * rate);
            for (long sidx : slots) {
                f4[F4_delL][sidx] += dl;
                f4[F4_delR][sidx] -= dl;
                f8[F8_p0][sidx] -= f8[F8_om][sidx] * (double)dl;
                f8[F8_p0R][sidx] += f8[F8_om][sidx] * (double)dl;
            }
        }
    }

    // Slab.soft_strings: una corda, the `drop` highest of the instrument's `top` strings
    void soft_strings(const std::vector<long> &slots, int drop, int top)
    {
        if (slots.empty() || drop <= 0 || top <= 0)
            return;
        for (long sidx : slots)
            if (i4[3][sidx] > top - drop) {
                aL0[sidx] = 0.0f; aR0[sidx] = 0.0f;
                f4[F4_aL][sidx] = 0.0f; f4[F4_aR][sidx] = 0.0f;
            }
    }

    // Slab.channel_gain: the fader moved under these slots, by a ratio (float32)
    void channel_gain(const std::vector<long> &slots, double ratio)
    {
        if (slots.empty())
            return;
        float r = (float)ratio;
        if ((double)r == 1.0)
            return;
        for (long sidx : slots) {
            aL0[sidx] *= r; aR0[sidx] *= r;
            f4[F4_aL][sidx] *= r; f4[F4_aR][sidx] *= r;
        }
    }

    long live_find(const Key &key) const
    {
        for (size_t i = 0; i < live.size(); i++)
            if (live[i].first == key)
                return (long)i;
        return -1;
    }

    std::vector<long> &live_of(const Key &key)
    {
        long i = live_find(key);
        if (i < 0) {
            live.push_back(std::make_pair(key, std::vector<long>()));
            return live.back().second;
        }
        return live[i].second;
    }

    void release(Key key, long long n)
    {
        long li = live_find(key);
        if (li < 0)
            return;
        std::vector<long> idx = live[li].second;
        live.erase(live.begin() + li);
        if (idx.empty())
            return;
        auto o = oneshot.find(key);
        if (o != oneshot.end()) {
            oneshot.erase(o);
            return;
        }
        for (long s : idx) {
            long long v = n + (long long)f4[F4_rdl][s];
            if (v < i8[1][s])
                i8[1][s] = v;
        }
        retiring.push_back(std::make_pair(idx, n));
    }

    // Slab.reap: slots whose release has rung out, freed
    void reap(long long n, long long blk)
    {
        std::vector<std::pair<std::vector<long>, long long>> keep;
        for (auto &r : retiring) {
            float mx = 0.0f;
            bool first = true;
            for (long s : r.first) {
                float d = f4[F4_delL][s] > f4[F4_delR][s] ? f4[F4_delL][s] : f4[F4_delR][s];
                float v = (f4[F4_re][s] + f4[F4_rdl][s]) + d;
                if (first || v > mx) {
                    mx = v;
                    first = false;
                }
            }
            double tail = (double)r.second + (double)mx + (double)blk + 1.0;
            if ((double)n > tail) {
                for (long s : r.first) {
                    i8[0][s] = IDLE;
                    if (busy[s]) {
                        busy[s] = 0;
                        free.push_back(s);
                    }
                }
            } else {
                keep.push_back(r);
            }
        }
        retiring.swap(keep);
    }
};

// ---------------------------------------------------------------------------
// A PIANO PART, LIVE: live.Live's events for one piano part on its slab --
// what _one_core, _note_on and _note_off do for a piano, block by block as
// live's callback runs them: the block's events at its start, then the sweep
// (a key neither down nor held released), then the reap. Not here yet: the
// pitch wheel, modulation, CC71-78, pressure, sostenuto, half-pedal damper
// tracks, the register (live's needs the GPU), mono, the other voices.

struct Ev {
    int type;               // 0 note-on, 1 note-off, 2 control change
    int ch, a, b;
};

struct Piano {
    Slab S;
    void *cache;
    long long pid;
    double level_db = 0.0, swell = 1.0, rate, retrigger;
    int nbuckets, speed, damper_pedal, soft_drop, soft_top;
    int vol[16], expr[16], cpan[16], pedal_v[16];
    bool soft[16];
    double cgain[16];
    bool cgain_set[16];
    std::set<std::pair<int, int>> down, pedalled;
    std::vector<Ev> events;

    Piano(long cap) : S(cap)
    {
        for (int c = 0; c < 16; c++) {
            vol[c] = 100; expr[c] = 127; cpan[c] = 64; pedal_v[c] = 0;     // GM's power-on
            soft[c] = false; cgain[c] = 1.0; cgain_set[c] = false;
        }
    }

    int bucket(int vel) const
    {
        int b = (int)(vel * nbuckets / 128.0);
        return b < nbuckets - 1 ? b : nbuckets - 1;
    }

    double chan_gain(int ch) const { return pow((vol[ch] / 127.0) * (expr[ch] / 127.0), 2.0); }

    bool pedal_holds(int ch, int note) const
    {
        int v = pedal_v[ch];
        return v > 0 && nv_damper_contact(v, note, 128) < 1.0;
    }

    std::vector<long> sounding(int ch) const
    {
        std::vector<long> out;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch)
                out.insert(out.end(), kv.second.begin(), kv.second.end());
        return out;
    }

    void note_on(int ch, int note, int vel, long long n0)
    {
        down.insert(std::make_pair(ch, note));
        pedalled.erase(std::make_pair(ch, note));
        if (note < 0 || note > 127)
            return;
        const nv::live::Template *T = nv_tcache_lookup(cache, note, bucket(vel), speed);
        if (!T)
            return;                         // a miss: live warms it off the audio thread
        double scale = pow(10.0, level_db / 20.0) * swell * chan_gain(ch);
        scale *= pow(vel / 127.0, 2.0) / std::max(pow(T->vel / 127.0, 2.0), 1e-9);    // touch: the press over the template's
        Key key(pid, ch, note, -1);
        long li = S.live_find(key);
        if (damper_pedal && li >= 0 && !S.live[li].second.empty() && !S.oneshot.count(key)) {
            // a restrike: the string under the hammer stops in a steal-fade
            float fade = (float)(retrigger * rate);
            for (long sidx : S.live[li].second)
                if (fade < S.f4[F4_re][sidx])
                    S.f4[F4_re][sidx] = fade;
            S.release(key, n0);
        }
        if (!S.stamp_t(*T, key, n0, scale, ch))
            return;                         // the slab full: this note does not sound
        long lj = S.live_find(key);
        std::vector<long> slots = lj >= 0 ? S.live[lj].second : std::vector<long>();
        if (cpan[ch] != 64 && !slots.empty())
            S.repan(slots, cpan[ch], 64, rate, true);
        if (soft[ch] && !slots.empty())
            S.soft_strings(slots, soft_drop, soft_top);
    }

    void note_off(int ch, int note, long long n0)
    {
        down.erase(std::make_pair(ch, note));
        if (pedal_holds(ch, note) && damper_pedal) {
            pedalled.insert(std::make_pair(ch, note));
            return;
        }
        S.release(Key(pid, ch, note, -1), n0);
    }

    void control(int ch, int cc, int v, long long n0)
    {
        if (cc == 7 || cc == 11) {
            (cc == 7 ? vol : expr)[ch] = v;
            double g = chan_gain(ch), was = cgain_set[ch] ? cgain[ch] : 1.0;
            if (g != was) {
                cgain[ch] = g;
                cgain_set[ch] = true;
                S.channel_gain(sounding(ch), g / std::max(was, 1e-9));
            }
        } else if (cc == 10) {
            int was = cpan[ch];
            if (v != was) {
                cpan[ch] = v;
                S.repan(sounding(ch), v, was, rate, false);
            }
        } else if (cc == 64) {
            int was_v = pedal_v[ch];
            pedal_v[ch] = v;
            if (v < was_v) {
                std::set<std::pair<int, int>> gone;
                for (auto &k : pedalled)
                    if (k.first == ch && !down.count(k) && !pedal_holds(ch, k.second))
                        gone.insert(k);
                std::vector<Key> rel;
                for (auto &kv : S.live)
                    if (gone.count(std::make_pair((int)std::get<1>(kv.first), (int)std::get<2>(kv.first))))
                        rel.push_back(kv.first);
                for (auto &k : rel)
                    S.release(k, n0);
                for (auto &k : gone)
                    pedalled.erase(k);
            }
        } else if (cc == 67) {
            soft[ch] = v >= 64;
        }
    }

    // LIVE'S SIDE TABLES (live.Slab's, at rest: a piano never moves them)
    // and its render over the slab (Renderer.render, one thread): every slot
    // from 0 past the last busy one through synth_voice, the fast bursts
    // apart through synth_voice_xdec (synth_partials' _xdec_rows)
    std::vector<float> G = std::vector<float>(1, 1.0f), Sx = std::vector<float>(1, 1.0f);
    std::vector<float> BRt = std::vector<float>(65, 1.0f), BLt = std::vector<float>(130, 1.0f);
    std::vector<double> BCt = std::vector<double>(65, 0.0);
    std::vector<float> FT = std::vector<float>(1024 * 30, 0.0f), KN = std::vector<float>(256 * 2 * 9, 0.0f);
    std::vector<int32_t> MPI = std::vector<int32_t>(1024 * 3, 0), MKI = std::vector<int32_t>(1024 * 7, 0);
    std::vector<double> MPC = std::vector<double>(1024 * 65, 0.0);
    std::vector<float> MPR = std::vector<float>(1024 * 65, 1.0f), MPK = std::vector<float>(1024 * 1920, 0.0f);
    float sh[4] = {0.06f, 1.6f, 3.5f, 1500.0f};
    double xdec_nepers = 2.302585;

    void init_tables()
    {
        for (int r = 0; r < 1024; r++) {
            MPI[3 * r + 2] = 1;
            MKI[7 * r + 2] = 1;
            MKI[7 * r + 4] = MKI[7 * r + 5] = MKI[7 * r + 6] = -1;
        }
    }

    void render(long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx, long long blk,
                double master_gain)
    {
        for (long k = 0; k < frames; k++) {
            L[k] = 0.0f;
            R[k] = 0.0f;
            if (SL) {
                SL[k] = 0.0f;
                SR[k] = 0.0f;
            }
        }
        // ...and after it, knobs_advance: each slot's level now is where the
        // next block's ramp starts (aLp, aRp)
        struct Advance {
            Slab &S;
            ~Advance() { S.aLp = S.f4[0]; S.aRp = S.f4[1]; }
        } advance{S};
        long hi = -1;
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q])
                hi = q;
        if (hi < 0)
            return;
        hi += 1;
        long kb0 = (long)(n0 / blk);                        // moog_grid(128) = 128
        long chunk = blk * std::max(1L, (long)(rate / blk));
        auto fast = [&](long q) {
            float lr = S.f4[6][q];
            return S.f4[9][q] <= 0 && S.f4[8][q] <= 0 && (float)(lr * (float)blk) > (float)(xdec_nepers * rate)
                   && S.i4[0][q] < 0 && S.i4[2][q] < 0 && S.dk[q] < 0 && S.i4[4][q] < 0;
        };
        std::vector<long> xr, keep;
        for (long q = 0; q < hi; q++)
            (fast(q) ? xr : keep).push_back(q);
        auto call = [&](void *fn, const long *rows, long n, bool whole) {
            if (!n)
                return;
            // columns gathered (a set of rows), or the slab's own (the whole range)
            std::vector<double> d[6];
            std::vector<float> f[32];
            std::vector<long> l[2];
            std::vector<int> i[6];
            auto gd = [&](const std::vector<double> &c, int k) {
                if (whole) return c.data();
                d[k].resize(n); for (long q = 0; q < n; q++) d[k][q] = c[rows[q]]; return (const double *)d[k].data();
            };
            int fk = 0;
            auto gf = [&](const std::vector<float> &c) {
                if (whole) return c.data();
                std::vector<float> &v = f[fk++];
                v.resize(n); for (long q = 0; q < n; q++) v[q] = c[rows[q]]; return (const float *)v.data();
            };
            auto gl = [&](const std::vector<long long> &c, int k) {
                l[k].resize(n); for (long q = 0; q < n; q++) l[k][q] = (long)c[whole ? q : rows[q]];
                return (const long *)l[k].data();
            };
            int ik = 0;
            auto gi = [&](const std::vector<int32_t> &c) {
                if (whole) return (const int *)c.data();
                std::vector<int> &v = i[ik++];
                v.resize(n); for (long q = 0; q < n; q++) v[q] = c[rows[q]]; return (const int *)v.data();
            };
            const std::vector<float> *F4 = S.f4.data(), *F4N = S.f4n.data();
            ((nv_voice_fn)fn)(L, R, (long)n0, frames, (int)blk, 1, (int)n, gd(S.f8[0], 0), gd(S.f8[1], 1),
                              gd(S.f8[2], 2), gf(F4[0]), gf(F4[1]), gf(F4[2]), gl(S.i8[0], 0), gl(S.i8[1], 1),
                              gf(F4[3]), gf(F4[4]), gf(F4[5]), gf(F4[6]), gf(F4[7]), gf(F4[8]), gf(F4[9]),
                              gf(F4[10]), gf(F4[11]), gf(F4[12]), gf(F4[13]), gf(F4[14]), gf(F4[15]), gf(F4[16]),
                              gf(F4[17]), gf(F4[18]), gf(F4N[0]), gf(F4N[1]), gf(F4N[2]), gf(F4[19]), gf(F4[20]),
                              gf(F4[21]), gf(F4N[3]), gf(F4[22]), gf(F4[23]), gi(S.i4[0]), gi(S.i4[1]), G.data(),
                              Sx.data(), gi(S.i4[2]), BRt.data(), BCt.data(), BLt.data(), gi(S.i4[4]), FT.data(),
                              KN.data(), 2, kb0, gf(S.aLp), gf(S.aRp), gi(S.i4[5]), MPI.data(), MPC.data(),
                              MPR.data(), MKI.data(), MPK.data(), gd(S.f8[3], 3), gd(S.f8[4], 4), gd(S.f8[5], 5),
                              sh[0], sh[1], sh[2], sh[3], chunk, SL ? gf(S.sw) : nullptr, SL, SR);
        };
        if (!xr.empty()) {
            call(sv, keep.data(), (long)keep.size(), false);
            call(sx, xr.data(), (long)xr.size(), false);
        } else {
            call(sv, nullptr, hi, true);
        }
        // the master gain (float32, as numpy multiplies by a Python float) and
        // the clip; the room's send scaled, not clipped
        float g = (float)master_gain;
        for (long k = 0; k < frames; k++) {
            L[k] *= g;
            R[k] *= g;
            L[k] = L[k] < -1.0f ? -1.0f : (L[k] > 1.0f ? 1.0f : L[k]);
            R[k] = R[k] < -1.0f ? -1.0f : (R[k] > 1.0f ? 1.0f : R[k]);
            if (SL) {
                SL[k] *= g;
                SR[k] *= g;
            }
        }
    }

    // live's callback for one block: its events, the sweep, the reap
    void block(long long n0, long long blk)
    {
        std::vector<Ev> evs;
        evs.swap(events);
        for (const Ev &e : evs) {
            if (e.type == 0)
                note_on(e.ch, e.a, e.b, n0);
            else if (e.type == 1)
                note_off(e.ch, e.a, n0);
            else
                control(e.ch, e.a, e.b, n0);
        }
        std::vector<Key> sw;
        for (auto &kv : S.live) {
            std::pair<int, int> ck((int)std::get<1>(kv.first), (int)std::get<2>(kv.first));
            if (!down.count(ck) && !pedalled.count(ck) && !S.oneshot.count(kv.first))
                sw.push_back(kv.first);
        }
        for (auto &k : sw)
            S.release(k, n0);
        S.reap(n0, blk);
    }
};

}  // namespace slab
}  // namespace nv

extern "C" {

// A piano part on its own slab: the template cache (nv_tcache_new, warmed),
// its part id, level, buckets, wheel step (-1 none), dampers, una corda
// (strings dropped, of the top), the rate, the steal-fade, the slab's
// capacity and headroom, the pan table (128 x 3) and the head's beta
void *nv_lp_new(void *cache, long long pid, double level_db, int nbuckets, int speed, int damper_pedal,
                int soft_drop, int soft_top, double rate, double retrigger, long cap, double headroom,
                const double *pan_tab, double pan_beta)
{
    nv::slab::Piano *P = new nv::slab::Piano(cap);
    P->cache = cache; P->pid = pid; P->level_db = level_db; P->nbuckets = nbuckets; P->speed = speed;
    P->damper_pedal = damper_pedal; P->soft_drop = soft_drop; P->soft_top = soft_top;
    P->rate = rate; P->retrigger = retrigger;
    P->S.headroom_d = headroom;
    P->S.headroom = (float)headroom;
    memcpy(P->S.pan_tab, pan_tab, sizeof P->S.pan_tab);
    P->S.pan_beta = pan_beta;
    P->init_tables();
    return P;
}

void nv_lp_free(void *h) { delete (nv::slab::Piano *)h; }

// an event for the next block: 0 note-on (a key, b velocity), 1 note-off, 2 control (a cc, b value)
void nv_lp_event(void *h, int type, int ch, int a, int b)
{
    ((nv::slab::Piano *)h)->events.push_back(nv::slab::Ev{type, ch, a, b});
}

void nv_lp_block(void *h, long long n0, long long blk) { ((nv::slab::Piano *)h)->block(n0, blk); }

// Renderer.render's block: L, R (and with SL the room's send pair) over
// [n0, n0 + frames), through synth_voice (sv) and synth_voice_xdec (sx)
void nv_lp_render(void *h, long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx,
                  long long blk, double master_gain)
{
    ((nv::slab::Piano *)h)->render(n0, frames, L, R, SL, SR, sv, sx, blk, master_gain);
}

// the part's slab, for nv_slab_col and nv_slab_free_list
void *nv_lp_slab(void *h) { return &((nv::slab::Piano *)h)->S; }


void *nv_slab_new(long capacity, double headroom)
{
    nv::slab::Slab *S = new nv::slab::Slab(capacity);
    S->headroom_d = headroom;
    S->headroom = (float)headroom;
    return S;
}

void nv_slab_free(void *h) { delete (nv::slab::Slab *)h; }

// a template's columns by group (live's COLS_F8, COLS_F4, COLS_I8, COLS_I4
// order), its hrel; key (part, channel, note, layer); send NAN for none
int nv_slab_stamp(void *h, double *const *tf8, float *const *tf4, long long *const *ti8, int32_t *const *ti4,
                  const float *threl, long n, long long part, long long ch, long long note, long long layer,
                  long long n0, double vel_scale, long long dur, int one, double tsend)
{
    nv::slab::Slab *S = (nv::slab::Slab *)h;
    return S->stamp(tf8, tf4, ti8, ti4, threl, n, nv::slab::Key(part, ch, note, layer), n0, vel_scale, dur, one != 0,
                    tsend, ch);
}

void nv_slab_release(void *h, long long part, long long ch, long long note, long long layer, long long n)
{
    ((nv::slab::Slab *)h)->release(nv::slab::Key(part, ch, note, layer), n);
}

void nv_slab_reap(void *h, long long n, long long blk) { ((nv::slab::Slab *)h)->reap(n, blk); }

// a column's values over the capacity: group 0 F8, 1 F4, 2 F4_NOTE, 3 I8, 4 I4;
// 5 the bookkeeping (index: sw aL0 aR0 sg sre hrel vbase vrbase vsc), 6 dk/slot_ch/busy
void nv_slab_col(void *h, int group, int index, void *out)
{
    nv::slab::Slab *S = (nv::slab::Slab *)h;
    long n = S->cap;
    switch (group) {
    case 0: memcpy(out, S->f8[index].data(), sizeof(double) * n); break;
    case 1: memcpy(out, S->f4[index].data(), sizeof(float) * n); break;
    case 2: memcpy(out, S->f4n[index].data(), sizeof(float) * n); break;
    case 3: memcpy(out, S->i8[index].data(), sizeof(long long) * n); break;
    case 4: memcpy(out, S->i4[index].data(), sizeof(int32_t) * n); break;
    case 5: {
        std::vector<float> *v[] = {&S->sw, &S->aL0, &S->aR0, &S->sg, &S->sre, &S->hrel, &S->vbase, &S->vrbase,
                                   &S->vsc};
        memcpy(out, v[index]->data(), sizeof(float) * n);
        break;
    }
    case 7:
        memcpy(out, (index == 0 ? S->aLp : S->aRp).data(), sizeof(float) * n);
        break;
    case 6: {
        if (index == 0)
            memcpy(out, S->dk.data(), sizeof(int32_t) * n);
        else if (index == 1)
            memcpy(out, S->slot_ch.data(), sizeof(int32_t) * n);
        else
            for (long i = 0; i < n; i++)
                ((int32_t *)out)[i] = S->busy[i];
        break;
    }
    }
}

// the free queue, in order: its length (out up to cap)
long nv_slab_free_list(void *h, long *out, long cap)
{
    nv::slab::Slab *S = (nv::slab::Slab *)h;
    long n = 0;
    for (long s : S->free)
        if (n < cap)
            out[n++] = s;
    return (long)S->free.size();
}

}  // extern "C"
