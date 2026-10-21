// Block additive-synth kernel for the organ/pipe voices (see blockrender.py).
//
// Each partial is a constant-frequency sinusoid, so its two ears are the SAME
// phasor with a per-ear amplitude (HRTF head-shadow gain, folded in by the
// caller) and a per-ear phase offset (the HRTF/path delay -- a pure sinusoid
// delayed is just phase-shifted, folded into ph0L/ph0R). Synthesis is a phasor
// recurrence (no sin/cos in the sample loop); amplitude is evaluated once per
// block from env * drawn-stop gate * swell shutter. Phase bookkeeping is f64
// (reset per block from the analytic angle), the recurrence f32. OpenMP runs
// over disjoint time chunks so threads never share output samples.
#include <math.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <omp.h>

// THE SAMPLE RATE, at compile time. It was six hardcoded 44100s, so it could not
// be changed at all; a live front end has to match whatever the audio device runs
// (PipeWire here is 48000, and resampling in the path is both latency and a filter
// we did not choose). A compile-time constant rather than a parameter because
// -ffast-math folds division by a literal into a reciprocal multiply: passing the
// rate in at runtime measurably changed the output of the existing corpus, and
// this way the 44100 build is byte-for-byte what it always was. blockrender caches
// one .so per rate.
#ifndef SRATE
#define SRATE 44100
#endif
#define SRATE_D ((double)SRATE)
#define SRATE_F ((float)SRATE)
// THE LONGEST ATTACK THAT IS A STRIKE (voice_block.inc's onset rule): one this
// short starts as a step, one longer ramps through a knee. Just past 1.5 ms:
// the cymbals and hats are 1.5 exactly (66.15 samples), and at 0.0015 float
// rounding sent their attacks both ways. The woodblocks, claves and guiros
// (4 ms by their classes) ramp: their step was the same position-dependent
// click as the pianos' (Ben: go ahead).
#define KNEE_MIN (0.0016f*SRATE_F)

/* CC78, vibrato delay: how long a delayed vibrato takes to bloom in once its
   delay has passed. tonelib.VIB_BLOOM_S must match; the selftest reads both. */
#define VIB_BLOOM 0.25

/* A DRUM MACHINE'S SWEEP, the tension bend's second shape (a NEGATIVE cutoff,
   |cut| the time): f/f0 = e^{tb e^{-t/tau}} -- an exponential control voltage,
   so the PITCH falls exponentially from the start's ln-ratio tb -- where the
   strike's bend is f/f0 = 1 + tb e^{-t/tau}. Its phase, the integral of
   (f/f0 - 1), is the series tau sum_k tb^k/(k k!) (1 - e^{-k t/tau}), whose
   first term is the linear bend exactly: closed form, so a block re-anchors
   from it as the linear one does; |tb| <= ~2 (7x) converges to double
   precision in under 30 terms.

   OUT OF LINE, AND AFTER the linear bend rather than around it: the linear
   lines in voice_block.inc are left exactly as they were, because branching
   them changed what gcc made of them under -ffast-math and moved 94 of the
   corpus's 167 files by a rounding. */
static double tbend_series(double tb, double tau, double c, double t) {
    double tt = t < c ? t : c, e = exp(-tt / tau);
    double sum = 0.0, term = 1.0, ek = 1.0;
    for (int k = 1; k <= 40; k++) {
        term *= tb / (double)k;
        ek *= e;
        sum += term * (1.0 - ek) / (double)k;
        if (fabs(term) < 1e-17 * (fabs(sum) + 1e-30)) break;
    }
    return tau * sum;
}

/* THE CUTOFF IS CARRIED SCALED DOWN by TBEND_CUT_SCALE. The linear bend's
   lines run first, untouched, and read the negative cutoff as a time: they add
   tb*tau*(1 - e^{-cut/tau}) to the phase and this path takes it back out. With
   the cutoff as itself (-1.6 s on a 26 ms sweep) that term is e^{61}, ~1e26 --
   the note's phase cannot survive being added to it and subtracted, and every
   block edge stepped: a click 11.6 ms apart on every swept drum (an 808 kick's
   >1 kHz band 20 dB over the machine's). Scaled, -cut/tau is ~1e-5 and the
   term all but zero. Mirrored in blockrender.py and register.py. */
#define TBEND_CUT_SCALE 1048576.0

__attribute__((noinline))
static void tbend_log(float tb, float ts, float cut, float t0, float t1,
                      float* integ, float* bendfac) {
    double c = -(double)cut * TBEND_CUT_SCALE;
    double i0 = tbend_series(tb, ts, c, t0), i1 = tbend_series(tb, ts, c, t1);
    *integ = (float)i0;
    double dt = (double)t1 - (double)t0;
    *bendfac = (float)(dt > 0.0 ? 1.0 + (i1 - i0) / dt
                                : 1.0 + (t0 < c ? expm1(tb * exp(-t0 / ts)) : 0.0));
}


/* The integral of g(s)*sin(w2*s + ph) from note-on to x, where the depth
   envelope g is 0 until t1, rises linearly to 1 over [t1, t2], and stays 1.
   Closed form, by parts on the ramp -- so a delayed vibrato keeps the EXACT
   phase the constant-depth one has, and blooming in costs no click: a depth
   that changed per block, evaluated with the constant-depth formula, would
   jump the phase at every block boundary. */
static inline double vib_ramp_integral(double x, double t1, double t2,
                                       double w2, double ph) {
    if (x <= t1) return 0.0;
    double B = t2 - t1;
    double xe = x < t2 ? x : t2;
    double r = (-(xe - t1) * cos(w2 * xe + ph) / w2
                + (sin(w2 * xe + ph) - sin(w2 * t1 + ph)) / (w2 * w2)) / B;
    if (x > t2) r += (cos(w2 * t2 + ph) - cos(w2 * x + ph)) / w2;
    return r;
}

#define RAND_GRAN 100000.0

// THE CHIFF'S RANDOMNESS, TWISTED. This used to read a 100000-entry table at
// index floor(t * f * granularity) MOD granularity, and that index depends on
// the NOTE: the sequence returns to its start at the smallest L samples where
// L * f / srate is a whole number, so how random the chiff is depends on how
// round the partial's frequency happens to be. Measured, at A=440: A2 (110 Hz)
// repeats every 200 ms -- a 5 Hz flutter -- and A3 and A4 every 50 ms, while
// E4, C4, G3 and D4 do not repeat inside a second at all. These renders use
// hybrid at A=441, where the A octaves are 110.25 / 220.5 / 441 and repeat at
// exactly the partial's own period: for those notes the chiff stops being noise
// altogether and becomes a fixed periodic waveform, purely harmonic, while the
// note a semitone away is still noisy. An inconsistency across the keyboard,
// worst on whichever notes the tuning happens to make round.
//
// Same index, no wrap and no table -- run through a splitmix64 finaliser
// instead. A stateless hash never repeats and treats every note alike, and any
// renderer that computes the same index gets the same value with nothing to
// carry between them.
static inline double hash01(uint64_t x) {
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    x ^= x >> 31;
    return (double)(x >> 11) * (1.0 / 9007199254740992.0);
}

// THE CHIFF'S INDEX, EXACT. It was floor(sec * nf * gran) in double, and a
// double's last-bit rounding of a product near 1e9-1e10 decided about one index
// in 25,000 -- which no machine without IEEE doubles (a GPU's float units)
// reproduces. Now: the step nf*gran/SRATE, a double, split into its integer part
// and its fraction scaled by 2^64 (both exact, a double having 53 bits), and the
// index floor(n * step) in integers, the 128-bit product's top half. Exact on
// anything with 64-bit integers; the GPU path computes the identical value.
static inline void chiff_step(double step, uint64_t* khi, uint64_t* klo){
    double ip = floor(step);
    *khi = (uint64_t)ip;
    *klo = (uint64_t)ldexp(step - ip, 64);
}
static inline uint64_t chiff_index(long n, uint64_t khi, uint64_t klo){
    uint64_t un = (uint64_t)n;
    return un*khi + (uint64_t)(((unsigned __int128)un * klo) >> 64);
}

static inline float smoothstep(float x) {
    if (x <= 0.f) return 0.f;
    if (x >= 1.f) return 1.f;
    return x * x * (3.f - 2.f * x);
}

void synth_organ(
    float* outL, float* outR, long N, int BLK, int nblk, int P,
    const double* omega, const double* ph0L, const double* ph0R,
    const float* ampL, const float* ampR, const float* nomfreq,
    const long* non, const long* noff, const float* fadeS, const float* relS,
    const int* grow, const int* crow, const float* G, const float* S,
    float sfloor, float spow, float shmax, float shref, long CHUNK)
{
    long nchunks = (N + CHUNK - 1) / CHUNK;
    #pragma omp parallel for schedule(dynamic)
    for (long c = 0; c < nchunks; c++) {
        long cs = c * CHUNK, ce = cs + CHUNK; if (ce > N) ce = N;
        for (int p = 0; p < P; p++) {
            long a = non[p], z = noff[p] + (long)relS[p] + BLK;
            if (a >= ce || z <= cs) continue;               // partial idle in this chunk
            double w = omega[p]; float invf = 1.f / fadeS[p], invr = 1.f / relS[p];
            float aL = ampL[p], aR = ampR[p], nf = nomfreq[p];
            const float* Grow = G + (long)grow[p] * nblk;
            const float* Srow = S + (long)crow[p] * nblk;
            long bstart = (cs > a ? cs : a) / BLK, bend = (ce < z ? ce : z + 1) / BLK + 1;
            for (long b = bstart; b < bend; b++) {
                long ns = b * BLK, ne = ns + BLK;
                if (ns < cs) ns = cs; if (ne > ce) ne = ce; if (ns >= ne) continue;
                long mid = (ns + ne) / 2;
                float env = smoothstep((mid - a) * invf) * (1.f - smoothstep((mid - noff[p]) * invr));
                if (env <= 0.f) continue;
                float sw = Srow[b < nblk ? b : nblk - 1];
                float shut = 1.f;
                if (sw < 1.f) {
                    float lvl = sfloor + (1.f - sfloor) * powf(sw, spow);
                    shut = lvl * expf(-(1.f - sw) * shmax * (nf / shref));
                }
                float g = Grow[b < nblk ? b : nblk - 1];
                float m = env * g * shut;
                if (m <= 1e-6f) continue;
                double phL = ph0L[p] + w * (double)ns, phR = ph0R[p] + w * (double)ns;
                float zrL = cos(phL), ziL = sin(phL), zrR = cos(phR), ziR = sin(phR);
                float rr = cosf(w), ri = sinf(w);
                float cL = aL * m, cR = aR * m;
                for (long n = ns; n < ne; n++) {
                    outL[n] += cL * zrL; outR[n] += cR * zrR;
                    float t;
                    t = zrL * rr - ziL * ri; ziL = zrL * ri + ziL * rr; zrL = t;
                    t = zrR * rr - ziR * ri; ziR = zrR * ri + ziR * rr; zrR = t;
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// General voice kernel: adds a two-stage decay envelope (piano/brass) and the
// chiff (a per-sample jittered-phase copy of the partial; strings/brass/pipes).
// Organ registration is optional: grow[p] >= 0 selects a drawn-stop gate row and
// crow[p] a swell row; grow[p] < 0 means "always on, no swell" (all other voices).
// Amplitude is interpolated between block endpoints so fast decays don't step.
static inline float sstep(float x){ if(x<=0.f)return 0.f; if(x>=1.f)return 1.f; return x*x*(3.f-2.f*x); }

/* A CHIFF SHORTER THAN A BLOCK. voice_block.inc reads the attack hump once a
   block, at its MIDDLE, and holds it: right for a burst spanning blocks, but a
   burst shorter than one (the metronome click's, 8.3 ms against 11.6) lands
   between two middles or on one depending on where in the block the note
   starts -- the click swung 13 dB in a cycle, beat by beat (Ben: "the click is
   varying in a period pattern, maybe related to where in the block it is
   being struck").

   So such a block takes the ONE level that puts the energy the burst puts in
   it, sample by sample. The chiff is the partial's own copy, phase-jittered
   uniformly over 2*pi*cc and scaled by jfa = jf*A (A = cv*csc), so a sample
   carries m^2 * (1 + 2 cos(j) jfa + jfa^2), j its draw -- at cv 28 (the
   click) far from the jfa^2 an RMS would match. Over the samples the block
   renders, weighted by the amplitude the loop gives it (the attack's knee,
   then the block's line), with each sample's own draw, the one level x whose
   energy is the samples' sum. Shared by both render paths through
   voice_block.inc, so file, live and GPU take it alike. Out of line, after
   the midpoint lines, which stay as they were: voices whose bursts span
   blocks never reach it (kernel-edits rule; bitident). */
/* EACH EAR ITS OWN ONSET, the CPU's attack: from ns to the later of the two
   knees, each ear its own ramp (from its origin kA to its knee kN; equal:
   silent before it) or, past its knee, the block's line -- as the loop after
   would draw it -- with the phasor, the chiff and the send exactly as there.
   Out of line, and only where the ears' ramps differ (voice_block.inc): the
   loop every other block takes is spelled as it was (kernel-edits rule).
   Returns where the loop after resumes. */
__attribute__((noinline))
static long ear_knees(long ns, long ne, long n0, long bs0, float invb,
                      long kAl, long kNl, float kgL, long kAr, long kNr, float kgR,
                      float mL0, float mL1, float mR0, float mR1, float aL, float aR,
                      float* zrL_, float* ziL_, float* zrR_, float* ziR_, float rr, float ri,
                      float jfa, uint64_t chk_hi, uint64_t chk_lo, float cc,
                      float* outL, float* outR, float* outSL, float* outSR, float swp){
    long kmax = kNl>kNr ? kNl : kNr;
    long ke = kmax<ne ? kmax : ne;
    float zrL=*zrL_, ziL=*ziL_, zrR=*zrR_, ziR=*ziR_;
    for(long n=ns;n<ke;n++){
        float t=(float)(n-bs0)*invb, mL, mR;
        if(n<kNl) mL = (kNl>kAl && n>=kAl) ? kgL*((float)(n-kAl)/(float)(kNl-kAl))*aL : 0.f;
        else      mL = (mL0+(mL1-mL0)*t)*aL;
        if(n<kNr) mR = (kNr>kAr && n>=kAr) ? kgR*((float)(n-kAr)/(float)(kNr-kAr))*aR : 0.f;
        else      mR = (mR0+(mR1-mR0)*t)*aR;
        float sL=zrL, sR=zrR;
        if(jfa>0.f){
            float jit=6.2831853f*(float)hash01(chiff_index(n, chk_hi, chk_lo))*cc;
            float cj=cosf(jit),sj2=sinf(jit);
            sL += (zrL*cj - ziL*sj2)*jfa;
            sR += (zrR*cj - ziR*sj2)*jfa;
        }
        outL[n-n0]+=mL*sL; outR[n-n0]+=mR*sR;
        if(outSL){ outSL[n-n0]+=mL*sL*swp; outSR[n-n0]+=mR*sR*swp; }
        float tmp; tmp=zrL*rr-ziL*ri; ziL=zrL*ri+ziL*rr; zrL=tmp;
        tmp=zrR*rr-ziR*ri; ziR=zrR*ri+ziR*rr; zrR=tmp;
    }
    *zrL_=zrL; *ziL_=ziL; *zrR_=zrR; *ziR_=ziR;
    return ke>ns ? ke : ns;
}

#if defined(LESLIE_KERNEL) || defined(VOICE_BLOCK)
/* THE LESLIE'S LOBE, AS A GAIN (leslie.py). A rotor row's level is its
   lobe at where its rotor has got to: fl + (1-fl)*((1+cos(angle-ph))/2)^sh,
   times nm (one over the lobe's mean, so it colours and does not level).
   LANG holds each rotor's angle at every grid point (MOOG_GRID samples, the
   live callback's block, so the file and the player swing on the same
   points); the lobe is worked out at the block's grid points here and drawn
   as a line between them, as a Moog's level is. It replaced sidebands, which
   froze each note at the rotor speed it started under and, to keep their
   number down, needed the whole file's loudest row before the first Leslie
   note could render. Out of line, both of these (kernel-edits rule): every
   other row takes the loops it always took. */
__attribute__((noinline))
static void leslie_grid(const float* LANG, long lgn, int rot, float ph, float fl, float sh, float nm,
                        long bs0, int mg, int nj, float* lg){
    const float* A=LANG+(long)rot*lgn;
    long g0=bs0/mg;
    for(int j=0;j<nj;j++){
        long gi=g0+j; if(gi>lgn-1) gi=lgn-1;
        float c=0.5f*(1.f+cosf(A[gi]-ph));
        lg[j]=(fl+(1.f-fl)*powf(c,sh))*nm;
    }
}
/* ...and the CPU's sample loop for such a row, the whole block: each ear's
   attack and the block's line exactly as ear_knees draws them (one knee, or
   none, is the case where the two ears' are equal), times the lobe. */
__attribute__((noinline))
static void leslie_samples(long ns, long ne, long n0, long bs0, float invb, int mg, const float* lg,
                           long kAl, long kNl, float kgL, long kAr, long kNr, float kgR,
                           float mL0, float mL1, float mR0, float mR1, float aL, float aR,
                           float zrL, float ziL, float zrR, float ziR, float rr, float ri,
                           float jfa, uint64_t chk_hi, uint64_t chk_lo, float cc,
                           float* outL, float* outR, float* outSL, float* outSR, float swp){
    float invg=1.f/(float)mg;
    for(long n=ns;n<ne;n++){
        float t=(float)(n-bs0)*invb, mL, mR;
        if(n<kNl) mL = (kNl>kAl && n>=kAl) ? kgL*((float)(n-kAl)/(float)(kNl-kAl))*aL : 0.f;
        else      mL = (mL0+(mL1-mL0)*t)*aL;
        if(n<kNr) mR = (kNr>kAr && n>=kAr) ? kgR*((float)(n-kAr)/(float)(kNr-kAr))*aR : 0.f;
        else      mR = (mR0+(mR1-mR0)*t)*aR;
        long k=n-bs0; long j=k/mg;
        float g=lg[j]+(lg[j+1]-lg[j])*((float)(k-j*mg)*invg);
        mL*=g; mR*=g;
        float sL=zrL, sR=zrR;
        if(jfa>0.f){
            float jit=6.2831853f*(float)hash01(chiff_index(n, chk_hi, chk_lo))*cc;
            float cj=cosf(jit),sj2=sinf(jit);
            sL += (zrL*cj - ziL*sj2)*jfa;
            sR += (zrR*cj - ziR*sj2)*jfa;
        }
        outL[n-n0]+=mL*sL; outR[n-n0]+=mR*sR;
        if(outSL){ outSL[n-n0]+=mL*sL*swp; outSR[n-n0]+=mR*sR*swp; }
        float tmp; tmp=zrL*rr-ziL*ri; ziL=zrL*ri+ziL*rr; zrL=tmp;
        tmp=zrR*rr-ziR*ri; ziR=zrR*ri+ziR*rr; zrR=tmp;
    }
}

/* A FILTER THAT MOVES (efxfilter.py: a Phaser, a wah, a Step Flanger, a
   Humanizer): each grid point's lg multiplied by the filter's |H| at the
   row's own frequency, the filter where its control (FCT: per channel, on
   the grid, as LANG is per rotor) has it. The row's type and parameters
   (fty, fpa, fpb, fpc) as efxfilter.response reads them. Out of line, and
   only in the builds that carry the lobe (kernel-edits rule). */
__attribute__((noinline))
static void filter_grid(const float* FCT, long fgn, int row, int ty, float pa, float pb, float pc,
                        float nf, long bs0, int mg, int nj, float* lg){
    long g0=bs0/mg;
    for(int j=0;j<nj;j++){
        long gi=g0+j; if(gi>fgn-1) gi=fgn-1;
        float c=FCT[(long)row*fgn+gi], h=1.f;
        if(ty==1 || ty==4){
            /* the phaser's all-passes, or the comb's line: z, then
               (1 - mix) + mix z / (1 - r z) */
            float ph = ty==1 ? -2.f*pc*atanf(nf/fmaxf(c,1.f)) : -6.2831853f*nf*c;
            float zr=cosf(ph), zi=sinf(ph), r = pb, mx = pa;
            float dr=1.f-r*zr, di=-r*zi, dd=dr*dr+di*di;
            float ar=(zr*dr+zi*di)/dd, ai=(zi*dr-zr*di)/dd;
            float yr=(1.f-mx)+mx*ar, yi=mx*ai;
            h=sqrtf(yr*yr+yi*yi);
        } else if(ty==2 || ty==3){
            float x=nf/fmaxf(c,1.f), q=fmaxf(pa,0.1f);
            float den=sqrtf((1.f-x*x)*(1.f-x*x)+(x/q)*(x/q));
            float w = ty==2 ? 1.f/den : (x/q)/den;
            h=(1.f-pb)+pb*w;
        } else if(ty==5){
            h=pa;
            for(int k=0;k<3;k++){
                float F=FCT[(long)(row+k)*fgn+gi];
                float B = k==0 ? 80.f : k==1 ? 110.f : 160.f, A = k==0 ? 1.f : k==1 ? 0.7f : 0.5f;
                float u=(nf-F)/(0.5f*B);
                h+=A/(1.f+u*u);
            }
            h*=pb;
        }
        lg[j]*=h;
    }
}
#endif

__attribute__((noinline))
static float jf_short_chiff(long bs0, long a, float chw, float sj, long blk,
                            float A, float cc, float m0, float m1, float nf, float bw,
                            long kA, long kN, float kg, long ns){
    // from the block's first sample the loop draws (ns: the arrival, past the
    // onset's travel delay), not its start -- what is not drawn carries nothing
    long n0 = ns > a ? ns : a, n1 = bs0 + blk;
    if(n1 <= n0 || A <= 0.f) return 0.f;
    // the very draws the block's loop will take (chiff_step, chiff_index):
    // a draw is held 1/(nf*bw) s -- longer than the whole burst at the click's
    // bw 0.055 -- so a burst's copy is coherent by cos(its draw), not by the
    // uniform draw's mean
    uint64_t khi = 0, klo = 0;
    if(bw > 0.f) chiff_step((double)nf * (double)bw / SRATE_D, &khi, &klo);
    double W = 0.0, C = 0.0, Q = 0.0; float invch = 1.f / chw; double Ad = (double)A;
    for(long n = n0; n < n1; n++){
        float v;
        if(n < a + (long)chw){ float s = sstep((float)(n - a) * invch); float r = sqrtf(s); v = fmaxf(r * (1.f - r), sj * s); }
        else v = sj;
        // the amplitude the loop gives this sample: the knee's ramp to kN (the
        // attack, which a short burst sits inside), then the block's line
        double m = (n < kN && kN > kA) ? (double)kg * (double)(n - kA) / (double)(kN - kA)
                 : (double)m0 + ((double)m1 - (double)m0) * (double)(n - bs0) / (double)blk;
        double w = m * m;
        double cj = cos(6.283185307179586 * hash01(chiff_index(n, khi, klo)) * (double)cc);
        W += w; C += w * cj; Q += w * (2.0 * Ad * cj * v + Ad * Ad * (double)v * v);
    }
    if(W <= 0.0) return 0.f;
    // A^2 x^2 W + 2 A x C = Q, the positive root
    double x = (-C + sqrt(C * C + W * Q)) / (Ad * W);
    return x > 0.0 ? (float)x : 0.f;
}

// THE MOOG: a ladder filter and two contours, evaluated per partial -- the C
// mirror of moog.py, which is the reference and says why each law is what it
// is. A Moog partial has fx >= 0: its row FT[fx] holds what is fixed at the
// key (key tracking, the contours' times, the filter mode), and the knob rows
// KN hold what a knob moves while the note sounds (cutoff, resonance, EG
// amount, the two sustains), one entry per grid point so a knob never steps
// at a block boundary. fx < 0, or no fx at all, is every other voice, whose
// arithmetic is untouched.
#define FTW 30          // FT: kbfac fA fD fR aA aD aR mode res_bass krow f0 pre_amp flags
                        //     fm_index, then FM_J complex modulator coefficients
#define FM_J 8
#define FT_PITCH 1      // flags: OSC 2 follows its note's pitch rows (MPI/MPC/MPR)
                        // 2 / 4 / 8: OSC 1 / OSC 2 / SUB's shape moves (MKI/MPK)
                        // 16: 1 -> 2 FM (FT 13-29, and OSC 1's phase in fmw/fmp/fmpR)
#define KNW 9           // KN: cutoff_hz k eg_octaves f_sustain a_sustain
                        //     lfo_hz lfo_octaves lfo_shape lfo_reset
#define MOOG_GRID 128   // samples between evaluations: the live block, so a
                        // file render and the player land on the same points
// THE CONTOURS (moog.adsr, measured): the attack charges toward MS_ATK_T and
// is cut at 1, MS_ATK_K = ln(T/(T-1)) time constants in; the decay falls
// toward S (the sustain's target, below zero for a low one), the release
// toward -MS_UNDER, and the contour stops at zero
#define MS_ATK_T 1.03
#define MS_ATK_K 3.5361166995615263
#define MS_UNDER 0.055
static inline float moog_held(float tt, float A, float D, float S){
    if(tt<0.f) return 0.f;
    if(tt<A) return (float)MS_ATK_T*(1.f-expf(-tt*(float)MS_ATK_K/fmaxf(A,1e-6f)));
    return fmaxf(0.f, S+(1.f-S)*expf(-(tt-A)/(fmaxf(D,1e-6f)*0.25f)));
}
static inline float moog_adsr(float t, float A, float D, float S, float R, float toff){
    if(t>=toff) return fmaxf(0.f, (moog_held(toff,A,D,S)+(float)MS_UNDER)*expf(-(t-toff)/(fmaxf(R,1e-6f)*0.25f))-(float)MS_UNDER);
    return moog_held(t,A,D,S);
}
// the output stage after the ladder and VCA (moog.output_gain): one pole at
// MS_OUT_HZ, every partial once -- sidebands and the ladder's own sine too
#define MS_OUT_HZ 12500.f
static inline float moog_out(float f){ float r=f/MS_OUT_HZ; return 1.f/sqrtf(1.f+r*r); }
static inline float moog_ladder(float x, float k, int mode, int rb){
    // |H| = |num| / |(1+jx)^4 + k|, the modes mixing the poles (moog.ladder_gain);
    // the band-pass and high-pass as measured: their corners moved, their
    // gains under the low-passes', the high-pass over a leak of the dry signal
    if(mode==2) x*=(float)(1.0/1.05);
    else if(mode==3) x*=(float)(1.0/0.91);
    float x2=x*x, re4=1.f-6.f*x2+x2*x2+k, im4=4.f*x-4.f*x*x2;
    if(mode==3){
        float nr=x2*x2-x2, ni=-2.f*x2*x, d2=re4*re4+im4*im4;
        float hr=0.47863f*(nr*re4+ni*im4)/d2+0.071f, hi=0.47863f*(ni*re4-nr*im4)/d2;
        return sqrtf(hr*hr+hi*hi);
    }
    float den=sqrtf(re4*re4+im4*im4);
    float num = mode==0 ? 1.f : mode==1 ? 1.f+x2 : 0.41687f*4.f*x2;   // moog.BP_GAIN
    float h=num/den;
    if(rb && mode<2) h*=1.f+k;
    return h;
}

// 1 -> 2 FM AS SIDEBANDS, so the ladder hears each one where it sounds. On the
// hardware the FM is at the oscillator and the filter comes after it, so a
// closing contour mellows an FM bell; filtering the whole modulated harmonic
// at its carrier's frequency (as this kernel first did) left every sideband
// at full strength over a shut ladder. A harmonic k phase-modulated by
// k I A(th1) is sum_m D_m e^{i(k th2 + m th1)}, D_m the Fourier coefficients
// of e^{i k I A} over one turn of OSC 1 -- note constants, computed here per
// block by an N-point FFT, N enough to hold the deviation (k I max|A'|, in
// units of f1) and OSC 1's own FM_J harmonics. Kept: the narrowest |m| <= M
// holding all but FM_TAIL of the energy (which is 1). Wider than FM_SBMAX --
// a low note, a high harmonic, a deep index -- and the caller falls back to
// the unfiltered phase modulation, which is what that partial always had.
#define FM_SBMAX 160
#define FM_NMAX 512
#define FM_TAIL 1e-11
// A sideband this far under its own harmonic -- its D_m and the ladder there
// together -- is not summed. RELATIVE, and decided per cell from that cell's
// two grid points alone: a floor on the partial's absolute level, or on its
// block's peak, made live (headroom, 128-sample blocks) drop different
// sidebands from the file (512) and the two came apart by 2e-5.
#define SB_TOL 1e-6f
static void fm_fft(double* xr, double* xi, int n){
    for(int i=1,j=0;i<n;i++){
        int bit=n>>1; for(;j&bit;bit>>=1) j^=bit; j^=bit;
        if(i<j){ double t=xr[i];xr[i]=xr[j];xr[j]=t; t=xi[i];xi[i]=xi[j];xi[j]=t; }
    }
    for(int len=2;len<=n;len<<=1){
        double ang=-6.283185307179586/(double)len, wr=cos(ang), wi=sin(ang);
        for(int i=0;i<n;i+=len){
            double cr=1.0, ci=0.0;
            for(int k=0;k<len/2;k++){
                double ur=xr[i+k], ui=xi[i+k];
                double vr=xr[i+k+len/2]*cr-xi[i+k+len/2]*ci, vi=xr[i+k+len/2]*ci+xi[i+k+len/2]*cr;
                xr[i+k]=ur+vr; xi[i+k]=ui+vi; xr[i+k+len/2]=ur-vr; xi[i+k+len/2]=ui-vi;
                double t=cr*wr-ci*wi; ci=cr*wi+ci*wr; cr=t;
            }
        }
    }
}
// D_{-M..M} into Dr/Di (index m+M); returns M, or -1 to fall back
static int fm_sidebands_calc(const float* B, float kI, float* Dr, float* Di){
    double sj=0.0;
    for(int j=0;j<FM_J;j++) sj+=(double)(j+1)*sqrt((double)B[2*j]*B[2*j]+(double)B[2*j+1]*B[2*j+1]);
    double ext=fabs((double)kI)*sj+FM_J+10.0;
    int n=32; while(n<2.0*ext && n<=FM_NMAX) n<<=1;
    if(n>FM_NMAX) return -1;
    double xr[FM_NMAX], xi[FM_NMAX];
    for(int i=0;i<n;i++){
        double th=6.283185307179586*(double)i/(double)n, A=0.0;
        for(int j=0;j<FM_J;j++) A+=(double)B[2*j]*sin((j+1)*th)+(double)B[2*j+1]*cos((j+1)*th);
        double ph=(double)kI*A; xr[i]=cos(ph)/(double)n; xi[i]=sin(ph)/(double)n;
    }
    fm_fft(xr,xi,n);
    // the tail, from the outside in: the smallest M leaving < FM_TAIL outside
    double tail=0.0; int M=n/2-1;
    while(M>0){
        int a=M, b=n-M;
        double e=xr[a]*xr[a]+xi[a]*xi[a]+xr[b]*xr[b]+xi[b]*xi[b];
        if(tail+e>=FM_TAIL) break;
        tail+=e; M--;
    }
    if(M>FM_SBMAX) return -1;
    for(int m=-M;m<=M;m++){
        int i = m>=0 ? m : n+m;
        Dr[m+M]=(float)xr[i]; Di[m+M]=(float)xi[i];
    }
    return M;
}
// ...REMEMBERED. D depends on k I and OSC 1's wave alone -- not on the pitch
// or the block -- so the FFT runs once per (k I, wave) rather than once per
// partial per block, which was nearly all of the cost. NOT ON THE NOTE EITHER,
// once its phase is taken out: each note's B is anchored to the phase its own
// OSC 1 fundamental carries (moog.fm_coeffs, phi1), B_j = B'_j e^{-i j psi},
// so A(th) = A'(th - psi) and D_m = D'_m e^{-i m psi}. B' -- B_1 turned real
// -- is the key, rounded to 1e-7 so two notes' float roundings of the one
// wave share an entry, and D' is computed FROM the rounded key, so a hit is
// bit for bit what a miss would have made.
//
// ONE CACHE FOR EVERY THREAD, direct-mapped. Per thread it was empty on every
// call -- the kernel's threads do not outlive one -- and missed half its
// lookups. Each entry carries a sequence count (a seqlock): odd while a
// thread writes it, so a reader that sees it change under its copy, or odd,
// computes its own, and a writer that cannot take an entry simply does not
// publish. The copy is the caller's anyway: it turns D' by its own psi.
typedef struct { int seq, M; float kI, B[2*FM_J]; float Dr[2*FM_SBMAX+1], Di[2*FM_SBMAX+1]; } fm_ent;
#define FM_CACHE 512
static fm_ent fm_cache[FM_CACHE];
static int fm_sidebands(const float* B, float kI, float* Dr, float* Di, double* psi){
    double b1=hypot((double)B[0],(double)B[1]);
    double ps = b1>1e-9 ? -atan2((double)B[1],(double)B[0]) : 0.0;
    float Bq[2*FM_J];
    for(int j=0;j<FM_J;j++){
        double c=cos((j+1)*ps), sn=sin((j+1)*ps);
        double br=(double)B[2*j]*c-(double)B[2*j+1]*sn, bi=(double)B[2*j]*sn+(double)B[2*j+1]*c;
        Bq[2*j]=(float)(nearbyint(br*1e7)*1e-7); Bq[2*j+1]=(float)(nearbyint(bi*1e7)*1e-7);
    }
    for(int j=0;j<2*FM_J;j++){   // -0 is +0: one key, not two
        uint32_t u; memcpy(&u,Bq+j,4); if((u&0x7fffffffu)==0u){ u=0u; memcpy(Bq+j,&u,4); }
    }
    uint32_t h=2166136261u, u;
    memcpy(&u,&kI,4); h=(h^u)*16777619u;
    for(int j=0;j<2*FM_J;j++){ memcpy(&u,Bq+j,4); h=(h^u)*16777619u; }
    // MIXED before the slot is taken: a multiply carries low bits only
    // upward, and k I = 1.5, 3, 4.5 ... are floats whose low bits are all
    // zero -- unmixed, every harmonic of a note fell in one slot
    h^=h>>16; h*=0x85ebca6bu; h^=h>>13; h*=0xc2b2ae35u; h^=h>>16;
    fm_ent* e=fm_cache+(h%FM_CACHE);
    *psi=ps;
    int s1=__atomic_load_n(&e->seq,__ATOMIC_ACQUIRE);
    if(s1>0 && !(s1&1) && memcmp(&e->kI,&kI,4)==0 && memcmp(e->B,Bq,sizeof(e->B))==0){
        int M=e->M;
        if(M>=0){ memcpy(Dr,e->Dr,(2*M+1)*sizeof(float)); memcpy(Di,e->Di,(2*M+1)*sizeof(float)); }
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        if(__atomic_load_n(&e->seq,__ATOMIC_RELAXED)==s1) return M;
    }
    int M=fm_sidebands_calc(Bq,kI,Dr,Di);
    int s0=__atomic_load_n(&e->seq,__ATOMIC_RELAXED);
    if(!(s0&1) && __atomic_compare_exchange_n(&e->seq,&s0,s0+1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)){
        e->M=M; e->kI=kI; memcpy(e->B,Bq,sizeof(e->B));
        if(M>=0){ memcpy(e->Dr,Dr,(2*M+1)*sizeof(float)); memcpy(e->Di,Di,(2*M+1)*sizeof(float)); }
        __atomic_store_n(&e->seq,s0+2,__ATOMIC_RELEASE);
    }
    return M;
}

// THE MOD SECTION'S PITCH ROWS, one cell each: moog.pitch_cells in C, because
// live builds them every block and numpy's per-call cost was half a millisecond
// at eight notes. moog.py keeps the reference (pitch_cells_ref) and the tests.
// P is n x 9: A_env fA fD fS fR A_lfo lfo_hz lfo_shape lfo_reset.
static double mp_held(double tt, double A, double D, double S){
    if(tt<0.0) return 0.0;
    if(tt<A) return MS_ATK_T*(1.0-exp(-tt*MS_ATK_K/fmax(A,1e-6)));
    return fmax(0.0, S+(1.0-S)*exp(-(tt-A)/(fmax(D,1e-6)/4.0)));
}
static double mp_ratio(double nn, double a0, double toff, const double* q, double sr){
    double t=(nn-a0)/sr;
    if(t<0.0) return 1.0;
    double to=(toff-a0)/sr, e;
    if(t>=to) e=fmax(0.0, (mp_held(to,q[1],q[2],q[3])+MS_UNDER)*exp(-(t-to)/(fmax(q[4],1e-6)/4.0))-MS_UNDER);
    else e=mp_held(t,q[1],q[2],q[3]);
    double x=q[0]*e;
    if(q[5]!=0.0){
        double tl = q[8]>0.5 ? t : nn/sr;
        double ph=tl*q[6]; ph-=floor(ph);
        int sh=(int)q[7];
        double lv = sh==0 ? 1.0-4.0*fabs(ph-0.5) : sh==1 ? 1.0-ph : sh==2 ? ph : (ph<0.5?1.0:0.0);   // moog.lfo
        x+=q[5]*lv;
    }
    return exp2(x);
}
static const double MP_GX[8]={0.019855071751231856,0.10166676129318664,0.2372337950418355,0.4082826787521751,
                              0.5917173212478249,0.7627662049581645,0.8983332387068134,0.9801449282487681};
static const double MP_GW[8]={0.05061426814518813,0.11119051722668724,0.15685332293894363,0.18134189168918100,
                              0.18134189168918100,0.15685332293894363,0.11119051722668724,0.05061426814518813};
void moog_pitch_cells(int n, const double* g, const double* a0, const double* toff,
                      const double* P, double sr, int mg, double* dc, double* r){
    for(int i=0;i<n;i++){
        const double* q=P+(long)i*9;
        double g0=g[i], g1=g0+mg, k[4];
        k[0]=a0[i]; k[1]=a0[i]+q[1]*sr; k[2]=toff[i];
        k[3]=INFINITY;
        if(q[5]!=0.0){
            double lhz=fmax(q[6],1e-9);
            double tl0 = q[8]>0.5 ? (g0-a0[i])/sr : g0/sr;
            double ph0=tl0*lhz; ph0-=floor(ph0);
            double nxt = ph0<0.5 ? 0.5 : 1.0;
            k[3]=g0+(nxt-ph0)/lhz*sr;
        }
        double e[6]; e[0]=g0; e[5]=g1;
        for(int j=0;j<4;j++) e[j+1]= k[j]<g0 ? g0 : (k[j]>g1 ? g1 : k[j]);
        for(int a=1;a<5;a++) for(int b=a+1;b<5;b++) if(e[b]<e[a]){ double t=e[a]; e[a]=e[b]; e[b]=t; }
        double tot=0.0;
        for(int s=0;s<5;s++){
            double h=e[s+1]-e[s];
            if(h<=0.0) continue;
            for(int j=0;j<8;j++) tot+=MP_GW[j]*h*(mp_ratio(e[s]+MP_GX[j]*h,a0[i],toff[i],q,sr)-1.0);
        }
        dc[i]=tot;
        r[i]=mp_ratio(g0,a0[i],toff[i],q,sr);
    }
}

// THE WAVESHAPES' COEFFICIENTS, in C: moog.osc_spectrum / sub_spectrum /
// sync_spectrum for a shape that MOVES within a note (the MOD section's F ENV ->
// OSC 2 WAVE / SUB WAVE, LFO 1 -> OSC 1 WAVE / SUB WAVE, and the sync sweep).
// Both renderers build a note's coefficient rows from this, and the kernel
// applies them as a complex gain. Straight segments, exactly as moog.py builds
// them (not quantised: a sweep is continuous), integrated exactly; each
// harmonic's exponentials are the last one's times a fixed step, so there is
// no sine per harmonic. SYNC is a geometric series over OSC 2's whole cycles
// plus the part-cycle at the end, so its cost does not grow with the ratio.
typedef struct { double t0, t1, y0, y1; } mseg;
static int ms_tri(mseg* o, double peak){
    if(peak>=1.0){ o[0]=(mseg){0.0,1.0,-1.0,1.0}; return 1; }
    o[0]=(mseg){0.0,peak,-1.0,1.0}; o[1]=(mseg){peak,1.0,1.0,-1.0}; return 2;
}
static int ms_pulse(mseg* o, double d){
    o[0]=(mseg){0.0,d,1.0,1.0}; o[1]=(mseg){d,1.0,-1.0,-1.0}; return 2;
}
// the pulse about its three-quarter point (moog._pulse_centred): the square in
// phase with the saw, as the Messenger crossfades them
static int ms_pulse_c(mseg* o, double d, double c){
    double a=c-d/2.0, b=c+d/2.0;
    o[0]=(mseg){0.0,a,-1.0,-1.0}; o[1]=(mseg){a,b,1.0,1.0}; o[2]=(mseg){b,1.0,-1.0,-1.0}; return 3;
}
static double ms_reflect(double x){
    x=fmod(x+1.0,4.0); if(x<0.0)x+=4.0;
    return x<=2.0 ? x-1.0 : 3.0-x;
}
// a triangle folder after `g` (moog._fold): split at every odd level crossed
static int ms_fold(const mseg* in, int n, double g, mseg* o){
    int m=0;
    for(int i=0;i<n;i++){
        double a=g*in[i].y0, b=g*in[i].y1, t0=in[i].t0, t1=in[i].t1;
        double pts[16]; int np=0; pts[np++]=a;
        double lo=a<b?a:b, hi=a<b?b:a;
        double c[12]; int nc=0;
        for(int j=(int)floor((lo-1.0)/2.0); j<=(int)ceil((hi-1.0)/2.0); j++){
            double v=2.0*j+1.0; if(v>lo && v<hi && nc<12) c[nc++]=v;
        }
        if(a<=b) for(int j=0;j<nc;j++) pts[np++]=c[j]; else for(int j=nc-1;j>=0;j--) pts[np++]=c[j];
        pts[np++]=b;
        for(int j=0;j+1<np;j++){
            double u=pts[j], v=pts[j+1];
            double s0 = b!=a ? t0+(t1-t0)*(u-a)/(b-a) : t0, s1 = b!=a ? t0+(t1-t0)*(v-a)/(b-a) : t1;
            o[m++]=(mseg){s0,s1,ms_reflect(u),ms_reflect(v)};
        }
    }
    return m;
}
// gain, then a hard limit at +-1 (moog._clip)
static int ms_clip(const mseg* in, int n, double g, mseg* o){
    int m=0;
    for(int i=0;i<n;i++){
        double a=g*in[i].y0, b=g*in[i].y1, t0=in[i].t0, t1=in[i].t1;
        double pts[4]; int np=0; pts[np++]=a;
        if(a<=b){ if(-1.0>a && -1.0<b) pts[np++]=-1.0; if(1.0>a && 1.0<b) pts[np++]=1.0; }
        else    { if(1.0<a && 1.0>b) pts[np++]=1.0; if(-1.0<a && -1.0>b) pts[np++]=-1.0; }
        pts[np++]=b;
        for(int j=0;j+1<np;j++){
            double u=pts[j], v=pts[j+1];
            double s0 = b!=a ? t0+(t1-t0)*(u-a)/(b-a) : t0, s1 = b!=a ? t0+(t1-t0)*(v-a)/(b-a) : t1;
            o[m++]=(mseg){s0,s1,fmax(-1.0,fmin(1.0,u)),fmax(-1.0,fmin(1.0,v))};
        }
    }
    return m;
}
#define MS_TRI 0.335      // moog.TRI, SAW, SQUARE: measured on Ben's Messenger
#define MS_SAW 0.5
#define MS_SQUARE 0.68
// WAVESHAPE (kind 0) or SUB WAVE (kind 1) at s: its parts, weighted (moog._osc_parts)
static int ms_parts(int kind, double s, double* wt, mseg seg[2][32], int* ns){
    mseg tmp[4];
    if(s<0.0)s=0.0; if(s>1.0)s=1.0;
    if(kind==1){
        // moog.SUB_SQUARE, SUB_PULSE_MIN: triangle crossfaded to square, then the pulse
        if(s<0.3){ double a=s/0.3; ns[0]=ms_tri(seg[0],0.5); wt[0]=1.0-a;
                   ns[1]=ms_pulse_c(seg[1],0.5,0.5); wt[1]=a; return 2; }
        double d=0.5-(0.5-0.0033)*(s-0.3)/(1.0-0.3);
        ns[0]=ms_pulse_c(seg[0],d,0.5); wt[0]=1.0; return 1;
    }
    // the landmarks where Ben's Messenger has them (moog.TRI, SAW, SQUARE)
    const double T=MS_TRI, W=MS_SAW, Q=MS_SQUARE;
    if(s<T){ double g=1.0+(5.0-1.0)*(T-s)/T; int n=ms_tri(tmp,0.5);
             ns[0]=ms_fold(tmp,n,g,seg[0]); wt[0]=1.0; return 1; }
    if(s<W){ double a=(s-T)/(W-T); ns[0]=ms_tri(seg[0],0.5); wt[0]=1.0-a;
             ns[1]=ms_tri(seg[1],1.0); wt[1]=a; return 2; }
    if(s<Q){ double a=(s-W)/(Q-W); ns[0]=ms_tri(seg[0],1.0); wt[0]=1.0-a;
             ns[1]=ms_pulse_c(seg[1],0.5,0.75); wt[1]=a; return 2; }
    ns[0]=ms_pulse_c(seg[0],0.5-(0.5-0.025)*(s-Q)/(1.0-Q),0.75); wt[0]=1.0; return 1;
}
// sum over segments (clipped to [0,uend]) of the integral of y e^{-2 pi i nu u},
// for nu = k*nu0, k = 1..K, added times `sc` into (re, im)
static void ms_accum(const mseg* sg, int n, double nu0, double uend, int K, double sc,
                     double* re, double* im){
    for(int i=0;i<n;i++){
        double t0=sg[i].t0, t1=sg[i].t1, y0=sg[i].y0, y1=sg[i].y1;
        if(t0>=uend || t1<=t0) continue;
        if(t1>uend){ y1=y0+(y1-y0)*(uend-t0)/(t1-t0); t1=uend; }
        double m=(y1-y0)/(t1-t0);
        double w0=6.283185307179586*nu0;
        double s0r=cos(w0*t0), s0i=-sin(w0*t0), s1r=cos(w0*t1), s1i=-sin(w0*t1);   // per-k steps
        double e0r=1.0, e0i=0.0, e1r=1.0, e1i=0.0;
        for(int k=1;k<=K;k++){
            double tr;
            tr=e0r*s0r-e0i*s0i; e0i=e0r*s0i+e0i*s0r; e0r=tr;
            tr=e1r*s1r-e1i*s1i; e1i=e1r*s1i+e1i*s1r; e1r=tr;
            double w=w0*k;
            // i (y1 E1 - y0 E0) / w  +  m (E1 - E0) / w^2
            double ar=y1*e1r-y0*e0r, ai=y1*e1i-y0*e0i;
            re[k-1]+=sc*(-ai/w + m*(e1r-e0r)/(w*w));
            im[k-1]+=sc*( ar/w + m*(e1i-e0i)/(w*w));
        }
    }
}
void moog_coeff_rows(int n, const int* kind, const double* s, const double* r, int K, float* out){
    double re[128], im[128], bre[128], bim[128], tre[128], tim[128];
    mseg seg[2][32]; int ns[2]; double wt[2];
    if(K>128) K=128;
    for(int i=0;i<n;i++){
        int np=ms_parts(kind[i], s[i], wt, seg, ns);
        for(int k=0;k<K;k++){ re[k]=im[k]=0.0; }
        double rr=r[i];
        if(!(rr>0.0) || kind[i]==1){                     // free-running: harmonics of the wave
            for(int q=0;q<np;q++) ms_accum(seg[q],ns[q],1.0,1.0,K,wt[q],re,im);
        } else {                                          // synced to OSC 1 at ratio rr
            int M=(int)floor(rr+1e-12); double fr=rr-M;
            for(int k=0;k<K;k++){ bre[k]=bim[k]=tre[k]=tim[k]=0.0; }
            for(int q=0;q<np;q++){
                ms_accum(seg[q],ns[q],1.0/rr,1.0,K,wt[q],bre,bim);
                if(fr>1e-12) ms_accum(seg[q],ns[q],1.0/rr,fr,K,wt[q],tre,tim);
            }
            double zr0=cos(6.283185307179586/rr), zi0=-sin(6.283185307179586/rr);
            double zMr0=cos(6.283185307179586*M/rr), zMi0=-sin(6.283185307179586*M/rr);
            double zr=1.0, zi=0.0, zMr=1.0, zMi=0.0;
            for(int k=1;k<=K;k++){
                double tr;
                tr=zr*zr0-zi*zi0; zi=zr*zi0+zi*zr0; zr=tr;
                tr=zMr*zMr0-zMi*zMi0; zMi=zMr*zMi0+zMi*zMr0; zMr=tr;
                double sr, si;                             // sum_{m<M} z^m
                double dr=1.0-zr, di=-zi, dd=dr*dr+di*di;
                if(dd<1e-20){ sr=(double)M; si=0.0; }
                else { double nr=1.0-zMr, ni=-zMi; sr=(nr*dr+ni*di)/dd; si=(ni*dr-nr*di)/dd; }
                double cr=bre[k-1]*sr-bim[k-1]*si, ci=bre[k-1]*si+bim[k-1]*sr;
                cr+=tre[k-1]*zMr-tim[k-1]*zMi; ci+=tre[k-1]*zMi+tim[k-1]*zMr;
                re[k-1]=cr/rr; im[k-1]=ci/rr;
            }
        }
        for(int k=0;k<K;k++){ out[((long)i*K+k)*2]=(float)re[k]; out[((long)i*K+k)*2+1]=(float)im[k]; }
    }
}

// ONE OSCILLATOR'S COEFFICIENTS at shape s (sync ratio r), K of them, as float
// pairs into out -- moog_coeff_rows' body, for the row builder below.
static void ms_coeff_one(int kind, double s, double rr, int K, float* out){
    double re[128], im[128], bre[128], bim[128], tre[128], tim[128];
    mseg seg[2][32]; int ns[2]; double wt[2];
    int np=ms_parts(kind, s, wt, seg, ns);
    for(int k=0;k<K;k++){ re[k]=im[k]=0.0; }
    if(!(rr>0.0) || kind==1){
        for(int q=0;q<np;q++) ms_accum(seg[q],ns[q],1.0,1.0,K,wt[q],re,im);
    } else {
        int M=(int)floor(rr+1e-12); double fr=rr-M;
        for(int k=0;k<K;k++){ bre[k]=bim[k]=tre[k]=tim[k]=0.0; }
        for(int q=0;q<np;q++){
            ms_accum(seg[q],ns[q],1.0/rr,1.0,K,wt[q],bre,bim);
            if(fr>1e-12) ms_accum(seg[q],ns[q],1.0/rr,fr,K,wt[q],tre,tim);
        }
        double zr0=cos(6.283185307179586/rr), zi0=-sin(6.283185307179586/rr);
        double zMr0=cos(6.283185307179586*M/rr), zMi0=-sin(6.283185307179586*M/rr);
        double zr=1.0, zi=0.0, zMr=1.0, zMi=0.0;
        for(int k=1;k<=K;k++){
            double tr;
            tr=zr*zr0-zi*zi0; zi=zr*zi0+zi*zr0; zr=tr;
            tr=zMr*zMr0-zMi*zMi0; zMi=zMr*zMi0+zMi*zMr0; zMr=tr;
            double sr, si, dr=1.0-zr, di=-zi, dd=dr*dr+di*di;
            if(dd<1e-20){ sr=(double)M; si=0.0; }
            else { double nr=1.0-zMr, ni=-zMi; sr=(nr*dr+ni*di)/dd; si=(ni*dr-nr*di)/dd; }
            double cr=bre[k-1]*sr-bim[k-1]*si, ci=bre[k-1]*si+bim[k-1]*sr;
            cr+=tre[k-1]*zMr-tim[k-1]*zMi; ci+=tre[k-1]*zMi+tim[k-1]*zMr;
            re[k-1]=cr/rr; im[k-1]=ci/rr;
        }
    }
    for(int k=0;k<K;k++){ out[2*k]=(float)re[k]; out[2*k+1]=(float)im[k]; }
}
// THE SHAPE ROWS, whole: for each note, at each of its grid points, the shapes
// its contour and LFO 1 have moved OSC 1, OSC 2 and the SUB to (moog.
// shape_values) and each moving one's coefficients, written into out at
// base + m*stride + offs[slot]. par is SHAPE_W (25) per note. Both renderers
// build their rows with this one function.
void moog_shape_rows(int nrows, const double* par, const double* a0, const double* toff,
                     const long* j0, const int* nj, int mg, double sr, int K,
                     const long* base, const int* stride, const int* offs, float* out){
    for(int i=0;i<nrows;i++){
        const double* q=par+(long)i*25;
        int fl=(int)q[0];
        for(int m=0;m<nj[i];m++){
            double g=(double)((j0[i]+m)*(long)mg);
            double t=(g-a0[i])/sr, fe;
            if(t<0.0) fe=0.0;
            else { double to=(toff[i]-a0[i])/sr;
                   fe = t>=to ? fmax(0.0, (mp_held(to,q[11],q[12],q[13])+MS_UNDER)*exp(-(t-to)/(fmax(q[14],1e-6)/4.0))-MS_UNDER)
                              : mp_held(t,q[11],q[12],q[13]); }
            double tl = q[10]>0.5 ? t : g/sr;
            double ph=tl*q[8]; ph-=floor(ph);
            int sh=(int)q[9];
            double lv = sh==0 ? 1.0-4.0*fabs(ph-0.5) : sh==1 ? 1.0-ph : sh==2 ? ph : (ph<0.5?1.0:0.0);   // moog.lfo
            double s1=q[1]+(q[6]==1.0 ? q[7]*lv : 0.0);
            double s2=q[2]+(q[4]==2.0 ? q[5]*fe : 0.0);
            double ss=q[3]+(q[4]==3.0 ? q[5]*fe : 0.0)+(q[6]==3.0 ? q[7]*lv : 0.0);
            double r = q[15]>0.0 ? q[15]*mp_ratio(g,a0[i],toff[i],q+16,sr) : 0.0;
            s1=fmin(1.0,fmax(0.0,s1)); s2=fmin(1.0,fmax(0.0,s2)); ss=fmin(1.0,fmax(0.0,ss));
            float* o=out+base[i]+(long)m*stride[i];
            if((fl&2) && offs[i*3+0]>=0) ms_coeff_one(0,s1,0.0,K,o+offs[i*3+0]);
            if((fl&4) && offs[i*3+1]>=0) ms_coeff_one(0,s2,r,K,o+offs[i*3+1]);
            if((fl&8) && offs[i*3+2]>=0) ms_coeff_one(1,ss,0.0,K,o+offs[i*3+2]);
        }
    }
}

// Renders absolute samples [n0, n0+winlen) into outL/outR[0 .. winlen). Phase is
// analytic (ph0 + w*n_absolute), so windows are stateless -- a player can call
// this per audio block with no carried state. render()/play both use it.
void synth_voice(
    float* outL, float* outR, long n0, long winlen, int BLK, int nblk, int P,
    const double* omega, const double* ph0L, const double* ph0R,
    const float* ampL, const float* ampR, const float* nomfreq,
    const long* non, const long* noff, const float* fadeS, const float* relS, const float* chiffS,
    const float* logr, const float* logrA, const float* aftL, const float* susL,
    const float* chVol, const float* chCyc, const float* chRel, const float* susJit, const float* chScale,
    const float* chBW,
    const float* tbav, const float* tau, const float* tcut,
    const float* gbav, const float* gtau, const float* gcut,
    const float* vdep, const float* vrate, const float* vph, const float* vdl,
    const float* delL, const float* delR,
    const int* grow, const int* crow, const float* G, const float* S,
    const int* brow, const float* BR, const double* BC, const float* BL,
    const int* fxr, const float* FT, const float* KN, long knk, long kb0,
    const float* ampLp, const float* ampRp, const int* mkr,
    const int* MPI, const double* MPC, const float* MPR,
    const int* MKI, const float* MPK,
    const double* fmw, const double* fmp, const double* fmpR,
    float sfloor, float spow, float shmax, float shref, long CHUNK,
    const float* sendW, float* outSL, float* outSR)
{
#include "voice_main.inc"
}


#ifdef LESLIE_KERNEL
// ---------------------------------------------------------------------------
// ONLY IN THE LESLIE'S BUILD (-DLESLIE_KERNEL, libsynthlobe_<rate>.so):
// synth_voice with the rotor rows' lobe (leslie_grid), for a table that
// has a Leslie. Every other table renders through synth_voice itself.
void synth_voice_lobe(
    float* outL, float* outR, long n0, long winlen, int BLK, int nblk, int P,
    const double* omega, const double* ph0L, const double* ph0R,
    const float* ampL, const float* ampR, const float* nomfreq,
    const long* non, const long* noff, const float* fadeS, const float* relS, const float* chiffS,
    const float* logr, const float* logrA, const float* aftL, const float* susL,
    const float* chVol, const float* chCyc, const float* chRel, const float* susJit, const float* chScale,
    const float* chBW,
    const float* tbav, const float* tau, const float* tcut,
    const float* gbav, const float* gtau, const float* gcut,
    const float* vdep, const float* vrate, const float* vph, const float* vdl,
    const float* delL, const float* delR,
    const int* grow, const int* crow, const float* G, const float* S,
    const int* brow, const float* BR, const double* BC, const float* BL,
    const int* fxr, const float* FT, const float* KN, long knk, long kb0,
    const float* ampLp, const float* ampRp, const int* mkr,
    const int* MPI, const double* MPC, const float* MPR,
    const int* MKI, const float* MPK,
    const double* fmw, const double* fmp, const double* fmpR,
    float sfloor, float spow, float shmax, float shref,
    const int* lsr, const float* lph, const float* lfl, const float* lsh, const float* lnm,
    const float* LANG, long lgn,
    const int* fsr, const int* fty, const float* fpa, const float* fpb, const float* fpc,
    const float* FCT, long fgn, long CHUNK,
    const float* sendW, float* outSL, float* outSR)
{
#define SV_LOBE
#include "voice_main.inc"
#undef SV_LOBE
}
#endif

// ---------------------------------------------------------------------------
// ONLY IN THE GPU'S BUILD (-DVOICE_BLOCK, libsynthgpu_<rate>.so): a second
// caller of the shared helpers changes gcc's inlining in synth_voice, and the
// CPU render must stay byte-for-byte what it was.
#ifdef VOICE_BLOCK
#include "voicedesc.h"
// ---------------------------------------------------------------------------
// THE BLOCK SETUP ALONE, for a renderer that does the samples elsewhere (the
// GPU, gpurender.py). One block -- [n0, n0+BLK), n0 a multiple of BLK, which
// is what live renders -- for the partials listed in idx, each written to its
// descriptor D[i] (voicedesc.h): everything synth_voice works out per partial,
// per block and per Moog cell before its sample loop, by the very same source
// (the voice_*.inc fragments are included here and there alike, so the two
// cannot come apart), stopping where the sample loop would start. A Moog
// partial's cells go to C and its sidebands to SB, taken in order by a shared
// count; counts[0..1] return how many of each were used. Returns 0, or -1 if
// C or SB was too small (counts then hold what was asked for).
//
// The arguments are synth_voice's, less its outputs, its window and CHUNK.
int voice_block(long n0, int BLK, int nblk, int P,
    const double* omega, const double* ph0L, const double* ph0R,
    const float* ampL, const float* ampR, const float* nomfreq,
    const long* non, const long* noff, const float* fadeS, const float* relS, const float* chiffS,
    const float* logr, const float* logrA, const float* aftL, const float* susL,
    const float* chVol, const float* chCyc, const float* chRel, const float* susJit, const float* chScale,
    const float* chBW,
    const float* tbav, const float* tau, const float* tcut,
    const float* gbav, const float* gtau, const float* gcut,
    const float* vdep, const float* vrate, const float* vph, const float* vdl,
    const float* delL, const float* delR,
    const int* grow, const int* crow, const float* G, const float* S,
    const int* brow, const float* BR, const double* BC, const float* BL,
    const int* fxr, const float* FT, const float* KN, long knk, long kb0,
    const float* ampLp, const float* ampRp, const int* mkr,
    const int* MPI, const double* MPC, const float* MPR,
    const int* MKI, const float* MPK,
    const double* fmw, const double* fmp, const double* fmpR,
    float sfloor, float spow, float shmax, float shref,
    const int* lsr, const float* lph, const float* lfl, const float* lsh, const float* lnm,
    const float* LANG, long lgn,
    const int* fsr, const int* fty, const float* fpa, const float* fpb, const float* fpc,
    const float* FCT, long fgn,
    const float* sendW, int send,
    const long* idx, int nact, vdesc* D, vcell* C, int ccap, vsb* SB, int sbcap,
    int nthr, int* counts, int nb)
{
    (void)P; (void)fmpR;
    // the send weight is read when there is a send bus (voice_partial.inc)
    const float* outSL = send ? sendW : 0;
    int nc=0, nsbt=0, over=0;
    // nb BLOCKS from n0, each for every partial in idx: descriptor
    // D[blk*nact + ii], so a file's window is one call (live's is one block).
    // Cells and sidebands are taken by shared counts across all of them.
    long tot=(long)nact*(nb>0?nb:1);
    #pragma omp parallel for schedule(dynamic,32) num_threads(nthr)
    for(long it=0; it<tot; it++){
        int ii=(int)(it%nact);
        long bn0=n0+(it/nact)*(long)BLK;
        // the fragments' names for the window: one block, one chunk
        const long cs=bn0, ce=bn0+BLK;
        int p=(int)idx[ii];
        vdesc* d=D+it;
        d->kind=0;
        #include "voice_partial.inc"
        {
        long b=bn0/BLK;
        #include "voice_block.inc"
        d->ns=(int)(ns-bn0); d->ne=(int)(ne-bn0);
        d->zLr=zrL; d->zLi=ziL; d->zRr=zrR; d->zRi=ziR; d->winst=winst;
        d->mL0=mL0; d->mL1=mL1; d->mR0=mR0; d->mR1=mR1;
        d->aL=aL; d->aR=aR; d->aLp=aLp; d->aRp=aRp;
        d->jfa=jfa; d->cc=cc; d->swp=swp;
        // the knee: its sample from the block's start (0, none), its gains
        d->kn=kNl>ns ? (int)(kNl-bn0) : 0; d->kgL=kgL; d->kgR=kgR;
        d->ka=kNl>ns ? (int)(kAl-bn0) : 0;
        d->knR=kNr>ns ? (int)(kNr-bn0) : 0;
        d->kaR=kNr>ns ? (int)(kAr-bn0) : 0; d->kpad=0;
        // the carrier at each V_SUB samples into the block, in double, as the
        // phasor's own steps of winst place it (voicedesc.h)
        for(int j=1;j<4;j++){
            if(ns+(long)j*V_SUB < ne){
                double el=(double)winst*(double)(j*V_SUB);
                d->za[4*(j-1)]=(float)cos(phL+el); d->za[4*(j-1)+1]=(float)sin(phL+el);
                d->za[4*(j-1)+2]=(float)cos(phR+el); d->za[4*(j-1)+3]=(float)sin(phR+el);
            } else for(int q=0;q<4;q++) d->za[4*(j-1)+q]=0.f;
        }
        d->chk_hi=chk_hi; d->chk_lo=chk_lo;
        d->flags=0; d->cell=0; d->nk_hi=d->nk_lo=d->nseed=0;
        (void)rr; (void)ri; (void)invb;
        if(!ftr){
            // an ordinary noise band (voice_noise.inc): the Moog's draw, seeded alike
            if(chBW[p]<0.f){
                uint64_t gh=0, gl=0;
                chiff_step((double)nf*(double)(-chBW[p])/SRATE_D, &gh, &gl);
                d->flags=VD_NOISE; d->nk_hi=gh; d->nk_lo=gl;
                d->jfa=0.f;      // a noise band has no chiff of its own (voice_noise.inc)
                d->nseed=(uint64_t)a*0x9E3779B97F4A7C15ULL + (uint64_t)(long long)((double)nf*1000.0);
            }
            // a rotor row: its lobe at the block's grid points (leslie_grid)
            if(lsr && (lsr[p]>=0 || (fsr && fsr[p]>=0)) && chBW[p]>=0.f && BLK/mg+1<=VD_LG){
                d->flags|=VD_LESLIE;
                if(lsr[p]>=0)
                    leslie_grid(LANG, lgn, lsr[p], lph[p], lfl[p], lsh[p], lnm[p], bn0, mg, BLK/mg+1, d->lg);
                else
                    for(int j=0;j<BLK/mg+1;j++) d->lg[j]=1.f;
                if(fsr && fsr[p]>=0)       /* ...and a moving filter (filter_grid) */
                    filter_grid(FCT, fgn, fsr[p], fty[p], fpa[p], fpb[p], fpc[p], nf, bn0, mg, BLK/mg+1, d->lg);
            }
            d->kind=1; continue;
        }
        #include "voice_moog.inc"
        (void)nui; (void)nh0; (void)ndh;
        // a Moog row on a rotor or a moving filter: its grid gains times them
        if(lsr && (lsr[p]>=0 || (fsr && fsr[p]>=0))){
            float lgm[65]; int njm=BLK/mg+1;
            if(lsr[p]>=0)
                leslie_grid(LANG, lgn, lsr[p], lph[p], lfl[p], lsh[p], lnm[p], bn0, mg, njm, lgm);
            else
                for(int j=0;j<njm;j++) lgm[j]=1.f;
            if(fsr && fsr[p]>=0)
                filter_grid(FCT, fgn, fsr[p], fty[p], fpa[p], fpb[p], fpc[p], nf, bn0, mg, njm, lgm);
            for(int j=0;j<njm;j++){ gLm[j]*=lgm[j]; gRm[j]*=lgm[j]; }
        }
        // (cbase, not c0: the cell fragment's c0 is the cell's first sample)
        int ncl=BLK/mg;
        int cbase=__atomic_fetch_add(&nc, ncl, __ATOMIC_RELAXED);
        if(cbase+ncl>ccap){ __atomic_store_n(&over, 1, __ATOMIC_RELAXED); continue; }
        int fl=0;
        if(noiz){ fl|=VD_NOISE; d->nk_hi=nk_hi; d->nk_lo=nk_lo; d->nseed=nseed; }
        if(shm) fl|=VD_SHAPE;
        if(fms) fl|=VD_FMS; else if(fmo) fl|=VD_FMO;
        if(pm) fl|=VD_PM;
        for(int cl=0; cl<ncl; cl++) memset(C+cbase+cl, 0, sizeof(vcell));
        for(int cl=0; cl<BLK/mg; cl++){
        #include "voice_cell.inc"
        vcell* v=C+cbase+cl;
        v->s0=(int)(s0-bn0); v->s1=(int)(s1-bn0);
        v->gL0=a0L; v->gL1=a1L; v->gR0=a0R; v->gR1=a1R;
        if(shm){ v->cRe0=cRe[cl]; v->cIm0=cIm[cl]; v->cRe1=cRe[cl+1]; v->cIm1=cIm[cl+1]; }
        if(pm){ v->zLr=zrL; v->zLi=ziL; v->zRr=zrR; v->zRi=ziR; v->wc=atan2f(ri, rr); }
        if(fmo && !fms){
            v->z1r=z1r; v->z1i=z1i; v->th1=atan2f(r1i, r1r); v->fmkI=(float)fmk*fmI;
            for(int j=0;j<2*FM_J;j++) v->B[j]=ftr[14+j];
        }
        if(fms && nsb>0){
            int s=__atomic_fetch_add(&nsbt, nsb, __ATOMIC_RELAXED);
            if(s+nsb>sbcap){ __atomic_store_n(&over, 1, __ATOMIC_RELAXED); continue; }
            v->sb=s; v->nsb=nsb;
            for(int i=0;i<nsb;i++){
                vsb* q=SB+s+i;
                q->g0r=g0r[slo+i]; q->g0i=g0i[slo+i]; q->dgr=dgr[slo+i]; q->dgi=dgi[slo+i];
                q->pzr=pzr[i]; q->pzi=pzi[i]; q->th=atan2f(pri[i], prr[i]); q->pad=0.f;
            }
        }
        }
        d->flags=fl; d->cell=cbase; d->kind=2;
        }
        #undef AMP
    }
    counts[0]=nc; counts[1]=nsbt;
    return over ? -1 : 0;
}

// EACH BLOCK'S SOUNDING ROWS, PACKED: voice_block over nb blocks leaves every
// partial of the window in every block, silent ones as kind 0. Block blk's
// rows D[blk*nact ..] are moved down over its silent ones, in order, and m[blk]
// is how many sound -- so the GPU never walks a row that adds nothing.
void voice_pack(vdesc* D, int nact, int nb, int* m)
{
    for(int blk=0; blk<nb; blk++){
        vdesc* base=D+(long)blk*nact;
        int k=0;
        for(int i=0;i<nact;i++)
            if(base[i].kind){ if(i!=k) base[k]=base[i]; k++; }
        m[blk]=k;
    }
}

// THE SAMPLE PASS IN C: voice_sample (voicedesc.h) over every descriptor and
// sample -- the reference the GPU's kernel is held to, and the proof that a
// descriptor carries everything synth_voice's sample loops use. Accumulates
// into L/R (and SL/SR when non-NULL).
void voice_samples(long n0, int BLK, int nact, const vdesc* D, const vcell* C, const vsb* SB,
                   float* L, float* R, float* SL, float* SR)
{
    int mg = (BLK%MOOG_GRID==0 && BLK/MOOG_GRID<=64) ? MOOG_GRID : BLK;
    float invb=1.f/(float)BLK, invg=1.f/(float)mg;
    for(int ii=0; ii<nact; ii++)
        for(int k=0;k<BLK;k++){
            float o[4]={0.f,0.f,0.f,0.f};
            voice_sample(D+ii, C, SB, k, (u64)(n0+k), invb, mg, invg, SL!=0, o);
            L[k]+=o[0]; R[k]+=o[1];
            if(SL){ SL[k]+=o[2]; SR[k]+=o[3]; }
        }
}

// the descriptor sizes, for the host to check its layout against
void voice_sizes(int* out){ out[0]=(int)sizeof(vdesc); out[1]=(int)sizeof(vcell); out[2]=(int)sizeof(vsb); }
#endif
