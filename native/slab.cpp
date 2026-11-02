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

#include <algorithm>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <chrono>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <map>
#include <memory>
#include <tuple>
#include <set>
#include <utility>
#include <vector>

#include "live.h"
#include "nv.h"

extern "C" int nv_tcache_slur_fade(void *h, int program, int note, double *out);

extern "C" double nv_damper_contact(int p, int key, int top);

extern "C" {
// livereg.cpp: register.LiveChannel
void *nv_lreg_new(const StringMode *modes, int M, double sr, double kappa, double knock, double fall, double fl,
                  int top, double beta);
int nv_lreg_strike(void *h, long long sid, int key, double at, int R, const double *cols, const long *slot,
                   const int *free_keys, int nfree);
int nv_lreg_release(void *h, long long sid, double at, const int *free_keys, int nfree);
void nv_lreg_damp(void *h, const int *keys, int n);
int nv_lreg_felt(void *h, double at, const int *keys, const double *rates, int n);
int nv_lreg_answer(void *h, long *idx, double *z, double *floor_);
void nv_lreg_forced(void *h, long *slot, double *wgt, double *beta, double *val);
void nv_lreg_free(void *h);
int nv_cl_launch(void *h, int slot, const void *D, long dn, const void *C, long cn, const void *S, long sn, int nd,
                 long long n0, int frames, int send, int mg);
int nv_cl_collect(void *h, int slot, float *out);
int nv_cl_samples(void *h, const void *D, long dn, const void *C, long cn, const void *S, long sn, int nd,
                  long long n0, int frames, int send, int mg, float *out);
}

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
enum { F4_aL = 0, F4_aR = 1, F4_nf = 2, F4_fa = 3, F4_re = 4, F4_ch = 5, F4_logr = 6, F4_logrA = 7, F4_aft = 8, F4_sus = 9, F4_cbw = 15, F4_vd = 19, F4_vr = 20, F4_delL = 22, F4_delR = 23, F4_rdl = 25 };
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

// ...and of a float64 array (np.sum's)
static double pairwise_d(const double *a, long n)
{
    if (n < 8) {
        double res = 0.0;
        for (long i = 0; i < n; i++)
            res += a[i];
        return res;
    }
    if (n <= 128) {
        double r[8];
        for (int k = 0; k < 8; k++)
            r[k] = a[k];
        long i;
        for (i = 8; i < n - (n % 8); i += 8)
            for (int k = 0; k < 8; k++)
                r[k] += a[i + k];
        double res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++)
            res += a[i];
        return res;
    }
    long n2 = n / 2;
    n2 -= n2 % 8;
    return pairwise_d(a, n2) + pairwise_d(a + n2, n - n2);
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
    std::vector<float> dg;                 // a damped row's weight (damper.weight)
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
        dg.assign(cap, 0.0f);
        aLp.assign(cap, 0.0f); aRp.assign(cap, 0.0f);
        busy.assign(cap, 0);
        for (long i = 0; i < cap; i++)
            free.push_back(i);
        for (int c = 0; c < 256; c++)
            send[c] = 1.0;
    }

    // Slab.stamp_cols for a template with none of the offsets (scatter,
    // contact, grain) but a stroked note's (sof: each row where its stroke
    // falls) and a row's own end (rof: from its onset, where >= 0): t_* the
    // template's columns (n rows), key, n0, vel_scale, hrel, dur, oneshot,
    // the template's send (NAN: none), sof and rof (NULL: none). False if
    // the slab is full.
    bool stamp(const double *const *tf8, const float *const *tf4, const long long *const *ti8,
               const int32_t *const *ti4, const float *threl, long n, Key key, long long n0, double vel_scale,
               long long dur, bool one, double tsend, long long ch, const long long *sof = nullptr,
               const long long *rof = nullptr)
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
            if (sof)
                newnon += sof[q];
            double sh = tf8[F8_om][q] * (double)(ti8[0][q] - newnon);
            f8[F8_p0][s] = tf8[F8_p0][q] + sh;
            f8[F8_p0R][s] = tf8[F8_p0R][q] + sh;
            i8[0][s] = newnon;
            i8[1][s] = one ? n0 + dur + rd : IDLE;
            if (rof && rof[q] >= 0)
                i8[1][s] = newnon + rof[q];
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
        return stamp(f8p, f4p, i8p, i4p, T.hrel.data(), T.P, key, n0, vel_scale, T.dur, T.oneshot, NAN, ch,
                     T.sof.empty() ? nullptr : T.sof.data(), T.rof.empty() ? nullptr : T.rof.data());
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
// CC71-78, portamento, the other voices. MONO MODE (CC126/127), THE RPNs (bend range, fine and coarse
// tuning, the mod range), CC120, CC121, CC123, the channel-mode messages and
// SOSTENUTO as live's. THE PITCH WHEEL
// (live._repitch: GM's 2-semitone range) and the mod wheel, which on a piano
// is nothing but a honky-tonk's detune.
// PRESSURE (channel aftertouch, live's Slab.press) as a level: a piano's
// effort_tilt is 0, so its partials are not tilted, only lifted by press_db
// at full pressure. THE DAMPERS IN BETWEEN (live._damp_block), when given damper.py's
// numbers (nv_lp_damper): a pedalled key in the band is taken down by its
// level through a damper track the kernel reads (synth_voice_damp). THE REGISTER (live's _reg_*), when given
// one (nv_lp_register): its worker's jobs answered in step -- each as it is
// sent, as a worker that kept up would, so a reply is placed at the first
// pump after its job (live's own worker answers a few blocks later, as it
// can: the same rows, later).

// THE LATE ROOM (live.RoomTail): the diffuse tail and the room's modes, each
// stereo, fed the send -- through convolver.c (live's Convolver, its library
// loaded by the caller: conv_new, conv_process, conv_free). Each impulse
// response split at one block: its first block's taps on the audio thread,
// the rest on a thread of its own a block behind -- exact, since the rest
// starts a block late by definition.
typedef void *(*conv_new_fn)(const float *ir, int len, int B, int M);
typedef void (*conv_proc_fn)(void *c, const float *x, float *out);
typedef void (*conv_free_fn)(void *c);

struct Room {
    static const int SEGMENT_BLOCKS = 16;           // live.Convolver.SEGMENT_BLOCKS
    conv_new_fn cnew;
    conv_proc_fn cproc;
    conv_free_fn cfree;
    int B, nconv = 0;
    void *head[4] = {}, *body[4] = {};
    std::vector<float> inp[4], res[4], out[4], tmp;
    std::thread worker;
    std::mutex mu;
    std::condition_variable cv;
    bool go = false, done = true, stop = false;

    // ir: n samples of 2 channels interleaved; mir the modes' (m 0: none)
    Room(void *cn, void *cp, void *cf, const float *ir, long n, const float *mir, long m, int frames)
        : cnew((conv_new_fn)cn), cproc((conv_proc_fn)cp), cfree((conv_free_fn)cf), B(frames)
    {
        std::vector<std::vector<float>> irs;
        for (int c = 0; c < 2; c++) {
            irs.emplace_back(n);
            for (long k = 0; k < n; k++)
                irs.back()[k] = ir[2 * k + c];
        }
        for (int c = 0; m > 0 && c < 2; c++) {
            irs.emplace_back(m);
            for (long k = 0; k < m; k++)
                irs.back()[k] = mir[2 * k + c];
        }
        nconv = (int)irs.size();
        for (int i = 0; i < nconv; i++) {
            const std::vector<float> &h = irs[i];
            long hb = std::min((long)h.size(), (long)B);
            head[i] = cnew(h.data(), (int)hb, B, SEGMENT_BLOCKS);
            body[i] = (long)h.size() > B ? cnew(h.data() + B, (int)(h.size() - B), B, SEGMENT_BLOCKS) : nullptr;
            inp[i].assign(B, 0.0f);
            res[i].assign(B, 0.0f);
            out[i].assign(B, 0.0f);
        }
        tmp.assign(B, 0.0f);
        worker = std::thread([this] { work(); });
    }

    ~Room()
    {
        {
            std::unique_lock<std::mutex> lk(mu);
            cv.wait(lk, [&] { return done; });
            stop = true;
            go = true;
        }
        cv.notify_all();
        worker.join();
        for (int i = 0; i < nconv; i++) {
            if (head[i]) cfree(head[i]);
            if (body[i]) cfree(body[i]);
        }
    }

    void work()
    {
        std::unique_lock<std::mutex> lk(mu);
        while (true) {
            cv.wait(lk, [&] { return go; });
            go = false;
            if (stop)
                return;
            lk.unlock();
            for (int i = 0; i < nconv; i++)
                if (body[i])
                    cproc(body[i], inp[i].data(), res[i].data());
            lk.lock();
            done = true;
            cv.notify_all();
        }
    }

    // RoomTail.process: the room's (wl, wr) for a block of the send
    void process(const float *sL, const float *sR, float *wl, float *wr)
    {
        {
            std::unique_lock<std::mutex> lk(mu);
            cv.wait(lk, [&] { return done; });     // last block's body: ready, normally long since
            done = false;
        }
        const float *xs[4] = {sL, sR, sL, sR};
        for (int i = 0; i < nconv; i++) {
            cproc(head[i], xs[i], tmp.data());
            for (int k = 0; k < B; k++)
                out[i][k] = tmp[k] + res[i][k];
        }
        for (int i = 0; i < nconv; i++)
            memcpy(inp[i].data(), xs[i], sizeof(float) * B);
        {
            std::lock_guard<std::mutex> lk(mu);
            go = true;
        }
        cv.notify_all();
        for (int k = 0; k < B; k++) {
            wl[k] = nconv == 4 ? out[0][k] + out[2][k] : out[0][k];
            wr[k] = nconv == 4 ? out[1][k] + out[3][k] : out[1][k];
        }
    }
};

struct Ev {
    int type;               // 0 note-on, 1 note-off, 2 control change, 3 channel aftertouch (a),
                            // 4 the pitch wheel (a, -8192..8191)
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
    std::map<std::pair<int, int>, int> key_vel;     // (ch, note) -> the strike's velocity
    double pressure[16] = {};                       // channel aftertouch, 0..1
    // THE PITCH WHEEL (live._repitch): each channel's raw wheel and the ratio
    // last applied to its notes; the range, GM's 2 semitones (no RPN 0 here)
    int wheel[16] = {};
    double bend[16] = {1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0};
    double bend_range = 2.0;                        // live.bend_range, the session's
    // THE RPNs (live's _rpn_data, _rpn_step; tonelib's arithmetic): the one
    // selected (an NRPN selected: none), and what the channel's are set to --
    // its bend range (-1: live's bend_range), fine and coarse tuning, the
    // fine tuning's last MSB, the mod wheel's range (cents; -1: live's)
    int rpn_msb[16], rpn_lsb[16];
    bool rpn_none[16] = {};
    double brange[16], fine[16] = {}, coarse[16] = {}, modrange[16];
    int fine_msb[16];
    double mod_cents = 35.0;                        // live.mod_cents (the session's)
    // SOSTENUTO (CC66): the keys down when it went down, held (live.sost)
    std::map<int, std::set<int>> sost;
    // MONO MODE (CC126; live.mono): one voice a channel -- its held keys in
    // press order (note, velocity) and the one sounding (-1 none)
    bool mono[16] = {};
    std::vector<std::pair<int, int>> mono_stack[16];
    int mono_cur[16] = {-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1};
    // THE MOD WHEEL on a honky-tonk (live's 'detune' role): which pre-warmed
    // detune new notes take, the nearest of DETUNE_STEPS (a piano's wheel
    // does nothing else: a hammered string takes no vibrato)
    bool detune_wheel = false;
    double press_db = 8.0;                          // tonelib.PRESS_DB (live.press_db)
    // A DRUM PART (live.Patch(program, True)): its program the drum set, and
    // each key's exclusive class (two words a key: native.kits' choke)
    bool drums = false;
    int program = 0;
    std::vector<unsigned long long> choke;
    // LEGATO (live._legato_on): each channel's last onset group -- when it
    // began, its keys, its last key up, whether it was a slur -- a note
    // struck within CHORD_WINDOW_S of it a member, else slurred where one of
    // its keys is still down or the last went up within LEGATO_GAP_S
    struct Group {
        long long on = 0;
        std::set<std::pair<int, int>> keys;
        bool has_off = false;
        long long off = 0;
        bool slur = false;
    };
    std::map<int, Group> onset_group;
    double legato_gap_s = 0.015, chord_window_s = 0.030;    // live.LEGATO_GAP_S, CHORD_WINDOW_S

    Piano(long cap) : S(cap)
    {
        for (int t = 0; t < DAMP_TRACKS; t++) {
            free_tracks.push_back(t);
            DMO[t] = 2 * t;
        }
        for (int c = 0; c < 16; c++) {
            rpn_msb[c] = rpn_lsb[c] = 127;
            brange[c] = modrange[c] = -1.0;
            fine_msb[c] = 64;
        }
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

    // a key down (live's note-on, before its parts): the key held, and in
    // MONO the voice handed over -- the note sounding cut, the new key on top
    // of the held stack
    bool legato_on(int ch, int note, long long n0)
    {
        auto it = onset_group.find(ch);
        if (it != onset_group.end() && (double)(n0 - it->second.on) <= chord_window_s * rate) {
            it->second.keys.insert(std::make_pair(ch, note));     // a chord member: the chord's answer
            return it->second.slur;
        }
        bool slur = false;
        if (it != onset_group.end()) {
            for (auto &k : it->second.keys)
                if (down.count(k))
                    slur = true;
            if (it->second.has_off && (double)(n0 - it->second.off) <= legato_gap_s * rate)
                slur = true;
        }
        // (_slur_cut: no native voice cuts the note it leaves -- slur_cuts_release)
        Group g;
        g.on = n0;
        g.keys.insert(std::make_pair(ch, note));
        g.slur = slur;
        onset_group[ch] = g;
        return slur;
    }

    void legato_off(int ch, int note, long long n0)
    {
        auto it = onset_group.find(ch);
        if (it != onset_group.end() && it->second.keys.count(std::make_pair(ch, note))) {
            Group &g = it->second;
            g.off = g.has_off ? std::max(g.off, n0) : n0;
            g.has_off = true;
        }
    }

    void note_on(int ch, int note, int vel, long long n0)
    {
        bool slur = legato_on(ch, note, n0);
        down.insert(std::make_pair(ch, note));
        pedalled.erase(std::make_pair(ch, note));
        if (mono[ch]) {
            std::vector<std::pair<int, int>> &st = mono_stack[ch];
            std::vector<std::pair<int, int>> keep;
            for (auto &x : st)
                if (x.first != note)
                    keep.push_back(x);
            keep.push_back(std::make_pair(note, vel));
            st.swap(keep);
            int prev = mono_cur[ch];
            if (prev >= 0 && prev != note) {
                mono_cut(ch, prev, n0);
                slur = true;                    // a handoff is a slur (_MONO_SLUR)
            }
            mono_cur[ch] = note;
        }
        strike(ch, note, vel, n0, slur);
    }

    // live._mono_cut: the voice taken -- this note stopped now over the
    // steal-fade, pedal or no pedal (its key has not come up)
    void mono_cut(int ch, int note, long long n0)
    {
        float fade = (float)(retrigger * rate);
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch && std::get<2>(kv.first) == note)
                for (long q : kv.second)
                    if (fade < S.f4[F4_re][q])
                        S.f4[F4_re][q] = fade;
        pedalled.erase(std::make_pair(ch, note));
        let_go(ch, note, n0);
    }

    // the part's note (live._note_on): stamped, panned, softened, pressed,
    // bent, its strings struck
    void strike(int ch, int note, int vel, long long n0, bool slur = false)
    {
        key_vel[std::make_pair(ch, note)] = vel;
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
            // a restrike: the string under the hammer stops in a steal-fade,
            // and its forced register rows (REG_FORCED) with it
            float fade = (float)(retrigger * rate);
            for (const Key &k : {key, Key(pid, ch, note, REG_FORCED)}) {
                long lk = S.live_find(k);
                if (lk < 0 || S.live[lk].second.empty())
                    continue;
                for (long sidx : S.live[lk].second)
                    if (fade < S.f4[F4_re][sidx])
                        S.f4[F4_re][sidx] = fade;
                S.release(k, n0);
            }
        }
        if (!S.stamp_t(*T, key, n0, scale, ch))
            return;                         // the slab full: this note does not sound
        long lj = S.live_find(key);
        std::vector<long> slots = lj >= 0 ? S.live[lj].second : std::vector<long>();
        if (cpan[ch] != 64 && !slots.empty())
            S.repan(slots, cpan[ch], 64, rate, true);
        if (soft[ch] && !slots.empty())
            S.soft_strings(slots, soft_drop, soft_top);
        if (slur && !slots.empty())
            slur_stamp(note, *T);
        if (drums && !choke.empty()) {
            // THE CHOKE, live (Live._note_on): the strike in an exclusive
            // class is a note-off written into whatever of it is ringing
            const unsigned long long *m = &choke[2 * (128 * program + note)];
            if (m[0] | m[1]) {
                std::vector<Key> hit;
                for (auto &kv : S.live) {
                    int k = (int)std::get<2>(kv.first);
                    if (std::get<0>(kv.first) == pid && k != note && k >= 0 && k < 128
                        && ((m[k >> 6] >> (k & 63)) & 1ULL))
                        hit.push_back(kv.first);
                }
                for (const Key &k : hit) {
                    S.oneshot.erase(k);
                    S.release(k, n0);
                }
            }
        }
        if (pressure[ch] != 0.0)
            press(slots, pressure[ch]);
        if (bend[ch] != 1.0)                // a note struck under a bend joins it
            retune(slots, n0, bend[ch]);
        if (reg_on && reg_note[note] && !S.last_slots.empty())
            reg_strike(ch, note, n0, *T, S.last_slots);
    }

    // live._slur_stamp: the slots just stamped given the voice's legato
    // attack -- the rows whose fade is the attack's (fa_at), their fade and
    // chiff no longer than its, under the note's caps
    void slur_stamp(int note, const nv::live::Template &T)
    {
        double sf[3];
        if (!nv_tcache_slur_fade(cache, program, note, sf))
            return;
        const std::vector<long> &sl = S.last_slots;
        if ((long)sl.size() != (long)T.fa_at.size())
            return;
        double dur = T.dur ? T.dur / rate : 1.0;
        float fa = (float)(std::max(1e-4, std::min(sf[0], sf[2] * dur)) * rate);
        float chf = (float)(std::max(1e-4, std::min(sf[1], 0.45 * dur)) * rate);
        for (size_t q = 0; q < sl.size(); q++) {
            if (!T.fa_at[q])
                continue;
            long s = sl[q];
            if (fa < S.f4[F4_fa][s])
                S.f4[F4_fa][s] = fa;
            if (chf < S.f4[F4_ch][s])
                S.f4[F4_ch][s] = chf;
        }
    }

    // a key up (live's note-off): in MONO, the sounding key's voice back to
    // the last key still held (struck again), or nothing if the voice had
    // gone on already; then, as ever, the damper or the release
    void note_off(int ch, int note, long long n0)
    {
        down.erase(std::make_pair(ch, note));
        legato_off(ch, note, n0);
        if (mono[ch]) {
            std::vector<std::pair<int, int>> &st = mono_stack[ch];
            for (size_t i = 0; i < st.size();)
                if (st[i].first == note)
                    st.erase(st.begin() + i);
                else
                    i++;
            if (mono_cur[ch] != note)
                return;                             // already handed over: nothing sounds for it
            if (!st.empty()) {
                std::pair<int, int> back = st.back();
                mono_cut(ch, note, n0);
                mono_cur[ch] = back.first;
                strike(ch, back.first, back.second, n0, true);     // back to a key still held: a slur too
                return;
            }
            mono_cur[ch] = -1;                      // last key up: an ordinary release
        }
        auto sq = sost.find(ch);
        if ((pedal_holds(ch, note) || (sq != sost.end() && sq->second.count(note))) && damper_pedal) {
            pedalled.insert(std::make_pair(ch, note));
            return;
        }
        let_go(ch, note, n0);
    }

    // the part's note let go (live._note_off): released, its forced register
    // rows with it, and its damper told
    void let_go(int ch, int note, long long n0)
    {
        S.release(Key(pid, ch, note, -1), n0);
        if (reg_on) {
            S.release(Key(pid, ch, note, REG_FORCED), n0);
            reg_damper(ch, n0, note, false);
        }
    }

    // live.Slab.press at tilt 0: each slot from its baseline (aL0, aR0),
    // the shape normalised by the left baseline's power, times
    // 10^(press_db * p / 20)
    void press(const std::vector<long> &slots, double p)
    {
        if (slots.empty())
            return;
        long n = (long)slots.size();
        std::vector<double> b2(n);
        for (long q = 0; q < n; q++) {
            double b = (double)S.aL0[slots[q]];
            b2[q] = b * b;
        }
        double sh = 1.0;                    // hrel ** (0 * p)
        double p2 = pairwise_d(b2.data(), n);
        if (p2 > 0.0)                       // (base * shape) ** 2 is base * base again
            sh = sh * pow(p2 / (pairwise_d(b2.data(), n) + 1e-30), 0.5);
        sh = sh * pow(10.0, press_db * p / 20.0);
        for (long s : slots) {
            S.f4[F4_aL][s] = (float)((double)S.aL0[s] * sh);
            S.f4[F4_aR][s] = (float)((double)S.aR0[s] * sh);
        }
    }

    // live.Slab.retune for a pitch (om_scale; the vibrato's depth and rate
    // as they are): om scaled, and the phase anchored where it is now -- the
    // vibrato's accumulated swing included, which moves with om (a piano's
    // depth is 0, so that term is too)
    void retune(const std::vector<long> &slots, long long n, double scale)
    {
        if (slots.empty())
            return;
        double tn = (double)n / rate;
        for (long q : slots) {
            double om0 = S.f8[F8_om][q], vd = (double)S.f4[F4_vd][q];
            double vr = std::max((double)S.f4[F4_vr][q], 1e-6), vp = (double)S.f4[21][q];   // vp
            double ton = (double)S.i8[0][q] / rate;
            auto extra = [&](double om) {
                double w2 = 2.0 * M_PI * vr;
                double swing = cos(w2 * ton + vp) - cos(w2 * tn + vp);
                return (om * rate / (2.0 * M_PI)) * vd / vr * swing;
            };
            double before = extra(om0);
            double om1 = om0 * scale;
            double after = extra(om1);
            double step = (om0 - om1) * (double)n - (after - before);
            S.f8[F8_p0][q] += step;
            S.f8[F8_p0R][q] += step;
            S.f8[F8_om][q] = om1;
        }
    }

    double range_of(int ch) const { return brange[ch] >= 0.0 ? brange[ch] : bend_range; }

    // live._repitch: the channel's ratio (tonelib.channel_pitch_ratio: the
    // wheel over its range, the coarse and fine tuning; no master tuning
    // here), its notes moved by the change
    void repitch(int ch, long long n0)
    {
        double st = range_of(ch) * (double)wheel[ch] / 8192.0 + coarse[ch] + fine[ch] / 100.0 + 0.0 + 0.0 / 100.0;
        double ratio = pow(2.0, st / 12.0);
        double prev = bend[ch];
        if (ratio == prev)
            return;
        bend[ch] = ratio;
        retune(sounding(ch), n0, ratio / prev);
    }

    void pitchwheel(int ch, int v, long long n0)
    {
        wheel[ch] = v;
        repitch(ch, n0);
    }

    // tonelib.RPN_STEP: (step, lo, hi) for (0, 0) .. (0, 5)
    static bool rpn_step_of(int lsb, double *step, double *lo, double *hi)
    {
        static const double T[6][3] = {{0.01, 0.0, 127.99},
                                       {100.0 / 8192.0, -100.0, 100.0 * 8191.0 / 8192.0},
                                       {1.0, -64.0, 63.0},
                                       {1.0, 0.0, 127.0},
                                       {1.0, 0.0, 127.0},
                                       {100.0 / 128.0, 0.0, 127.0 * 100.0 + 127.0 * 100.0 / 128.0}};
        if (lsb < 0 || lsb > 5)
            return false;
        *step = T[lsb][0];
        *lo = T[lsb][1];
        *hi = T[lsb][2];
        return true;
    }

    // live._rpn_data: CC6/CC38 into the RPN selected; the pitch ones re-pitch
    // the channel; MTS's (0/3, 0/4) only a gm2 part acts on, none here; MPE's
    // configuration (0/6) is not read here
    void rpn_data(int ch, int cc, int v, long long n0)
    {
        if (rpn_none[ch])
            return;                                 // an NRPN (GS's sound ones: not here)
        int m = rpn_msb[ch], l = rpn_lsb[ch];
        if (m != 0 || l > 5)
            return;                                 // null, or not one read
        if (l == 0) {
            brange[ch] = cc == 6 ? (double)v : (double)(long)range_of(ch) + v / 100.0;     // rpn_bend_range
        } else if (l == 1) {
            if (cc == 6)
                fine_msb[ch] = v;                   // rpn_fine
            int lsb = cc == 38 ? v : 0;
            fine[ch] = (double)(((fine_msb[ch] << 7) | lsb) - 8192) / 8192.0 * 100.0;
        } else if (l == 2) {
            if (cc != 6)
                return;
            coarse[ch] = (double)(v - 64);          // rpn_coarse
        } else if (l == 5) {
            double cur = modrange[ch] >= 0.0 ? modrange[ch] : mod_cents;
            modrange[ch] = cc == 6 ? (double)v * 100.0 : (double)(long)floor(cur / 100.0) * 100.0 + v * (100.0 / 128.0);
            return;                                 // (a piano's wheel takes no vibrato to re-send)
        } else {
            return;                                 // MTS: a gm2 part's
        }
        repitch(ch, n0);
    }

    // live._rpn_step: CC96 (up) / CC97, the selected RPN one unit of its finest byte
    void rpn_step(int ch, bool up, long long n0)
    {
        if (rpn_none[ch] || rpn_msb[ch] != 0)
            return;
        int l = rpn_lsb[ch];
        double step, lo, hi;
        if (l == 3 || l == 4 || !rpn_step_of(l, &step, &lo, &hi))
            return;                                 // (MTS's: a gm2 part's)
        double cur = l == 0 ? range_of(ch) : l == 1 ? fine[ch] : l == 2 ? coarse[ch]
                                                                    : (modrange[ch] >= 0.0 ? modrange[ch] : mod_cents);
        double v = cur + (up ? step : -step);
        v = std::max(lo, v);                        // min(hi, max(lo, v)): Python keeps the first of equals
        v = std::min(hi, v);
        if (l == 2)
            v = (double)(long)nearbyint(v);
        if (l == 0) {
            brange[ch] = v;
        } else if (l == 1) {
            fine[ch] = v;
            long code = (long)nearbyint(v / 100.0 * 8192.0) + 8192;       // rpn_fine_msb
            fine_msb[ch] = (int)(std::max(0L, std::min(16383L, code)) >> 7);
        } else if (l == 2) {
            coarse[ch] = v;
        } else {
            modrange[ch] = v;
            return;
        }
        repitch(ch, n0);
    }

    // PANIC (live.panic, _all_off): every key let go over its own release,
    // what no key holds ended the same way (an orphan: busy, no key, not yet
    // ending -- noff at n0 plus its release delay), the keys and the pedal's
    // holds forgotten
    bool room_on = true;                            // the panel's: the tail on or off
    void panic(long long n0)
    {
        std::vector<Key> keys;
        for (auto &kv : S.live)
            keys.push_back(kv.first);
        for (const Key &k : keys) {
            S.oneshot.erase(k);
            S.release(k, n0);
        }
        std::vector<char> held(S.cap, 0);
        for (auto &kv : S.live)
            for (long q : kv.second)
                held[q] = 1;
        std::vector<long> orphan;
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q] && !held[q] && S.i8[1][q] == IDLE)
                orphan.push_back(q);
        for (long q : orphan)
            S.i8[1][q] = std::min(S.i8[1][q], n0 + (long long)S.f4[F4_rdl][q]);
        if (!orphan.empty())
            S.retiring.push_back(std::make_pair(orphan, n0));
        down.clear();
        pedalled.clear();
    }

    // CC120, ALL SOUND OFF (live's): the channel stopped now, pedal or no
    // pedal -- every key on it over the steal-fade, its keys, pedals and
    // sostenuto cleared, and its register killed (_reg_channel, kill)
    void all_sound_off(int ch, long long n0)
    {
        for (auto it = down.begin(); it != down.end();)
            it = it->first == ch ? down.erase(it) : std::next(it);
        for (auto it = pedalled.begin(); it != pedalled.end();)
            it = it->first == ch ? pedalled.erase(it) : std::next(it);
        sost.erase(ch);
        pedal_v[ch] = 0;
        float fade = (float)(retrigger * rate);
        std::vector<Key> keys;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch)
                keys.push_back(kv.first);
        for (const Key &k : keys) {
            long li = S.live_find(k);
            if (li >= 0)
                for (long q : S.live[li].second)
                    if (fade < S.f4[F4_re][q])
                        S.f4[F4_re][q] = fade;
            S.oneshot.erase(k);
            S.release(k, n0);
        }
        if (!reg_on)
            return;
        for (RegSt &st : reg) {
            if (st.ch != ch)
                continue;
            if (st.ready) {
                std::vector<long> on;
                for (long m = 0; m < (long)st.slot_of.size(); m++)
                    if (st.slot_of[m] >= 0)
                        on.push_back(m);
                reg_close(st, on, n0, retrigger * rate);
            }
            for (size_t i = 0; i < reg_strike_of.size();)
                if (reg_strike_of[i].first.first == ch)
                    reg_strike_of.erase(reg_strike_of.begin() + i);
                else
                    i++;
            Job j;
            j.kind = 2;
            j.ch = ch;
            for (int k = 21; k < 109; k++)
                j.keys.push_back(k);
            send_job(std::move(j));
        }
    }

    // CC123, ALL NOTES OFF (live's): the keys come up -- a note under a held
    // damper or the sostenuto rings on (pedalled), a one-shot on its own decay
    void all_notes_off(int ch, long long n0)
    {
        for (auto it = down.begin(); it != down.end();)
            it = it->first == ch ? down.erase(it) : std::next(it);
        auto sq = sost.find(ch);
        std::vector<Key> keys;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch)
                keys.push_back(kv.first);
        for (const Key &k : keys) {
            if (S.oneshot.count(k) && S.oneshot[k])
                continue;
            int nt = (int)std::get<2>(k);
            if (pedal_holds(ch, nt) || (sq != sost.end() && sq->second.count(nt))) {
                pedalled.insert(std::make_pair(ch, nt));
                continue;
            }
            S.release(k, n0);
        }
    }

    // live._reset_controllers (CC121): the wheel to centre, then CC1, CC11,
    // CC64, CC65, CC66, CC67 as live sends them, pressure off, no RPN
    // selected -- not the volume, pan, program or the tuning RPNs' values
    void reset_controllers(int ch, long long n0)
    {
        wheel[ch] = 0;
        repitch(ch, n0);
        static const int RESET_CC[6][2] = {{1, 0}, {11, 127}, {64, 0}, {65, 0}, {66, 0}, {67, 0}};
        for (auto &cv : RESET_CC)
            control(ch, cv[0], cv[1], n0);
        aftertouch(ch, 0);
        rpn_none[ch] = false;
        rpn_msb[ch] = rpn_lsb[ch] = 127;
    }

    // channel aftertouch: every key sounding on the channel (live's
    // _press_groups: the slab's keys in order, one tilt)
    void aftertouch(int ch, int v)
    {
        pressure[ch] = v / 127.0;
        press(sounding(ch), pressure[ch]);
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
            reg_felt(ch, n0);
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
                if (reg_on)                         // _reg_channel: the pedal came up
                    for (size_t i = 0; i < reg.size(); i++)
                        if (reg[i].ch == ch)
                            reg_damper(ch, n0, -1, true);
            }
        } else if (cc == 91) {
            // a DISTANCE (live's): CC91 over GM's 40 times the room's nominal
            // one, on the notes sounding too
            double d = v / 40.0;
            S.send[ch] = d;
            for (long q : sounding(ch))
                S.sw[q] = (float)d;
        } else if (cc == 67) {
            soft[ch] = v >= 64;
        } else if (cc == 66) {
            // SOSTENUTO: a snapshot of the keys down as it goes down; up, the
            // ones it held let go where nothing else holds them
            bool dn = v >= 64, was = sost.count(ch) > 0;
            if (dn && !was) {
                std::set<int> &h = sost[ch];
                for (auto &d : down)
                    if (d.first == ch)
                        h.insert(d.second);
            } else if (!dn && was) {
                std::set<int> gone = sost[ch];
                sost.erase(ch);
                std::vector<Key> rel;
                for (auto &kv : S.live) {
                    int c2 = (int)std::get<1>(kv.first), nt = (int)std::get<2>(kv.first);
                    if (c2 == ch && gone.count(nt) && !down.count(std::make_pair(c2, nt)) && !pedal_holds(ch, nt))
                        rel.push_back(kv.first);
                }
                for (auto &k : rel)
                    S.release(k, n0);
                for (int nt : gone)
                    pedalled.erase(std::make_pair(ch, nt));
                if (reg_on)                         // _reg_channel
                    for (size_t i = 0; i < reg.size(); i++)
                        if (reg[i].ch == ch)
                            reg_damper(ch, n0, -1, true);
            }
        } else if (cc == 98 || cc == 99) {
            rpn_none[ch] = true;                    // NRPN select: no RPN takes the data
        } else if (cc == 101 || cc == 100) {
            if (rpn_none[ch]) {
                rpn_none[ch] = false;
                rpn_msb[ch] = rpn_lsb[ch] = 127;
            }
            (cc == 101 ? rpn_msb : rpn_lsb)[ch] = v;
        } else if (cc == 6 || cc == 38) {
            rpn_data(ch, cc, v, n0);
        } else if (cc == 96 || cc == 97) {
            rpn_step(ch, cc == 96, n0);
        } else if (cc == 121) {
            reset_controllers(ch, n0);
        } else if (cc == 120) {
            all_sound_off(ch, n0);
        } else if (cc == 123) {
            all_notes_off(ch, n0);
        } else if (cc >= 124 && cc <= 127) {
            // CHANNEL MODE, as live sends it: all four are All Notes Off, MONO
            // and POLY All Sound Off first; MONO (126) one voice on the
            // channel, POLY (127) as many as it plays
            if (cc >= 126)
                all_sound_off(ch, n0);
            all_notes_off(ch, n0);
            mono_stack[ch].clear();
            mono_cur[ch] = -1;
            if (cc == 126)
                mono[ch] = true;
            else if (cc == 127)
                mono[ch] = false;
        } else if (cc == 1 && detune_wheel) {
            static const int steps[3] = {0, 64, 127};       // live.DETUNE_STEPS: min(), the first of a tie
            int best = steps[0];
            for (int st : steps)
                if (abs(st - v) < abs(best - v))
                    best = st;
            speed = best;
        }
    }

    // THE DAMPERS IN BETWEEN (live._damp_block, _damp_open, _damp_mark;
    // damper.py): a pedalled note whose key's contact is in the band takes a
    // TRACK -- its damping so far at the block's two edges, DM -- its rows
    // marked with it (the slab's dk, and dg their weight). A track stays with
    // its note while any row of it sounds. Track numbers are handed out in
    // `pedalled`'s order, which is not live's (a Python set's): the same
    // tracks under other numbers, the same sound.
    static const int DAMP_TRACKS = 256;     // live.DAMP_TRACKS
    bool dmp_on = false;
    double dmp_full = 0.0, dmp_res = 0.0, dmp_knee = 0.0, dmp_beta = 0.0, dmp_ln = 0.0;
    struct DTrack {
        int t;
        double dc, f0, non, lr, lra, af, su, vdb;
        std::set<Key> keys;
        std::vector<long> slots;            // sorted (np.union1d)
    };
    std::vector<std::pair<std::pair<int, int>, DTrack>> dtracks;   // live's damp_tracks, in its order
    std::vector<int> free_tracks;
    std::vector<float> DM = std::vector<float>(2 * DAMP_TRACKS, 0.0f);
    std::vector<long> DMO = std::vector<long>(DAMP_TRACKS, 0), DMB = std::vector<long>(DAMP_TRACKS, 0),
                      DMN = std::vector<long>(DAMP_TRACKS, 2);

    long dtrack_find(int ch, int note) const
    {
        for (size_t i = 0; i < dtracks.size(); i++)
            if (dtracks[i].first == std::make_pair(ch, note))
                return (long)i;
        return -1;
    }

    void damp_block(long long n0, long long frames)
    {
        if (!dmp_on)
            return;
        bool any = !dtracks.empty();
        for (int c = 0; c < 16 && !any; c++)
            any = pedal_v[c] > 0 && pedal_v[c] < 127;
        if (!any)
            return;
        double dt = frames / rate;
        for (const auto &cn : pedalled) {
            int ch = cn.first, note = cn.second;
            double c = nv_damper_contact(pedal_v[ch], note, 128);
            std::vector<Key> ks;
            for (auto &kv : S.live)
                if (std::get<1>(kv.first) == ch && std::get<2>(kv.first) == note)
                    ks.push_back(kv.first);
            for (const Key &k : ks) {
                long i = dtrack_find(ch, note);
                if (i < 0) {
                    if (!(0.0 < c && c < 1.0) || free_tracks.empty())
                        continue;
                    i = damp_open(ch, note);
                    if (i < 0)
                        continue;
                }
                if (!dtracks[i].second.keys.count(k))
                    damp_mark(dtracks[i].second, k);
            }
        }
        for (size_t i = 0; i < dtracks.size();) {
            DTrack &st = dtracks[i].second;
            std::vector<long> alive;
            for (long q : st.slots)
                if (S.busy[q] && S.dk[q] == st.t)
                    alive.push_back(q);
            if (alive.empty()) {
                free_tracks.push_back(st.t);
                dtracks.erase(dtracks.begin() + i);
                continue;
            }
            st.slots = alive;
            int ch = dtracks[i].first.first, note = dtracks[i].first.second;
            double c = pedalled.count(dtracks[i].first) ? nv_damper_contact(pedal_v[ch], note, 128) : 0.0;
            double d0 = st.dc;
            if (0.0 < c && c < 1.0) {
                double x = std::max(((double)n0 - st.non) / rate, 0.0);
                double dc = st.su + (1.0 - st.su) * ((1.0 - st.af) * exp(-st.lr * x) + st.af * exp(-st.lra * x));
                double lvl = st.vdb + 20.0 * log10(dc >= 1e-12 ? dc : 1e-12) - d0;
                double thr = -dmp_knee * c / (1.0 - c);         // damper.threshold_db
                double r = dmp_full * c;                        // damper.rate_db_s
                st.dc = d0 + (lvl > thr ? r : r * dmp_res) * dt;
            }
            DM[2 * st.t] = (float)d0;
            DM[2 * st.t + 1] = (float)st.dc;
            i++;
        }
    }

    // a track for this pressed-and-pedalled key: its level model from its
    // fundamental's decay and the strike's velocity (live._damp_open)
    long damp_open(int ch, int note)
    {
        std::vector<long> rows;
        std::vector<Key> ks;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch && std::get<2>(kv.first) == note) {
                ks.push_back(kv.first);
                rows.insert(rows.end(), kv.second.begin(), kv.second.end());
            }
        if (rows.empty())
            return -1;
        double f0 = 440.0 * pow(2.0, (note - 69) / 12.0);
        long j = rows[0];
        double best = 0.0;
        for (size_t q = 0; q < rows.size(); q++) {
            double nf = (double)S.f4[F4_nf][rows[q]];
            double d = fabs(log((nf >= 1e-3 ? nf : 1e-3) / f0));
            if (q == 0 || d < best) {
                best = d;
                j = rows[q];
            }
        }
        DTrack st;
        st.t = free_tracks.back();
        free_tracks.pop_back();
        st.dc = 0.0;
        st.f0 = f0;
        st.non = (double)S.i8[0][j];
        st.lr = S.f4[F4_logr][j];
        st.lra = S.f4[F4_logrA][j];
        st.af = S.f4[F4_aft][j];
        st.su = S.f4[F4_sus][j];
        auto kv = key_vel.find(std::make_pair(ch, note));
        int vel = kv == key_vel.end() ? 100 : kv->second;
        st.vdb = 40.0 * log10((vel > 1 ? vel : 1) / 127.0);
        DM[2 * st.t] = DM[2 * st.t + 1] = 0.0f;
        dtracks.emplace_back(std::make_pair(ch, note), st);
        long i = (long)dtracks.size() - 1;
        for (const Key &k : ks)
            damp_mark(dtracks[i].second, k);
        return i;
    }

    // this slab key's rows onto the track: its index, each row's weight
    void damp_mark(DTrack &st, const Key &k)
    {
        st.keys.insert(k);
        long li = S.live_find(k);
        if (li < 0 || S.live[li].second.empty())
            return;
        for (long q : S.live[li].second) {
            S.dk[q] = st.t;
            double x = std::max((double)S.f4[F4_nf][q], 1e-6) / std::max(st.f0, 1e-6);
            S.dg[q] = (float)(dmp_ln * pow(x, dmp_beta));     // damper.weight
            st.slots.insert(std::lower_bound(st.slots.begin(), st.slots.end(), q), q);
        }
        st.slots.erase(std::unique(st.slots.begin(), st.slots.end()), st.slots.end());
    }

    // THE FREE-STRING REGISTER, LIVE (live._reg_strike, _reg_damper, _reg_felt,
    // _reg_channel, _reg_pump, _reg_place, _reg_close): one register channel
    // per MIDI channel (register.LiveChannel, livereg.cpp), its free rows the
    // register's own slots, one per string mode, retired once -- at its
    // damper or under the floor; its forced rows on their note's key (layer
    // REG_FORCED), going when it does.
    typedef std::complex<double> cplx;
    static const long long REG_KEY = -2, REG_FORCED = -3;      // live's "reg" and REG_FORCED layers
    static const long REG_PLACE_MAX = 256;
    bool reg_on = false;
    std::vector<StringMode> rmodes;
    double r_kappa = 0, r_knock = 0, r_fall = 0, r_fl = 0, r_beta = 0, r_rel = 0, r_full = 0, r_resid = 0,
           r_ln = 0, r_blk = 128;
    int r_top = 128, r_pedals = 1;
    bool reg_note[128];
    struct RegSt {
        int ch;
        bool ready = false;
        double row_f8[NF8], row_f4[NF4];
        int32_t row_i4[NI4];
        std::vector<long> slot_of;
        std::vector<double> n_floor, krate, dw;
        bool has_krate = false;
        std::map<int, double> krate_key;
    };
    std::vector<RegSt> reg;                         // by channel, as made (live's self.reg)
    struct Pend {
        int ch;
        long long sid;
        int note;
        long long at;
        std::vector<long> slots;
    };
    std::vector<Pend> reg_pend;
    struct Reply {
        int kind;                                   // 0 'free', 1 'forced'
        int ch, note;
        std::vector<long> modes;
        std::vector<cplx> z;
        double at, floor;
        std::vector<long> f_slot;
        std::vector<double> f_wgt, f_beta;
        std::vector<cplx> f_val;
    };
    std::deque<Reply> reg_out;
    std::vector<std::pair<std::pair<int, int>, long long>> reg_strike_of;      // (ch, note) -> sid, a dict's order
    std::vector<std::pair<long long, std::vector<long>>> reg_retire;          // n0 -> slots closed, a dict's order
    long long reg_sid = 0;
    bool reg_live = false, reg_more = false;
    long reg_budget = 0, reg_dropped = 0;

    // THE WORKER'S JOBS (live's reg_jobs: 'strike', 'release', 'damp',
    // 'felt'), each answered onto a queue of Replies by run_job -- at once,
    // into reg_out, when the register runs in step (the checks: live's
    // worker as regsync answers it); or on a worker thread of its own
    // (reg_async, nvlive: live's worker process, off the audio thread), its
    // answers taken up at the next pump after they are ready
    struct Job {
        int kind;                                   // 0 strike, 1 release, 2 damp, 3 felt
        int ch, note = -1, R = 0;
        long long sid = 0;
        double at = 0.0;
        std::vector<double> cols, rates;
        std::vector<long> d;
        std::vector<int> keys;
    };
    std::map<int, void *> lcs;                      // channel -> its register (the worker's chans)
    bool reg_async = false;
    std::thread reg_thread;
    std::mutex reg_mu;
    std::condition_variable reg_cv;
    std::deque<Job> reg_jobs;
    std::deque<Reply> reg_done;
    std::atomic<long> reg_ndone{0};
    bool reg_stop = false;

    ~Piano()
    {
        if (reg_thread.joinable()) {
            {
                std::lock_guard<std::mutex> lk(reg_mu);
                reg_stop = true;
            }
            reg_cv.notify_all();
            reg_thread.join();
        }
        for (auto &kv : lcs)
            nv_lreg_free(kv.second);
    }

    void *lc_of(int ch)
    {
        auto it = lcs.find(ch);
        if (it != lcs.end())
            return it->second;
        void *h = nv_lreg_new(rmodes.data(), (int)rmodes.size(), rate, r_kappa, r_knock, r_fall, r_fl, r_top, r_beta);
        lcs[ch] = h;
        return h;
    }

    // a 'free' answer (the job's at sample `at`) onto out -- always, or only
    // with modes in it; returns the strike's forced rows
    int answer(int ch, void *lc, int n, double at, bool always, std::deque<Reply> &out)
    {
        Reply r;
        r.kind = 0;
        r.ch = ch;
        r.note = -1;
        r.at = at;
        r.modes.resize(n);
        std::vector<double> zz(2 * (size_t)n + 2);
        double fl;
        int nf = nv_lreg_answer(lc, r.modes.data(), zz.data(), &fl);
        r.z.resize(n);
        for (int q = 0; q < n; q++)
            r.z[q] = cplx(zz[2 * q], zz[2 * q + 1]);
        r.floor = fl;
        if (always || n)
            out.push_back(std::move(r));
        return nf;
    }

    void run_job(const Job &j, std::deque<Reply> &out)
    {
        void *lc = lc_of(j.ch);
        if (j.kind == 0) {
            int n = nv_lreg_strike(lc, j.sid, j.note, j.at, j.R, j.cols.data(), j.d.data(), j.keys.data(),
                                   (int)j.keys.size());
            int nf = answer(j.ch, lc, n, j.at, true, out);
            if (nf) {
                Reply r;
                r.kind = 1;
                r.ch = j.ch;
                r.note = j.note;
                r.at = j.at;
                r.f_slot.resize(nf); r.f_wgt.resize(nf); r.f_beta.resize(nf);
                std::vector<double> v(2 * (size_t)nf);
                nv_lreg_forced(lc, r.f_slot.data(), r.f_wgt.data(), r.f_beta.data(), v.data());
                for (int q = 0; q < nf; q++)
                    r.f_val.push_back(cplx(v[2 * q], v[2 * q + 1]));
                out.push_back(std::move(r));
            }
        } else if (j.kind == 1) {
            answer(j.ch, lc, nv_lreg_release(lc, j.sid, j.at, j.keys.data(), (int)j.keys.size()), j.at, true, out);
        } else if (j.kind == 2) {
            nv_lreg_damp(lc, j.keys.data(), (int)j.keys.size());
        } else {
            answer(j.ch, lc, nv_lreg_felt(lc, j.at, j.keys.data(), j.rates.data(), (int)j.keys.size()), j.at, false,
                   out);
        }
    }

    void send_job(Job &&j)
    {
        if (!reg_async) {
            run_job(j, reg_out);
            return;
        }
        {
            std::lock_guard<std::mutex> lk(reg_mu);
            reg_jobs.push_back(std::move(j));
        }
        reg_cv.notify_one();
    }

    void reg_worker()
    {
        std::unique_lock<std::mutex> lk(reg_mu);
        while (true) {
            reg_cv.wait(lk, [&] { return reg_stop || !reg_jobs.empty(); });
            if (reg_stop)
                return;
            Job j = std::move(reg_jobs.front());
            reg_jobs.pop_front();
            lk.unlock();
            std::deque<Reply> out;
            run_job(j, out);
            lk.lock();
            for (Reply &r : out)
                reg_done.push_back(std::move(r));
            reg_ndone = (long)reg_done.size();
        }
    }

    void start_reg_worker()
    {
        if (reg_async)
            return;
        reg_async = true;
        reg_thread = std::thread([this] { reg_worker(); });
    }

    // the worker's answers so far, onto reg_out (the audio thread)
    void reg_collect()
    {
        if (!reg_async || reg_ndone.load() == 0)
            return;
        std::lock_guard<std::mutex> lk(reg_mu);
        for (Reply &r : reg_done)
            reg_out.push_back(std::move(r));
        reg_done.clear();
        reg_ndone = 0;
    }

    RegSt *reg_of(int ch)
    {
        for (RegSt &st : reg)
            if (st.ch == ch)
                return &st;
        return nullptr;
    }

    long strike_of_find(int ch, int note) const
    {
        for (size_t i = 0; i < reg_strike_of.size(); i++)
            if (reg_strike_of[i].first == std::make_pair(ch, note))
                return (long)i;
        return -1;
    }

    // _reg_free: the keys whose strings are free on this channel, now (sorted)
    std::vector<int> reg_free(int ch) const
    {
        std::set<int> keys;
        if (r_pedals && pedal_v[ch] > 0) {
            std::vector<int> held;
            for (int k = 21; k < 109; k++)
                if (nv_damper_contact(pedal_v[ch], k, r_top) < 1.0)
                    held.push_back(k);
            if (held.size() == 88)
                return held;
            keys.insert(held.begin(), held.end());
        }
        for (auto &d : down)
            if (d.first == ch)
                keys.insert(d.second);
        auto sq = sost.find(ch);
        if (r_pedals && sq != sost.end())
            keys.insert(sq->second.begin(), sq->second.end());
        for (int k = r_top; k < 109; k++)
            keys.insert(k);
        return std::vector<int>(keys.begin(), keys.end());
    }

    void reg_strike(int ch, int note, long long n0, const nv::live::Template &T, const std::vector<long> &slots)
    {
        if (!reg_of(ch)) {
            RegSt st;
            st.ch = ch;
            for (int c = 0; c < NF8; c++) st.row_f8[c] = T.f8[c][0];
            for (int c = 0; c < NF4; c++) st.row_f4[c] = T.f4[c][0];
            for (int c = 0; c < NI4; c++) st.row_i4[c] = T.i4[c][0];
            reg.push_back(st);
        }
        reg_sid += 1;
        long i = strike_of_find(ch, note);
        if (i >= 0)
            reg_strike_of[i].second = reg_sid;
        else
            reg_strike_of.push_back(std::make_pair(std::make_pair(ch, note), reg_sid));
        reg_pend.push_back(Pend{ch, reg_sid, note, n0, slots});
    }

    void reg_close(RegSt &st, const std::vector<long> &modes, long long n0, double re_)
    {
        if (modes.empty())
            return;
        std::vector<long> sl;
        for (long m : modes) {
            long s = st.slot_of[m];
            st.slot_of[m] = -1;
            if (S.busy[s])
                sl.push_back(s);
        }
        if (sl.empty())
            return;
        for (long s : sl) {
            S.i8[1][s] = n0;
            S.f4[F4_re][s] = (float)re_;
        }
        for (auto &e : reg_retire)
            if (e.first == n0) {
                e.second.insert(e.second.end(), sl.begin(), sl.end());
                return;
            }
        reg_retire.push_back(std::make_pair(n0, sl));
    }

    void reg_damper(int ch, long long n0, int released, bool pedal_up)
    {
        RegSt *st = reg_of(ch);
        if (!st)
            return;
        std::vector<int> fv = reg_free(ch);
        std::set<int> free(fv.begin(), fv.end());
        if (released >= 0 && !free.count(released)) {
            long i = strike_of_find(ch, released);
            if (i >= 0) {
                long long sid = reg_strike_of[i].second;
                reg_strike_of.erase(reg_strike_of.begin() + i);
                Job j;
                j.kind = 1; j.ch = ch; j.sid = sid; j.at = (double)n0; j.keys = fv;
                send_job(std::move(j));
            }
        }
        if (pedal_up) {
            std::vector<std::pair<std::pair<int, int>, long long>> was = reg_strike_of;
            for (auto &e : was) {
                if (e.first.first != ch || free.count(e.first.second))
                    continue;
                reg_strike_of.erase(reg_strike_of.begin() + strike_of_find(e.first.first, e.first.second));
                Job j;
                j.kind = 1; j.ch = ch; j.sid = e.second; j.at = (double)n0; j.keys = fv;
                send_job(std::move(j));
            }
        }
        if (st->ready) {
            std::vector<long> dead;
            for (long m = 0; m < (long)rmodes.size(); m++)
                if (!free.count((int)rmodes[m].key) && st->slot_of[m] >= 0)
                    dead.push_back(m);
            reg_close(*st, dead, n0, r_rel);
        }
        Job j;
        j.kind = 2;
        j.ch = ch;
        for (int k = 21; k < 109; k++)
            if (!free.count(k))
                j.keys.push_back(k);
        send_job(std::move(j));
    }

    void reg_felt(int ch, long long n0)
    {
        if (!reg_on)
            return;
        int v = pedal_v[ch];
        for (RegSt &st : reg) {
            if (st.ch != ch || !st.ready || !r_pedals)
                continue;
            std::vector<int> keys;
            std::vector<double> rates;
            for (int k = 21; k < 109; k++) {
                double c = nv_damper_contact(v, k, r_top);
                double r = (0.0 < c && c < 1.0) ? r_full * c * r_resid * r_ln : 0.0;
                auto it = st.krate_key.find(k);
                if (r != (it == st.krate_key.end() ? 0.0 : it->second)) {
                    st.krate_key[k] = r;
                    keys.push_back(k);
                    rates.push_back(r);
                }
            }
            if (keys.empty())
                continue;
            if (!st.has_krate) {
                st.has_krate = true;
                st.krate.assign(rmodes.size(), 0.0);
                for (const StringMode &q : rmodes) {
                    double f0 = 440.0 * pow(2.0, ((double)q.key - 69.0) / 12.0);
                    st.dw.push_back(pow((q.f >= 1e-6 ? q.f : 1e-6) / f0, r_beta));
                }
            }
            for (size_t q = 0; q < keys.size(); q++)
                for (size_t m = 0; m < rmodes.size(); m++)
                    if (rmodes[m].key == keys[q])
                        st.krate[m] = rates[q] * st.dw[m];
            Job j;
            j.kind = 3; j.ch = st.ch; j.at = (double)n0; j.keys = keys; j.rates = rates;
            send_job(std::move(j));
        }
    }

    void reg_pump(long long n0)
    {
        for (RegSt &st : reg) {
            if (!st.ready) {
                st.slot_of.assign(rmodes.size(), -1);
                st.n_floor.assign(rmodes.size(), 0.0);
                st.ready = true;
                reg_felt(st.ch, n0);            // a pedal already in the band
            }
        }
        // this block's strikes: their stamped direct rows, read now, and the keys free now
        std::vector<Pend> pend;
        pend.swap(reg_pend);
        for (const Pend &p : pend) {
            std::vector<long> idx;
            for (long s : p.slots)
                if (S.busy[s])
                    idx.push_back(s);
            if (idx.empty())
                continue;
            double mn = 0.0;
            std::vector<double> dl(idx.size());
            for (size_t q = 0; q < idx.size(); q++) {
                dl[q] = (double)S.f4[F4_delL][idx[q]] + (double)S.f4[F4_delR][idx[q]];
                if (q == 0 || dl[q] < mn)
                    mn = dl[q];
            }
            std::vector<long> d;
            for (size_t q = 0; q < idx.size(); q++)
                if (dl[q] <= mn + 2.0)
                    d.push_back(idx[q]);
            int R = (int)d.size();
            // drv's columns, livereg.cpp's order: om p0 delL aM non logr logrA aft sus tbav tau tcut
            std::vector<double> cols(12 * (size_t)R);
            static const int f4c[] = {6, 7, 8, 9, 16, 17, 18};      // logr logrA aft sus tbav tau tcut
            for (int r = 0; r < R; r++) {
                long s = d[r];
                cols[0 * R + r] = S.f8[F8_om][s];
                cols[1 * R + r] = S.f8[F8_p0][s];
                cols[2 * R + r] = (double)S.f4[F4_delL][s];
                cols[3 * R + r] = 0.5 * ((double)S.aL0[s] + (double)S.aR0[s]);
                cols[4 * R + r] = (double)S.i8[0][s];
                for (int c = 0; c < 7; c++)
                    cols[(5 + c) * R + r] = (double)S.f4[f4c[c]][s];
            }
            Job j;
            j.kind = 0; j.ch = p.ch; j.sid = p.sid; j.note = p.note; j.at = (double)p.at; j.R = R;
            j.cols.swap(cols);
            j.d.swap(d);
            j.keys = reg_free(p.ch);
            send_job(std::move(j));
        }
        reg_collect();
        // what the worker handed back: until a block's worth is placed
        reg_more = false;
        reg_budget = REG_PLACE_MAX;
        while (!reg_out.empty() && !reg_more) {
            Reply r = std::move(reg_out.front());
            reg_out.pop_front();
            reg_place(n0, r);
        }
        // rows fallen under the floor: ended
        if (reg_live) {
            bool live_ = false;
            for (RegSt &st : reg) {
                if (!st.ready)
                    continue;
                bool on = false;
                std::vector<long> done;
                for (size_t m = 0; m < st.slot_of.size(); m++)
                    if (st.slot_of[m] >= 0) {
                        on = true;
                        if (st.n_floor[m] <= (double)n0)
                            done.push_back((long)m);
                    }
                if (on) {
                    reg_close(st, done, n0, (double)r_blk);
                    for (long x : st.slot_of)
                        if (x >= 0) {
                            live_ = true;
                            break;
                        }
                }
            }
            reg_live = live_;
        }
        for (auto &e : reg_retire)
            S.retiring.push_back(std::make_pair(e.second, e.first));
        reg_retire.clear();
    }

    void reg_place(long long n0, Reply &job)
    {
        RegSt *stp = reg_of(job.ch);
        if (!stp || !stp->ready)
            return;
        RegSt &st = *stp;
        if (job.kind == 0) {
            // ONLY STRINGS STILL FREE NOW
            if (!job.modes.empty()) {
                std::vector<int> fv = reg_free(job.ch);
                std::set<int> free(fv.begin(), fv.end());
                std::vector<long> m2;
                std::vector<cplx> z2;
                for (size_t q = 0; q < job.modes.size(); q++)
                    if (free.count((int)rmodes[job.modes[q]].key)) {
                        m2.push_back(job.modes[q]);
                        z2.push_back(job.z[q]);
                    }
                job.modes.swap(m2);
                job.z.swap(z2);
            }
            if (job.modes.empty())
                return;
            long nb = std::max(reg_budget, 1L);
            if ((long)job.modes.size() > nb) {
                // A BLOCK'S WORTH AT A TIME: the rest waits a block
                Reply rest = job;
                rest.modes.assign(job.modes.begin() + nb, job.modes.end());
                rest.z.assign(job.z.begin() + nb, job.z.end());
                reg_out.push_front(std::move(rest));
                job.modes.resize(nb);
                job.z.resize(nb);
                reg_more = true;
            }
            reg_budget -= (long)job.modes.size();
            if (reg_budget <= 0)
                reg_more = true;
            std::vector<long> old;
            for (long m : job.modes)
                if (st.slot_of[m] >= 0)
                    old.push_back(m);
            reg_close(st, old, n0, (double)r_blk);
            // each mode's rate: its own, and the felt's in the band
            double dt = (double)n0 - job.at;
            dt = 0.0 > dt ? 0.0 : dt;                               // Python's max(n0 - at, 0.0)
            std::vector<long> modes;
            std::vector<cplx> zz;
            std::vector<double> lr;
            for (size_t q = 0; q < job.modes.size(); q++) {
                long m = job.modes[q];
                double l = st.has_krate ? rmodes[m].alpha + st.krate[m] : rmodes[m].alpha;
                double g = exp(-l * dt / rate);
                cplx a(job.z[q].real() * g - job.z[q].imag() * 0.0, job.z[q].real() * 0.0 + job.z[q].imag() * g);
                if (hypot(a.real(), a.imag()) >= job.floor) {
                    modes.push_back(m);
                    zz.push_back(a);
                    lr.push_back(l);
                }
            }
            long n = (long)modes.size();
            if (!n)
                return;
            // the rows: the template's first, with the mode's own pitch, level, ears and decay
            std::vector<std::vector<double>> tf8(NF8, std::vector<double>(n));
            std::vector<std::vector<float>> tf4(NF4, std::vector<float>(n));
            std::vector<std::vector<long long>> ti8(NI8, std::vector<long long>(n, n0));
            std::vector<std::vector<int32_t>> ti4(NI4, std::vector<int32_t>(n));
            std::vector<float> hr(n, 1.0f);
            double hd = S.headroom_d > 1e-12 ? S.headroom_d : 1e-12;
            static const int zero4[] = {7, 8, 9, 10, 13, 12, 14, 15, 16, 18, 19, 24};   // logrA aft sus cv sj crl csc cbw tbav tcut vd az
            for (long q = 0; q < n; q++) {
                long m = modes[q];
                const StringMode &M_ = rmodes[m];
                for (int c = 0; c < NF8; c++) tf8[c][q] = st.row_f8[c];
                for (int c = 0; c < NF4; c++) tf4[c][q] = (float)st.row_f4[c];
                for (int c = 0; c < NI4; c++) ti4[c][q] = st.row_i4[c];
                double om = (2.0 * M_PI * M_.f) / rate;
                double ph = atan2(zz[q].imag(), zz[q].real());
                double mag = hypot(zz[q].real(), zz[q].imag()) / hd;
                tf8[F8_om][q] = om;
                tf8[F8_p0][q] = ph - om * M_.dl;
                tf8[F8_p0R][q] = ph - om * M_.dr;
                tf4[F4_aL][q] = (float)(mag * M_.hl);
                tf4[F4_aR][q] = (float)(mag * M_.hr);
                tf4[F4_nf][q] = (float)M_.f;
                tf4[26][q] = (float)M_.f;                           // nfr
                tf4[3][q] = (float)r_blk;                           // fa
                tf4[6][q] = (float)lr[q];                           // logr
                tf4[F4_delL][q] = (float)M_.dl;
                tf4[F4_delR][q] = (float)M_.dr;
                tf4[F4_rdl][q] = 0.0f;
                for (int c : zero4)
                    tf4[c][q] = 0.0f;
                ti4[3][q] = (int32_t)M_.string;                     // pl
                ti4[I4_fx][q] = -1;
                ti4[5][q] = 0;                                      // mk
            }
            const double *f8p[NF8];
            const float *f4p[NF4];
            const long long *i8p[NI8];
            const int32_t *i4p[NI4];
            for (int c = 0; c < NF8; c++) f8p[c] = tf8[c].data();
            for (int c = 0; c < NF4; c++) f4p[c] = tf4[c].data();
            for (int c = 0; c < NI8; c++) i8p[c] = ti8[c].data();
            for (int c = 0; c < NI4; c++) i4p[c] = ti4[c].data();
            Key key(pid, job.ch, REG_KEY, REG_KEY);
            if (!S.stamp(f8p, f4p, i8p, i4p, hr.data(), n, key, n0, 1.0, 0, false, NAN, job.ch)) {
                reg_dropped += n;
                return;
            }
            std::vector<long> got = S.last_slots;
            long li = S.live_find(key);
            if (li >= 0)
                S.live.erase(S.live.begin() + li);         // the register keeps its own slots
            if (cpan[job.ch] != 64)
                S.repan(got, cpan[job.ch], 64, rate, true);
            for (long q = 0; q < n; q++) {
                long m = modes[q];
                st.slot_of[m] = got[q];
                double a = hypot(zz[q].real(), zz[q].imag()) / job.floor;
                st.n_floor[m] = (double)n0 + rate * log(a >= 1.0 ? a : 1.0) / (lr[q] >= 1e-9 ? lr[q] : 1e-9);
            }
            reg_live = true;
            return;
        }
        // 'forced': its note still sounding -- and still ITS note
        double win = 0.05 * rate;
        std::vector<long> sl;
        std::vector<double> wgt, beta;
        std::vector<cplx> F;
        for (size_t q = 0; q < job.f_slot.size(); q++) {
            long s = job.f_slot[q];
            double age = (double)(S.i8[0][s]) - job.at;                // float(non - at)
            double d = age - (double)S.f4[F4_rdl][s];
            if (S.busy[s] && S.i8[1][s] >= n0 && 0.0 <= d && d <= win) {
                sl.push_back(s);
                wgt.push_back(job.f_wgt[q]);
                beta.push_back(job.f_beta[q]);
                F.push_back(job.f_val[q]);
            }
        }
        if (sl.empty())
            return;
        reg_budget -= (long)sl.size();
        if (reg_budget <= 0)
            reg_more = true;
        long n = (long)sl.size();
        std::vector<std::vector<double>> tf8(NF8, std::vector<double>(n));
        std::vector<std::vector<float>> tf4(NF4, std::vector<float>(n));
        std::vector<std::vector<long long>> ti8(NI8, std::vector<long long>(n, n0));
        std::vector<std::vector<int32_t>> ti4(NI4, std::vector<int32_t>(n));
        std::vector<float> hr(n, 1.0f);
        double hd = S.headroom_d > 1e-12 ? S.headroom_d : 1e-12;
        for (long q = 0; q < n; q++) {
            long s = sl[q];
            for (int c = 0; c < NF8; c++) tf8[c][q] = S.f8[c][s];
            for (int c = 0; c < NF4; c++) tf4[c][q] = S.f4[c][s];
            for (int c = 0; c < NI4; c++) ti4[c][q] = S.i4[c][s];
            double a0 = (double)n0 - (double)S.i8[0][s];
            double age = (a0 >= 0.0 ? a0 : 0.0) / rate;
            double g = hypot(F[q].real(), F[q].imag()) * wgt[q] * exp(-beta[q] * age) / hd;
            double om = S.f8[F8_om][s];
            double ph = atan2(F[q].imag(), F[q].real())
                        + glide_phase(om * rate, (double)S.f4[16][s], (double)S.f4[17][s], (double)S.f4[18][s], age);
            tf4[F4_aL][q] = (float)((double)S.aL0[s] * g);
            tf4[F4_aR][q] = (float)((double)S.aR0[s] * g);
            tf8[F8_p0][q] = S.f8[F8_p0][s] + ph;
            tf8[F8_p0R][q] = S.f8[F8_p0R][s] + ph;
            tf4[3][q] = (float)r_blk;                                   // fa
            tf4[6][q] = (float)beta[q];                                 // logr
            tf4[7][q] = 0.0f;                                           // logrA
            tf4[8][q] = 0.0f;                                           // aft
            tf4[9][q] = beta[q] > 0 ? 0.0f : 1.0f;                      // sus
            tf4[16][q] = 0.0f;                                          // tbav
            tf4[F4_rdl][q] = 0.0f;
        }
        const double *f8p[NF8];
        const float *f4p[NF4];
        const long long *i8p[NI8];
        const int32_t *i4p[NI4];
        for (int c = 0; c < NF8; c++) f8p[c] = tf8[c].data();
        for (int c = 0; c < NF4; c++) f4p[c] = tf4[c].data();
        for (int c = 0; c < NI8; c++) i8p[c] = ti8[c].data();
        for (int c = 0; c < NI4; c++) i4p[c] = ti4[c].data();
        if (!S.stamp(f8p, f4p, i8p, i4p, hr.data(), n, Key(pid, job.ch, job.note, REG_FORCED), n0, 1.0, 0, false,
                     NAN, job.ch))
            reg_dropped += n;
    }

    // register._glide_phase_x
    static double glide_phase(double Wi, double tb, double tau, double cut, double t)
    {
        double ct = cut < 0 ? -cut * 1048576.0 : cut;
        double e = exp(-(!(ct < t) ? t : ct) / tau);
        if (cut >= 0)
            return Wi * tb * tau * (1.0 - e);
        double acc = 0.0, term = 1.0, ek = 1.0;
        for (int k = 1; k < 41; k++) {
            term = term * tb / k;
            ek = ek * e;
            acc = acc + term * (1.0 - ek) / k;
        }
        return Wi * tau * acc;
    }

    // LIVE'S SIDE TABLES (live.Slab's, at rest: a piano never moves them)
    // and its render over the slab (Renderer.render, one thread): every slot
    // from 0 past the last busy one through synth_voice, the fast bursts
    // apart through synth_voice_xdec (synth_partials' _xdec_rows), and the
    // rows on a damper track after them through synth_voice_damp (sd)
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

    // THE GPU'S BLOCK (live.GpuRenderer._render_now, gpurender.BlockTables):
    // the setup on the CPU, voice_block over every busy slot (through the
    // damper's build, its tracks handed over first, when one of them is on a
    // track), into page-aligned tables that grow when a block asks for more
    // cells or sidebands -- then the samples: the OpenCL GPU (gpu.cpp) or
    // the C reference (voice_samples)
    struct Table {
        void *p = nullptr;
        long n = 0, size = 0;           // records, and each one's bytes
        ~Table() { free(p); }
        // gpurender.aligned_zeros: n records, whole pages and whole records
        void make(long want, long sz)
        {
            long a = 4096, b = sz;
            while (b) {
                long t = a % b;
                a = b;
                b = t;
            }
            long per = 4096 / a;                    // lcm(4096, sz) / sz
            long m = std::max((std::max(want, 1L) + per - 1) / per * per, per);
            free(p);
            p = aligned_alloc(4096, (size_t)(m * sz));
            memset(p, 0, (size_t)(m * sz));
            n = m;
            size = sz;
        }
        long bytes() const { return n * size; }
    };
    struct GpuSide {
        void *vb = nullptr, *vbd = nullptr, *vds = nullptr, *vs = nullptr, *cl = nullptr;
        long gpu_min = 1000;
        int nthr = 4;
        Table D, C, SB;
        Table D2, C2, SB2;              // the pipeline's second set (its blocks take turns)
    } gp;
    // PIPELINED (live.GpuRenderer, TUNING_GPU_PIPELINE): every block a block
    // late, so the CPU builds block n+1's tables while the GPU renders block
    // n -- the block started (rendered on the CPU and held, or launched on
    // the GPU in its turn's tables) and the one started before it finished
    bool pipeline = false;
    int turn = 0;
    struct GpuPend {
        int kind = 0;                   // 0 none (the first block), 1 done on the CPU, 2 on the GPU
        int slot = 0;
        bool snd = false;
        std::vector<float> L, R, SL, SR;
    } gpend;
    bool on_gpu = false;                // did the last block go to the GPU
    bool gpu_off = false;               // the panel's: the CPU for every block
    double ms_setup = 0.0, ms_samples = 0.0;    // its two halves (live's GpuRenderer.ms_*)
    std::vector<long> gidx, gnon, gnoff;
    std::vector<float> gout;

    bool render_gpu(long long n0, long frames, float *L, float *R, float *SL, float *SR, long long blk)
    {
        long mg = 0;
        long nact = setup_gpu(n0, blk, gp.D, gp.C, gp.SB, SL != nullptr, mg);
        auto t1 = std::chrono::steady_clock::now();
        struct Ms {
            double &out;
            std::chrono::steady_clock::time_point t;
            ~Ms() { out = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t).count(); }
        } ms{ms_samples, t1};
        if (gp.cl) {
            gout.resize(4 * frames);
            if (nv_cl_samples(gp.cl, gp.D.p, gp.D.bytes(), gp.C.p, gp.C.bytes(), gp.SB.p, gp.SB.bytes(), (int)nact,
                              n0, (int)frames, SL ? 1 : 0, (int)mg, gout.data()) != 0)
                return false;
            for (long k = 0; k < frames; k++) {
                L[k] = gout[k];
                R[k] = gout[frames + k];
                if (SL) {
                    SL[k] = gout[2 * frames + k];
                    SR[k] = gout[3 * frames + k];
                }
            }
        } else {
            ((nv_vsamples_fn)gp.vs)((long)n0, (int)blk, (int)nact, gp.D.p, gp.C.p, gp.SB.p, L, R, SL, SR);
        }
        return true;
    }

    // the GPU block's setup (voice_block over every busy slot) into the
    // tables D, C, SB, grown as it asks; the busy slots' count, and *mg the
    // Moog's grid. ms_setup its time
    long setup_gpu(long long n0, long long blk, Table &D, Table &C, Table &SB, bool snd, long &mgo)
    {
        if (!D.size) {                      // (a second set takes the first's record sizes)
            D.size = gp.D.size;
            C.size = gp.C.size;
            SB.size = gp.SB.size;
        }
        gidx.clear();
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q])
                gidx.push_back(q);
        long nact = (long)gidx.size();
        if (nact > D.n)
            D.make(std::max(nact, 2 * D.n), D.size);
        long mg = (blk % 128 == 0 && blk / 128 <= 64) ? 128 : blk;     // moog_grid
        long kb0 = (long)(n0 / mg);
        gnon.resize(S.cap);
        gnoff.resize(S.cap);
        for (long q = 0; q < S.cap; q++) {
            gnon[q] = (long)S.i8[0][q];
            gnoff[q] = (long)S.i8[1][q];
        }
        void *vb = gp.vb;
        bool damp = false;
        for (long q : gidx)
            damp = damp || S.dk[q] >= 0;
        if (damp && gp.vbd && gp.vds) {
            vb = gp.vbd;
            ((nv_vdamp_fn)gp.vds)(S.dk.data(), S.dg.data(), DM.data(), DMO.data(), DMB.data(), DMN.data());
        }
        const std::vector<float> *F4 = S.f4.data(), *F4N = S.f4n.data();
        int counts[2] = {0, 0};
        auto t0 = std::chrono::steady_clock::now();
        while (true) {
            int r = ((nv_vblock_fn)vb)(
                (long)n0, (int)blk, 1, (int)S.cap, S.f8[0].data(), S.f8[1].data(), S.f8[2].data(), F4[0].data(),
                F4[1].data(), F4[2].data(), gnon.data(), gnoff.data(), F4[3].data(), F4[4].data(), F4[5].data(),
                F4[6].data(), F4[7].data(), F4[8].data(), F4[9].data(), F4[10].data(), F4[11].data(),
                F4[12].data(), F4[13].data(), F4[14].data(), F4[15].data(), F4[16].data(), F4[17].data(),
                F4[18].data(), F4N[0].data(), F4N[1].data(), F4N[2].data(), F4[19].data(), F4[20].data(),
                F4[21].data(), F4N[3].data(), F4[22].data(), F4[23].data(), S.i4[0].data(), S.i4[1].data(),
                G.data(), Sx.data(), S.i4[2].data(), BRt.data(), BCt.data(), BLt.data(), S.i4[4].data(), FT.data(),
                KN.data(), 2, kb0, S.aLp.data(), S.aRp.data(), S.i4[5].data(), MPI.data(), MPC.data(), MPR.data(),
                MKI.data(), MPK.data(), S.f8[3].data(), S.f8[4].data(), S.f8[5].data(), sh[0], sh[1], sh[2], sh[3],
                nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, 0, nullptr, nullptr, nullptr, nullptr,
                nullptr, nullptr, 0, S.sw.data(), snd ? 1 : 0, gidx.data(), (int)nact, D.p, C.p,
                (int)C.n, SB.p, (int)SB.n, gp.nthr, counts, 1);
            if (r == 0)
                break;
            if (counts[0] > C.n)
                C.make(2L * counts[0], C.size);
            if (counts[1] > SB.n)
                SB.make(2L * counts[1], SB.size);
        }
        ms_setup = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        mgo = mg;
        return nact;
    }

    // THE PIPELINE'S BLOCK (GpuRenderer.render, _start, _finish): this one
    // started, the one before finished into L, R (SL, SR)
    void render(long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx, void *sd,
                long long blk, double master_gain)
    {
        if (!pipeline || !gp.cl) {
            render_now(n0, frames, L, R, SL, SR, sv, sx, sd, blk, master_gain);
            return;
        }
        GpuPend cur;
        cur.snd = SL != nullptr;
        long hi = -1, act = 0;
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q]) {
                hi = q;
                act++;
            }
        bool g = hi >= 0 && gp.vb && !gpu_off && act >= gp.gpu_min && frames == blk && n0 % frames == 0;
        if (g) {
            // set up in this turn's tables and launched, not waited for
            Table &D = turn ? gp.D2 : gp.D, &C = turn ? gp.C2 : gp.C, &SB = turn ? gp.SB2 : gp.SB;
            long mg = 0;
            long nact = setup_gpu(n0, blk, D, C, SB, cur.snd, mg);
            if (nv_cl_launch(gp.cl, turn, D.p, D.bytes(), C.p, C.bytes(), SB.p, SB.bytes(), (int)nact, n0,
                             (int)frames, cur.snd ? 1 : 0, (int)mg) == 0) {
                cur.kind = 2;
                cur.slot = turn;
                turn ^= 1;
                S.aLp = S.f4[0];            // knobs_advance
                S.aRp = S.f4[1];
            } else {
                g = false;
            }
        }
        if (!g) {
            // the CPU's, rendered now and held
            cur.kind = 1;
            cur.L.assign(frames, 0.0f);
            cur.R.assign(frames, 0.0f);
            if (cur.snd) {
                cur.SL.assign(frames, 0.0f);
                cur.SR.assign(frames, 0.0f);
            }
            render_now(n0, frames, cur.L.data(), cur.R.data(), cur.snd ? cur.SL.data() : nullptr,
                       cur.snd ? cur.SR.data() : nullptr, sv, sx, sd, blk, master_gain);
        }
        on_gpu = g;
        GpuPend prev = std::move(gpend);
        gpend = std::move(cur);
        // ...and the one before it, finished
        for (long k = 0; k < frames; k++) {
            L[k] = R[k] = 0.0f;
            if (SL)
                SL[k] = SR[k] = 0.0f;
        }
        if (prev.kind == 1) {
            for (long k = 0; k < frames; k++) {
                L[k] = prev.L[k];
                R[k] = prev.R[k];
                if (SL && prev.snd) {
                    SL[k] = prev.SL[k];
                    SR[k] = prev.SR[k];
                }
            }
        } else if (prev.kind == 2) {
            auto t1 = std::chrono::steady_clock::now();
            gout.resize(4 * frames);
            if (nv_cl_collect(gp.cl, prev.slot, gout.data()) == 0) {
                float gn = (float)master_gain;
                for (long k = 0; k < frames; k++) {
                    L[k] = gout[k] * gn;
                    R[k] = gout[frames + k] * gn;
                    L[k] = L[k] < -1.0f ? -1.0f : (L[k] > 1.0f ? 1.0f : L[k]);
                    R[k] = R[k] < -1.0f ? -1.0f : (R[k] > 1.0f ? 1.0f : R[k]);
                    if (SL && prev.snd) {
                        SL[k] = gout[2 * frames + k] * gn;
                        SR[k] = gout[3 * frames + k] * gn;
                    }
                }
            }
            ms_samples = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t1).count();
        }
    }

    void render_now(long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx,
                    void *sd, long long blk, double master_gain)
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
        // THE GPU (live.GpuRenderer), when given one and the block has rows
        // enough for it (gpu_min); the CPU below otherwise
        long act = 0;
        for (long q = 0; q < hi; q++)
            act += S.busy[q] != 0;
        on_gpu = gp.vb && !gpu_off && act >= gp.gpu_min && frames == blk && n0 % frames == 0;
        if (on_gpu && !render_gpu(n0, frames, L, R, SL, SR, blk))
            on_gpu = false;
        if (!on_gpu) {
        long kb0 = (long)(n0 / blk);                        // moog_grid(128) = 128
        long chunk = blk * std::max(1L, (long)(rate / blk));
        auto fast = [&](long q) {
            float lr = S.f4[6][q];
            return S.f4[9][q] <= 0 && S.f4[8][q] <= 0 && (float)(lr * (float)blk) > (float)(xdec_nepers * rate)
                   && S.i4[0][q] < 0 && S.i4[2][q] < 0 && S.dk[q] < 0 && S.i4[4][q] < 0;
        };
        std::vector<long> xr, keep, dm;
        for (long q = 0; q < hi; q++)
            (S.dk[q] >= 0 && sd ? dm : fast(q) ? xr : keep).push_back(q);
#define VOICE_ARGS L, R, (long)n0, frames, (int)blk, 1, (int)n, gd(S.f8[0], 0), gd(S.f8[1], 1), gd(S.f8[2], 2), \
    gf(F4[0]), gf(F4[1]), gf(F4[2]), gl(S.i8[0], 0), gl(S.i8[1], 1), gf(F4[3]), gf(F4[4]), gf(F4[5]), gf(F4[6]), \
    gf(F4[7]), gf(F4[8]), gf(F4[9]), gf(F4[10]), gf(F4[11]), gf(F4[12]), gf(F4[13]), gf(F4[14]), gf(F4[15]), \
    gf(F4[16]), gf(F4[17]), gf(F4[18]), gf(F4N[0]), gf(F4N[1]), gf(F4N[2]), gf(F4[19]), gf(F4[20]), gf(F4[21]), \
    gf(F4N[3]), gf(F4[22]), gf(F4[23]), gi(S.i4[0]), gi(S.i4[1]), G.data(), Sx.data(), gi(S.i4[2]), BRt.data(), \
    BCt.data(), BLt.data(), gi(S.i4[4]), FT.data(), KN.data(), 2, kb0, gf(S.aLp), gf(S.aRp), gi(S.i4[5]), \
    MPI.data(), MPC.data(), MPR.data(), MKI.data(), MPK.data(), gd(S.f8[3], 3), gd(S.f8[4], 4), gd(S.f8[5], 5), \
    sh[0], sh[1], sh[2], sh[3], chunk, SL ? gf(S.sw) : nullptr, SL, SR
        auto call = [&](void *fn, const long *rows, long n, bool whole, bool damp) {
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
            if (damp) {
                std::vector<int> &dkr = i[ik++];
                dkr.resize(n); for (long q = 0; q < n; q++) dkr[q] = S.dk[rows[q]];
                std::vector<float> &dgr = f[fk++];
                dgr.resize(n); for (long q = 0; q < n; q++) dgr[q] = S.dg[rows[q]];
                // synth_voice_damp: synth_voice's arguments, then the tracks
                ((nv_damp_fn)fn)(VOICE_ARGS, dkr.data(), dgr.data(), DM.data(), DMO.data(), DMB.data(), DMN.data());
            } else {
                ((nv_voice_fn)fn)(VOICE_ARGS);
            }
        };
        if (!dm.empty()) {
            call(sv, keep.data(), (long)keep.size(), false, false);
            call(sx, xr.data(), (long)xr.size(), false, false);
            call(sd, dm.data(), (long)dm.size(), false, true);
        } else if (!xr.empty()) {
            call(sv, keep.data(), (long)keep.size(), false, false);
            call(sx, xr.data(), (long)xr.size(), false, false);
        } else {
            call(sv, nullptr, hi, true, false);
        }
#undef VOICE_ARGS
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

    // AFTER THE RENDER (live's callback): the master volume (live's Master
    // Volume, 1.0: no ramp), the room on the send -- the kernel's second
    // output when the channels' CC91s differ, else the dry mix times their
    // one distance -- and the soft limiter's knee
    std::unique_ptr<Room> room;
    double thresh = 0.70;                           // live.thresh
    std::vector<float> oSL, oSR, oA, oB, oWL, oWR;

    // Live.limit: a soft knee above thresh (libm's tanhf, as live's now)
    void limit(float *x, long n) const
    {
        float t = (float)thresh, k = (float)(1.0 - thresh);
        for (long i = 0; i < n; i++) {
            float a = fabsf(x[i]);
            if (a > t)
                x[i] = (x[i] > 0.0f ? 1.0f : -1.0f) * (t + k * tanhf((a - t) / k));
        }
    }

    void output(long long n0, long frames, float *L, float *R, void *sv, void *sx, void *sd, long long blk,
                double master_gain)
    {
        bool uniform = true;
        for (int c = 1; c < 256 && uniform; c++)
            uniform = S.send[c] == S.send[0];
        bool snd = room && room_on && !uniform;
        oSL.assign(frames, 0.0f);
        oSR.assign(frames, 0.0f);
        render(n0, frames, L, R, snd ? oSL.data() : nullptr, snd ? oSR.data() : nullptr, sv, sx, sd, blk,
               master_gain);
        if (room && room_on) {
            const float *sl = L, *sr = R;
            if (snd) {
                sl = oSL.data();                    // (times the master volume's 1.0)
                sr = oSR.data();
            } else if (S.send[0] != 1.0) {
                float u = (float)S.send[0];
                oA.resize(frames);
                oB.resize(frames);
                for (long k = 0; k < frames; k++) {
                    oA[k] = L[k] * u;
                    oB[k] = R[k] * u;
                }
                sl = oA.data();
                sr = oB.data();
            }
            oWL.resize(frames);
            oWR.resize(frames);
            room->process(sl, sr, oWL.data(), oWR.data());
            for (long k = 0; k < frames; k++) {
                L[k] = L[k] + oWL[k];
                R[k] = R[k] + oWR[k];
            }
        }
        limit(L, frames);
        limit(R, frames);
    }

    // THE BUDGET GOVERNOR (live's callback, after its render; Slab.shed):
    // each block's time against its slot, the last four kept; when their
    // median-ish (the second smallest) is over 95% of the slot -- so one
    // chord's strike is not a reason -- the highest tenth of the partials
    // still sounding end over SHED_FADE: the top of each note's spectrum
    // first, where its partials are quietest and the rest mask them. A shed
    // slot keeps its key and is reaped with its note; only its sound stops.
    // Ties in frequency (a note and its forced register rows share one) go
    // by slot, where numpy's argpartition picks as it partitions.
    static constexpr double SHED_FADE = 0.005;
    double ms_hist[4];
    int ms_n = 0;
    long partials_shed = 0;

    long shed(long long n, double frac)
    {
        std::vector<long> idx;
        for (long q = 0; q < S.cap; q++) {
            long long off = S.i8[1][q];
            if (S.busy[q] && S.i8[0][q] <= n && (off == IDLE || off > n))
                idx.push_back(q);
        }
        long k = (long)(frac * (double)idx.size());
        if (k < 1)
            return 0;
        const std::vector<float> &nf = S.f4[F4_nf];
        std::partial_sort(idx.begin(), idx.begin() + k, idx.end(), [&](long a, long b) {
            return nf[a] > nf[b] || (nf[a] == nf[b] && a < b);
        });
        float fade = (float)(SHED_FADE * rate);
        for (long i = 0; i < k; i++) {
            long q = idx[i];
            if (S.i4[I4_fx][q] >= 0)
                continue;                       // a Moog row (none on a piano): its panel's, not ours
            S.i8[1][q] = std::min(S.i8[1][q], n);
            S.f4[F4_re][q] = std::min(S.f4[F4_re][q], fade);
        }
        return k;
    }

    // a block took ms of budget_ms; the next starts at n
    long govern(double ms, double budget_ms, long long n)
    {
        if (ms_n == 4) {
            for (int i = 0; i < 3; i++)
                ms_hist[i] = ms_hist[i + 1];
            ms_hist[3] = ms;
        } else {
            ms_hist[ms_n++] = ms;
        }
        if (ms_n < 4)
            return 0;
        double o[4] = {ms_hist[0], ms_hist[1], ms_hist[2], ms_hist[3]};
        std::sort(o, o + 4);
        if (!(o[1] > 0.95 * budget_ms))
            return 0;
        long k = shed(n, 0.1);
        if (k) {
            partials_shed += k;
            ms_n = 0;
        }
        return k;
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
            else if (e.type == 3)
                aftertouch(e.ch, e.a);
            else if (e.type == 4)
                pitchwheel(e.ch, e.a, n0);
            else
                control(e.ch, e.a, e.b, n0);
        }
        if (reg_on && (!reg_pend.empty() || !reg_out.empty() || reg_live || !reg_retire.empty()
                       || reg_ndone.load() > 0))
            reg_pump(n0);
        std::vector<Key> sw;
        for (auto &kv : S.live) {
            std::pair<int, int> ck((int)std::get<1>(kv.first), (int)std::get<2>(kv.first));
            auto sq = sost.find(ck.first);
            if (!down.count(ck) && !pedalled.count(ck) && !S.oneshot.count(kv.first)
                && !(sq != sost.end() && sq->second.count(ck.second)))
                sw.push_back(kv.first);
        }
        for (auto &k : sw)
            S.release(k, n0);
        damp_block(n0, blk);
        S.reap(n0, blk);
    }
};

// THE ROUTES (live.Route, and Live.on_midi's pass over them): one hardware
// control made to drive another, ahead of the part. A message is (type, ch,
// a, b): 0 note-on (a key, b velocity), 1 note-off, 2 control change (a
// number, b value), 3 channel aftertouch (a), 4 the pitch wheel (a,
// -8192..8191). A source is a CC, the wheel's up, down or both halves,
// channel pressure, or a key; a destination one of live.CONTROLS -- a CC,
// or BEND, PRESSURE, MONO -- and the transform follows from the two:
//   the wheel onto a switch    held while pushed: down past PW_FIRE of its
//                              half, up under PW_REARM
//   a CC onto a switch         64 and above is down
//   anything onto a CC         its travel scaled 0-127
//   a CC onto the wheel        0-127 onto -8192..8191, centred at 64
//   a key onto a switch        held while down, or each press toggles (latch);
//                              held as the sustain pedal, its channel's
//                              aftertouch while it is down is 127 - pressure
//   a key onto anything else   its velocity while held, and on release the
//                              value the control had before
// A route REPLACES its source unless it keeps it; the messages that pass are
// what the last value of each control is kept from (live.seen), which a key
// puts back when it comes up.
enum { DST_BEND = -1, DST_PRESSURE = -2, DST_MONO = -3 };
enum { SRC_CC = 0, SRC_BEND = 1, SRC_PRESSURE = 2, SRC_NOTE = 3 };
enum { K_SWITCH = 0, K_CONT = 1, K_BEND = 2, K_PRESSURE = 3 };
static const double PW_FIRE = 0.50, PW_REARM = 0.20;    // live's

struct Msg {
    int type, ch, a, b;
};

// live.CONTROLS: (key, kind, default); a key not here is no destination
static bool control_spec(int key, int *kind, int *dflt)
{
    static const int T[][3] = {{64, K_SWITCH, 0}, {66, K_SWITCH, 0}, {67, K_SWITCH, 0}, {65, K_SWITCH, 0},
                               {DST_MONO, K_SWITCH, 0}, {1, K_CONT, 0}, {11, K_CONT, 127}, {7, K_CONT, 100},
                               {10, K_CONT, 64}, {5, K_CONT, 0}, {93, K_CONT, 0}, {94, K_CONT, 0},
                               {74, K_CONT, 64}, {71, K_CONT, 64}, {73, K_CONT, 64}, {75, K_CONT, 64},
                               {72, K_CONT, 64}, {76, K_CONT, 64}, {77, K_CONT, 64}, {78, K_CONT, 64},
                               {DST_BEND, K_BEND, 0}, {DST_PRESSURE, K_PRESSURE, 0}};
    for (auto &r : T)
        if (r[0] == key) {
            *kind = r[1];
            *dflt = r[2];
            return true;
        }
    return false;
}

// live.control_message: the message one catalogue control sends at value
static Msg control_message(int key, long value, int ch)
{
    auto clamp = [](long v, long lo, long hi) { return v < lo ? lo : v > hi ? hi : v; };
    if (key == DST_BEND)
        return Msg{4, ch, (int)clamp(value, -8192, 8191), 0};
    if (key == DST_PRESSURE)
        return Msg{3, ch, (int)clamp(value, 0, 127), 0};
    if (key == DST_MONO)
        return value >= 64 ? Msg{2, ch, 126, 1} : Msg{2, ch, 127, 0};
    return Msg{2, ch, key, (int)clamp(value, 0, 127)};
}

static long pyround(double x) { return (long)nearbyint(x); }    // round(): to even

struct Route {
    int src, arg, dst;          // arg: the CC, the key, or the wheel's half (0 up, 1 down, 2 both)
    bool keep = false, latch = false, press = true;
    int channel = -1;           // -1 every channel
    bool down[16] = {}, held[16] = {};
    std::map<int, int> prior;   // channel -> the value before the key went down

    static bool is_on(const Msg &m) { return m.type == 0 && m.b > 0; }

    bool pressing(int ch) const
    {
        return press && !latch && dst == 64 && held[ch];
    }

    bool matches(const Msg &m) const
    {
        if (channel >= 0 && m.ch != channel)
            return false;
        if (src == SRC_CC)
            return m.type == 2 && m.a == arg;
        if (src == SRC_BEND)
            return m.type == 4;
        if (src == SRC_PRESSURE)
            return m.type == 3;
        if (m.type == 3)
            return pressing(m.ch);
        if ((m.type != 0 && m.type != 1) || m.a != arg)
            return false;
        // a release only if this route took the press
        return is_on(m) || held[m.ch];
    }

    double level(const Msg &m) const
    {
        if (src == SRC_BEND) {
            int p = m.a;
            if (arg == 0)
                return std::max(0, p) / 8191.0;
            if (arg == 1)
                return std::max(0, -p) / 8192.0;
            return abs(p) / 8192.0;
        }
        return (m.type == 3 ? m.a : m.b) / 127.0;
    }

    void rewrite(const Msg &m, const std::map<std::pair<int, int>, int> &seen, std::vector<Msg> &out)
    {
        int kind, dflt;
        if (!control_spec(dst, &kind, &dflt))
            return;
        int ch = m.ch;
        if (src == SRC_NOTE) {
            key(m, ch, kind, dflt, seen, out);
            return;
        }
        double x = level(m);
        if (kind == K_SWITCH) {
            bool was = down[ch], now;
            if (src == SRC_BEND)
                now = !was ? x >= PW_FIRE : x > PW_REARM;
            else
                now = x >= 64.0 / 127.0;
            if (now == was)
                return;                         // a pedal is sent on a change, not a stream
            down[ch] = now;
            out.push_back(control_message(dst, now ? 127 : 0, ch));
            return;
        }
        if (kind == K_BEND) {
            if (src == SRC_BEND) {
                out.push_back(control_message(DST_BEND, m.a, ch));
                return;
            }
            // each half on its own scale: 64 centre, 0 full down, 127 full up
            double v = x * 127.0;
            double p = v >= 64.0 ? (v - 64.0) / 63.0 * 8191.0 : (v - 64.0) / 64.0 * 8192.0;
            out.push_back(control_message(DST_BEND, pyround(p), ch));
            return;
        }
        out.push_back(control_message(dst, pyround(x * 127.0), ch));
    }

    void key(const Msg &m, int ch, int kind, int dflt, const std::map<std::pair<int, int>, int> &seen,
             std::vector<Msg> &out)
    {
        if (m.type == 3) {
            // pushed into while held: the dampers lowered (Route.press)
            out.push_back(control_message(dst, 127 - m.a, ch));
            return;
        }
        bool on = is_on(m);
        held[ch] = on;
        if (kind == K_SWITCH) {
            bool was = down[ch], now;
            if (latch) {
                if (!on)
                    return;
                now = !was;
            } else {
                now = on;
                if (now == was)
                    return;
            }
            down[ch] = now;
            out.push_back(control_message(dst, now ? 127 : 0, ch));
            return;
        }
        if (on) {
            if (!prior.count(ch)) {
                auto it = seen.find(std::make_pair(ch, dst));
                prior[ch] = it != seen.end() ? it->second : dflt;
            }
            int v = m.b;
            out.push_back(control_message(dst, kind == K_BEND ? pyround(v / 127.0 * 8191) : v, ch));
            return;
        }
        auto it = prior.find(ch);
        if (it == prior.end())
            return;
        int pv = it->second;
        prior.erase(it);
        out.push_back(control_message(dst, pv, ch));
    }
};

struct Router {
    std::vector<Route> routes;
    std::map<std::pair<int, int>, int> seen;    // (channel, control) -> its last value (live.seen)

    // Live.on_midi's pass: the messages msg becomes, each then seen
    std::vector<Msg> feed(const Msg &msg)
    {
        std::vector<Msg> out;
        bool consumed = false;
        for (Route &r : routes)
            if (r.matches(msg)) {
                r.rewrite(msg, seen, out);
                consumed = consumed || !r.keep;
            }
        std::vector<Msg> msgs;
        if (!consumed)
            msgs.push_back(msg);
        msgs.insert(msgs.end(), out.begin(), out.end());
        for (const Msg &m : msgs)
            see(m);
        return msgs;
    }

    // Live._see: the last value of each control on each channel; CC121 forgets
    // the ones it resets
    void see(const Msg &m)
    {
        int kind, dflt;
        if (m.type == 2) {
            if (m.a == 121) {
                for (int k : {1, 11, 64, 65, 66, 67, (int)DST_BEND, (int)DST_PRESSURE})
                    seen.erase(std::make_pair(m.ch, k));
            } else if (control_spec(m.a, &kind, &dflt)) {
                seen[std::make_pair(m.ch, m.a)] = m.b;
            }
        } else if (m.type == 4) {
            seen[std::make_pair(m.ch, (int)DST_BEND)] = m.a;
        } else if (m.type == 3) {
            seen[std::make_pair(m.ch, (int)DST_PRESSURE)] = m.a;
        }
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

// The part a DRUM PART (live.Patch(program, True)): program its drum set,
// choke[2 * (128 * program + key) + w] each key's exclusive class (native.kits')
void nv_lp_drums(void *h, int program, const unsigned long long *choke)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    P->drums = true;
    P->program = program;
    P->choke.assign(choke, choke + 2 * 16384);
}

void nv_lp_free(void *h) { delete (nv::slab::Piano *)h; }

// The part's free strings (live's register): its string bank (M modes, as
// nv_strings makes it), register.LiveChannel's constants (kappa, knock,
// fall, floor, damper_top, the felt's BETA), the class's dampers and release
// (samples), damper.py's FULL_DB_S, RESIDUAL, LN10_20, the block, and which
// keys' classes answer (live._reg_voice, 128 flags)
void nv_lp_register(void *h, const StringMode *modes, int M, double kappa, double knock, double fall, double fl,
                    int top, double beta, int pedals, double rel, double full_db_s, double residual, double ln10_20,
                    long long blk, const int *reg_note)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    P->reg_on = true;
    P->rmodes.assign(modes, modes + M);
    P->r_kappa = kappa; P->r_knock = knock; P->r_fall = fall; P->r_fl = fl; P->r_top = top; P->r_beta = beta;
    P->r_pedals = pedals; P->r_rel = rel; P->r_full = full_db_s; P->r_resid = residual; P->r_ln = ln10_20;
    P->r_blk = (double)blk;
    for (int k = 0; k < 128; k++)
        P->reg_note[k] = reg_note[k] != 0;
}

// the register's rows dropped for a full slab, and whether any are placed
long nv_lp_reg_dropped(void *h) { return ((nv::slab::Piano *)h)->reg_dropped; }

// an event for the next block: 0 note-on (a key, b velocity), 1 note-off, 2 control (a cc, b value)
void nv_lp_event(void *h, int type, int ch, int a, int b)
{
    ((nv::slab::Piano *)h)->events.push_back(nv::slab::Ev{type, ch, a, b});
}

void nv_lp_block(void *h, long long n0, long long blk) { ((nv::slab::Piano *)h)->block(n0, blk); }

// Renderer.render's block: L, R (and with SL the room's send pair) over
// [n0, n0 + frames), through synth_voice (sv), synth_voice_xdec (sx) and
// synth_voice_damp (sd; NULL: no row is drawn by a damper track)
void nv_lp_render(void *h, long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx,
                  void *sd, long long blk, double master_gain)
{
    ((nv::slab::Piano *)h)->render(n0, frames, L, R, SL, SR, sv, sx, sd, blk, master_gain);
}

// THE ROUTES (live.Route, Live.on_midi): a router, its routes added in
// order, each (source kind, its CC/half/key, destination, keep, channel -1
// all, latch, press)
void *nv_rt_new() { return new nv::slab::Router(); }

void nv_rt_add(void *h, int src, int arg, int dst, int keep, int channel, int latch, int press)
{
    nv::slab::Route r;
    r.src = src; r.arg = arg; r.dst = dst; r.keep = keep != 0; r.channel = channel; r.latch = latch != 0;
    r.press = press != 0;
    ((nv::slab::Router *)h)->routes.push_back(r);
}

// one message in (type, ch, a, b); up to cap out, 4 ints each; how many
int nv_rt_feed(void *h, int type, int ch, int a, int b, int *out, int cap)
{
    std::vector<nv::slab::Msg> got = ((nv::slab::Router *)h)->feed(nv::slab::Msg{type, ch, a, b});
    int n = 0;
    for (const nv::slab::Msg &m : got)
        if (n < cap) {
            out[4 * n] = m.type; out[4 * n + 1] = m.ch; out[4 * n + 2] = m.a; out[4 * n + 3] = m.b;
            n++;
        }
    return n;
}

void nv_rt_free(void *h) { delete (nv::slab::Router *)h; }

// the panel's: how many routes, route i's seven (nv_rt_add's), route i gone
int nv_rt_count(void *h) { return (int)((nv::slab::Router *)h)->routes.size(); }

void nv_rt_get(void *h, int i, int *out)
{
    const nv::slab::Route &r = ((nv::slab::Router *)h)->routes[i];
    int v[7] = {r.src, r.arg, r.dst, r.keep, r.channel, r.latch, r.press};
    memcpy(out, v, sizeof v);
}

void nv_rt_del(void *h, int i)
{
    auto &rs = ((nv::slab::Router *)h)->routes;
    if (i >= 0 && i < (int)rs.size())
        rs.erase(rs.begin() + i);
}

// the damper tracks' values (DM: 2 x 256 floats)
void nv_lp_dm(void *h, float *out)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    memcpy(out, P->DM.data(), sizeof(float) * P->DM.size());
}

// THE GPU (live.GpuRenderer): voice_block from the GPU's build (vb), its
// damper build's voice_block and voice_damp_set (vbd, vds), voice_samples
// (vs, the C reference) and voice_sizes (vz); cl an OpenCL GPU (nv_cl_new),
// NULL to run the samples through voice_samples; a block of gpu_min busy
// slots or more goes to it, its setup on nthr threads
void nv_lp_gpu(void *h, void *vb, void *vbd, void *vds, void *vs, void *vz, void *cl, long gpu_min, int nthr)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    auto &g = P->gp;
    g.vb = vb; g.vbd = vbd; g.vds = vds; g.vs = vs; g.cl = cl; g.gpu_min = gpu_min; g.nthr = nthr;
    int sz[3];
    ((nv_vsizes_fn)vz)(sz);
    g.D.make(1024, sz[0]);
    g.C.make(1024, sz[1]);
    g.SB.make(1 << 14, sz[2]);
}

// THE PIPELINE (live's TUNING_GPU_PIPELINE): on, every block a block late --
// the CPU's setup of the next while the GPU renders this one (an OpenCL GPU's)
void nv_lp_pipeline(void *h, int on) { ((nv::slab::Piano *)h)->pipeline = on != 0; }

// The register's jobs on a worker thread of the part's own, off the audio
// thread (live's worker process): answers placed at the pump after they are
// ready, not in step -- for playing, not for the checks
void nv_lp_reg_async(void *h) { ((nv::slab::Piano *)h)->start_reg_worker(); }

// Slab.shed: the highest frac of the partials sounding at n end over 5 ms; how many
long nv_lp_shed(void *h, long long n, double frac) { return ((nv::slab::Piano *)h)->shed(n, frac); }

// The governor: a block took ms against its budget_ms, the next starts at n;
// returns the partials it shed now
long nv_lp_govern(void *h, double ms, double budget_ms, long long n)
{
    return ((nv::slab::Piano *)h)->govern(ms, budget_ms, n);
}

long nv_lp_partials_shed(void *h) { return ((nv::slab::Piano *)h)->partials_shed; }

// THE PANEL'S: a global set between blocks -- 0 headroom (dB), 1 the
// pressure's lift (dB), 2 the limiter's knee, 3 the wheel's range, 4 the mod
// range (cents), 5 the GPU on (1) or off, 6 the room's tail on or off
void nv_lp_set(void *h, int what, double v)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    switch (what) {
    case 0:
        P->S.headroom_d = pow(10.0, -v / 20.0);
        P->S.headroom = (float)P->S.headroom_d;
        break;
    case 1: P->press_db = v; break;
    case 2: P->thresh = v; break;
    case 3: P->bend_range = v; break;
    case 4: P->mod_cents = v; break;
    case 5: P->gpu_off = v < 0.5; break;
    case 6: P->room_on = v >= 0.5; break;
    }
}

// what the panel shows: 0 busy slots, 1 keys sounding, 2 partials shed, 3
// register rows dropped, 4 the GPU took the last block, 5 its setup ms, 6
// its samples ms, 7 channel 1's pedal, 8 sostenuto down on it, 9 mono on it,
// 10 damper tracks, 11 a room, 12 the GPU on, 13 the tail on, 14 the bend
// on channel 1 (cents)
void nv_lp_stats(void *h, double *out)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    long busy = 0;
    for (long q = 0; q < P->S.cap; q++)
        busy += P->S.busy[q] != 0;
    out[0] = (double)busy;
    out[1] = (double)P->S.live.size();
    out[2] = (double)P->partials_shed;
    out[3] = (double)P->reg_dropped;
    out[4] = P->on_gpu;
    out[5] = P->ms_setup;
    out[6] = P->ms_samples;
    out[7] = P->pedal_v[0];
    out[8] = P->sost.count(0) ? 1.0 : 0.0;
    out[9] = P->mono[0];
    out[10] = (double)P->dtracks.size();
    out[11] = P->room ? 1.0 : 0.0;
    out[12] = P->gp.vb && !P->gpu_off;
    out[13] = P->room_on;
    out[14] = 1200.0 * log2(P->bend[0]);
}

// live.panic, at n0
void nv_lp_panic(void *h, long long n0) { ((nv::slab::Piano *)h)->panic(n0); }

// did the last block render on the GPU
int nv_lp_on_gpu(void *h) { return ((nv::slab::Piano *)h)->on_gpu; }

// ...and its two halves, ms: the setup (voice_block), the samples
void nv_lp_gpu_ms(void *h, double *out)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    out[0] = P->ms_setup;
    out[1] = P->ms_samples;
}

// The late room (live.RoomTail) through convolver.c's conv_new, conv_process
// and conv_free: ir n stereo samples interleaved, mir the modes' (m 0: none)
void nv_lp_room(void *h, void *cn, void *cp, void *cf, const float *ir, long n, const float *mir, long m, int frames)
{
    ((nv::slab::Piano *)h)->room.reset(new nv::slab::Room(cn, cp, cf, ir, n, mir, m, frames));
}

// the soft limiter's knee (live.thresh), the pitch wheel's range (live.bend_range)
// and the mod wheel's (live.mod_cents)
void nv_lp_post(void *h, double thresh, double bend_range, double mod_cents)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    P->thresh = thresh;
    P->bend_range = bend_range;
    P->mod_cents = mod_cents;
}

// live's callback after its events and step: the render, the room, the limiter
void nv_lp_output(void *h, long long n0, long frames, float *L, float *R, void *sv, void *sx, void *sd,
                  long long blk, double master_gain)
{
    ((nv::slab::Piano *)h)->output(n0, frames, L, R, sv, sx, sd, blk, master_gain);
}

// The mod wheel picks a honky-tonk's detune (live's 'detune' role)
void nv_lp_detune_wheel(void *h, int on) { ((nv::slab::Piano *)h)->detune_wheel = on != 0; }

// Pressure's level at full aftertouch, dB (live.press_db)
void nv_lp_press_db(void *h, double db) { ((nv::slab::Piano *)h)->press_db = db; }

// The dampers in between (live._damp_block): damper.py's FULL_DB_S,
// RESIDUAL, KNEE_DB, BETA and LN10_20
void nv_lp_damper(void *h, double full_db_s, double residual, double knee_db, double beta, double ln10_20)
{
    nv::slab::Piano *P = (nv::slab::Piano *)h;
    P->dmp_on = true;
    P->dmp_full = full_db_s; P->dmp_res = residual; P->dmp_knee = knee_db; P->dmp_beta = beta; P->dmp_ln = ln10_20;
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
// 5 the bookkeeping (index: sw aL0 aR0 sg sre hrel vbase vrbase vsc), 6 dk/slot_ch/busy,
// 7 aLp/aRp, 8 dg (index 3)
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
    case 8:
        memcpy(out, S->dg.data(), sizeof(float) * n);
        break;
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
