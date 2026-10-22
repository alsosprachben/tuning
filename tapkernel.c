/* REFERENCED TAPS (live.py, the insertion effect's copies).

   A partial on a part with an insertion effect carries a tap set (its
   channel's): every delay repeat, pitch-shifted voice, ring-modulator
   sideband and chorus voice the effect makes of it. Rather than stamping each
   copy into the slab at note-on, the copies are WRITTEN HERE EVERY BLOCK into
   the slab's scratch rows, from the partial as it stands now -- its pitch,
   level, pan and release whatever the note has done since -- and the
   unchanged kernel renders them as rows. So a knob moved on the panel
   reaches held notes, and a press stamps nothing.

   Each copy is the file renderer's (gsdelay.expand, chorus.gs_copies):
     non, noff   + D                      (an unreleased noff stays IDLE)
     om, nf      * ratio, + Hz for a ring modulator (a sideband below 0 Hz
                   folds back, its phase turned: sin(-x + p) = sin(x - p + pi))
     p0, p0R     the copy's phase at its onset the source's at its own, the
                 modulator's phase on the file's clock
     aL, aR      * g * lpf(f) * eq(f') / (eq(f) * dry) * the pan's shelf at
                 the side against the source's (live.Slab.repan's law)
     delL, delR  + the side's interaural delay against the source's
     vd, vr, vp  a chorus voice's LFO on the file's clock, else the note's
                 own vibrato delayed by D
   Moog rows (fx >= 0), organ gates (gr >= 0) and bend rows (br >= 0) read
   tables indexed by absolute block and are not tapped.

   ONLY WHAT SOUNDS IN THIS BLOCK is written: a copy whose onset is after
   the block, or whose end (noff + release + its ears' delays) is before it,
   is no row this block -- and one more than `floor` under the loudest
   tapped partial is none at all, as the file renderer drops its repeats
   (gsdelay.REPEAT_FLOOR).

   Built on its own (live.py ensure_tap_lib); synthkernel.c is untouched. */
#include <math.h>
#include <stdint.h>
#include <string.h>

#define TWO_PI 6.283185307179586

static double eq_db(double f, const double* e, int nmid)
{
    /* gsefx.eq_gain: first-order shelves at their corners, peaking mids */
    double x = (f / e[2]) * (f / e[2]);
    double y = (f / e[3]) * (f / e[3]);
    double db = e[0] / (1.0 + x) + e[1] * y / (1.0 + y);
    for (int k = 0; k < nmid; k++) {
        double mf = e[4 + 3 * k], q = e[5 + 3 * k], mg = e[6 + 3 * k];
        if (mf > 0.0 && mg != 0.0) {
            double u = q * (f / mf - mf / (f > 0.0 ? f : 1e-6));
            db += mg / (1.0 + u * u);
        }
    }
    return db;
}

/* cols: ncol generic columns (pointer, element size) copied whole; the
   patched ones by name below. src: the source rows; set: each one's tap set.
   Tap sets: tap rows [ts[s], ts[s+1]) of the tap arrays; per set an EQ
   (eq + 4 + 3*nmid doubles at eqo[s], nmid[s]; eqo[s] < 0 none) and the
   direct's dry factor (dry[s]).
   Taps: D (samples), g, fc (0 none), r, hz, al1, ar1 (the side's shelf
   coefficients), dl (the side's interaural delay against the source's, as
   delL += dl, delR -= dl), lvd (< 0: no LFO), lvr, lph; per set al0, ar0
   (the source's own pan). Writes rows from dst0 up to dst0 + cap; returns
   how many. */
int tap_expand(int ncol, void** colp, const int* colsz,
               int nsrc, const int64_t* src, const int32_t* set,
               double* om, double* p0, double* p0R, int64_t* non, int64_t* noff,
               float* nf, float* aL, float* aR, float* vd, float* vr, float* vp, float* vdl,
               float* delL, float* delR, const int32_t* fx, const int32_t* gr, const int32_t* br,
               const int32_t* ts, const double* eq, const int32_t* eqo, const int32_t* nmid,
               const double* dry, const double* al0, const double* ar0,
               const int64_t* tD, const double* tg, const double* tfc, const double* tr,
               const double* thz, const double* tal1, const double* tar1, const double* tdl,
               const double* tvd, const double* tvr, const double* tph,
               const float* re, double floor, int64_t n0, int64_t n1,
               double beta, double sr, int64_t idle, int64_t dst0, int cap)
{
    int m = 0;
    double b2 = beta * beta;
    double top = 0.0;
    for (int i = 0; i < nsrc; i++) {
        double x = fabs((double)aL[src[i]]), y = fabs((double)aR[src[i]]);
        if (x > top) top = x;
        if (y > top) top = y;
    }
    double fl = floor * top;
    /* RANK BY RANK -- every note's loudest tap, then every note's next (the
       sets come loudest first: Live._tap_tables) -- so a cap (the budget's:
       Live's governor) drops the quietest echoes everywhere, not one note's
       whole effect */
    int R = 0;
    for (int i = 0; i < nsrc; i++)
        if (set[i] >= 0 && ts[set[i] + 1] - ts[set[i]] > R)
            R = ts[set[i] + 1] - ts[set[i]];
    for (int rk = 0; rk < R; rk++)
    for (int i = 0; i < nsrc; i++) {
        int64_t s = src[i];
        int st = set[i];
        if (st < 0 || ts[st] + rk >= ts[st + 1] || fx[s] >= 0 || gr[s] >= 0 || br[s] >= 0)
            continue;
        if (aL[s] == 0.0f && aR[s] == 0.0f)
            continue;
        double oms = om[s];
        double f = oms * sr / TWO_PI;
        if (f <= 0.0)
            continue;
        double wn = TWO_PI * (double)nf[s];
        double sh0L = sqrt((al0[st] * wn) * (al0[st] * wn) + b2);
        double sh0R = sqrt((ar0[st] * wn) * (ar0[st] * wn) + b2);
        double eq0 = eqo[st] >= 0 ? eq_db(f, eq + eqo[st], nmid[st]) : 0.0;
        double ph0L = p0[s] + oms * ((double)non[s] + (double)delL[s]);
        double ph0R = p0R[s] + oms * ((double)non[s] + (double)delR[s]);
        {
            int t = ts[st] + rk;
            if (m >= cap)
                return m;
            int64_t D = tD[t];
            int64_t on2 = non[s] + D;
            if (on2 >= n1)
                continue;                                   /* not yet begun */
            if (noff[s] != idle) {
                double dmx = delL[s] > delR[s] ? delL[s] : delR[s];
                if ((double)(noff[s] + D) + re[s] + (dmx > 0.0 ? dmx : 0.0) + 2.0 * (n1 - n0) < (double)n0)
                    continue;                               /* already rung out */
            }
            double fr = f * tr[t] + thz[t];
            if (fr == 0.0)
                continue;
            int flip = fr < 0.0;
            double ratio = fabs(fr) / f;
            double g = tg[t] / dry[st];
            if (tfc[t] > 0.0)
                g /= sqrt(1.0 + (f / tfc[t]) * (f / tfc[t]));
            if (eqo[st] >= 0)
                g *= pow(10.0, (eq_db(f * ratio, eq + eqo[st], nmid[st]) - eq0) / 20.0);
            double gl = g * sqrt((tal1[t] * wn) * (tal1[t] * wn) + b2) / sh0L;
            double grr = g * sqrt((tar1[t] * wn) * (tar1[t] * wn) + b2) / sh0R;
            if (fabs((double)aL[s] * gl) < fl && fabs((double)aR[s] * grr) < fl)
                continue;                                   /* under the floor */
            int64_t d = dst0 + m;
            for (int c = 0; c < ncol; c++)
                memcpy((char*)colp[c] + d * colsz[c], (char*)colp[c] + s * colsz[c], colsz[c]);
            non[d] = on2;
            noff[d] = noff[s] == idle ? idle : noff[s] + D;
            double om2 = oms * ratio;
            om[d] = om2;
            nf[d] = (float)((double)nf[s] * ratio);
            delL[d] = (float)((double)delL[s] + tdl[t]);
            delR[d] = (float)((double)delR[s] - tdl[t]);
            double mp = TWO_PI * thz[t] * (double)non[d] / sr;
            double qL = ph0L + mp, qR = ph0R + mp;
            if (flip) { qL = M_PI - qL; qR = M_PI - qR; }
            p0[d] = -om2 * ((double)non[d] + (double)delL[d]) + qL;
            p0R[d] = -om2 * ((double)non[d] + (double)delR[d]) + qR;
            aL[d] = (float)((double)aL[s] * gl);
            aR[d] = (float)((double)aR[s] * grr);
            if (tvd[t] >= 0.0) {
                vd[d] = (float)tvd[t];
                vr[d] = (float)tvr[t];
                vp[d] = (float)fmod(TWO_PI * tvr[t] * (double)non[d] / sr + tph[t], TWO_PI);
                vdl[d] = 0.0f;
            } else if (D) {
                vp[d] = (float)((double)vp[s] - TWO_PI * (double)vr[s] * (double)D / sr);
            }
            m++;
        }
    }
    return m;
}
