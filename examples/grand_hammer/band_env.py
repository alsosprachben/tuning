"""Each octave band's level over time (0.25 s windows, averaging over the
unison's beats), dB re the note's whole first 0.25 s: recorded / ours."""
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
BANDS=((63,125),(125,250),(250,500),(500,1000),(1000,2000),(2000,4000),(4000,8000))
TS=(0.0,0.25,0.5,1.0,1.5,2.0,3.0)
def env(x,sr):
    t0=U.onset(x,sr); x=x[t0:]; ref=np.mean(x[:int(0.25*sr)]**2)
    out=[]
    for lo,hi in BANDS:
        y=sosfilt(butter(4,[lo,hi],'band',fs=sr,output='sos'),x)
        out.append([10*np.log10(np.mean(y[int(t*sr):int((t+0.25)*sr)]**2)/ref+1e-30) for t in TS])
    return np.array(out)
print("t (s):",TS)
for k in [int(v) for v in os.environ.get('KEYS','62,70,78,86').split(',')]:
    x,sr=U.load(U.recordings(3)[k]); y,s2=U.render(0,k,U.vel_for(k,3),3.5)
    r=env(x,sr); o=env(y,s2); f0=440*2**((k-69)/12)
    print(U.name(k))
    for i,(lo,hi) in enumerate(BANDS):
        if hi<f0*0.9: continue
        print("  %4d-%4d  rec %s"%(lo,hi," ".join("%5.0f"%v for v in r[i])))
        print("             ours %s"%(" ".join("%5.0f"%v for v in o[i])))
