"""Loud bass notes: each low band's level at 0.5, 1, 1.5, 2, 3 s (0.25 s windows,
re its own first window) -- ours under SETV, against the Steinway."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
from scipy.signal import butter,sosfilt
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.ring_db=eval(open('../gring2.txt').read()); C.ring_tuned=False
C.strike_noise_vel_power_register=eval(open('../gkvp1.txt').read())
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
if os.environ.get('SG'): C.string_gain=tuple(float(v) for v in os.environ['SG'].split('/'))
if os.environ.get('UB'): C.unison_beat_hz=tuple(float(v) for v in os.environ['UB'].split('/'))
BANDS=((63,125),(125,250),(250,500))
TS=(0.5,1.0,1.5,2.0,3.0)
def env(x,sr):
    t0=U.onset(x,sr); x=x[t0:]; out=[]
    for b in BANDS:
        y=sosfilt(butter(4,list(b),'band',fs=sr,output='sos'),x); r0=np.mean(y[:int(0.25*sr)]**2)
        out.append([10*np.log10(np.mean(y[int(t*sr):int((t+0.25)*sr)]**2)/r0+1e-30) for t in TS])
    return np.array(out)
lab=os.environ.get('LAB','')
for k in (34,46):
    o=env(*U.render(0,k,U.vel_for(k,3),3.5))
    if lab=='rec': o=env(*U.load(U.recordings(3)[k]))
    print("%-12s %-4s "%(lab,U.name(k))+" | ".join("%d-%d: %s"%(b[0],b[1]," ".join("%4.0f"%v for v in o[i])) for i,b in enumerate(BANDS)),flush=True)
