// voice_block's items (synthkernel.c includes it twice: voice_block's
// OpenMP team shares them -- Python's -- and, after voice_team_set, every
// thread of the native engine's own team). Items are taken GRAB at a
// time from the shared count *vb_nextp; cells, sidebands and the overflow
// flag by the shared counts vb_shp[0..2]. In scope: voice_block's arguments,
// tot, vb_shp, vb_nextp, vb_grab.
    for(;;){
    long it0=__atomic_fetch_add(vb_nextp, (long)vb_grab, __ATOMIC_RELAXED);
    if(it0>=tot) break;
    long it1=it0+vb_grab<tot ? it0+vb_grab : tot;
    for(long it=it0; it<it1; it++){
        int ii=(int)(it%nact);
        long bn0=n0+(it/nact)*(long)BLK;
        // the fragments' names for the window: one block, one chunk
        const long cs=bn0, ce=bn0+BLK;
        int p=(int)idx[ii];
        vdesc* d=D+it;
        d->kind=0;
        #include "voice_partial.inc"
        {
        long b=bn0/BLK;
#ifdef DAMP_KERNEL
        // a half-pedalled row: its damping as its BLrow, this block's two
        // edges (synth_voice_damp's, voice_main.inc)
        float dsc[2];
        if(vd_drow && vd_drow[p]>=0){
            long bb=b<nblk?b:nblk-1;
            long t=vd_drow[p];
            dsc[0]=(BLrow?BLrow[bb]:1.f)*expf(-vd_dwt[p]*vd_track(t, bb));
            dsc[1]=(BLrow?BLrow[bb+1]:1.f)*expf(-vd_dwt[p]*vd_track(t, bb+1));
            BLrow=dsc-bb;
        }
#endif
#ifdef MOOGX_KERNEL
        const float* MX=vm_MX;
#define MOOGX_PASS
#endif
        #include "voice_block.inc"
#ifdef MOOGX_KERNEL
#undef MOOGX_PASS
#endif
        d->ns=(int)(ns-bn0); d->ne=(int)(ne-bn0);
        d->zLr=zrL; d->zLi=ziL; d->zRr=zrR; d->zRi=ziR; d->winst=winst;
        d->mL0=mL0; d->mL1=mL1; d->mR0=mR0; d->mR1=mR1;
        // A FAST EXPONENTIAL (xdec_decide): its rate, and its anchors in the line's place
        {
            xdecs X=xdec_decide(!ftr && !BLrow && !Grow && sl<=0.f && af<=0.f,
                                a, bs0, (long)BLK, dL, dR, fadeS[p], invf, invr, off, lr, chBW[p]);
            d->xr=X.xr;
            if(X.xr!=0.f){ d->mL0=X.gL; d->mR0=X.gR; d->mL1=X.kL; d->mR1=X.kR;
                // no knee: its fade drawn from the onset (voice_main.inc's
                // XDEC_PASS); a noise row never had one
                kNl=kAl=kNr=kAr=0;
                // from the onset, not the strike's step (xdec_block): the
                // carrier wound back to the new start, and the V_SUB anchors
                // below counted from it
                long on=a+(long)ceilf(dL<dR?dL:dR), s0=on>bn0?on:bn0;
                if(s0<ns){
                    double back=(double)winst*(double)(ns-s0);
                    phL-=back; phR-=back; ns=s0;
                    d->zLr=(float)cos(phL); d->zLi=(float)sin(phL);
                    d->zRr=(float)cos(phR); d->zRi=(float)sin(phR);
                    d->ns=(int)(ns-bn0);
                } }
        }
        d->aL=aL; d->aR=aR; d->aLp=aLp; d->aRp=aRp;
        d->jfa=jfa; d->cc=cc; d->swp=swp;
        // the knee: its sample from the block's start (0, none), its gains
        d->kn=kNl>ns ? (int)(kNl-bn0) : 0; d->kgL=kgL; d->kgR=kgR;
        d->ka=kNl>ns ? (int)(kAl-bn0) : 0;
        d->knR=kNr>ns ? (int)(kNr-bn0) : 0;
        d->kaR=kNr>ns ? (int)(kAr-bn0) : 0; d->kpad=0;
        // a fast exponential's onset fade, in samples (voicedesc.h)
        if(d->xr!=0.f) d->kpad=(int)fadeS[p];
        // the carrier at each V_SUB samples into the block, in double, as the
        // phasor's own steps of winst place it (voicedesc.h)
        for(int j=1;j<4;j++){
            if(ns+(long)j*V_SUB < ne){
                double el=(double)winst*(double)(j*V_SUB);
                d->za[4*(j-1)]=(float)cos(phL+el); d->za[4*(j-1)+1]=(float)sin(phL+el);
                d->za[4*(j-1)+2]=(float)cos(phR+el); d->za[4*(j-1)+3]=(float)sin(phR+el);
            } else for(int q=0;q<4;q++) d->za[4*(j-1)+q]=0.f;
        }
        d->chk_hi=chk_hi; d->chk_lo=chk_lo;
        d->flags=0; d->cell=0; d->nk_hi=d->nk_lo=d->nseed=0;
        (void)rr; (void)ri; (void)invb;
        if(!ftr){
            // an ordinary noise band (voice_noise.inc): the Moog's draw, seeded alike
            if(chBW[p]<0.f){
                uint64_t gh=0, gl=0;
                chiff_step((double)nf*(double)(-chBW[p])/SRATE_D, &gh, &gl);
                d->flags=VD_NOISE; d->nk_hi=gh; d->nk_lo=gl;
                d->jfa=0.f;      // a noise band has no chiff of its own (voice_noise.inc)
                d->nseed=(uint64_t)a*0x9E3779B97F4A7C15ULL + (uint64_t)(long long)((double)nf*1000.0);
            }
            // a rotor row: its lobe at the block's grid points (leslie_grid)
            if(lsr && (lsr[p]>=0 || (fsr && fsr[p]>=0)) && chBW[p]>=0.f && BLK/mg+1<=VD_LG){
                d->flags|=VD_LESLIE;
                if(lsr[p]>=0 && lsh[p]<0.f){
                    // A SPECTRA-TONE's ROW (cone_grid, lsh -1 marks it): its gain
                    // complex at the grid points, lg + i li; a moving filter's
                    // level on both, as the CPU's cone branch has it
                    d->flags|=VD_CONE;
                    cone_grid(LANG, lgn, lsr[p], lph[p], lfl[p], nf, bn0, mg, BLK/mg+1, d->lg, d->li);
                    if(fsr && fsr[p]>=0){
                        float lgc[VD_LG];
                        for(int j=0;j<BLK/mg+1;j++) lgc[j]=1.f;
                        filter_grid(FCT, fgn, fsr[p], fty[p], fpa[p], fpb[p], fpc[p], nf, bn0, mg, BLK/mg+1, lgc);
                        for(int j=0;j<BLK/mg+1;j++){ d->lg[j]*=lgc[j]; d->li[j]*=lgc[j]; }
                    }
                } else {
                if(lsr[p]>=0)
                    leslie_grid(LANG, lgn, lsr[p], lph[p], lfl[p], lsh[p], lnm[p], bn0, mg, BLK/mg+1, d->lg);
                else
                    for(int j=0;j<BLK/mg+1;j++) d->lg[j]=1.f;
                if(fsr && fsr[p]>=0)       /* ...and a moving filter (filter_grid) */
                    filter_grid(FCT, fgn, fsr[p], fty[p], fpa[p], fpb[p], fpc[p], nf, bn0, mg, BLK/mg+1, d->lg);
                }
            }
            d->kind=1; continue;
        }
        #include "voice_moog.inc"
        (void)nui; (void)nh0; (void)ndh;
        // a Moog row on a rotor or a moving filter: its grid gains times them
        if(lsr && (lsr[p]>=0 || (fsr && fsr[p]>=0))){
            float lgm[65]; int njm=BLK/mg+1;
            if(lsr[p]>=0 && lsh[p]>=0.f)    /* (a Moog on a Spectra-Tone: not turned, as the cone build's) */
                leslie_grid(LANG, lgn, lsr[p], lph[p], lfl[p], lsh[p], lnm[p], bn0, mg, njm, lgm);
            else
                for(int j=0;j<njm;j++) lgm[j]=1.f;
            if(fsr && fsr[p]>=0)
                filter_grid(FCT, fgn, fsr[p], fty[p], fpa[p], fpb[p], fpc[p], nf, bn0, mg, njm, lgm);
            for(int j=0;j<njm;j++){ gLm[j]*=lgm[j]; gRm[j]*=lgm[j]; }
        }
        // (cbase, not c0: the cell fragment's c0 is the cell's first sample)
        int ncl=BLK/mg;
        int cbase=__atomic_fetch_add(&vb_shp[0], ncl, __ATOMIC_RELAXED);
        if(cbase+ncl>ccap){ __atomic_store_n(&vb_shp[2], 1, __ATOMIC_RELAXED); continue; }
        int fl=0;
        if(noiz){ fl|=VD_NOISE; d->nk_hi=nk_hi; d->nk_lo=nk_lo; d->nseed=nseed; }
        if(shm) fl|=VD_SHAPE;
        if(fms) fl|=VD_FMS; else if(fmo) fl|=VD_FMO;
        if(pm) fl|=VD_PM;
        for(int cl=0; cl<ncl; cl++) memset(C+cbase+cl, 0, sizeof(vcell));
        for(int cl=0; cl<BLK/mg; cl++){
        #include "voice_cell.inc"
        vcell* v=C+cbase+cl;
        v->s0=(int)(s0-bn0); v->s1=(int)(s1-bn0);
        v->gL0=a0L; v->gL1=a1L; v->gR0=a0R; v->gR1=a1R;
        if(shm){ v->cRe0=cRe[cl]; v->cIm0=cIm[cl]; v->cRe1=cRe[cl+1]; v->cIm1=cIm[cl+1]; }
        if(pm){ v->zLr=zrL; v->zLi=ziL; v->zRr=zrR; v->zRi=ziR; v->wc=atan2f(ri, rr); }
        if(fmo && !fms){
            v->z1r=z1r; v->z1i=z1i; v->th1=atan2f(r1i, r1r); v->fmkI=(float)fmk*fmI;
            for(int j=0;j<2*FM_J;j++) v->B[j]=ftr[14+j];
        }
        if(fms && nsb>0){
            int s=__atomic_fetch_add(&vb_shp[1], nsb, __ATOMIC_RELAXED);
            if(s+nsb>sbcap){ __atomic_store_n(&vb_shp[2], 1, __ATOMIC_RELAXED); continue; }
            v->sb=s; v->nsb=nsb;
            for(int i=0;i<nsb;i++){
                vsb* q=SB+s+i;
                q->g0r=g0r[slo+i]; q->g0i=g0i[slo+i]; q->dgr=dgr[slo+i]; q->dgi=dgi[slo+i];
                q->pzr=pzr[i]; q->pzi=pzi[i]; q->th=atan2f(pri[i], prr[i]); q->pad=0.f;
            }
        }
        }
        d->flags=fl; d->cell=cbase; d->kind=2;
        }
        #undef AMP
    }
    }
