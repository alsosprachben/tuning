import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; C=T.ElectricGrandProperties
if os.environ.get('KTABS'): C.strike_noise_register_db=eval(os.environ['KTABS'])
if os.environ.get('VPTS'): C.hammer_vel_power_points=eval(os.environ['VPTS'])
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,eval(v_))
lab=os.environ.get('LAB',''); out=[]
for d in (1,3):
    for k in (80,85,91,97,102,107):
        x,sr=U.load(U.recordings(d)[k]) if lab=='rec' else U.render(2,k,U.vel_for(k,d),0.6)
        t0=U.onset(x,sr); pk=np.abs(x[max(0,t0-int(.002*sr)):t0+int(.005*sr)]).max(); rms=np.sqrt(np.mean(x[t0+int(.01*sr):t0+int(.1*sr)]**2))
        out.append("%s%d %.0f"%(U.name(k),d,20*np.log10(pk/rms)))
print("%-8s spike (first-5ms peak re 10-100ms level, dB):"%lab," ".join(out))
