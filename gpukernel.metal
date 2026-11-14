// THE GPU'S SAMPLE PASS ON METAL (macOS, and iOS, which has no OpenCL):
// gpukernel.cl's two kernels, the same voice_sample (voicedesc.h, its Metal
// branch), the same work-groups -- LK samples by LG groups, each group's
// descriptors summed per sample, each threadgroup's groups summed in its
// memory, the host adding the threadgroups up. native/gpu_metal.mm compiles
// this at run time (no Xcode: the Command Line Tools have no offline Metal
// compiler), voicedesc.h's text put in place of its #include.
#include <metal_stdlib>
using namespace metal;
#include "voicedesc.h"

// the scalars, as gpukernel.cl takes them one by one
struct vargs { int nd, per, frames, mg; ulong n0; int send, pad; };

constant int RED = 4 * 8 * 16;      // (4 channels by LG by LK: the threadgroup's sums)

kernel void voices(constant vargs& A [[buffer(0)]], device const vdesc* D [[buffer(1)]],
                   device const vcell* C [[buffer(2)]], device const vsb* SB [[buffer(3)]],
                   device float* acc [[buffer(4)]],
                   uint2 gid [[thread_position_in_grid]], uint2 lid [[thread_position_in_threadgroup]],
                   uint2 lsz [[threads_per_threadgroup]], uint2 tg [[threadgroup_position_in_grid]],
                   uint2 ntg [[threadgroups_per_grid]])
{
    threadgroup float red[RED];
    int k = gid.x, g = gid.y, lk = lid.x, lg = lid.y, LK = lsz.x, LG = lsz.y;
    int i0 = g*A.per, i1 = min(A.nd, i0+A.per);
    float invb = 1.f/(float)A.frames, invg = 1.f/(float)A.mg;
    float o[4] = {0.f, 0.f, 0.f, 0.f};
    if(k < A.frames)
        for(int i=i0; i<i1; i++)
            voice_sample(D+i, C, SB, k, A.n0+(ulong)k, invb, A.mg, invg, A.send, o);
    for(int c=0; c<4; c++) red[(c*LG+lg)*LK+lk] = o[c];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if(lg == 0 && k < A.frames){
        int NG = ntg.y, wg = tg.y;
        for(int c=0; c<4; c++){
            float s = 0.f;
            for(int j=0; j<LG; j++) s += red[(c*LG+j)*LK+lk];
            acc[(c*NG+wg)*A.frames+k] = s;
        }
    }
}

// A FILE'S WINDOW (gpukernel.cl's voices_win): many blocks in one launch
kernel void voices_win(constant vargs& A [[buffer(0)]], device const int4* G [[buffer(1)]],
                       device const vdesc* D [[buffer(2)]], device const vcell* C [[buffer(3)]],
                       device const vsb* SB [[buffer(4)]], device float* acc [[buffer(5)]],
                       uint2 gid [[thread_position_in_grid]], uint2 lid [[thread_position_in_threadgroup]],
                       uint2 lsz [[threads_per_threadgroup]], uint2 tg [[threadgroup_position_in_grid]],
                       uint2 ntg [[threadgroups_per_grid]])
{
    threadgroup float red[RED];
    int k = gid.x, g = gid.y, lk = lid.x, lg = lid.y, LK = lsz.x, LG = lsz.y;
    int4 gr = G[g];
    float invb = 1.f/(float)A.frames, invg = 1.f/(float)A.mg;
    float o[4] = {0.f, 0.f, 0.f, 0.f};
    if(k < A.frames)
        for(int i=gr.x; i<gr.y; i++)
            voice_sample(D+i, C, SB, k, A.n0+(ulong)(gr.z+k), invb, A.mg, invg, A.send, o);
    for(int c=0; c<4; c++) red[(c*LG+lg)*LK+lk] = o[c];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if(lg == 0 && k < A.frames){
        int NG = ntg.y, wg = tg.y;
        for(int c=0; c<4; c++){
            float s = 0.f;
            for(int j=0; j<LG; j++) s += red[(c*LG+j)*LK+lk];
            acc[(c*NG+wg)*A.frames+k] = s;
        }
    }
}

// the descriptor sizes as this compiler lays them out, against the host's
kernel void sizes(device int* out [[buffer(0)]])
{
    out[0] = sizeof(vdesc); out[1] = sizeof(vcell); out[2] = sizeof(vsb);
}
