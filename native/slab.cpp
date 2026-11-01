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
#include <vector>

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
enum { F4_aL = 0, F4_aR = 1, F4_re = 4, F4_cbw = 15, F4_vd = 19, F4_vr = 20, F4_delL = 22, F4_delR = 23, F4_rdl = 25 };
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
    std::vector<char> busy;
    std::deque<long> free;
    std::map<Key, std::vector<long>> live;
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
        std::vector<long> &lv = live[key];
        lv.insert(lv.end(), idx.begin(), idx.end());
        for (long s : idx)
            i4[I4_fx][s] = -1;                  // _moog_stamp: not a Moog note
        last_slots = idx;
        return true;
    }

    void release(Key key, long long n)
    {
        auto it = live.find(key);
        if (it == live.end() || it->second.empty()) {
            if (it != live.end())
                live.erase(it);
            return;
        }
        std::vector<long> idx = it->second;
        live.erase(it);
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

}  // namespace slab
}  // namespace nv

extern "C" {

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
