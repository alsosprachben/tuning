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
    const float* tbav, const float* tau, const float* tcut,
    const float* vdep, const float* vrate, const float* vph,
    const float* delL, const float* delR,
    const int* grow, const int* crow, const float* G, const float* S,
    float sfloor, float spow, float shmax, float shref, long CHUNK)
{
    long nchunks=(winlen+CHUNK-1)/CHUNK;
    #pragma omp parallel for schedule(dynamic)
    for(long c=0;c<nchunks;c++){
        long cs=n0+c*CHUNK, ce=cs+CHUNK; if(ce>n0+winlen)ce=n0+winlen;
        for(int p=0;p<P;p++){
            long a=non[p], off=noff[p], zend=off+(long)relS[p]+BLK;
            if(a>=ce||zend<=cs) continue;
            double w=omega[p]; float invf=1.f/fadeS[p], invr=1.f/relS[p];
            float aL=ampL[p], aR=ampR[p], nf=nomfreq[p];
            float sl=susL[p], af=aftL[p], lr=logr[p], lrA=logrA[p];
            float cv=chVol[p], cc=chCyc[p], crl=chRel[p], sj=susJit[p], csc=chScale[p];
            int gr=grow[p]; const float* Grow = gr>=0 ? G+(long)gr*nblk : 0;
            const float* Srow = gr>=0 ? S+(long)crow[p]*nblk : 0;
            // amplitude at absolute sample n (env * decay * gate * shutter). The
            // envelope onset is shifted per ear by the HRTF path delay d (samples)
            // -- the interaural time difference -- while the carrier phase (ph0)
            // is not delayed, exactly as the reference does.
            float dL=delL[p], dR=delR[p];
            #define AMP(nn, b, d) ({ \
                float tt=(float)((nn)-a-(d))/SRATE_F; \
                float dc=sl+(1.f-sl)*((1.f-af)*expf(-tt*lr)+af*expf(-tt*lrA)); \
                float e=sstep((float)((nn)-a-(d))*invf)*(1.f-sstep((float)((nn)-off-(d))*invr))*dc; \
                float gg=1.f, sh=1.f; \
                if(Grow){ int bb=(b)<nblk?(b):nblk-1; gg=Grow[bb]; float sw=Srow[bb]; \
                    if(sw<1.f){ float lvl=sfloor+(1.f-sfloor)*powf(sw,spow); sh=lvl*expf(-(1.f-sw)*shmax*(nf/shref)); } } \
                e*gg*sh; })
            long bstart=(cs>a?cs:a)/BLK, bend=(ce<zend?ce:zend+1)/BLK+1;
            for(long b=bstart;b<bend;b++){
                // Amp is interpolated across the FULL block [bs0,bs1); only the
                // [ns,ne) slice inside this chunk/window is written. Using the true
                // block bounds (not the clipped ones) makes the result independent
                // of chunking/windowing -- a streamed window == the full render.
                long bs0=b*BLK, bs1=bs0+BLK;
                long ns=bs0<cs?cs:bs0, ne=bs1>ce?ce:bs1; if(ns>=ne)continue;
                float mL0=AMP(bs0,b,dL), mL1=AMP(bs1,b,dL), mR0=AMP(bs0,b,dR), mR1=AMP(bs1,b,dR);
                if(mL0<=1e-7f && mL1<=1e-7f && mR0<=1e-7f && mR1<=1e-7f) continue;
                // chiff fade for this block (state: attack/sustain/release). The
                // attack chiff rides chiffS -- its OWN short, capped width, NOT the
                // slow speech fade fadeS -- so a big pipe chuffs briefly, no hiss.
                float jf=0.f; long mid=bs0+BLK/2; float invch=1.f/chiffS[p];
                if(cv>0.f){
                    if(mid < a+(long)chiffS[p]){ float s=sstep((float)(mid-a)*invch); float r=sqrtf(s); jf=r*(1.f-r); }
                    else if(mid >= off){ float s=sstep((float)(mid-off)*invr); float r=sqrtf(s); jf=r*(1.f-r)*crl; }
                    else jf=sj;
                }
                // Tension bend (piano strike): frequency starts sharp by
                // tbav*e^{-t/tau} and settles, cut off at tcut. Phase is the exact
                // integral to the block start; the recurrence uses the block-start
                // instantaneous frequency. tbav==0 -> plain constant-frequency phasor.
                double bph=0.0; float winst=(float)w;
                // PER-PLAYER VIBRATO. A section detuned to FIXED offsets beats at
                // fixed rates forever: N voices held exactly apart are a comb whose
                // notches march at constant speed, which is what a phaser is. Real
                // players never hold a pitch -- each has its own vibrato, so the
                // beat rates wander and never settle into a pattern.
                //
                // f(t) = fp*(1 + d*sin(2*pi*r*t + ph)), integrated ANALYTICALLY so
                // the block stays stateless like every other path here:
                //   phase(T) = 2*pi*fp*T + (fp*d/r)*(cos(ph) - cos(2*pi*r*T + ph))
                // bph carries the second term to the block start; winst is the
                // instantaneous frequency there, for the within-block recurrence.
                if(vdep[p]!=0.f){
                    // Absolute clock, not time-since-onset: a player does not
                    // restart their vibrato for every note, and it keeps this
                    // analytic integral on the same clock as the reference
                    // renderer's sample-by-sample one. Integrated from note-on,
                    // so the accumulated phase matches what the reference adds up.
                    double d=vdep[p], r=vrate[p], vp0=vph[p];
                    double fp=w*SRATE_D/6.283185307179586;
                    double ta=(double)ns/SRATE_D, tb2=(double)ne/SRATE_D, ton=(double)a/SRATE_D;
                    double w2=6.283185307179586*r;
                    bph += (fp*d/r)*(cos(w2*ton+vp0)-cos(w2*ta+vp0));
                    // The recurrence holds one frequency for the whole block, so
                    // use the block's EXACT MEAN frequency, not its value at the
                    // start: that lands the phase at the block end exactly where
                    // the integral says, leaving only a bounded, non-accumulating
                    // error mid-block (each block re-anchors from bph anyway).
                    double dt=tb2-ta;
                    double avg = dt > 0.0
                        ? 1.0 + d*(cos(w2*ta+vp0)-cos(w2*tb2+vp0))/(w2*dt)
                        : 1.0 + d*sin(w2*ta+vp0);
                    winst = (float)(w*avg);
                }
                if(tbav[p]!=0.f){
                    float tb=tbav[p], ts=tau[p], cut=tcut[p];
                    float trel=(float)(ns-a)/SRATE_F;
                    float integ = tb*ts*(1.f - expf(-(trel<cut?trel:cut)/ts));
                    bph = (double)w*SRATE_D*(double)integ;
                    winst = w*(1.f + (trel<cut ? tb*expf(-trel/ts) : 0.f));
                }
                double phL=ph0L[p]+w*(double)ns+bph, phR=ph0R[p]+w*(double)ns+bph;
                float zrL=cos(phL),ziL=sin(phL),zrR=cos(phR),ziR=sin(phR);
                float rr=cosf(winst),ri=sinf(winst);
                float invb=1.f/(float)BLK;
                float jfa=jf*cv*csc;
                for(long n=ns;n<ne;n++){
                    float t=(float)(n-bs0)*invb; float mL=(mL0+(mL1-mL0)*t)*aL, mR=(mR0+(mR1-mR0)*t)*aR;
                    float sL=zrL, sR=zrR;
                    if(jfa>0.f){
                        double sec=(double)n/SRATE_D;
                        float jit=6.2831853f*(float)hash01((uint64_t)(long long)(sec*(double)nf*(double)RAND_GRAN))*cc;
                        float cj=cosf(jit),sj2=sinf(jit);
                        sL += (zrL*cj - ziL*sj2)*jfa;
                        sR += (zrR*cj - ziR*sj2)*jfa;
                    }
                    outL[n-n0]+=mL*sL; outR[n-n0]+=mR*sR;
                    float tmp; tmp=zrL*rr-ziL*ri; ziL=zrL*ri+ziL*rr; zrL=tmp;
                    tmp=zrR*rr-ziR*ri; ziR=zrR*ri+ziR*rr; zrR=tmp;
                }
            }
            #undef AMP
        }
    }
}
