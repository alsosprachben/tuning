"""Ours - recorded by absolute frequency band (octaves, re each note's own
250-500 Hz... re its whole level), per register and dynamic, 30-530 ms."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; C=T.ElectricGrandProperties
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,eval(v_))
ED=[125,250,500,1000,2000,4000,8000,16000]
def bands(x,sr,a,b):
    t0=U.onset(x,sr); X,f=U.spectrum(x,sr,t0,a,b,1<<16)
    e=np.array([X[(f>=lo)&(f<hi)].sum() for lo,hi in zip(ED[:-1],ED[1:])]); return 10*np.log10(e/X.sum()+1e-30)
regs=(("bass",(27,42,50)),("middle",(57,63,65,68,72)),("upper",(80,85,91)),("top",(97,102,107)))
win=(float(os.environ.get('A','0.03')),float(os.environ.get('B','0.53')))
ALL=[]
print("ours - recorded, dB re each note's whole energy, %g-%g s; bands: "%win+" ".join("%d-%d"%(a,b) for a,b in zip(ED[:-1],ED[1:])))
for d in (1,3):
    for nm,ks in regs:
        rows=[]
        for k in ks:
            x,sr=U.load(U.recordings(d)[k]); y,s2=U.render(2,k,U.vel_for(k,d),0.7)
            r=bands(x,sr,*win); o=bands(y,s2,*win); w=r>-45
            rows.append(np.where(w,o-r,np.nan))
        import warnings; warnings.simplefilter('ignore')
        m=np.nanmean(np.array(rows),0); ALL.extend([v for v in np.array(rows)[:,3:].ravel() if np.isfinite(v)])
        print("  dyn%d %-14s %s"%(d,nm," ".join("%6.1f"%v if np.isfinite(v) else "     ." for v in m)),flush=True)
print('RMS above 1 kHz, every key and dynamic: %.2f dB (mean %+.2f)'%(np.sqrt(np.mean(np.square(ALL))),np.mean(ALL)))
