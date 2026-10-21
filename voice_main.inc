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
    #pragma omp parallel for schedule(dynamic)
    for(long c=0;c<nchunks;c++){
        long cs=n0+c*CHUNK, ce=cs+CHUNK; if(ce>n0+winlen)ce=n0+winlen;
        for(int p=0;p<P;p++){
            #include "voice_partial.inc"
            long bstart=(cs>a?cs:a)/BLK, bend=(ce<zend?ce:zend+1)/BLK+1;
            for(long b=bstart;b<bend;b++){
                #include "voice_block.inc"
                // EVERY OTHER VOICE takes the loop it always took, spelled as it
                // always was: -ffast-math contracts a restructured expression
                // differently, and a render moves by an ULP. A MOOG runs the
                // same body over grid cells, each interpolated between its own
                // two grid gains; the phasor runs on across them untouched.
                // THE KNEE (voice_block.inc): the attack's own ramp, from its
                // onset to its end, before the block's line takes over -- a loop
                // of its own, so the one below is spelled as it always was
#ifdef SV_LOBE
                // A ROTOR ROW (leslie_grid): its own loop, its level swung by
                // the lobe; every other row goes on as it always went
                if(lsr && lsr[p]>=0 && !ftr && chBW[p]>=0.f){
                    float lg[65];
                    leslie_grid(LANG, lgn, lsr[p], lph[p], lfl[p], lsh[p], lnm[p], bs0, mg, BLK/mg+1, lg);
                    leslie_samples(ns, ne, n0, bs0, invb, mg, lg, kAl, kNl, kgL, kAr, kNr, kgR,
                                   mL0, mL1, mR0, mR1, aL, aR, zrL, ziL, zrR, ziR, rr, ri,
                                   jfa, chk_hi, chk_lo, cc, outL, outR, outSL, outSR, swp);
                    continue;
                }
#endif
                if(kAl!=kAr || kNl!=kNr){
                    // EACH EAR ITS OWN ONSET (voice_block.inc): out of line
                    ns=ear_knees(ns, ne, n0, bs0, invb, kAl, kNl, kgL, kAr, kNr, kgR,
                                 mL0, mL1, mR0, mR1, aL, aR, &zrL, &ziL, &zrR, &ziR, rr, ri,
                                 jfa, chk_hi, chk_lo, cc, outL, outR, outSL, outSR, swp);
                } else
                if(kN>ns){
                    long ke=kN<ne?kN:ne; float ik=1.f/(float)(kN-kA);
                    for(long n=ns;n<ke;n++){
                        float r=(float)(n-kA)*ik; float mL=kgL*r*aL, mR=kgR*r*aR;
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
                    ns=ke;
                }
                if(!ftr && chBW[p]<0.f){
                #include "voice_noise.inc"
                } else if(!ftr){
                for(long n=ns;n<ne;n++){
                    float t=(float)(n-bs0)*invb; float mL=(mL0+(mL1-mL0)*t)*aL, mR=(mR0+(mR1-mR0)*t)*aR;
                    float sL=zrL, sR=zrR;
                    if(jfa>0.f){
                        // THE WASH'S BANDWIDTH. The phase is redrawn at nf*gran per
                        // second, so gran IS the noise's bandwidth as a fraction of
                        // the partial's own frequency: at RAND_GRAN it is redrawn
                        // every sample and the noise is white, spread flat over the
                        // whole spectrum no matter which partial it came from. That
                        // is why turning the wash up far enough to fill between a
                        // cymbal's modes also fills the notches BETWEEN its bands.
                        // A smaller gran keeps each partial's noise around the
                        // partial, so the wash inherits the plate's own shape.
                        // the index floor(n * nf * gran / SRATE), exactly (chiff_index)
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
                } else {
                #include "voice_moog.inc"
                for(int cl=0; cl<BLK/mg; cl++){
                #include "voice_cell.inc"
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
                        uint64_t ui=chiff_index(n, nk_hi, nk_lo);
                        double uf=(double)((uint64_t)n*nk_lo)*(1.0/18446744073709551616.0);
                        if((long long)ui!=nui){   // a new draw: hash only then
                            nui=(long long)ui; nh0=hash01(nseed+ui);
                            double h1=hash01(nseed+ui+1);
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
                        // THE WASH'S BANDWIDTH. The phase is redrawn at nf*gran per
                        // second, so gran IS the noise's bandwidth as a fraction of
                        // the partial's own frequency: at RAND_GRAN it is redrawn
                        // every sample and the noise is white, spread flat over the
                        // whole spectrum no matter which partial it came from. That
                        // is why turning the wash up far enough to fill between a
                        // cymbal's modes also fills the notches BETWEEN its bands.
                        // A smaller gran keeps each partial's noise around the
                        // partial, so the wash inherits the plate's own shape.
                        // the index floor(n * nf * gran / SRATE), exactly (chiff_index)
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
                }
            }
            #undef AMP
        }
    }
