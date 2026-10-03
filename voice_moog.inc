// a Moog partial's per-block setup before its cells: the noise band and the
// FM sidebands' window, shared verbatim with voice_block.
                // a Moog partial with a NEGATIVE wash bandwidth is a noise band
                // (moog.NOISE): seeded by its note's onset and its own centre, so
                // two notes' noise is not one noise twice
                int noiz = chBW[p] < 0.f;
                double nrate = noiz ? (double)nf*(double)(-chBW[p]) : 0.0;
                uint64_t nseed = (uint64_t)a*0x9E3779B97F4A7C15ULL + (uint64_t)(long long)((double)nf*1000.0);
                long long nui=-1; double nh0=0.0, ndh=0.0;
                // THE SIDEBANDS WORTH WEIGHING: those whose D_m could reach
                // SB_TOL through the ladder at its loudest -- a bound the
                // resonance alone sets (the peak of a ladder at K_MAX, with
                // room to spare), so it is the same in every block and
                // either renderer -- and the far tail never costs a ladder
                // evaluation; each grid point's gains are kept for the next
                // cell, which starts where this one ends
                int dlo=0, dhi=-1, hEndJ=-1;
                float hEnd[2*FM_SBMAX+1];
                if(fms){
                    float td = SB_TOL/(1.5f*moog_ladder(1.f,3.9f,0,1));   // moog.K_MAX, RES BASS on
                    for(dlo=0; dlo<=2*sbM; dlo++) if(fabsf(sbD0r[dlo])+fabsf(sbD0i[dlo])>td) break;
                    for(dhi=2*sbM; dhi>=dlo; dhi--) if(fabsf(sbD0r[dhi])+fabsf(sbD0i[dhi])>td) break;
                    // this note's own phase back on: D_m = D'_m e^{-i m psi}
                    double er=cos(-(double)(dlo-sbM)*sbPsi), ei=sin(-(double)(dlo-sbM)*sbPsi);
                    double sr=cos(-sbPsi), si=sin(-sbPsi);
                    for(int i=dlo;i<=dhi;i++){
                        sbDr[i]=(float)((double)sbD0r[i]*er-(double)sbD0i[i]*ei);
                        sbDi[i]=(float)((double)sbD0r[i]*ei+(double)sbD0i[i]*er);
                        double t=er*sr-ei*si; ei=er*si+ei*sr; er=t;
                    }
                }
