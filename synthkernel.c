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

/* CC78, vibrato delay: how long a delayed vibrato takes to bloom in once its
   delay has passed. tonelib.VIB_BLOOM_S must match; the selftest reads both. */
#define VIB_BLOOM 0.25

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
static inline float moog_ladder(float x, float k, int mode, int rb){
    // |H| = |num| / |(1+jx)^4 + k|, the modes mixing the poles (moog.ladder_gain)
    float x2=x*x, re4=1.f-6.f*x2+x2*x2+k, im4=4.f*x-4.f*x*x2;
    float den=sqrtf(re4*re4+im4*im4);
    float num = mode==0 ? 1.f : mode==1 ? 1.f+x2 : mode==2 ? 4.f*x2 : x2*(1.f+x2);
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
        double lv = sh==0 ? 1.0-4.0*fabs(ph-0.5) : sh==1 ? 2.0*ph-1.0 : sh==2 ? 1.0-2.0*ph : (ph<0.5?1.0:-1.0);
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
            double lv = sh==0 ? 1.0-4.0*fabs(ph-0.5) : sh==1 ? 2.0*ph-1.0 : sh==2 ? 1.0-2.0*ph : (ph<0.5?1.0:-1.0);
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
    const int* brow, const float* BR, const double* BC,
    const int* fxr, const float* FT, const float* KN, long knk, long kb0,
    const float* ampLp, const float* ampRp, const int* mkr,
    const int* MPI, const double* MPC, const float* MPR,
    const int* MKI, const float* MPK,
    const double* fmw, const double* fmp, const double* fmpR,
    float sfloor, float spow, float shmax, float shref, long CHUNK,
    const float* sendW, float* outSL, float* outSR)
{
    // THE SEND BUS, for the live room. When outSL is non-NULL every partial is
    // ALSO accumulated into outSL/outSR scaled by sendW[p] -- its channel's
    // CC91 distance multiple -- and that pair feeds the room's tail. The
    // oscillator is computed once; only the accumulation doubles. NULL (the
    // file renderer, which makes its send by a second render) touches nothing,
    // so outL/outR are bit-identical to before.
    long nchunks=(winlen+CHUNK-1)/CHUNK;
    #pragma omp parallel for schedule(dynamic)
    for(long c=0;c<nchunks;c++){
        long cs=n0+c*CHUNK, ce=cs+CHUNK; if(ce>n0+winlen)ce=n0+winlen;
        for(int p=0;p<P;p++){
            long a=non[p], off=noff[p], zend=off+(long)relS[p]+BLK;
            if(a>=ce||zend<=cs) continue;
            double w=omega[p]; float invf=1.f/fadeS[p], invr=1.f/relS[p];
            float aL=ampL[p], aR=ampR[p], nf=nomfreq[p];
            float swp = outSL ? sendW[p] : 0.f;
            float sl=susL[p], af=aftL[p], lr=logr[p], lrA=logrA[p];
            float cv=chVol[p], cc=chCyc[p], crl=chRel[p], sj=susJit[p], csc=chScale[p];
            // a partial the mixer or the waveshape has set to nothing costs
            // nothing (a Moog template carries every harmonic, some at zero)
            int fxp = fxr ? fxr[p] : -1;
            // A MOOG'S LEVEL MOVES ACROSS THE BLOCK, not at its edge: live
            // re-weighs its partials when a knob turns, and a level that steps
            // every block is a click (ampLp is the last block's; NULL offline,
            // where nothing moves it). Every other voice: as before.
            float aLp = (fxp>=0 && ampLp) ? ampLp[p] : aL, aRp = (fxp>=0 && ampRp) ? ampRp[p] : aR;
            if(aL==0.f && aR==0.f && aLp==0.f && aRp==0.f) continue;
            const float* ftr = fxp>=0 ? FT+(long)fxp*FTW : 0;
            int mg = (BLK%MOOG_GRID==0 && BLK/MOOG_GRID<=64) ? MOOG_GRID : BLK;
            int gr=grow[p]; const float* Grow = gr>=0 ? G+(long)gr*nblk : 0;
            const float* Srow = gr>=0 ? S+(long)crow[p]*nblk : 0;
            // PITCH BEND: a per-CHANNEL pair of rows, selected exactly as the
            // organ's gate and shutter are. BR is the frequency ratio in force
            // during each block and BC the extra phase accumulated up to the
            // START of it, in samples -- see bend_blocks in blockrender.
            int br=brow[p];
            const float*  BRrow = br>=0 ? BR+(long)br*nblk : 0;
            const double* BCrow = br>=0 ? BC+(long)br*nblk : 0;
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
                // Spelled exactly as it always was, and for every partial: moved
                // inside a branch, gcc vectorised the four evaluations another way
                // and the organ's swell moved by an ULP. A Moog ignores them.
                float mL0=AMP(bs0,b,dL), mL1=AMP(bs1,b,dL), mR0=AMP(bs0,b,dR), mR1=AMP(bs1,b,dR);
                if(!ftr && mL0<=1e-7f && mL1<=1e-7f && mR0<=1e-7f && mR1<=1e-7f) continue;
                // chiff fade for this block (state: attack/sustain/release). The
                // attack chiff rides chiffS -- its OWN short, capped width, NOT the
                // slow speech fade fadeS -- so a big pipe chuffs briefly, no hiss.
                float jf=0.f; long mid=bs0+BLK/2; float invch=1.f/chiffS[p];
                if(cv>0.f){
                    // THE SUSTAINED WASH IS A FLOOR UNDER THE ATTACK HUMP, not a
                    // level the hump drops to zero before reaching. The hump is
                    // r*(1-r): it peaks at 0.25 and returns to 0 at chiffS, and
                    // the sustain then began at sj -- so any voice whose sj is
                    // large compared with 0.25 STEPPED UP when its hump ended.
                    // The floor RISES with the hump's own progress (sj*s), so the
                    // attack is untouched at t=0 and the two meet exactly where the
                    // hump ends. A flat floor from t=0 would fix the step but raise
                    // the attack peak, which clipped the triangle and the cabasa.
                    // Inaudible where chiffS is a few ms, which is most voices;
                    // on the chinese cymbal, chiffS 0.29 s against sj 1.0, it is
                    // a burst of noise arriving a quarter second after the strike.
                    // Ben: "sounding fine to start, then after a quarter second
                    // or so, it suddenly adds noise."
                    if(mid < a+(long)chiffS[p]){ float s=sstep((float)(mid-a)*invch); float r=sqrtf(s); jf=fmaxf(r*(1.f-r), sj*s); }
                    // AND THE SAME ON THE WAY OUT. The attack floor rises so the
                    // hump does not step up when it ends; the release had no floor
                    // at all, so jf fell from sj to ZERO in one block at note-off
                    // and humped back up -- a step in the noise at every note end.
                    // Inaudible while the voice is buried; a solo line placed
                    // forward puts it in the open, which is where Ben heard it:
                    // "subtle clicking each note... an edge case involving attack
                    // or release." The floor now FALLS as sj*(1-s), mirroring the
                    // attack, so it leaves the sustain continuously and reaches
                    // zero exactly when the release does.
                    else if(mid >= off){ float s=sstep((float)(mid-off)*invr); float r=sqrtf(s); jf=fmaxf(r*(1.f-r)*crl, sj*(1.f-s)); }
                    else jf=sj;
                }
                // Tension bend (piano strike): frequency starts sharp by
                // tbav*e^{-t/tau} and settles, cut off at tcut. Phase is the exact
                // integral to the block start; the recurrence uses the block-start
                // instantaneous frequency. tbav==0 -> plain constant-frequency phasor.
                // A partial can be BOTH vibrating and speaking. These two used to
                // ASSIGN bph and winst, so whichever ran second threw the other
                // away: mode lock is a driven air column (brass, mode_lock_spread
                // = 0.003) and it silently deleted the mod wheel's vibrato for the
                // whole life of the note -- after the transient it wrote back a
                // plain w. Ben, playing: "the modulation value keeps getting
                // pulled back to 0 ... on violin it is persisting, but not
                // trumpet." Violin has mode_lock_spread = 0 and never entered the
                // branch. They compose now: the phases add and the frequency
                // factors multiply.
                double bph=0.0, vibfac=1.0; float bendfac=1.f;
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
                    double dt=tb2-ta;
                    if(vdl[p] > 0.f){
                        // CC78: STRAIGHT, THEN BLOOMING. A held note on a string
                        // or a voice starts without vibrato and the vibrato grows
                        // in; the depth is d*g(t), and the phase and the block's
                        // mean frequency both come from the exact integral of
                        // that envelope rather than from the constant-depth form.
                        double t1=ton+(double)vdl[p], t2=t1+VIB_BLOOM;
                        double Sa=vib_ramp_integral(ta, t1, t2, w2, vp0);
                        double Sb=vib_ramp_integral(tb2, t1, t2, w2, vp0);
                        bph += 6.283185307179586*fp*d*Sa;
                        vibfac = dt > 0.0 ? 1.0 + d*(Sb-Sa)/dt
                                          : 1.0 + d*(ta>=t2 ? 1.0 : (ta>t1 ? (ta-t1)/VIB_BLOOM : 0.0))
                                                   *sin(w2*ta+vp0);
                    } else {
                    bph += (fp*d/r)*(cos(w2*ton+vp0)-cos(w2*ta+vp0));
                    // The recurrence holds one frequency for the whole block, so
                    // use the block's EXACT MEAN frequency, not its value at the
                    // start: that lands the phase at the block end exactly where
                    // the integral says, leaving only a bounded, non-accumulating
                    // error mid-block (each block re-anchors from bph anyway).
                    double avg = dt > 0.0
                        ? 1.0 + d*(cos(w2*ta+vp0)-cos(w2*tb2+vp0))/(w2*dt)
                        : 1.0 + d*sin(w2*ta+vp0);
                    vibfac = avg;
                    }
                }
                if(tbav[p]!=0.f){
                    float tb=tbav[p], ts=tau[p], cut=tcut[p];
                    float trel=(float)(ns-a)/SRATE_F;
                    float integ = tb*ts*(1.f - expf(-(trel<cut?trel:cut)/ts));
                    bph += (double)w*SRATE_D*(double)integ;
                    // kept in float, and summed in float, so a voice with only
                    // this term rounds exactly as it did before it was factored out
                    bendfac = 1.f + (trel<cut ? tb*expf(-trel/ts) : 0.f);
                }
                // PORTAMENTO, and it settles exponentially in LENGTH rather than
                // in pitch -- which is the one thing that makes a modelled glide
                // different from a synthesiser's. A trombone slide, a finger on a
                // string and a slide whistle's plunger all move a LENGTH, and f is
                // 1/L. So a hand settling toward its target position gives
                // 1/(1 + g*e^{-t/tau}) in FREQUENCY, not the 1 + g*e^{-t/tau} the
                // tension bend above uses. A glide up therefore accelerates in
                // cents and a glide down decelerates, by the same amount, from the
                // same hand. Nothing had to be tuned to get that; it is what the
                // reciprocal does.
                //
                // g = f_target/f_source - 1, so t=0 gives exactly the source pitch
                // and t->infinity the target the note was built at. g > -1 for any
                // two real frequencies, so the denominator cannot vanish.
                //
                // Extra phase is the exact integral of (bendfac - 1):
                //     tau * ln( (1 + g*e^{-t/tau}) / (1 + g) )
                // zero at t=0 by construction, the same way BC is -- and frozen
                // past the cutoff, where the instantaneous factor is already 1.
                //
                // MULTIPLIES, never assigns. This is the fourth modulator in this
                // block and the rule the mode-lock bug wrote is now load-bearing
                // four ways: phases ADD and frequency factors MULTIPLY.
                if(gbav[p]!=0.f){
                    float gg=gbav[p], gs=gtau[p], gcu=gcut[p];
                    float trel=(float)(ns-a)/SRATE_F;
                    float e=expf(-(trel<gcu?trel:gcu)/gs);
                    bph += (double)w*SRATE_D*(double)(gs*logf((1.f+gg*e)/(1.f+gg)));
                    if(trel<gcu) bendfac *= 1.f/(1.f+gg*e);
                }
                // PITCH BEND, and it is the THIRD modulator here, so it obeys
                // the rule the comment at the top of this block was written to
                // enforce: phases ADD and frequency factors MULTIPLY. Never
                // assign -- that is the bug that deleted the mod wheel's
                // vibrato on trumpet and left it on violin.
                //
                // A bend is a RATIO, so the phase a partial accrues over a
                // block is w*(r-1)*BLK and the w factors out: the cumulative
                // term is partial-INDEPENDENT, which is why one pair of rows
                // serves a whole channel and the kernel stays stateless.
                //
                // ...AND IT ANCHORS AT ns, NOT AT bs0. A chunk boundary does
                // not land on a block boundary (CHUNK is a second, BLK is 512),
                // so once per chunk ns is clipped into the middle of a block.
                // BC holds the integral to the block START, so the remainder
                // from there to ns has to be added here. Anchoring at bs0
                // instead is a phase error of up to w*(r-1)*BLK -- some 190
                // radians during a full bend -- once per chunk, an audible
                // click that would only ever appear on bent notes.
                if(BRrow){
                    int bb=(b)<nblk?(b):nblk-1;
                    double rb=(double)BRrow[bb];
                    bph += w*(BCrow[bb] + (rb-1.0)*(double)(ns-bs0));
                    vibfac *= rb;
                }
                // With either term absent its factor is 1 and its phase 0, so a
                // voice that has only one of them renders exactly as before.
                float winst=(float)(w*vibfac*(double)bendfac);
                // THE MOOG'S GAIN on its grid: the amp contour times the ladder
                // at the cutoff the filter contour has reached, at the
                // frequency this partial is sounding NOW (bend, glide and
                // vibrato included, so the peak follows the note). The filter
                // is shared by both ears; the contour's onset keeps each ear's
                // own delay, as AMP's does.
                float gLm[65], gRm[65]; int j0=0;
                // THE MOD SECTION'S PITCH (moog.pitch_rows): an OSC 2 partial of
                // a note with pitch rows sounds at its ratio R_j at each grid
                // point, and carries the extra phase C_j accumulated to it --
                // integrated in Python, cell by cell, so a knob turned mid-sweep
                // changes only what is still to come.
                double mCp[65]; int pm=0;
                if(ftr && MPI && ((int)ftr[12] & FT_PITCH) && mkr && (mkr[p]>>12)==2) pm=1;
                // A MOVING SHAPE (moog.shape_rows): this partial's complex
                // coefficient at each grid point, from its note's rows
                float cRe[65], cIm[65]; int shm=0; const float* mkp=0; long mks=0; const int* mki=0;
                // 1 -> 2 FM: OSC 1's angle, from its frequency and phase anchor as
                // copied onto this OSC 2 partial (fmw, fmp, fmpR)
                int fmo = ftr && fmw && ((int)ftr[12] & 16) && mkr && (mkr[p]>>12)==2 && fmw[p]>0.0;
                float fmI = fmo ? ftr[13] : 0.f; int fmk = fmo ? (mkr[p]&4095) : 0;
                // ...as SIDEBANDS where it can be (fm_sidebands): fms, M of
                // them each side, and the ladder's cutoff, resonance and this
                // harmonic's frequency at each grid point to weigh them by
                float sbD0r[2*FM_SBMAX+1], sbD0i[2*FM_SBMAX+1]; double sbPsi=0.0;
                float sbDr[2*FM_SBMAX+1], sbDi[2*FM_SBMAX+1];
                float sbFc[65], sbK[65], sbF[65], sbBig=0.f; int sbMode=0, sbRb=0, fms=0, sbM=0;
                if(fmo){
                    sbM=fm_sidebands(ftr+14,(float)fmk*fmI,sbD0r,sbD0i,&sbPsi);
                    fms = sbM>=0;
                }
                if(ftr && MKI && MPK && mkr){
                    int o=mkr[p]>>12, bit = o==1 ? 2 : o==2 ? 4 : o==3 ? 8 : 0;
                    if(bit && ((int)ftr[12] & bit)){
                        mki=MKI+(long)fxp*7;
                        int off = mki[4+(o-1)];
                        if(off>=0){ shm=1; mks=mki[3]; mkp=MPK+mki[0]+off+2*((mkr[p]&4095)-1); }
                    }
                }
                if(ftr){
                    j0=(int)(bs0/mg); int nj=BLK/mg+1;
                    float kbf=ftr[0], fA=ftr[1], fD=ftr[2], fR=ftr[3], aA=ftr[4], aD=ftr[5], aR2=ftr[6];
                    int mode=(int)ftr[7], rb=ftr[8]>0.5f, pre=ftr[11]>0.5f; long krow=(long)ftr[9];
                    int selfosc = mkr && (mkr[p]>>12)==5;
                    float fhz=winst*SRATE_F/6.2831853f;
                    float toffL=(float)(off-a-(long)dL)/SRATE_F, toffR=(float)(off-a-(long)dR)/SRATE_F;
                    float toff=(float)(off-a)/SRATE_F;
                    float big=0.f;
                    const int* mpi = pm ? MPI+(long)fxp*3 : 0;
                    for(int j=0;j<nj;j++){
                        long nn=(long)(j0+j)*mg;
                        long ki=(long)(j0+j)-kb0; if(ki<0)ki=0; if(ki>knk-1)ki=knk-1;
                        const float* kn=KN+(krow*knk+ki)*KNW;
                        float fhzj=fhz, fade=1.f;
                        if(shm){
                            long mi=(long)(j0+j)-mki[1]; if(mi<0)mi=0; if(mi>mki[2]-1)mi=mki[2]-1;
                            cRe[j]=mkp[mi*mks]; cIm[j]=mkp[mi*mks+1];
                        }
                        if(pm){
                            long mi=(long)(j0+j)-mpi[1]; if(mi<0)mi=0; if(mi>mpi[2]-1)mi=mpi[2]-1;
                            mCp[j]=MPC[mpi[0]+mi]; fhzj=fhz*MPR[mpi[0]+mi];
                            // swept up past the top it would alias: fade it out
                            float fr=fhzj/SRATE_F;
                            fade = fr<0.40f ? 1.f : fr>0.45f ? 0.f : (0.45f-fr)*20.f;
                        }
                        if(fmo && !fms){
                            // a carrier whose deviation would reach Nyquist fades out
                            float fr=(fhzj+(float)fmk*fabsf(fmI)*(float)(fmw[p]*SRATE_D/6.283185307179586))/SRATE_F;
                            fade *= fr<0.40f ? 1.f : fr>0.45f ? 0.f : (0.45f-fr)*20.f;
                        }
                        float t=(float)(nn-a)/SRATE_F;
                        float fe=moog_adsr(t,fA,fD,kn[3],fR,toff);
                        float fc=kn[0]*kbf*exp2f(kn[2]*fe);
                        if(kn[6]!=0.f && kn[5]>0.f){
                            // LFO 1 on the cutoff: from the key (KB RESET) or
                            // free-running on the absolute clock (moog.lfo)
                            double tl = kn[8]>0.5f ? (double)(nn-a)/SRATE_D : (double)nn/SRATE_D;
                            double x=tl*(double)kn[5]; x-=floor(x);
                            int ls=(int)kn[7]; float xf=(float)x;
                            float lv = ls==0 ? 1.f-4.f*fabsf(xf-0.5f) : ls==1 ? 2.f*xf-1.f
                                     : ls==2 ? 1.f-2.f*xf : (xf<0.5f ? 1.f : -1.f);
                            fc*=exp2f(kn[6]*lv);
                        }
                        if(fc<1.f)fc=1.f;
                        // the ladder's OWN sine (moog.SELF) is not filtered by it;
                        // an FM'd harmonic's sidebands are, each at its own
                        // frequency, in the cell loop below
                        float h = selfosc ? 1.f : fms ? fade : moog_ladder(fhzj/fc,kn[1],mode,rb)*fade;
                        if(fms){ sbFc[j]=fc; sbK[j]=kn[1]; sbF[j]=fhzj; sbMode=mode; sbRb=rb; }
                        if(pre && !selfosc){   // the partials carry the ladder at its sustain already
                            float fcs=kn[0]*kbf*exp2f(kn[2]*fmaxf(kn[3],0.f)); if(fcs<1.f)fcs=1.f;
                            h/=fmaxf(moog_ladder(fhz/fcs,kn[1],mode,rb),1e-12f);
                        }
                        gLm[j]=moog_adsr((float)(nn-a-dL)/SRATE_F,aA,aD,kn[4],aR2,toffL)*h;
                        gRm[j]=moog_adsr((float)(nn-a-dR)/SRATE_F,aA,aD,kn[4],aR2,toffR)*h;
                        big=fmaxf(big,fmaxf(gLm[j],gRm[j]));
                    }
                    // silent for the whole block: above a closed ladder the
                    // top harmonics of a lead mostly are. The level here is
                    // BEFORE the master gain, where a note sits near -50 dBFS,
                    // so 1e-8 is ~110 dB under it -- at 1e-6 it was 70, and a
                    // renderer with a different headroom skipped different
                    // partials (live against the file: 2.9e-4 apart).
                    if(big*fmaxf(fabsf(aL),fabsf(aR))<=1e-8f) continue;
                }
                float invg=1.f/(float)mg;
                double phL=ph0L[p]+w*(double)ns+bph, phR=ph0R[p]+w*(double)ns+bph;
                float zrL=cos(phL),ziL=sin(phL),zrR=cos(phR),ziR=sin(phR);
                float rr=cosf(winst),ri=sinf(winst);
                float invb=1.f/(float)BLK;
                float jfa=jf*cv*csc;
                // EVERY OTHER VOICE takes the loop it always took, spelled as it
                // always was: -ffast-math contracts a restructured expression
                // differently, and a render moves by an ULP. A MOOG runs the
                // same body over grid cells, each interpolated between its own
                // two grid gains; the phasor runs on across them untouched.
                if(!ftr){
                for(long n=ns;n<ne;n++){
                    float t=(float)(n-bs0)*invb; float mL=(mL0+(mL1-mL0)*t)*aL, mR=(mR0+(mR1-mR0)*t)*aR;
                    float sL=zrL, sR=zrR;
                    if(jfa>0.f){
                        double sec=(double)n/SRATE_D;
                        // THE WASH'S BANDWIDTH. The phase is redrawn at nf*gran per
                        // second, so gran IS the noise's bandwidth as a fraction of
                        // the partial's own frequency: at RAND_GRAN it is redrawn
                        // every sample and the noise is white, spread flat over the
                        // whole spectrum no matter which partial it came from. That
                        // is why turning the wash up far enough to fill between a
                        // cymbal's modes also fills the notches BETWEEN its bands.
                        // A smaller gran keeps each partial's noise around the
                        // partial, so the wash inherits the plate's own shape.
                        double gbw=(double)chBW[p];
                        // Two spellings, not a ternary: a voice that does not set
                        // chiff_bandwidth must take the IDENTICAL expression it took
                        // before this column existed. -ffast-math folds a constant
                        // differently from a loaded value, and the index runs to
                        // ~1e9, so a 1-ULP shift reseeds the hash completely --
                        // same loudness and same spectrum to 0.01 dB, but not the
                        // same samples, and every render in the corpus would move.
                        float jit;
                        if(gbw==(double)RAND_GRAN)
                            jit=6.2831853f*(float)hash01((uint64_t)(long long)(sec*(double)nf*(double)RAND_GRAN))*cc;
                        else
                            jit=6.2831853f*(float)hash01((uint64_t)(long long)(sec*(double)nf*gbw))*cc;
                        float cj=cosf(jit),sj2=sinf(jit);
                        sL += (zrL*cj - ziL*sj2)*jfa;
                        sR += (zrR*cj - ziR*sj2)*jfa;
                    }
                    outL[n-n0]+=mL*sL; outR[n-n0]+=mR*sR;
                    if(outSL){ outSL[n-n0]+=mL*sL*swp; outSR[n-n0]+=mR*sR*swp; }
                    float tmp; tmp=zrL*rr-ziL*ri; ziL=zrL*ri+ziL*rr; zrL=tmp;
                    tmp=zrR*rr-ziR*ri; ziR=zrR*ri+ziR*rr; zrR=tmp;
                }
                } else {
                // a Moog partial with a NEGATIVE wash bandwidth is a noise band
                // (moog.NOISE): seeded by its note's onset and its own centre, so
                // two notes' noise is not one noise twice
                int noiz = chBW[p] < 0.f;
                double nrate = noiz ? (double)nf*(double)(-chBW[p]) : 0.0;
                uint64_t nseed = (uint64_t)a*0x9E3779B97F4A7C15ULL + (uint64_t)(long long)((double)nf*1000.0);
                long long nui=-1; double nh0=0.0, ndh=0.0;
                // THE SIDEBANDS WORTH WEIGHING: those whose D_m could reach
                // SB_TOL through the ladder at its loudest -- a bound the
                // resonance alone sets (the peak of a ladder at K_MAX, with
                // room to spare), so it is the same in every block and
                // either renderer -- and the far tail never costs a ladder
                // evaluation; each grid point's gains are kept for the next
                // cell, which starts where this one ends
                int dlo=0, dhi=-1, hEndJ=-1;
                float hEnd[2*FM_SBMAX+1];
                if(fms){
                    float td = SB_TOL/(1.5f*moog_ladder(1.f,3.9f,0,1));   // moog.K_MAX, RES BASS on
                    for(dlo=0; dlo<=2*sbM; dlo++) if(fabsf(sbD0r[dlo])+fabsf(sbD0i[dlo])>td) break;
                    for(dhi=2*sbM; dhi>=dlo; dhi--) if(fabsf(sbD0r[dhi])+fabsf(sbD0i[dhi])>td) break;
                    // this note's own phase back on: D_m = D'_m e^{-i m psi}
                    double er=cos(-(double)(dlo-sbM)*sbPsi), ei=sin(-(double)(dlo-sbM)*sbPsi);
                    double sr=cos(-sbPsi), si=sin(-sbPsi);
                    for(int i=dlo;i<=dhi;i++){
                        sbDr[i]=(float)((double)sbD0r[i]*er-(double)sbD0i[i]*ei);
                        sbDi[i]=(float)((double)sbD0r[i]*ei+(double)sbD0i[i]*er);
                        double t=er*sr-ei*si; ei=er*si+ei*sr; er=t;
                    }
                }
                for(int cl=0; cl<BLK/mg; cl++){
                long c0=bs0+(long)cl*mg, c1=c0+mg;
                long s0 = ns>c0 ? ns : c0, s1 = ne<c1 ? ne : c1;
                if(s0>=s1) continue;
                float a0L=gLm[cl], a1L=gLm[cl+1], a0R=gRm[cl], a1R=gRm[cl+1];
                float z1r=0.f, z1i=0.f, r1r=1.f, r1i=0.f;
                float g0r[2*FM_SBMAX+1], g0i[2*FM_SBMAX+1], dgr[2*FM_SBMAX+1], dgi[2*FM_SBMAX+1];
                float pzr[2*FM_SBMAX+1], pzi[2*FM_SBMAX+1], prr[2*FM_SBMAX+1], pri[2*FM_SBMAX+1];
                int slo=0, nsb=0;
                if(fmo){
                    // OSC 1's angle at the cell's start, exactly; its vibrato and
                    // bend (bph) scale with frequency, as every partial's do
                    double w1=fmw[p], ps=fmp[p]+w1*(double)s0+bph*(w1/w);
                    z1r=(float)cos(ps); z1i=(float)sin(ps);
                    double w1v=(double)winst*(w1/w);
                    r1r=(float)cos(w1v); r1i=(float)sin(w1v);
                    if(fms){
                        // EACH SIDEBAND THROUGH THE LADDER at its own frequency
                        // |k f2 + m f1|, at both ends of the cell, and faded as
                        // it nears Nyquist -- one sideband at a time, where the
                        // unfiltered path had to fade the whole harmonic
                        float f1=(float)(w1v*SRATE_D/6.283185307179586);
                        int reuse = hEndJ==cl;
                        for(int i=dlo;i<=dhi;i++){
                            float m=(float)(i-sbM), hg[2];
                            for(int e = reuse ? 1 : 0; e<2; e++){
                                float fs=fabsf(sbF[cl+e]+m*f1), fr=fs/SRATE_F;
                                float nq = fr<0.40f ? 1.f : fr>0.45f ? 0.f : (0.45f-fr)*20.f;
                                hg[e] = nq>0.f ? moog_ladder(fs/sbFc[cl+e],sbK[cl+e],sbMode,sbRb)*nq : 0.f;
                            }
                            if(reuse) hg[0]=hEnd[i];
                            hEnd[i]=hg[1];
                            g0r[i]=sbDr[i]*hg[0]; g0i[i]=sbDi[i]*hg[0];
                            dgr[i]=sbDr[i]*hg[1]-g0r[i]; dgi[i]=sbDi[i]*hg[1]-g0i[i];
                        }
                        hEndJ=cl+1;
                        // ...and only the ones that sound (SB_TOL): a shut
                        // ladder leaves a handful of a bell's dozens
                        float tg = SB_TOL;
                        int shi;
                        for(slo=dlo; slo<=dhi; slo++)
                            if(fmaxf(fabsf(g0r[slo])+fabsf(g0i[slo]),
                                     fabsf(g0r[slo]+dgr[slo])+fabsf(g0i[slo]+dgi[slo]))>tg) break;
                        for(shi=dhi; shi>=slo; shi--)
                            if(fmaxf(fabsf(g0r[shi])+fabsf(g0i[shi]),
                                     fabsf(g0r[shi]+dgr[shi])+fabsf(g0i[shi]+dgi[shi]))>tg) break;
                        nsb=shi-slo+1;
                        // EACH SIDEBAND ITS OWN PHASOR, e^{i m th1} turning at
                        // m w1, as any partial is: independent, so the sum
                        // below runs across them in vector lanes, where a
                        // Horner chain is one long dependency. Set in double
                        // at the cell's start, as OSC 1's angle is.
                        double czr=cos((double)(slo-sbM)*ps), czi=sin((double)(slo-sbM)*ps);
                        double crr=cos((double)(slo-sbM)*w1v), cri=sin((double)(slo-sbM)*w1v);
                        double sr1=cos(ps), si1=sin(ps), tr1=cos(w1v), ti1=sin(w1v);
                        for(int i=0;i<nsb;i++){
                            pzr[i]=(float)czr; pzi[i]=(float)czi; prr[i]=(float)crr; pri[i]=(float)cri;
                            double t=czr*sr1-czi*si1; czi=czr*si1+czi*sr1; czr=t;
                            t=crr*tr1-cri*ti1; cri=crr*ti1+cri*tr1; crr=t;
                        }
                    }
                }
                if(pm){
                    // re-anchor the phase at the cell's start, exactly, and turn
                    // at this cell's own rate: a 512-sample file block and a
                    // 128-sample live one then walk the same phase
                    double cs=mCp[cl]+(mCp[cl+1]-mCp[cl])*(double)(s0-c0)/(double)mg;
                    double el=(double)winst*(double)(s0-ns)+w*cs;
                    zrL=(float)cos(phL+el); ziL=(float)sin(phL+el);
                    zrR=(float)cos(phR+el); ziR=(float)sin(phR+el);
                    double wc=(double)winst+w*(mCp[cl+1]-mCp[cl])/(double)mg;
                    rr=(float)cos(wc); ri=(float)sin(wc);
                }
                for(long n=s0;n<s1;n++){
                    float t=(float)(n-c0)*invg, tb=(float)(n-bs0)*invb;
                    float mL=(a0L+(a1L-a0L)*t)*(aLp+(aL-aLp)*tb), mR=(a0R+(a1R-a0R)*t)*(aRp+(aR-aRp)*tb);
                    float sL=zrL, sR=zrR;
                    if(noiz){
                        // A NOISE BAND: the carrier's phase moved to a new
                        // random value nrate times a second, which spreads it
                        // over a band that wide around its centre -- and no
                        // carrier left. MOVED, not jumped: each draw is joined
                        // to the next the short way round the circle. A phase
                        // that jumps is a click at every draw, and a thousand
                        // of them leaked the low bands up the spectrum to a
                        // floor 45 dB down, which a closed ladder cannot take out.
                        double sec=(double)n/SRATE_D, u=sec*nrate;
                        long long ui=(long long)u; double uf=u-(double)ui;
                        if(ui!=nui){   // a new draw: hash only then
                            nui=ui; nh0=hash01(nseed+(uint64_t)ui);
                            double h1=hash01(nseed+(uint64_t)(ui+1));
                            ndh=h1-nh0; ndh-=floor(ndh+0.5);
                        }
                        float jn=6.2831853f*(float)(nh0+ndh*uf);
                        float cn=cosf(jn), sn=sinf(jn);
                        sL = zrL*cn - ziL*sn; sR = zrR*cn - ziR*sn;
                    }
                    float czL=zrL, czR=zrR, sgL=ziL, sgR=ziR;
                    if(fms){
                        // F = sum_m G_m(t) e^{i m th1}; the harmonic is
                        // Re(e^{i k th2} F)
                        const float *G0r=g0r+slo, *G0i=g0i+slo, *DGr=dgr+slo, *DGi=dgi+slo;
                        float Fr=0.f, Fi=0.f;
                        for(int i=0;i<nsb;i++){
                            float gr=G0r[i]+DGr[i]*t, gi=G0i[i]+DGi[i]*t;
                            Fr+=gr*pzr[i]-gi*pzi[i]; Fi+=gr*pzi[i]+gi*pzr[i];
                            float tr=pzr[i]*prr[i]-pzi[i]*pri[i]; pzi[i]=pzr[i]*pri[i]+pzi[i]*prr[i]; pzr[i]=tr;
                        }
                        czL=zrL*Fr-ziL*Fi; sgL=zrL*Fi+ziL*Fr;
                        czR=zrR*Fr-ziR*Fi; sgR=zrR*Fi+ziR*Fr;
                        sL=czL; sR=czR;
                    } else if(fmo){
                        // A = sum_j Re(B_j) sin(j th1) + Im(B_j) cos(j th1): the
                        // integral of OSC 1's wave; OSC 2's harmonic k moves by k I A
                        float pr=z1r, pi=z1i, A=0.f;
                        const float* B=ftr+14;
                        for(int jj=0;jj<FM_J;jj++){
                            A += B[2*jj]*pi + B[2*jj+1]*pr;
                            float tr=pr*z1r-pi*z1i; pi=pr*z1i+pi*z1r; pr=tr;
                        }
                        float dl=(float)fmk*fmI*A, cd=cosf(dl), sd=sinf(dl);
                        czL=zrL*cd-ziL*sd; sgL=zrL*sd+ziL*cd;
                        czR=zrR*cd-ziR*sd; sgR=zrR*sd+ziR*cd;
                        sL=czL; sR=czR;
                        float t1=z1r*r1r-z1i*r1i; z1i=z1r*r1i+z1i*r1r; z1r=t1;
                    }
                    if(shm){
                        // Re(c e^{i theta}) with c moving across the cell
                        float gr=cRe[cl]+(cRe[cl+1]-cRe[cl])*t, gi=cIm[cl]+(cIm[cl+1]-cIm[cl])*t;
                        sL = gr*czL - gi*sgL; sR = gr*czR - gi*sgR;
                    }
                    if(jfa>0.f){
                        double sec=(double)n/SRATE_D;
                        // THE WASH'S BANDWIDTH. The phase is redrawn at nf*gran per
                        // second, so gran IS the noise's bandwidth as a fraction of
                        // the partial's own frequency: at RAND_GRAN it is redrawn
                        // every sample and the noise is white, spread flat over the
                        // whole spectrum no matter which partial it came from. That
                        // is why turning the wash up far enough to fill between a
                        // cymbal's modes also fills the notches BETWEEN its bands.
                        // A smaller gran keeps each partial's noise around the
                        // partial, so the wash inherits the plate's own shape.
                        double gbw=(double)chBW[p];
                        // Two spellings, not a ternary: a voice that does not set
                        // chiff_bandwidth must take the IDENTICAL expression it took
                        // before this column existed. -ffast-math folds a constant
                        // differently from a loaded value, and the index runs to
                        // ~1e9, so a 1-ULP shift reseeds the hash completely --
                        // same loudness and same spectrum to 0.01 dB, but not the
                        // same samples, and every render in the corpus would move.
                        float jit;
                        if(gbw==(double)RAND_GRAN)
                            jit=6.2831853f*(float)hash01((uint64_t)(long long)(sec*(double)nf*(double)RAND_GRAN))*cc;
                        else
                            jit=6.2831853f*(float)hash01((uint64_t)(long long)(sec*(double)nf*gbw))*cc;
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
                }
            }
            #undef AMP
        }
    }
}
