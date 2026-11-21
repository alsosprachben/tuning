import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.max_partial_hz=10000.0; C.hammer_model=True
for kv in os.environ['SETV'].split(','):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
C.strike_noise_db=tuple((h,db-22) for h,db in C.strike_noise_db)
recs=U.recordings(3)
print("T20 s by octave band "+" ".join("%d-%d"%b for b in U.BANDS))
for k in (22,30,38,46,62,78):
    x,sr=U.load(recs[k]); r=[q[0] for q in U.band_decay(x,sr)]
    y,s2=U.render(0,k,U.vel_for(k,3),6.0); o=[q[0] for q in U.band_decay(y,s2)]
    print("%-4s rec  %s"%(U.name(k)," ".join("%6.2f"%v for v in r)))
    print("     ours %s"%(" ".join("%6.2f"%v for v in o)),flush=True)
