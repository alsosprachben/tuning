"""Loud tenor notes: energy between the partials re on them, 2-6 kHz, 0.05-0.5 s
(each partial +-1.5% of its place on the fitted law); the Steinway's and ours."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples');sys.path.insert(0,'..')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T, robust_ladder as RL
U.REF[0]='steinway'; C=T.GrandPianoProperties
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
if os.environ.get('NOKNOCK'): C.strike_noise_db=()
lab=os.environ.get('LAB',''); out=[]
for k in (46,50,54,58):
    x,sr=U.load(U.recordings(3)[k]) if lab=='rec' else U.render(0,k,U.vel_for(k,3),0.7)
    _,f0,B=RL.ladder(x,sr,k); t0=U.onset(x,sr); seg=x[t0+int(float(os.environ.get('A','0.05'))*sr):t0+int(float(os.environ.get('B','0.5'))*sr)]
    n=1<<15; X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2; f=np.fft.rfftfreq(n,1/sr)
    on=np.zeros_like(f,bool)
    for h in range(1,400):
        fh=h*f0*np.sqrt(1+B*h*h)
        if fh>6500: break
        on|=(f>fh*0.985)&(f<fh*1.015)
    band=(f>2000)&(f<6000)
    out.append(10*np.log10(X[band&~on].sum()/X[band&on].sum()))
print("%-14s between/on partials 2-6 kHz, dB (A#2 D3 F#3 A#3): %s  mean %+.1f"%(lab," ".join("%+.1f"%v for v in out),np.mean(out)))
