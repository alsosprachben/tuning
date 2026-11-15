// synth_voice's body, whole: synth_voice and synth_voice_lobe (the
// Leslie's build, -DLESLIE_KERNEL) are this text, the second with SV_LOBE
// defined. A separate function, not a branch in the one: a rotor-row test
// inside synth_voice's block loop moved 110 of 167 corpus files by an ULP
// (-ffast-math; the kernel-edits rule). In scope: synth_voice's arguments.
    // THE SEND BUS, for the live room. When outSL is non-NULL every partial is
    // ALSO accumulated into outSL/outSR scaled by sendW[p] -- its channel's
    // CC91 distance multiple -- and that pair feeds the room's tail. The
    // oscillator is computed once; only the accumulation doubles. NULL (the
    // file renderer, which makes its send by a second render) touches nothing,
    // so outL/outR are bit-identical to before.
    long nchunks=(winlen+CHUNK-1)/CHUNK;
    //
    // ONE CHUNK -- A LIVE BLOCK -- NEVER ENTERS OPENMP: there is nothing to
    // share, and libgomp builds and frees a team for every parallel region,
    // even of one thread or under a false if() -- an allocation on the
    // audio thread a call (tests/live/alloc_check.py). The same chunk text
    // either way (voice_chunk.inc); each chunk writes only its own samples.
    if(nchunks>1){
        #pragma omp parallel for schedule(dynamic)
        for(long c=0;c<nchunks;c++){
            #include "voice_chunk.inc"
        }
    }else{
        for(long c=0;c<nchunks;c++){
            #include "voice_chunk.inc"
        }
    }
