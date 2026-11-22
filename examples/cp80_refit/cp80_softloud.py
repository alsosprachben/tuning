import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; C=T.ElectricGrandProperties
if os.environ.get('KTABS'): C.strike_noise_register_db=eval(os.environ['KTABS'])
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,eval(v_))
lab=os.environ.get('LAB',''); out=[]
for k in (72,80,85,91,97,102,107):
    lv=[]
    for d in (1,3):
        x,sr=U.load(U.recordings(d)[k]) if lab=='rec' else U.render(2,k,U.vel_for(k,d),0.6)
        t0=U.onset(x,sr); lv.append(10*np.log10(np.mean(x[t0+int(.01*sr):t0+int(.2*sr)]**2)))
    out.append("%s %.0f"%(U.name(k),lv[1]-lv[0]))
print("%-8s loud minus soft tone level (10-200 ms), dB:"%lab," ".join(out))
