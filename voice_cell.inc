// a Moog cell's setup: its grid gains, OSC 1's angle and the sidebands
// through the ladder, the pitch rows' re-anchor -- shared verbatim with
// voice_block. `continue` skips the cell.
                long c0=bs0+(long)cl*mg, c1=c0+mg;
                long s0 = ns>c0 ? ns : c0, s1 = ne<c1 ? ne : c1;
                if(s0>=s1) continue;
                float a0L=gLm[cl], a1L=gLm[cl+1], a0R=gRm[cl], a1R=gRm[cl+1];
                float z1r=0.f, z1i=0.f, r1r=1.f, r1i=0.f;
                float g0r[2*FM_SBMAX+1], g0i[2*FM_SBMAX+1], dgr[2*FM_SBMAX+1], dgi[2*FM_SBMAX+1];
                float pzr[2*FM_SBMAX+1], pzi[2*FM_SBMAX+1], prr[2*FM_SBMAX+1], pri[2*FM_SBMAX+1];
                int slo=0, nsb=0;
                if(fmo){
                    // OSC 1's angle at the cell's start, exactly; its vibrato and
                    // bend (bph) scale with frequency, as every partial's do
                    double w1=fmw[p], ps=fmp[p]+w1*(double)s0+bph*(w1/w);
                    z1r=(float)cos(ps); z1i=(float)sin(ps);
                    double w1v=(double)winst*(w1/w);
                    r1r=(float)cos(w1v); r1i=(float)sin(w1v);
                    if(fms){
                        // EACH SIDEBAND THROUGH THE LADDER at its own frequency
                        // |k f2 + m f1|, at both ends of the cell, and faded as
                        // it nears Nyquist -- one sideband at a time, where the
                        // unfiltered path had to fade the whole harmonic
                        float f1=(float)(w1v*SRATE_D/6.283185307179586);
                        int reuse = hEndJ==cl;
                        for(int i=dlo;i<=dhi;i++){
                            float m=(float)(i-sbM), hg[2];
                            for(int e = reuse ? 1 : 0; e<2; e++){
                                float fs=fabsf(sbF[cl+e]+m*f1), fr=fs/SRATE_F;
                                float nq = fr<0.40f ? 1.f : fr>0.45f ? 0.f : (0.45f-fr)*20.f;
                                hg[e] = nq>0.f ? moog_ladder(fs/sbFc[cl+e],sbK[cl+e],sbMode,sbRb)*moog_out(fs)*nq : 0.f;
                            }
                            if(reuse) hg[0]=hEnd[i];
                            hEnd[i]=hg[1];
                            g0r[i]=sbDr[i]*hg[0]; g0i[i]=sbDi[i]*hg[0];
                            dgr[i]=sbDr[i]*hg[1]-g0r[i]; dgi[i]=sbDi[i]*hg[1]-g0i[i];
                        }
                        hEndJ=cl+1;
                        // ...and only the ones that sound (SB_TOL): a shut
                        // ladder leaves a handful of a bell's dozens
                        float tg = SB_TOL;
                        int shi;
                        for(slo=dlo; slo<=dhi; slo++)
                            if(fmaxf(fabsf(g0r[slo])+fabsf(g0i[slo]),
                                     fabsf(g0r[slo]+dgr[slo])+fabsf(g0i[slo]+dgi[slo]))>tg) break;
                        for(shi=dhi; shi>=slo; shi--)
                            if(fmaxf(fabsf(g0r[shi])+fabsf(g0i[shi]),
                                     fabsf(g0r[shi]+dgr[shi])+fabsf(g0i[shi]+dgi[shi]))>tg) break;
                        nsb=shi-slo+1;
                        // EACH SIDEBAND ITS OWN PHASOR, e^{i m th1} turning at
                        // m w1, as any partial is: independent, so the sum
                        // below runs across them in vector lanes, where a
                        // Horner chain is one long dependency. Set in double
                        // at the cell's start, as OSC 1's angle is.
                        double czr=cos((double)(slo-sbM)*ps), czi=sin((double)(slo-sbM)*ps);
                        double crr=cos((double)(slo-sbM)*w1v), cri=sin((double)(slo-sbM)*w1v);
                        double sr1=cos(ps), si1=sin(ps), tr1=cos(w1v), ti1=sin(w1v);
                        for(int i=0;i<nsb;i++){
                            pzr[i]=(float)czr; pzi[i]=(float)czi; prr[i]=(float)crr; pri[i]=(float)cri;
                            double t=czr*sr1-czi*si1; czi=czr*si1+czi*sr1; czr=t;
                            t=crr*tr1-cri*ti1; cri=crr*ti1+cri*tr1; crr=t;
                        }
                    }
                }
                if(pm){
                    // re-anchor the phase at the cell's start, exactly, and turn
                    // at this cell's own rate: a 512-sample file block and a
                    // 128-sample live one then walk the same phase
                    double cs=mCp[cl]+(mCp[cl+1]-mCp[cl])*(double)(s0-c0)/(double)mg;
                    double el=(double)winst*(double)(s0-ns)+w*cs;
                    zrL=(float)cos(phL+el); ziL=(float)sin(phL+el);
                    zrR=(float)cos(phR+el); ziR=(float)sin(phR+el);
                    double wc=(double)winst+w*(mCp[cl+1]-mCp[cl])/(double)mg;
                    rr=(float)cos(wc); ri=(float)sin(wc);
                }
