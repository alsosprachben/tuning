// THE SAMPLE PASS, ONCE, for the CPU and the GPU.
//
// synth_voice does two kinds of work. Once a partial a block: its amplitude at
// the block's edges, its chiff fade, vibrato and bends, the Moog's ladder on
// its grid, and the phasor's anchor -- the part that needs doubles. Then once
// a sample: the phasor turned, the chiff's hash, the noise band, FM, the
// moving shape, summed into the output. voice_block (synthkernel.c) runs the
// first half, through the SAME source text synth_voice runs (the voice_*.inc
// fragments), and writes what the second half needs into the descriptors
// below. voice_sample is that second half for one partial and one sample; it
// compiles as C (voice_samples, the reference) and as OpenCL C (gpukernel.cl),
// so the two cannot drift.
//
// ONE DIFFERENCE FROM synth_voice, deliberately: the phasors are not turned
// sample by sample but evaluated directly, z0 * e^{i k w}, because a GPU
// computes samples in parallel and a recurrence is a chain. k is at most a
// block, so k*w stays within a few hundred radians, where a float places it
// to ~1e-5 -- the recurrence's own rounding is of the same size. Every angle
// arrives here already reduced (the block's anchor in double, each step
// within (-pi, pi]), so nothing here needs a double: the Iris Xe has none.
#ifndef VOICEDESC_H
#define VOICEDESC_H

#ifdef __OPENCL_VERSION__
typedef ulong u64; typedef int i32; typedef long i64;
#define VGLOBAL __global
#define VCOS cos
#define VSIN sin
#define VFLOOR floor
static inline u64 v_mulhi(u64 a, u64 b){ return mul_hi(a, b); }
#else
#include <stdint.h>
#include <math.h>
typedef uint64_t u64; typedef int32_t i32; typedef int64_t i64;
#define VGLOBAL
#define VCOS cosf
#define VSIN sinf
#define VFLOOR floorf
static inline u64 v_mulhi(u64 a, u64 b){ return (u64)(((unsigned __int128)a * b) >> 64); }
#endif

// what a partial's block carries beyond its sinusoid
#define VD_NOISE 1      // a Moog noise band (moog.NOISE)
#define VD_SHAPE 2      // a moving waveshape (MKI/MPK)
#define VD_FMO   4      // 1 -> 2 FM, unfiltered
#define VD_FMS   8      // 1 -> 2 FM as sidebands, each through the ladder
#define VD_PM    16     // OSC 2 on its pitch rows: the carrier re-anchored per cell

// ONE PARTIAL'S BLOCK. kind 0: silent this block (skipped); 1: every voice but
// the Moog; 2: a Moog partial, whose cells follow in the cell table.
typedef struct {
    u64 chk_hi, chk_lo;          // the chiff's index step (chiff_step)
    u64 nk_hi, nk_lo, nseed;     // the noise band's draw step and seed
    i32 ns, ne;                  // samples [ns, ne) of the block, from its start
    i32 kind, flags, cell, kn;   // kn: the attack's knee, samples from the block's start (0: none)
    float zLr, zLi, zRr, zRi;    // the carrier at ns, each ear
    float winst;                 // its step, radians a sample
    float mL0, mL1, mR0, mR1;    // kind 1: the amplitude at the block's edges
    float aL, aR, aLp, aRp;      // the partial's level (a Moog's: last block's, then this one's)
    float jfa, cc, swp;          // the chiff's level, its cycle, the send weight
    float kgL, kgR;              // kind 1: the amplitude at the knee (voice_block.inc), each ear
    float za[12];                // the carrier again at ns+128, +256, +384 (zLr zLi zRr zRi each)
} vdesc;

// THE CARRIER IS RE-ANCHORED EVERY V_SUB SAMPLES. A file renders in 512-sample
// blocks, and z0 e^{i k w} at k up to 511 puts the angle out to ~1600 rad,
// which a float places only to ~1e-4: -80 dB, against the -110 the live
// block's 128 reaches. So the setup computes the carrier afresh, in double,
// at each V_SUB samples of the block (za), and k never runs past V_SUB from
// an anchor. A live block of 128 uses the first anchor alone, as it did.
#define V_SUB 128

// ONE MOOG CELL (a grid interval, MOOG_GRID samples): its gains at both ends,
// and whatever turns within it
typedef struct {
    i32 s0, s1, sb, nsb;         // samples [s0, s1) from the block's start; sidebands sb..sb+nsb
    float gL0, gL1, gR0, gR1;    // the contour times the ladder, at the cell's ends
    float cRe0, cIm0, cRe1, cIm1;// VD_SHAPE: the harmonic's coefficient at the ends
    float zLr, zLi, zRr, zRi, wc;// VD_PM: the carrier at s0, and its step
    float z1r, z1i, th1, fmkI;   // VD_FMO: OSC 1 at s0, its step, k * index
    float B[16];                 // VD_FMO: OSC 1's wave (FT 14-29)
    float pad[3];
} vcell;

// ONE FM SIDEBAND in one cell: its gain at the cell's ends (as start and
// change), its phasor at s0 and its step
typedef struct { float g0r, g0i, dgr, dgi, pzr, pzi, th, pad; } vsb;

// synthkernel.c's hash01, in integers and a float: the 53-bit value rounds to
// a float exactly as (float)hash01 does
static inline float v_hash01(u64 x){
    x += 0x9E3779B97F4A7C15UL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9UL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBUL;
    x ^= x >> 31;
    return (float)(x >> 11) * (1.0f / 9007199254740992.0f);
}

// A NOISE BAND'S PHASE at draw ui and fraction uf: the draw's value joined to
// the next's the short way round. Which way is short is decided EXACTLY as
// the CPU's double arithmetic decides it (voice_noise.inc: ndh = h1 - h0,
// ndh -= floor(ndh + 0.5)), from the hashes' 53-bit integers: in floats, two
// draws almost exactly half a turn apart went round the other way now and
// then, and for one draw (~27 samples at 6.6 kHz) the GPU's phase swept the
// wrong way -- samba's shakes, 1.7e-2 of the peak at one instant.
static inline float v_noise_phase(u64 seed, u64 ui, float uf){
    u64 x0=seed+ui, x1=seed+ui+1;
    x0 += 0x9E3779B97F4A7C15UL; x0 = (x0 ^ (x0 >> 30)) * 0xBF58476D1CE4E5B9UL;
    x0 = (x0 ^ (x0 >> 27)) * 0x94D049BB133111EBUL; x0 ^= x0 >> 31;
    x1 += 0x9E3779B97F4A7C15UL; x1 = (x1 ^ (x1 >> 30)) * 0xBF58476D1CE4E5B9UL;
    x1 = (x1 ^ (x1 >> 27)) * 0x94D049BB133111EBUL; x1 ^= x1 >> 31;
    i64 a=(i64)(x0 >> 11), d=(i64)(x1 >> 11) - a;
    const i64 H=(i64)1 << 52, F=(i64)1 << 53;
    if(d >= H) d -= F; else if(d < -H) d += F;
    return (float)a*(1.0f/9007199254740992.0f) + (float)d*(1.0f/9007199254740992.0f)*uf;
}

// a phasor z0 turned k steps of w: z0 e^{i k w}
#define V_TURN(r, i, z0r, z0i, k, w) { float a_=(float)(k)*(w), c_=VCOS(a_), s_=VSIN(a_); \
    r=(z0r)*c_-(z0i)*s_; i=(z0r)*s_+(z0i)*c_; }

#define V_TURN2(rL, iL, rR, iR, zLr, zLi, zRr, zRi, k, w) { float a_=(float)(k)*(w), c_=VCOS(a_), s_=VSIN(a_); \
    rL=(zLr)*c_-(zLi)*s_; iL=(zLr)*s_+(zLi)*c_; rR=(zRr)*c_-(zRi)*s_; iR=(zRr)*s_+(zRi)*c_; }

// partial d at sample k of the block (absolute sample n), added into o[0..3]:
// L, R, and the send pair when `send`
static inline void voice_sample(const VGLOBAL vdesc* d, const VGLOBAL vcell* C, const VGLOBAL vsb* SB,
                                int k, u64 n, float invb, int mg, float invg, int send, float* o)
{
    if(d->kind==0 || k<d->ns || k>=d->ne) return;
    // both ears turn at one rate: one sine and cosine for the two, from the
    // last anchor (V_SUB)
    float zrL, ziL, zrR, ziR;
    int kk=k-d->ns, sub=kk/V_SUB;
    if(sub==0){
        V_TURN2(zrL, ziL, zrR, ziR, d->zLr, d->zLi, d->zRr, d->zRi, kk, d->winst);
    } else {
        const VGLOBAL float* a=d->za+4*(sub-1);
        V_TURN2(zrL, ziL, zrR, ziR, a[0], a[1], a[2], a[3], kk-sub*V_SUB, d->winst);
    }
    float tb=(float)k*invb, mL, mR, sL, sR;
    if(d->kind==1){
        mL=(d->mL0+(d->mL1-d->mL0)*tb)*d->aL; mR=(d->mR0+(d->mR1-d->mR0)*tb)*d->aR;
        if(k<d->kn){
            // the attack's ramp, up to its knee (voice_block.inc)
            float r=(float)(k-d->ns)/(float)(d->kn-d->ns);
            mL=d->kgL*r*d->aL; mR=d->kgR*r*d->aR;
        }
        sL=zrL; sR=zrR;
        if(d->flags & VD_NOISE){
            // an ordinary noise band (voice_noise.inc), as the Moog's below
            u64 ui=n*d->nk_hi+v_mulhi(n, d->nk_lo);
            float uf=(float)(n*d->nk_lo)*(1.0f/18446744073709551616.0f);
            float jn=6.2831853f*v_noise_phase(d->nseed, ui, uf), cn=VCOS(jn), sn=VSIN(jn);
            sL=zrL*cn-ziL*sn; sR=zrR*cn-ziR*sn;
        }
    } else {
        int cl=k/mg; const VGLOBAL vcell* v=C+d->cell+cl;
        float t=(float)(k-cl*mg)*invg;
        mL=(v->gL0+(v->gL1-v->gL0)*t)*(d->aLp+(d->aL-d->aLp)*tb);
        mR=(v->gR0+(v->gR1-v->gR0)*t)*(d->aRp+(d->aR-d->aRp)*tb);
        int fl=d->flags;
        if(fl & VD_PM){
            V_TURN2(zrL, ziL, zrR, ziR, v->zLr, v->zLi, v->zRr, v->zRi, k-v->s0, v->wc);
        }
        sL=zrL; sR=zrR;
        if(fl & VD_NOISE){
            // the draw index floor(n * nrate / SRATE) and its fraction, exactly
            u64 ui=n*d->nk_hi+v_mulhi(n, d->nk_lo);
            float uf=(float)(n*d->nk_lo)*(1.0f/18446744073709551616.0f);
            float jn=6.2831853f*v_noise_phase(d->nseed, ui, uf), cn=VCOS(jn), sn=VSIN(jn);
            sL=zrL*cn-ziL*sn; sR=zrR*cn-ziR*sn;
        }
        float czL=zrL, czR=zrR, sgL=ziL, sgR=ziR;
        if(fl & VD_FMS){
            float Fr=0.f, Fi=0.f;
            for(int i=0;i<v->nsb;i++){
                const VGLOBAL vsb* q=SB+v->sb+i;
                float gr=q->g0r+q->dgr*t, gi=q->g0i+q->dgi*t, pr, pi;
                V_TURN(pr, pi, q->pzr, q->pzi, k-v->s0, q->th);
                Fr+=gr*pr-gi*pi; Fi+=gr*pi+gi*pr;
            }
            czL=zrL*Fr-ziL*Fi; sgL=zrL*Fi+ziL*Fr;
            czR=zrR*Fr-ziR*Fi; sgR=zrR*Fi+ziR*Fr;
            sL=czL; sR=czR;
        } else if(fl & VD_FMO){
            float z1r, z1i;
            V_TURN(z1r, z1i, v->z1r, v->z1i, k-v->s0, v->th1);
            float pr=z1r, pi=z1i, A=0.f;
            for(int jj=0;jj<8;jj++){
                A += v->B[2*jj]*pi + v->B[2*jj+1]*pr;
                float tr=pr*z1r-pi*z1i; pi=pr*z1i+pi*z1r; pr=tr;
            }
            float dl=v->fmkI*A, cd=VCOS(dl), sd=VSIN(dl);
            czL=zrL*cd-ziL*sd; sgL=zrL*sd+ziL*cd;
            czR=zrR*cd-ziR*sd; sgR=zrR*sd+ziR*cd;
            sL=czL; sR=czR;
        }
        if(fl & VD_SHAPE){
            float gr=v->cRe0+(v->cRe1-v->cRe0)*t, gi=v->cIm0+(v->cIm1-v->cIm0)*t;
            sL=gr*czL-gi*sgL; sR=gr*czR-gi*sgR;
        }
    }
    if(d->jfa>0.f){
        u64 idx=n*d->chk_hi+v_mulhi(n, d->chk_lo);          // chiff_index, exactly
        float jit=6.2831853f*v_hash01(idx)*d->cc, cj=VCOS(jit), sj=VSIN(jit);
        sL+=(zrL*cj-ziL*sj)*d->jfa;
        sR+=(zrR*cj-ziR*sj)*d->jfa;
    }
    o[0]+=mL*sL; o[1]+=mR*sR;
    if(send){ o[2]+=mL*sL*d->swp; o[3]+=mR*sR*d->swp; }
}
#endif
