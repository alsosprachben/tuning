"""Ours - recorded by absolute frequency band (octaves, re each note's own
250-500 Hz... re its whole level), per register and dynamic, 30-530 ms."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='steinway'; C=T.GrandPianoProperties
if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
if os.environ.get('KVP'): C.strike_noise_vel_power_register=eval(open(os.environ['KVP']).read())
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
ED=[125,250,500,1000,2000,4000,8000,16000]
def bands(x,sr,a,b):
    t0=U.onset(x,sr); X,f=U.spectrum(x,sr,t0,a,b,1<<16)
    e=np.array([X[(f>=lo)&(f<hi)].sum() for lo,hi in zip(ED[:-1],ED[1:])]); return 10*np.log10(e/X.sum()+1e-30)
regs=(("bass A0-A2",(22,26,30,34,38,42,46)),("tenor A#2-A#3",(46,50,54,58)),("middle C4-C5",(60,64,68,72)),("treble C6-C7",(84,88,92,96)))
win=(float(os.environ.get('A','0.03')),float(os.environ.get('B','0.53')))
ALL=[]
print("ours - recorded, dB re each note's whole energy, %g-%g s; bands: "%win+" ".join("%d-%d"%(a,b) for a,b in zip(ED[:-1],ED[1:])))
for d in (1,3):
    for nm,ks in regs:
        rows=[]
        for k in ks:
            x,sr=U.load(U.recordings(d)[k]); y,s2=U.render(0,k,U.vel_for(k,d),0.7)
            r=bands(x,sr,*win); o=bands(y,s2,*win); w=r>-45
            rows.append(np.where(w,o-r,np.nan))
        import warnings; warnings.simplefilter('ignore')
        m=np.nanmean(np.array(rows),0); ALL.extend([v for v in np.array(rows)[:,3:].ravel() if np.isfinite(v)])
        print("  dyn%d %-14s %s"%(d,nm," ".join("%6.1f"%v if np.isfinite(v) else "     ." for v in m)),flush=True)
print('RMS above 1 kHz, every key and dynamic: %.2f dB (mean %+.2f)'%(np.sqrt(np.mean(np.square(ALL))),np.mean(ALL)))
