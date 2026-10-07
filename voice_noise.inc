// AN ORDINARY ROW THAT IS A NOISE BAND: a negative wash bandwidth, outside the
// Moog (whose noise is voice_moog.inc's). The same band, made the same way --
// the carrier's phase moved to a new random value nf*(-cbw) times a second,
// joined to the next draw the short way round, no carrier left -- so a pipe's
// wind or anything else that is noise and not a tone can be a row like any
// other, with its own envelope, onset and damper. Its own loop, not a branch
// in the ordinary one: that loop is spelled as it always was, and -ffast-math
// would round a restructured one differently.
                {
                double nrate=(double)nf*(double)(-chBW[p]);
                uint64_t nseed=(uint64_t)a*0x9E3779B97F4A7C15ULL + (uint64_t)(long long)((double)nf*1000.0);
                uint64_t nk_hi=0, nk_lo=0;
                chiff_step(nrate/SRATE_D, &nk_hi, &nk_lo);
                long long nui=-1; double nh0=0.0, ndh=0.0;
                for(long n=ns;n<ne;n++){
                    float t=(float)(n-bs0)*invb; float mL=(mL0+(mL1-mL0)*t)*aL, mR=(mR0+(mR1-mR0)*t)*aR;
                    uint64_t ui=chiff_index(n, nk_hi, nk_lo);
                    double uf=(double)((uint64_t)n*nk_lo)*(1.0/18446744073709551616.0);
                    if((long long)ui!=nui){
                        nui=(long long)ui; nh0=hash01(nseed+ui);
                        double h1=hash01(nseed+ui+1);
                        ndh=h1-nh0; ndh-=floor(ndh+0.5);
                    }
                    float jn=6.2831853f*(float)(nh0+ndh*uf);
                    float cn=cosf(jn), sn=sinf(jn);
                    float sL=zrL*cn-ziL*sn, sR=zrR*cn-ziR*sn;
                    outL[n-n0]+=mL*sL; outR[n-n0]+=mR*sR;
                    if(outSL){ outSL[n-n0]+=mL*sL*swp; outSR[n-n0]+=mR*sR*swp; }
                    float tmp; tmp=zrL*rr-ziL*ri; ziL=zrL*ri+ziL*rr; zrL=tmp;
                    tmp=zrR*rr-ziR*ri; ziR=zrR*ri+ziR*rr; zrR=tmp;
                }
                }
