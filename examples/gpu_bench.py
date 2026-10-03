#!/usr/bin/env python3
"""Can the GPU render a live block of partials faster than the CPU?

    python3 examples/gpu_bench.py [--frames 128] [--blocks 400] [--attack]

The live engine's work, reduced to its core: N partials, each a sinusoid with
its own frequency, block-start phase and gain ramped linearly across the
block, summed into a stereo block of FRAMES samples. Timed, per block, for
1k-16k partials:

  cpu   C, the way synthkernel.c does it -- each partial's phasor rotated
        sample by sample (one complex multiply a sample, no sin in the loop),
        -O3 -march=native (AVX-512 here), single thread and OpenMP over
        partials;
  gpu   OpenCL, the GPU-natural form: one work-item per (sample, group of
        partials), each partial's sample computed directly as
        a * cos(phase0 + s * w), then a second pass summing the groups.

THE PRECISION, which is what makes a GPU port non-trivial: the kernel keeps a
partial's phase in double, because over a long note it runs past where a
float can place it. Here the CPU keeps every phase in double and wraps it to
[0, 2 pi) at each block start; within a block, s * w is at most a few hundred
radians, which float holds to ~1e-5 -- 100 dB down. So the GPU needs no
doubles (the Iris Xe has none in hardware).

Every gpu block is checked against the cpu block; the max difference is
printed (float cos vs double phasor: ~1e-5 of full scale is expected).

The GPU half needs pyopencl and an OpenCL driver for the GPU (Intel:
intel-opencl-icd). Without them the cpu timings alone are printed.
"""
import ctypes
import math
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

C_SRC = r"""
#include <math.h>
#include <string.h>
#include <omp.h>
#include <stdint.h>
void threads(int n){ omp_set_num_threads(n); }
#define RAND_GRAN 100000.0
static inline double hash01(uint64_t x){          /* synthkernel.c's, verbatim */
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    x ^= x >> 31;
    return (double)(x >> 11) * (1.0 / 9007199254740992.0);
}
static inline uint64_t chiff_index(long n, uint64_t khi, uint64_t klo){   /* synthkernel.c's */
    uint64_t un=(uint64_t)n; return un*khi + (uint64_t)(((unsigned __int128)un*klo)>>64);
}
/* the step's split, ONCE, for both sides: the C reference and the GPU must
   take khi/klo from the same compiled arithmetic -- -ffast-math may evaluate
   f*GRAN/sr as f*(GRAN/sr), a different double in its last bit, and then
   floor(n*step) lands one integer over now and then */
void chiff_steps(int n, const float* f, double sr, uint64_t* khi, uint64_t* klo){
    for(int p=0;p<n;p++){
        double step=(double)f[p]*RAND_GRAN/sr, ip=floor(step);
        khi[p]=(uint64_t)ip; klo[p]=(uint64_t)ldexp(step-ip,64);
    }
}
static inline float moog_out(float f){ float r=f/12500.f; return 1.f/sqrtf(1.f+r*r); }
static inline float ladder_lp4(float x, float k){  /* moog_ladder, mode 0, no RES BASS */
    float x2=x*x, re4=1.f-6.f*x2+x2*x2+k, im4=4.f*x-4.f*x*x2;
    return 1.f/sqrtf(re4*re4+im4*im4);
}
/* THE ATTACK: every partial in its chiff -- a phase-jittered copy of itself,
   redrawn every sample from the hash of floor(t f GRAN) -- through a Moog
   ladder whose cutoff moves across the block, as synthkernel.c does it */
void render_attack(int n, int frames, long n0, double sr, const double* ph0, const double* w,
                   const float* g0, const float* g1, const float* panL, const float* panR,
                   const float* f, const float* fc0, const float* fc1, const float* k,
                   const float* jfa, float* outL, float* outR){
    memset(outL, 0, frames*sizeof(float)); memset(outR, 0, frames*sizeof(float));
    #pragma omp parallel
    {
        float L[1024], R[1024];
        memset(L, 0, frames*sizeof(float)); memset(R, 0, frames*sizeof(float));
        #pragma omp for schedule(static)
        for(int p=0;p<n;p++){
            float m0=g0[p]*ladder_lp4(f[p]/fc0[p],k[p])*moog_out(f[p]);
            float m1=g1[p]*ladder_lp4(f[p]/fc1[p],k[p])*moog_out(f[p]);
            float zr=cosf((float)ph0[p]), zi=sinf((float)ph0[p]);
            float wr=cosf((float)w[p]), wi=sinf((float)w[p]);
            uint64_t khi, klo; chiff_steps(1, &f[p], sr, &khi, &klo);
            float ja=jfa[p], pl=panL[p], pr=panR[p];
            for(int s=0;s<frames;s++){
                float m=m0+(m1-m0)*(float)s/(float)frames, sm=zr;
                if(ja>0.f){
                    float jit=6.2831853f*(float)hash01(chiff_index(n0+s, khi, klo));
                    sm += (zr*cosf(jit) - zi*sinf(jit))*ja;
                }
                L[s]+=m*sm*pl; R[s]+=m*sm*pr;
                float t=zr*wr-zi*wi; zi=zr*wi+zi*wr; zr=t;
            }
        }
        #pragma omp critical
        for(int s=0;s<frames;s++){ outL[s]+=L[s]; outR[s]+=R[s]; }
    }
}
void render(int n, int frames, const double* ph0, const double* w,
            const float* g0, const float* g1, const float* panL, const float* panR,
            float* outL, float* outR){
    memset(outL, 0, frames*sizeof(float)); memset(outR, 0, frames*sizeof(float));
    #pragma omp parallel
    {
        float L[1024], R[1024];
        memset(L, 0, frames*sizeof(float)); memset(R, 0, frames*sizeof(float));
        #pragma omp for schedule(static)
        for(int p=0;p<n;p++){
            float zr=cosf((float)ph0[p]), zi=sinf((float)ph0[p]);
            float wr=cosf((float)w[p]), wi=sinf((float)w[p]);
            float g=g0[p], dg=(g1[p]-g0[p])/frames, pl=panL[p], pr=panR[p];
            for(int s=0;s<frames;s++){
                float a=g*zr; L[s]+=a*pl; R[s]+=a*pr;
                float t=zr*wr-zi*wi; zi=zr*wi+zi*wr; zr=t; g+=dg;
            }
        }
        #pragma omp critical
        for(int s=0;s<frames;s++){ outL[s]+=L[s]; outR[s]+=R[s]; }
    }
}
"""

CL_SRC = r"""
// one work-item per (sample s, group of partials g): sum that group's
// partials at sample s, directly -- no recurrence, so samples are parallel
__kernel void partials(const int n, const int frames, const int per,
                       __global const float* ph0, __global const float* w,
                       __global const float* g0, __global const float* g1,
                       __global const float* panL, __global const float* panR,
                       __global float* accL, __global float* accR){
    int s = get_global_id(0), grp = get_global_id(1);
    int p0 = grp*per, p1 = min(n, p0+per);
    float fs = (float)s, fr = fs/(float)frames, L = 0.f, R = 0.f;
    for(int p=p0;p<p1;p++){
        float a = (g0[p] + (g1[p]-g0[p])*fr) * cos(ph0[p] + fs*w[p]);
        L += a*panL[p]; R += a*panR[p];
    }
    accL[grp*frames+s] = L; accR[grp*frames+s] = R;
}
// THE LADDER, once a partial a block: its gain at both ends of the block
float ladder_lp4(float x, float k){
    float x2=x*x, re4=1.f-6.f*x2+x2*x2+k, im4=4.f*x-4.f*x*x2;
    return 1.f/sqrt(re4*re4+im4*im4);
}
__kernel void ladder(const int n, __global const float* f, __global const float* fc0,
                     __global const float* fc1, __global const float* k,
                     __global const float* g0, __global const float* g1,
                     __global float* m0, __global float* m1){
    int p = get_global_id(0); if(p >= n) return;
    float r = f[p]/12500.f, out = 1.f/sqrt(1.f+r*r);
    m0[p] = g0[p]*ladder_lp4(f[p]/fc0[p], k[p])*out;
    m1[p] = g1[p]*ladder_lp4(f[p]/fc1[p], k[p])*out;
}
// synthkernel.c's hash, in 64-bit integers -- no double needed
float hash01(ulong x){
    x += 0x9E3779B97F4A7C15UL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9UL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBUL;
    x ^= x >> 31;
    return (float)(x >> 11) * (1.0f / 9007199254740992.0f);
}
// THE CHIFF, per sample: the hash index floor(n * f * GRAN / sr) exactly as the
// C kernel now computes it -- the step's integer part and its 2^64-scaled
// fraction, the 128-bit product's top half from mul_hi
__kernel void attack(const int n, const int frames, const int per, const ulong n0,
                     __global const float* ph0, __global const float* w,
                     __global const float* m0, __global const float* m1,
                     __global const float* panL, __global const float* panR,
                     __global const ulong* khi, __global const ulong* klo,
                     __global const float* jfa, __global float* accL, __global float* accR){
    int s = get_global_id(0), grp = get_global_id(1);
    int p0 = grp*per, p1 = min(n, p0+per);
    float fs = (float)s, fr = fs/(float)frames, L = 0.f, R = 0.f;
    for(int p=p0;p<p1;p++){
        float ph = ph0[p] + fs*w[p], zr = cos(ph), zi = sin(ph), sm = zr;
        if(jfa[p] > 0.f){
            ulong un = n0 + (ulong)s;
            ulong idx = un*khi[p] + mul_hi(un, klo[p]);       // synthkernel.c chiff_index, exactly
            float jit = 6.2831853f*hash01(idx);
            sm += (zr*cos(jit) - zi*sin(jit))*jfa[p];
        }
        float a = (m0[p] + (m1[p]-m0[p])*fr)*sm;
        L += a*panL[p]; R += a*panR[p];
    }
    accL[grp*frames+s] = L; accR[grp*frames+s] = R;
}
__kernel void reduce(const int frames, const int groups,
                     __global const float* accL, __global const float* accR,
                     __global float* outL, __global float* outR){
    int s = get_global_id(0); float L = 0.f, R = 0.f;
    for(int g=0; g<groups; g++){ L += accL[g*frames+s]; R += accR[g*frames+s]; }
    outL[s] = L; outR[s] = R;
}
"""


def build_cpu():
    d = tempfile.mkdtemp()
    src, lib = os.path.join(d, "bench.c"), os.path.join(d, "bench.so")
    open(src, "w").write(C_SRC)
    subprocess.check_call(["gcc", "-O3", "-march=native", "-ffast-math", "-fopenmp",
                           "-shared", "-fPIC", src, "-o", lib, "-lm"])
    dll = ctypes.CDLL(lib)
    dp, fp = ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_float)
    dll.render.argtypes = [ctypes.c_int, ctypes.c_int, dp, dp, fp, fp, fp, fp, fp, fp]
    dll.threads.argtypes = [ctypes.c_int]
    u64 = ctypes.POINTER(ctypes.c_uint64)
    dll.chiff_steps.argtypes = [ctypes.c_int, fp, ctypes.c_double, u64, u64]
    dll.render_attack.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_long, ctypes.c_double, dp, dp,
                                  fp, fp, fp, fp, fp, fp, fp, fp, fp, fp, fp]
    return dll


def scene(n, sr=44100.0, seed=1):
    """N partials as a section would have them: frequencies over 55 Hz-10 kHz,
    gains falling as 1/k, a random pan."""
    rng = np.random.default_rng(seed)
    f = 55.0 * 2 ** (rng.random(n) * 7.5)
    w = 2 * math.pi * f / sr
    g = (0.3 / np.sqrt(n) * rng.random(n)).astype(np.float32)
    pan = rng.random(n)
    return (w, g, (g * 0.98).astype(np.float32), np.cos(pan * math.pi / 2).astype(np.float32),
            np.sin(pan * math.pi / 2).astype(np.float32), rng.random(n) * 2 * math.pi)


def ptr(a, t):
    return a.ctypes.data_as(ctypes.POINTER(t))


GRAN = 100000.0


def chiff_steps(f, sr):
    """Each partial's chiff step f*GRAN/sr, split as the kernel splits it: the
    integer part, and the fraction scaled by 2^64 -- exact, a double having 53
    bits (synthkernel.c chiff_step)."""
    step = f.astype(np.float64) * GRAN / sr
    ip = np.floor(step)
    return ip.astype(np.uint64), np.array([int(math.ldexp(x, 64)) for x in step - ip], dtype=np.uint64)


def exact_index(n, khi, klo):
    """floor(n * step), in Python's exact integers, for checking."""
    return np.array([(n * int(h) + ((n * int(l)) >> 64)) & (2 ** 64 - 1) for h, l in zip(khi, klo)], dtype=np.uint64)


def attack(argv, dll, cl, ctx, q, prg, cores):
    """THE ATTACK: every partial in its chiff, through a moving ladder -- the
    case that overruns live (a six-note string chord's attack: 2.5 ms a block)."""
    frames = int(argv[argv.index("--frames") + 1]) if "--frames" in argv else 128
    blocks = int(argv[argv.index("--blocks") + 1]) if "--blocks" in argv else 400
    sr = 48000.0
    print("ATTACK: every partial chiffing, a ladder moving under it (median / 99th percentile, ms)")
    print("  partials   cpu 1 thread     cpu %d threads    gpu              gpu vs cpu   max diff   indices off" % cores)
    k_lad, k_att, k_red = cl.Kernel(prg, "ladder"), cl.Kernel(prg, "attack"), cl.Kernel(prg, "reduce")
    mf = cl.mem_flags
    for n in (1000, 2000, 4000, 8000, 16000):
        w, g0, g1, pl, pr, ph = scene(n)
        f = (w * sr / (2 * math.pi)).astype(np.float32)
        rng = np.random.default_rng(2)
        fc0 = np.full(n, 1800.0, np.float32); fc1 = np.full(n, 2400.0, np.float32)
        k = np.full(n, 1.5, np.float32); jfa = (0.2 + 0.2 * rng.random(n)).astype(np.float32)
        outL = np.zeros(frames, np.float32); outR = np.zeros(frames, np.float32)
        P = lambda a, t=ctypes.c_float: ptr(a, t)                  # noqa: E731
        times = {}
        for threads in (1, cores):
            dll.threads(threads); phase = ph.copy(); t = []
            for b in range(blocks):
                t0 = time.perf_counter()
                dll.render_attack(n, frames, b * frames, sr, P(phase, ctypes.c_double), P(w, ctypes.c_double),
                                  P(g0), P(g1), P(pl), P(pr), P(f), P(fc0), P(fc1), P(k), P(jfa), P(outL), P(outR))
                t.append(time.perf_counter() - t0)
                phase = np.mod(phase + w * frames, 2 * math.pi)
            times[threads] = (1000 * np.median(t[10:]), 1000 * np.percentile(t[10:], 99))
        dll.threads(cores)
        best = min(times.values())
        per = 64; groups = -(-n // per)
        rd = lambda a: cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=a)   # noqa: E731
        bw, bpl, bpr, bf, bfc0, bfc1, bk, bg0, bg1, bj = map(rd, (w.astype(np.float32), pl, pr, f, fc0, fc1, k, g0, g1, jfa))
        bph = cl.Buffer(ctx, mf.READ_ONLY, n * 4)
        khi, klo = np.empty(n, np.uint64), np.empty(n, np.uint64)
        dll.chiff_steps(n, P(f), sr, P(khi, ctypes.c_uint64), P(klo, ctypes.c_uint64))   # the C side's own split
        bkhi, bklo = rd(khi), rd(klo)
        bm0, bm1 = cl.Buffer(ctx, mf.READ_WRITE, n * 4), cl.Buffer(ctx, mf.READ_WRITE, n * 4)
        aL, aR = cl.Buffer(ctx, mf.READ_WRITE, groups * frames * 4), cl.Buffer(ctx, mf.READ_WRITE, groups * frames * 4)
        oL, oR = cl.Buffer(ctx, mf.WRITE_ONLY, frames * 4), cl.Buffer(ctx, mf.WRITE_ONLY, frames * 4)
        gL = np.empty(frames, np.float32); gR = np.empty(frames, np.float32)
        k_lad.set_args(np.int32(n), bf, bfc0, bfc1, bk, bg0, bg1, bm0, bm1)
        k_att.set_args(np.int32(n), np.int32(frames), np.int32(per), np.uint64(0), bph, bw, bm0, bm1, bpl, bpr, bkhi, bklo, bj, aL, aR)
        k_red.set_args(np.int32(frames), np.int32(groups), aL, aR, oL, oR)
        phase = ph.copy(); t = []; worst = 0.0; off = 0; total = 0
        for b in range(blocks):
            t0 = time.perf_counter()
            k_att.set_arg(3, np.uint64(b * frames))
            cl.enqueue_copy(q, bph, phase.astype(np.float32))
            cl.enqueue_nd_range_kernel(q, k_lad, (n,), None)
            cl.enqueue_nd_range_kernel(q, k_att, (frames, groups), None)
            cl.enqueue_nd_range_kernel(q, k_red, (frames,), None)
            cl.enqueue_copy(q, gL, oL); cl.enqueue_copy(q, gR, oR)
            q.finish()
            t.append(time.perf_counter() - t0)
            if b % 50 == 0:
                dll.render_attack(n, frames, b * frames, sr, P(phase, ctypes.c_double), P(w, ctypes.c_double),
                                  P(g0), P(g1), P(pl), P(pr), P(f), P(fc0), P(fc1), P(k), P(jfa), P(outL), P(outR))
                worst = max(worst, float(np.abs(gL - outL).max()), float(np.abs(gR - outR).max()))
                # the GPU's index arithmetic (64-bit, mul_hi) against exact integers
                for sm in (0, frames - 1):
                    nn = b * frames + sm
                    un = np.uint64(nn)
                    lo = klo.astype(object); hi_part = [(nn * int(l)) >> 64 for l in lo]
                    gpu_idx = (un * khi + np.array(hi_part, dtype=np.uint64))
                    off += int((gpu_idx != exact_index(nn, khi, klo)).sum()); total += n
            phase = np.mod(phase + w * frames, 2 * math.pi)
        gpu = (1000 * np.median(t[10:]), 1000 * np.percentile(t[10:], 99))
        print("  %6d     %.3f / %.3f    %.3f / %.3f    %.3f / %.3f    %4.2fx / %4.2fx   %.1e    %d of %d"
              % ((n,) + times[1] + times[cores] + gpu + (best[0] / gpu[0], best[1] / gpu[1], worst, off, total)))


def main(argv):
    frames = int(argv[argv.index("--frames") + 1]) if "--frames" in argv else 128
    blocks = int(argv[argv.index("--blocks") + 1]) if "--blocks" in argv else 400
    budget = frames / 48000.0 * 1000
    dll = build_cpu()
    try:
        import pyopencl as cl
        ctx = cl.create_some_context(interactive=False)
        dev = ctx.devices[0]
        q = cl.CommandQueue(ctx)
        prg = cl.Program(ctx, CL_SRC).build(options=["-cl-fast-relaxed-math"])
        # KERNEL OBJECTS MADE ONCE: prg.partials(...) builds a new one on every
        # call, and that -- not the launch, not the copies (14 us each) -- was
        # most of the 0.36 ms the first run measured as the GPU's fixed cost
        k_part, k_red = cl.Kernel(prg, "partials"), cl.Kernel(prg, "reduce")
        print("gpu: %s (%s), %d compute units, fp64 %s" % (
            dev.name, dev.platform.name, dev.max_compute_units,
            "yes" if "cl_khr_fp64" in dev.extensions else "no"))
    except Exception as e:                                    # noqa: BLE001
        cl = None
        print("gpu: none (%s) -- the cpu timings alone" % str(e).splitlines()[0][:100])
    print("budget per block: %.2f ms (%d frames at 48 kHz)\n" % (budget, frames))
    if "--attack" in argv:
        if cl is None:
            print("the attack needs the GPU"); return 1
        return attack(argv, dll, cl, ctx, q, prg, max(1, os.cpu_count() // 2)) or 0
    cores = max(1, os.cpu_count() // 2)            # one a physical core: hyperthreads share AVX units
    print("  (median / 99th percentile, ms: a block that misses its deadline is a click)")
    print("  partials   cpu 1 thread     cpu %d threads    gpu              gpu vs cpu   max diff" % cores)
    for n in (1000, 2000, 4000, 8000, 16000):
        w, g0, g1, pl, pr, ph = scene(n)
        outL = np.zeros(frames, np.float32); outR = np.zeros(frames, np.float32)
        times = {}
        for threads in (1, cores):
            dll.threads(threads)                               # OMP_NUM_THREADS is read only once
            phase = ph.copy(); t = []
            for b in range(blocks):
                t0 = time.perf_counter()
                dll.render(n, frames, ptr(phase, ctypes.c_double), ptr(w, ctypes.c_double),
                           ptr(g0, ctypes.c_float), ptr(g1, ctypes.c_float), ptr(pl, ctypes.c_float),
                           ptr(pr, ctypes.c_float), ptr(outL, ctypes.c_float), ptr(outR, ctypes.c_float))
                t.append(time.perf_counter() - t0)
                phase = np.mod(phase + w * frames, 2 * math.pi)    # the block-start anchor, in double
            times[threads] = (1000 * np.median(t[10:]), 1000 * np.percentile(t[10:], 99))
        cpu_best = min(times.values())
        dll.threads(cores)
        line = "  %6d     %.3f / %.3f    %.3f / %.3f" % ((n,) + times[1] + times[cores])
        if cl is not None:
            per = 64
            groups = -(-n // per)
            mf = cl.mem_flags
            buf = {k: cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=v)
                   for k, v in (("w", w.astype(np.float32)), ("g0", g0), ("g1", g1), ("pl", pl), ("pr", pr))}
            bph = cl.Buffer(ctx, mf.READ_ONLY, n * 4)
            aL = cl.Buffer(ctx, mf.READ_WRITE, groups * frames * 4)
            aR = cl.Buffer(ctx, mf.READ_WRITE, groups * frames * 4)
            oL = cl.Buffer(ctx, mf.WRITE_ONLY, frames * 4)
            oR = cl.Buffer(ctx, mf.WRITE_ONLY, frames * 4)
            gL = np.empty(frames, np.float32); gR = np.empty(frames, np.float32)
            phase = ph.copy(); t = []; worst = 0.0
            for b in range(blocks):
                t0 = time.perf_counter()
                cl.enqueue_copy(q, bph, phase.astype(np.float32))
                k_part.set_args(np.int32(n), np.int32(frames), np.int32(per), bph, buf["w"], buf["g0"],
                                buf["g1"], buf["pl"], buf["pr"], aL, aR)
                cl.enqueue_nd_range_kernel(q, k_part, (frames, groups), None)
                k_red.set_args(np.int32(frames), np.int32(groups), aL, aR, oL, oR)
                cl.enqueue_nd_range_kernel(q, k_red, (frames,), None)
                cl.enqueue_copy(q, gL, oL); cl.enqueue_copy(q, gR, oR)
                q.finish()
                t.append(time.perf_counter() - t0)
                if b % 50 == 0:                                # against the cpu, same block
                    dll.render(n, frames, ptr(phase, ctypes.c_double), ptr(w, ctypes.c_double),
                               ptr(g0, ctypes.c_float), ptr(g1, ctypes.c_float), ptr(pl, ctypes.c_float),
                               ptr(pr, ctypes.c_float), ptr(outL, ctypes.c_float), ptr(outR, ctypes.c_float))
                    worst = max(worst, float(np.abs(gL - outL).max()), float(np.abs(gR - outR).max()))
                phase = np.mod(phase + w * frames, 2 * math.pi)
            gpu = (1000 * np.median(t[10:]), 1000 * np.percentile(t[10:], 99))
            line += "    %.3f / %.3f    %4.2fx / %4.2fx   %.1e" % (gpu + (cpu_best[0] / gpu[0], cpu_best[1] / gpu[1], worst))
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
