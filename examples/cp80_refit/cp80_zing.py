"""Attack zing: 1.6-8 kHz in the first 40 ms re its level at 0.3-0.6 s (dB),
low keys, soft and loud; recorded, ours (SETV)."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
from scipy.signal import butter,sosfiltfilt
U.REF[0]='cp80'; C=T.ElectricGrandProperties
if os.environ.get('KTABS'): C.strike_noise_register_db=eval(os.environ['KTABS'])
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,eval(v_))
lab=os.environ.get('LAB','')
def z(x,sr):
    t0=U.onset(x,sr); y=sosfiltfilt(butter(4,[1600,8000],'band',fs=sr,output='sos'),x[t0:t0+int(0.7*sr)])
    a=np.mean(y[:int(0.04*sr)]**2); b=np.mean(y[int(0.3*sr):int(0.6*sr)]**2); return 10*np.log10(a/b)
out=[]
for d in (1,3):
    for k in (27,42,50,57,63,72):
        x,sr=U.load(U.recordings(d)[k]) if lab=='rec' else U.render(2,k,U.vel_for(k,d),0.7)
        out.append("%s%d %+.0f"%(U.name(k),d,z(x,sr)))
print("%-9s"%lab," ".join(out))
