#!/usr/bin/env python3
"""Can the GPU render a live block of partials faster than the CPU?

    python3 examples/gpu_bench.py [--frames 128] [--blocks 400]

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
void threads(int n){ omp_set_num_threads(n); }
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
        print("gpu: %s (%s), %d compute units, fp64 %s" % (
            dev.name, dev.platform.name, dev.max_compute_units,
            "yes" if "cl_khr_fp64" in dev.extensions else "no"))
    except Exception as e:                                    # noqa: BLE001
        cl = None
        print("gpu: none (%s) -- the cpu timings alone" % str(e).splitlines()[0][:100])
    print("budget per block: %.2f ms (%d frames at 48 kHz)\n" % (budget, frames))
    cores = max(1, os.cpu_count() // 2)            # one a physical core: hyperthreads share AVX units
    print("  partials   cpu 1 thread   cpu %d threads   gpu            gpu vs cpu best   max diff" % cores)
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
            times[threads] = 1000 * np.median(t[10:])
        cpu_best = min(times.values())
        dll.threads(cores)
        line = "  %6d     %7.3f ms     %7.3f ms" % (n, times[1], times[cores])
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
                prg.partials(q, (frames, groups), None, np.int32(n), np.int32(frames), np.int32(per),
                             bph, buf["w"], buf["g0"], buf["g1"], buf["pl"], buf["pr"], aL, aR)
                prg.reduce(q, (frames,), None, np.int32(frames), np.int32(groups), aL, aR, oL, oR)
                cl.enqueue_copy(q, gL, oL); cl.enqueue_copy(q, gR, oR)
                q.finish()
                t.append(time.perf_counter() - t0)
                if b % 50 == 0:                                # against the cpu, same block
                    dll.render(n, frames, ptr(phase, ctypes.c_double), ptr(w, ctypes.c_double),
                               ptr(g0, ctypes.c_float), ptr(g1, ctypes.c_float), ptr(pl, ctypes.c_float),
                               ptr(pr, ctypes.c_float), ptr(outL, ctypes.c_float), ptr(outR, ctypes.c_float))
                    worst = max(worst, float(np.abs(gL - outL).max()), float(np.abs(gR - outR).max()))
                phase = np.mod(phase + w * frames, 2 * math.pi)
            gpu = 1000 * np.median(t[10:])
            line += "     %7.3f ms     %5.2fx            %.1e" % (gpu, cpu_best / gpu, worst)
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
