// THE GPU'S SAMPLE PASS: synth_voice's sample loops, for one live block, as
// voice_sample (voicedesc.h) -- the same function the C reference runs.
//
// One work-item per (sample k, group of `per` descriptors): it adds up its
// group's partials at sample k. Samples are independent here because every
// phasor is evaluated directly rather than turned (voicedesc.h says why that
// holds to float precision), so the block's samples run side by side, and the
// lanes of a work-group read the same descriptors at once. Each work-group
// then sums its groups in local memory, and the host adds up the few that are
// left: a second kernel to do that was a launch dearer than the sum.
#include "voicedesc.h"

__kernel void voices(const int nd, const int per, const int frames, const int mg,
                     const ulong n0, const int send,
                     __global const vdesc* D, __global const vcell* C, __global const vsb* SB,
                     __global float* acc, __local float* red)
{
    int k = get_global_id(0), g = get_global_id(1);
    int lk = get_local_id(0), lg = get_local_id(1), LK = get_local_size(0), LG = get_local_size(1);
    int i0 = g*per, i1 = min(nd, i0+per);
    float invb = 1.f/(float)frames, invg = 1.f/(float)mg;
    float o[4] = {0.f, 0.f, 0.f, 0.f};
    if(k < frames)
        for(int i=i0; i<i1; i++)
            voice_sample(D+i, C, SB, k, n0+(ulong)k, invb, mg, invg, send, o);
    for(int c=0; c<4; c++) red[(c*LG+lg)*LK+lk] = o[c];
    barrier(CLK_LOCAL_MEM_FENCE);
    if(lg == 0 && k < frames){
        int NG = get_num_groups(1), wg = get_group_id(1);
        for(int c=0; c<4; c++){
            float s = 0.f;
            for(int j=0; j<LG; j++) s += red[(c*LG+j)*LK+lk];
            acc[(c*NG+wg)*frames+k] = s;
        }
    }
}

// A FILE'S WINDOW: many blocks in one launch, so the launch's fixed cost is
// paid once a window rather than once a block. Group g covers descriptors
// G[g].x .. G[g].y, all of one block, which starts G[g].z samples into the
// window; a work-group's LG groups are all of one block too (the host pads
// each block's groups to a multiple of LG), so its sum belongs to that block
// and the host adds the work-groups up block by block.
__kernel void voices_win(const int frames, const int mg, const ulong n0, const int send,
                         __global const int4* G,
                         __global const vdesc* D, __global const vcell* C, __global const vsb* SB,
                         __global float* acc, __local float* red)
{
    int k = get_global_id(0), g = get_global_id(1);
    int lk = get_local_id(0), lg = get_local_id(1), LK = get_local_size(0), LG = get_local_size(1);
    int4 gr = G[g];
    float invb = 1.f/(float)frames, invg = 1.f/(float)mg;
    float o[4] = {0.f, 0.f, 0.f, 0.f};
    if(k < frames)
        for(int i=gr.x; i<gr.y; i++)
            voice_sample(D+i, C, SB, k, n0+(ulong)(gr.z+k), invb, mg, invg, send, o);
    for(int c=0; c<4; c++) red[(c*LG+lg)*LK+lk] = o[c];
    barrier(CLK_LOCAL_MEM_FENCE);
    if(lg == 0 && k < frames){
        int NG = get_num_groups(1), wg = get_group_id(1);
        for(int c=0; c<4; c++){
            float s = 0.f;
            for(int j=0; j<LG; j++) s += red[(c*LG+j)*LK+lk];
            acc[(c*NG+wg)*frames+k] = s;
        }
    }
}

// the descriptor sizes as this compiler lays them out, against the host's
__kernel void sizes(__global int* out)
{
    out[0] = sizeof(vdesc); out[1] = sizeof(vcell); out[2] = sizeof(vsb);
}
