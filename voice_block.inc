// synth_voice's per-block setup -- amplitude, chiff fade, vibrato, bends,
// the Moog grid, the phasor's anchor -- shared verbatim with voice_block.
// In scope: voice_partial.inc's names, and b; `continue` skips the block.
                // Amp is interpolated across the FULL block [bs0,bs1); only the
                // [ns,ne) slice inside this chunk/window is written. Using the true
                // block bounds (not the clipped ones) makes the result independent
                // of chunking/windowing -- a streamed window == the full render.
                long bs0=b*BLK, bs1=bs0+BLK;
                long ns=bs0<cs?cs:bs0, ne=bs1>ce?ce:bs1; if(ns>=ne)continue;
                // Spelled exactly as it always was, and for every partial: moved
                // inside a branch, gcc vectorised the four evaluations another way
                // and the organ's swell moved by an ULP. A Moog ignores them.
                float mL0=AMP(bs0,b,dL), mL1=AMP(bs1,b,dL), mR0=AMP(bs0,b,dR), mR1=AMP(bs1,b,dR);
                if(BLrow){ long bb=b<nblk?b:nblk-1; float w0=BLrow[bb], w1=BLrow[bb+1];
                    mL0*=w0; mR0*=w0; mL1*=w1; mR1*=w1; }
                // THE ONSET BLOCK STARTS AT THE ONSET. The amplitude is a line
                // across each block, and in the block a partial starts in that
                // line ran from the block's START: every onset was smeared over
                // up to a block (512 samples, 10.7 ms), sounding before its note
                // did. A ringing drum hides that; a snare, most of it gone in
                // 50 ms, became a swell -- Ben: "the old one still sounds way
                // more like a snare". Now the line starts at the onset sample
                // and nothing is written before it. An attack that ends inside
                // this block starts halfway through it, at the level it ends
                // on (sharp, as a strike is); a longer one ramps from zero, from
                // the onset rather than the block's start. The line is carried
                // as the two numbers the block already had -- a start sample
                // (ns) and a start gain (mL0, re-aimed so the line through the
                // block's end passes through it) -- so the live descriptors and
                // the GPU follow without change.
                //
                // ...BUT A STEP IS ONLY A STRIKE. An attack of several ms (the
                // upright's 4-8, the grand's 3) made a step too, wherever it fit
                // inside its first block -- so the same key clicked or did not by
                // where its onset fell: the grand's E5 read -21 dB of early treble
                // at most positions and -50 at the rest (Ben: "a little clicky,
                // but only on some of the attacks"). Past KNEE_MIN the block has
                // a KNEE: a ramp from zero at the onset to the attack's own level
                // at its end (kN, kgL/kgR), then the line as before. A strike
                // (KNEE_MIN or less: a kit's sticks, beaters and hands) keeps its step.
                // Not on a noise row or a Moog partial, whose loops are their own.
                long kN=0, kA=0; float kgL=0.f, kgR=0.f;
                {
                    float dmin=fminf(dL,dR);
                    long sA=a+(long)ceilf(dmin);
                    if(sA>bs0 && sA<bs1){
                        long sF=sA+(long)fadeS[p];
                        int knee = sF<bs1 && fadeS[p]>KNEE_MIN && !ftr && chBW[p]>=0.f;
                        long s0=sF<bs1 ? (knee ? sF : sA+(long)(0.5f*fadeS[p])) : sA;
                        if(s0>=bs1) s0=bs1-1;
                        float g0L=0.f, g0R=0.f;
                        if(sF<bs1){
                            g0L=AMP(sF,b,dL); g0R=AMP(sF,b,dR);
                            if(BLrow){ long bb=b<nblk?b:nblk-1;
                                float wq=BLrow[bb]+(BLrow[bb+1]-BLrow[bb])*(float)(sF-bs0)/(float)BLK;
                                g0L*=wq; g0R*=wq; }
                        }
                        float kq=(float)BLK/(float)(bs1-s0);
                        mL0=mL1-(mL1-g0L)*kq; mR0=mR1-(mR1-g0R)*kq;
                        if(knee){
                            // the line from the knee on; before it, the ramp
                            kN=sF; kA=sA; kgL=g0L; kgR=g0R;
                            if(ns<sA) ns=sA;
                        } else if(ns<s0) ns=s0;
                        if(ns>=ne) continue;
                    }
                }
                // ...AND A GROWTH'S BLOCK ENDS AT ITS CUT, the onset's rule
                // mirrored. Only a partial that GROWS (a negative decay rate: a
                // note played backwards, blockrender._reverse_partial) peaks at
                // its release, and a release a millisecond long inside a block
                // left the line running from the block's start to zero at its
                // end, past the peak -- the reversed crash's arrival came out
                // 5-7 dB short. So where such a release ends inside the block,
                // the line runs to the level the release starts from, halfway
                // through it, and nothing is written after. Every other partial
                // is untouched: none has a negative rate.
                if(lr<0.f){
                    float dmin=fminf(dL,dR);
                    long sR=off+(long)ceilf(dmin), sE=sR+(long)relS[p];
                    if(sR>bs0 && sR<bs1 && sE<=bs1){
                        long s1=sR+(long)(0.5f*relS[p]);
                        if(s1<=bs0) s1=bs0+1;
                        float g1L=AMP(sR,b,dL), g1R=AMP(sR,b,dR);
                        if(BLrow){ long bb=b<nblk?b:nblk-1;
                            float wq=BLrow[bb]+(BLrow[bb+1]-BLrow[bb])*(float)(sR-bs0)/(float)BLK;
                            g1L*=wq; g1R*=wq; }
                        float kq=(float)BLK/(float)(s1-bs0);
                        mL1=mL0+(g1L-mL0)*kq; mR1=mR0+(g1R-mR0)*kq;
                        if(ne>s1) ne=s1;
                        if(ns>=ne) continue;
                    }
                }
                if(!ftr && mL0<=1e-7f && mL1<=1e-7f && mR0<=1e-7f && mR1<=1e-7f) continue;
                // chiff fade for this block (state: attack/sustain/release). The
                // attack chiff rides chiffS -- its OWN short, capped width, NOT the
                // slow speech fade fadeS -- so a big pipe chuffs briefly, no hiss.
                float jf=0.f; long mid=bs0+BLK/2; float invch=1.f/chiffS[p];
                if(cv>0.f){
                    // THE SUSTAINED WASH IS A FLOOR UNDER THE ATTACK HUMP, not a
                    // level the hump drops to zero before reaching. The hump is
                    // r*(1-r): it peaks at 0.25 and returns to 0 at chiffS, and
                    // the sustain then began at sj -- so any voice whose sj is
                    // large compared with 0.25 STEPPED UP when its hump ended.
                    // The floor RISES with the hump's own progress (sj*s), so the
                    // attack is untouched at t=0 and the two meet exactly where the
                    // hump ends. A flat floor from t=0 would fix the step but raise
                    // the attack peak, which clipped the triangle and the cabasa.
                    // Inaudible where chiffS is a few ms, which is most voices;
                    // on the chinese cymbal, chiffS 0.29 s against sj 1.0, it is
                    // a burst of noise arriving a quarter second after the strike.
                    // Ben: "sounding fine to start, then after a quarter second
                    // or so, it suddenly adds noise."
                    if(mid < a+(long)chiffS[p]){ float s=sstep((float)(mid-a)*invch); float r=sqrtf(s); jf=fmaxf(r*(1.f-r), sj*s); }
                    // AND THE SAME ON THE WAY OUT. The attack floor rises so the
                    // hump does not step up when it ends; the release had no floor
                    // at all, so jf fell from sj to ZERO in one block at note-off
                    // and humped back up -- a step in the noise at every note end.
                    // Inaudible while the voice is buried; a solo line placed
                    // forward puts it in the open, which is where Ben heard it:
                    // "subtle clicking each note... an edge case involving attack
                    // or release." The floor now FALLS as sj*(1-s), mirroring the
                    // attack, so it leaves the sustain continuously and reaches
                    // zero exactly when the release does.
                    else if(mid >= off){ float s=sstep((float)(mid-off)*invr); float r=sqrtf(s); jf=fmaxf(r*(1.f-r)*crl, sj*(1.f-s)); }
                    else jf=sj;
                }
                // Tension bend (piano strike): frequency starts sharp by
                // tbav*e^{-t/tau} and settles, cut off at tcut. Phase is the exact
                // integral to the block start; the recurrence uses the block-start
                // instantaneous frequency. tbav==0 -> plain constant-frequency phasor.
                // A partial can be BOTH vibrating and speaking. These two used to
                // ASSIGN bph and winst, so whichever ran second threw the other
                // away: mode lock is a driven air column (brass, mode_lock_spread
                // = 0.003) and it silently deleted the mod wheel's vibrato for the
                // whole life of the note -- after the transient it wrote back a
                // plain w. Ben, playing: "the modulation value keeps getting
                // pulled back to 0 ... on violin it is persisting, but not
                // trumpet." Violin has mode_lock_spread = 0 and never entered the
                // branch. They compose now: the phases add and the frequency
                // factors multiply.
                double bph=0.0, vibfac=1.0; float bendfac=1.f;
                // PER-PLAYER VIBRATO. A section detuned to FIXED offsets beats at
                // fixed rates forever: N voices held exactly apart are a comb whose
                // notches march at constant speed, which is what a phaser is. Real
                // players never hold a pitch -- each has its own vibrato, so the
                // beat rates wander and never settle into a pattern.
                //
                // f(t) = fp*(1 + d*sin(2*pi*r*t + ph)), integrated ANALYTICALLY so
                // the block stays stateless like every other path here:
                //   phase(T) = 2*pi*fp*T + (fp*d/r)*(cos(ph) - cos(2*pi*r*T + ph))
                // bph carries the second term to the block start; winst is the
                // instantaneous frequency there, for the within-block recurrence.
                if(vdep[p]!=0.f){
                    // Absolute clock, not time-since-onset: a player does not
                    // restart their vibrato for every note, and it keeps this
                    // analytic integral on the same clock as the reference
                    // renderer's sample-by-sample one. Integrated from note-on,
                    // so the accumulated phase matches what the reference adds up.
                    double d=vdep[p], r=vrate[p], vp0=vph[p];
                    double fp=w*SRATE_D/6.283185307179586;
                    double ta=(double)ns/SRATE_D, tb2=(double)ne/SRATE_D, ton=(double)a/SRATE_D;
                    double w2=6.283185307179586*r;
                    double dt=tb2-ta;
                    if(vdl[p] > 0.f){
                        // CC78: STRAIGHT, THEN BLOOMING. A held note on a string
                        // or a voice starts without vibrato and the vibrato grows
                        // in; the depth is d*g(t), and the phase and the block's
                        // mean frequency both come from the exact integral of
                        // that envelope rather than from the constant-depth form.
                        double t1=ton+(double)vdl[p], t2=t1+VIB_BLOOM;
                        double Sa=vib_ramp_integral(ta, t1, t2, w2, vp0);
                        double Sb=vib_ramp_integral(tb2, t1, t2, w2, vp0);
                        bph += 6.283185307179586*fp*d*Sa;
                        vibfac = dt > 0.0 ? 1.0 + d*(Sb-Sa)/dt
                                          : 1.0 + d*(ta>=t2 ? 1.0 : (ta>t1 ? (ta-t1)/VIB_BLOOM : 0.0))
                                                   *sin(w2*ta+vp0);
                    } else {
                    bph += (fp*d/r)*(cos(w2*ton+vp0)-cos(w2*ta+vp0));
                    // The recurrence holds one frequency for the whole block, so
                    // use the block's EXACT MEAN frequency, not its value at the
                    // start: that lands the phase at the block end exactly where
                    // the integral says, leaving only a bounded, non-accumulating
                    // error mid-block (each block re-anchors from bph anyway).
                    double avg = dt > 0.0
                        ? 1.0 + d*(cos(w2*ta+vp0)-cos(w2*tb2+vp0))/(w2*dt)
                        : 1.0 + d*sin(w2*ta+vp0);
                    vibfac = avg;
                    }
                }
                if(tbav[p]!=0.f){
                    float tb=tbav[p], ts=tau[p], cut=tcut[p];
                    float trel=(float)(ns-a)/SRATE_F;
                    float integ = tb*ts*(1.f - expf(-(trel<cut?trel:cut)/ts));
                    bph += (double)w*SRATE_D*(double)integ;
                    // kept in float, and summed in float, so a voice with only
                    // this term rounds exactly as it did before it was factored out
                    bendfac = 1.f + (trel<cut ? tb*expf(-trel/ts) : 0.f);
                }
                // PORTAMENTO, and it settles exponentially in LENGTH rather than
                // in pitch -- which is the one thing that makes a modelled glide
                // different from a synthesiser's. A trombone slide, a finger on a
                // string and a slide whistle's plunger all move a LENGTH, and f is
                // 1/L. So a hand settling toward its target position gives
                // 1/(1 + g*e^{-t/tau}) in FREQUENCY, not the 1 + g*e^{-t/tau} the
                // tension bend above uses. A glide up therefore accelerates in
                // cents and a glide down decelerates, by the same amount, from the
                // same hand. Nothing had to be tuned to get that; it is what the
                // reciprocal does.
                //
                // g = f_target/f_source - 1, so t=0 gives exactly the source pitch
                // and t->infinity the target the note was built at. g > -1 for any
                // two real frequencies, so the denominator cannot vanish.
                //
                // Extra phase is the exact integral of (bendfac - 1):
                //     tau * ln( (1 + g*e^{-t/tau}) / (1 + g) )
                // zero at t=0 by construction, the same way BC is -- and frozen
                // past the cutoff, where the instantaneous factor is already 1.
                //
                // MULTIPLIES, never assigns. This is the fourth modulator in this
                // block and the rule the mode-lock bug wrote is now load-bearing
                // four ways: phases ADD and frequency factors MULTIPLY.
                if(gbav[p]!=0.f){
                    float gg=gbav[p], gs=gtau[p], gcu=gcut[p];
                    float trel=(float)(ns-a)/SRATE_F;
                    float e=expf(-(trel<gcu?trel:gcu)/gs);
                    bph += (double)w*SRATE_D*(double)(gs*logf((1.f+gg*e)/(1.f+gg)));
                    if(trel<gcu) bendfac *= 1.f/(1.f+gg*e);
                }
                // PITCH BEND, and it is the THIRD modulator here, so it obeys
                // the rule the comment at the top of this block was written to
                // enforce: phases ADD and frequency factors MULTIPLY. Never
                // assign -- that is the bug that deleted the mod wheel's
                // vibrato on trumpet and left it on violin.
                //
                // A bend is a RATIO, so the phase a partial accrues over a
                // block is w*(r-1)*BLK and the w factors out: the cumulative
                // term is partial-INDEPENDENT, which is why one pair of rows
                // serves a whole channel and the kernel stays stateless.
                //
                // ...AND IT ANCHORS AT ns, NOT AT bs0. A chunk boundary does
                // not land on a block boundary (CHUNK is a second, BLK is 512),
                // so once per chunk ns is clipped into the middle of a block.
                // BC holds the integral to the block START, so the remainder
                // from there to ns has to be added here. Anchoring at bs0
                // instead is a phase error of up to w*(r-1)*BLK -- some 190
                // radians during a full bend -- once per chunk, an audible
                // click that would only ever appear on bent notes.
                if(BRrow){
                    int bb=(b)<nblk?(b):nblk-1;
                    double rb=(double)BRrow[bb];
                    bph += w*(BCrow[bb] + (rb-1.0)*(double)(ns-bs0));
                    vibfac *= rb;
                }
                // With either term absent its factor is 1 and its phase 0, so a
                // voice that has only one of them renders exactly as before.
                float winst=(float)(w*vibfac*(double)bendfac);
                // THE MOOG'S GAIN on its grid: the amp contour times the ladder
                // at the cutoff the filter contour has reached, at the
                // frequency this partial is sounding NOW (bend, glide and
                // vibrato included, so the peak follows the note). The filter
                // is shared by both ears; the contour's onset keeps each ear's
                // own delay, as AMP's does.
                float gLm[65], gRm[65]; int j0=0;
                // THE MOD SECTION'S PITCH (moog.pitch_rows): an OSC 2 partial of
                // a note with pitch rows sounds at its ratio R_j at each grid
                // point, and carries the extra phase C_j accumulated to it --
                // integrated in Python, cell by cell, so a knob turned mid-sweep
                // changes only what is still to come.
                double mCp[65]; int pm=0;
                if(ftr && MPI && ((int)ftr[12] & FT_PITCH) && mkr && (mkr[p]>>12)==2) pm=1;
                // A MOVING SHAPE (moog.shape_rows): this partial's complex
                // coefficient at each grid point, from its note's rows
                float cRe[65], cIm[65]; int shm=0; const float* mkp=0; long mks=0; const int* mki=0;
                // 1 -> 2 FM: OSC 1's angle, from its frequency and phase anchor as
                // copied onto this OSC 2 partial (fmw, fmp, fmpR)
                int fmo = ftr && fmw && ((int)ftr[12] & 16) && mkr && (mkr[p]>>12)==2 && fmw[p]>0.0;
                float fmI = fmo ? ftr[13] : 0.f; int fmk = fmo ? (mkr[p]&4095) : 0;
                // ...as SIDEBANDS where it can be (fm_sidebands): fms, M of
                // them each side, and the ladder's cutoff, resonance and this
                // harmonic's frequency at each grid point to weigh them by
                float sbD0r[2*FM_SBMAX+1], sbD0i[2*FM_SBMAX+1]; double sbPsi=0.0;
                float sbDr[2*FM_SBMAX+1], sbDi[2*FM_SBMAX+1];
                float sbFc[65], sbK[65], sbF[65], sbBig=0.f; int sbMode=0, sbRb=0, fms=0, sbM=0;
                if(fmo){
                    sbM=fm_sidebands(ftr+14,(float)fmk*fmI,sbD0r,sbD0i,&sbPsi);
                    fms = sbM>=0;
                }
                if(ftr && MKI && MPK && mkr){
                    int o=mkr[p]>>12, bit = o==1 ? 2 : o==2 ? 4 : o==3 ? 8 : 0;
                    if(bit && ((int)ftr[12] & bit)){
                        mki=MKI+(long)fxp*7;
                        int off = mki[4+(o-1)];
                        if(off>=0){ shm=1; mks=mki[3]; mkp=MPK+mki[0]+off+2*((mkr[p]&4095)-1); }
                    }
                }
                if(ftr){
                    j0=(int)(bs0/mg); int nj=BLK/mg+1;
                    float kbf=ftr[0], fA=ftr[1], fD=ftr[2], fR=ftr[3], aA=ftr[4], aD=ftr[5], aR2=ftr[6];
                    int mode=(int)ftr[7], rb=ftr[8]>0.5f, pre=ftr[11]>0.5f; long krow=(long)ftr[9];
                    int selfosc = mkr && (mkr[p]>>12)==5;
                    float fhz=winst*SRATE_F/6.2831853f;
                    float toffL=(float)(off-a-(long)dL)/SRATE_F, toffR=(float)(off-a-(long)dR)/SRATE_F;
                    float toff=(float)(off-a)/SRATE_F;
                    float big=0.f;
                    const int* mpi = pm ? MPI+(long)fxp*3 : 0;
                    for(int j=0;j<nj;j++){
                        long nn=(long)(j0+j)*mg;
                        long ki=(long)(j0+j)-kb0; if(ki<0)ki=0; if(ki>knk-1)ki=knk-1;
                        const float* kn=KN+(krow*knk+ki)*KNW;
                        float fhzj=fhz, fade=1.f;
                        if(shm){
                            long mi=(long)(j0+j)-mki[1]; if(mi<0)mi=0; if(mi>mki[2]-1)mi=mki[2]-1;
                            cRe[j]=mkp[mi*mks]; cIm[j]=mkp[mi*mks+1];
                        }
                        if(pm){
                            long mi=(long)(j0+j)-mpi[1]; if(mi<0)mi=0; if(mi>mpi[2]-1)mi=mpi[2]-1;
                            mCp[j]=MPC[mpi[0]+mi]; fhzj=fhz*MPR[mpi[0]+mi];
                            // swept up past the top it would alias: fade it out
                            float fr=fhzj/SRATE_F;
                            fade = fr<0.40f ? 1.f : fr>0.45f ? 0.f : (0.45f-fr)*20.f;
                        }
                        if(fmo && !fms){
                            // a carrier whose deviation would reach Nyquist fades out
                            float fr=(fhzj+(float)fmk*fabsf(fmI)*(float)(fmw[p]*SRATE_D/6.283185307179586))/SRATE_F;
                            fade *= fr<0.40f ? 1.f : fr>0.45f ? 0.f : (0.45f-fr)*20.f;
                        }
                        float t=(float)(nn-a)/SRATE_F;
                        float fe=moog_adsr(t,fA,fD,kn[3],fR,toff);
                        float fc=kn[0]*kbf*exp2f(kn[2]*fe);
                        if(kn[6]!=0.f && kn[5]>0.f){
                            // LFO 1 on the cutoff: from the key (KB RESET) or
                            // free-running on the absolute clock (moog.lfo)
                            double tl = kn[8]>0.5f ? (double)(nn-a)/SRATE_D : (double)nn/SRATE_D;
                            double x=tl*(double)kn[5]; x-=floor(x);
                            int ls=(int)kn[7]; float xf=(float)x;
                            float lv = ls==0 ? 1.f-4.f*fabsf(xf-0.5f) : ls==1 ? 1.f-xf
                                     : ls==2 ? xf : (xf<0.5f ? 1.f : 0.f);      // moog.lfo
                            fc*=exp2f(kn[6]*lv);
                        }
                        if(fc<1.f)fc=1.f;
                        // the ladder's OWN sine (moog.SELF) is not filtered by it;
                        // an FM'd harmonic's sidebands are, each at its own
                        // frequency, in the cell loop below
                        float h = selfosc ? moog_out(fhzj) : fms ? fade : moog_ladder(fhzj/fc,kn[1],mode,rb)*fade*moog_out(fhzj);
                        if(fms){ sbFc[j]=fc; sbK[j]=kn[1]; sbF[j]=fhzj; sbMode=mode; sbRb=rb; }
                        if(pre && !selfosc){   // the partials carry the ladder at its sustain already
                            float fcs=kn[0]*kbf*exp2f(kn[2]*fmaxf(kn[3],0.f)); if(fcs<1.f)fcs=1.f;
                            h/=fmaxf(moog_ladder(fhz/fcs,kn[1],mode,rb),1e-12f);
                        }
                        gLm[j]=moog_adsr((float)(nn-a-dL)/SRATE_F,aA,aD,kn[4],aR2,toffL)*h;
                        gRm[j]=moog_adsr((float)(nn-a-dR)/SRATE_F,aA,aD,kn[4],aR2,toffR)*h;
                        big=fmaxf(big,fmaxf(gLm[j],gRm[j]));
                    }
                    // silent for the whole block: above a closed ladder the
                    // top harmonics of a lead mostly are. The level here is
                    // BEFORE the master gain, where a note sits near -50 dBFS,
                    // so 1e-8 is ~110 dB under it -- at 1e-6 it was 70, and a
                    // renderer with a different headroom skipped different
                    // partials (live against the file: 2.9e-4 apart).
                    if(big*fmaxf(fabsf(aL),fabsf(aR))<=1e-8f) continue;
                }
                float invg=1.f/(float)mg;
                double phL=ph0L[p]+w*(double)ns+bph, phR=ph0R[p]+w*(double)ns+bph;
                float zrL=cos(phL),ziL=sin(phL),zrR=cos(phR),ziR=sin(phR);
                float rr=cosf(winst),ri=sinf(winst);
                float invb=1.f/(float)BLK;
                float jfa=jf*cv*csc;
                // the chiff index's step, once a partial a block (chiff_step);
                // a negative wash bandwidth is a Moog noise band, not a chiff
                uint64_t chk_hi=0, chk_lo=0;
                if(jfa>0.f && chBW[p]>0.f)
                    chiff_step((double)nf*(double)chBW[p]/SRATE_D, &chk_hi, &chk_lo);
