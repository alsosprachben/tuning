// synth_voice's per-partial setup, shared verbatim with voice_block (see
// the note above voice_block in synthkernel.c). In scope: p, cs, ce, and
// the kernel's arguments; `continue` skips the partial.
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
