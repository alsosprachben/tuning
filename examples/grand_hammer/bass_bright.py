"""Hard (and soft) bass notes: ours - recorded, third octaves above 1 kHz
(where the recording is within 45 dB of its peak), 30-530 ms and 0-40 ms."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.ring_db=eval(open('../gring2.txt').read()); C.ring_tuned=False
C.strike_noise_vel_power_register=eval(open('../gkvp1.txt').read()); C.string_gain=(0.4,0.3)
if os.environ.get('SC'): C.strike_curve=tuple(float(x) for x in os.environ['SC'].split('/'))
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ or 'e' in v_ else int(v_))
def th(x,sr,k,a,b):
    t0=U.onset(x,sr); X,f=U.spectrum(x,sr,t0,a,b,1<<16)
    bb=np.array([X[(f>=lo)&(f<hi)].sum() for lo,hi in zip(U.E3[:-1],U.E3[1:])]); bb=10*np.log10(bb+1e-30); return bb-bb.max()
hi=U.E3[:-1]>=1000
for d in (3,1):
    rows=[]
    for k in (22,30,38,46,54):
        x,sr=U.load(U.recordings(d)[k]); y,s2=U.render(0,k,U.vel_for(k,d),0.7)
        out=[]
        for a,b in ((0.03,0.53),(0.0,0.04)):
            r=th(x,sr,k,a,b); o=th(y,s2,k,a,b); w=hi&(r>-45); out.append(np.mean((o-r)[w]) if w.any() else np.nan)
        rows.append((U.name(k),out))
    print("dyn%d above 1 kHz, ours-rec dB (sustain, attack): "%d+"  ".join("%s %+.0f/%+.0f"%(n,a,b) for n,(a,b) in rows),flush=True)
