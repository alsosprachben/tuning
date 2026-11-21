import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='steinway'; C=T.GrandPianoProperties
mode=sys.argv[1]
if mode!='old':
    C.max_partial_hz=10000.0; C.hammer_model=True
    for kv in os.environ['SETV'].split(','):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
    C.strike_noise_db=tuple((h,db-22) for h,db in C.strike_noise_db)
    for kv in filter(None,os.environ.get('EXTRA','').split(',')):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
T_=(0.05,0.3,0.7,1.5,3.0)
def env(x,sr):
    x=x[U.onset(x,sr):]; w=int(.05*sr)
    pk=max(np.mean(x[i:i+w]**2) for i in range(0,int(.2*sr),w//2))
    return [10*np.log10(np.mean(x[int(t*sr):int(t*sr)+w]**2)/pk+1e-30) for t in T_]
recs=U.recordings(3)
for k in (22,30,38,46,54):
    x,sr=U.load(recs[k]); r=env(x,sr)
    y,s2=U.render(0,k,U.vel_for(k,3),3.5); o=env(y,s2)
    print("%-8s %-4s level re peak at %s s: rec %s | ours %s"%(mode,U.name(k),"/".join(str(t) for t in T_)," ".join("%5.1f"%v for v in r)," ".join("%5.1f"%v for v in o)))
