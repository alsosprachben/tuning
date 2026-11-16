// rubfill.h -- THE HELD MOMENT (rubato, host.cpp): what the callback plays
// while a late block is still being made, in place of the silence that was a
// click.
//
// The sound just heard goes on: the callback keeps the last H frames it handed
// out, and on a hold replays a stretch of them from 20-40 ms back -- the one
// whose start best matches the latest sound (the normalised correlation of
// the last W frames with themselves that far back), marked down if it holds
// an attack, which would be heard again. A stall of up to that long plays it
// once: nothing repeats, so no period of it is heard as a low buzz (a short
// period, repeated, was a thud in a dense chord, Ben). Its first JOIN frames
// cross from the last frame's line into it, a hold past FADE_AFTER fades (-3
// dB each 10 ms), and when the late block comes its first XF frames cross
// from the replay into it.
//
// The audio thread's alone: no lock, no allocation (fixed arrays).
#ifndef NV_RUBFILL_H
#define NV_RUBFILL_H

#include <cmath>

namespace nv {

struct RubFill {
    enum { H = 4096, W = 256, LMIN = 960, LMAX = 1920, XF = 128, FADE_AFTER = 1440, JOIN = 16 };
    float hL[H] = {}, hR[H] = {};
    long long hn = 0;                       // frames heard, ever (the history ends at hn)
    bool on = false;                        // a continuation under way
    int lag = 0;
    long long src = 0;                      // its next frame, in the history
    float gain = 1.0f;
    long run = 0;                           // frames of it so far
    float x0L = 0, x0R = 0, dL = 0, dR = 0; // the last frame heard and its slope (the join's line)
    float fade = 0.99993f;                  // per frame past FADE_AFTER (-3 dB / 10 ms at 48 kHz)

    void set_rate(double sr) { fade = (float)std::pow(10.0, -3.0 / 20.0 / (0.010 * sr)); }

    void heard(const float *L, const float *R, int n)
    {
        for (int i = 0; i < n; i++, hn++) {
            hL[hn % H] = L[i];
            hR[hn % H] = R[i];
        }
    }
    float mono(long long k) const { return hL[k % H] + hR[k % H]; }

    // the stretch back (LMIN-LMAX frames) whose start best continues the last W (0: too little heard, or silence)
    int find_lag() const
    {
        if (hn < W + LMAX)
            return 0;
        double e0 = 0.0;
        for (long long t = hn - W; t < hn; t++)
            e0 += (double)mono(t) * mono(t);
        if (e0 <= 1e-12)
            return 0;
        int best = 0;
        double bc = -2.0;
        // AN ATTACK IN THE STRETCH REPLAYED would be heard again -- a ghost
        // note: the change (first difference) energy in 64-frame pieces, and
        // a stretch whose loudest piece is well over the last 20 ms's mean
        // marked down
        enum { P = 64, NP = H / P };
        double pe[NP];
        const long long p0 = hn - (long long)NP * P;
        for (int k = 0; k < NP; k++) {
            double e = 0.0;
            for (long long t = p0 + (long long)k * P; t < p0 + (long long)(k + 1) * P; t++) {
                const double d = mono(t) - mono(t - 1);
                e += d * d;
            }
            pe[k] = e;
        }
        double ref = 0.0;
        for (int k = NP - LMIN / P; k < NP; k++)
            ref += pe[k];
        ref = ref / (LMIN / P) + 1e-20;
        auto score = [&](int L) {
            double c = 0.0, e = 0.0;
            for (long long t = hn - W; t < hn; t++) {
                const double a = mono(t), b = mono(t - L);
                c += a * b;
                e += b * b;
            }
            if (e <= 1e-12)
                return -2.0;
            double mx = 0.0;
            for (int k = (int)((hn - L - p0) / P); k < NP && k < (int)((hn - L + LMIN - p0) / P); k++)
                mx = pe[k] > mx ? pe[k] : mx;
            const double over = std::log2(mx / ref);
            return c / std::sqrt(e * e0) - (over > 1.0 ? 0.5 * (over - 1.0) : 0.0);
        };
        for (int L = LMIN; L <= LMAX; L += 2) {     // (every other lag, then the best's neighbours)
            const double c = score(L);
            if (c > bc) {
                bc = c;
                best = L;
            }
        }
        for (int L = best - 1; L <= best + 1; L += 2) {
            const double c = score(L);
            if (c > bc) {
                bc = c;
                best = L;
            }
        }
        return best;
    }

    // the continuation's next n frames, heard (into the history: the next period repeats them)
    void gen(float *L, float *R, int n)
    {
        if (!on) {
            on = true;
            lag = find_lag();
            src = hn - lag;
            gain = 1.0f;
            run = 0;
            if (hn >= 2) {
                x0L = hL[(hn - 1) % H];
                x0R = hR[(hn - 1) % H];
                dL = x0L - hL[(hn - 2) % H];
                dR = x0R - hR[(hn - 2) % H];
            }
        }
        for (int i = 0; i < n; i++) {
            if (lag > 0) {
                if (run >= FADE_AFTER)
                    gain *= fade;
                L[i] = hL[src % H] * gain;
                R[i] = hR[src % H] * gain;
                src++;
                // THE JOIN: the stretch's first frame is not quite the next
                // after the last heard -- the first JOIN frames cross from
                // that frame's line into it
                if (run < JOIN) {
                    const float w = 0.5f - 0.5f * std::cos(3.14159265f * (run + 0.5f) / JOIN);
                    const float k = (float)(run + 1);
                    L[i] = w * L[i] + (1.0f - w) * (x0L + dL * k) * gain;
                    R[i] = w * R[i] + (1.0f - w) * (x0R + dR * k) * gain;
                }
            } else {
                L[i] = R[i] = 0.0f;
            }
            run++;
            hL[hn % H] = L[i];                  // (heard at once: a period on, it is the source)
            hR[hn % H] = R[i];
            hn++;
        }
    }

    // the late block's first frames (L, R: its n, at the callback's start),
    // crossed in from the continuation; then heard
    void resume(float *L, float *R, int n)
    {
        if (on && lag > 0) {
            const int m = n < XF ? n : XF;
            float g = gain;
            long long s = src;
            for (int i = 0; i < m; i++) {
                if (run + i >= FADE_AFTER)
                    g *= fade;
                long long k = s + i;
                while (k >= hn)
                    k -= lag;                   // (past the history's end: a period back)
                const float w = 0.5f - 0.5f * std::cos(3.14159265f * (i + 0.5f) / m);
                L[i] = w * L[i] + (1.0f - w) * hL[k % H] * g;
                R[i] = w * R[i] + (1.0f - w) * hR[k % H] * g;
            }
        }
        on = false;
        heard(L, R, n);
    }
};

}  // namespace nv

#endif
