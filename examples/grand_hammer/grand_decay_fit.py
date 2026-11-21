import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='steinway'; U.FIT_KEYS=(22,30,38,46,62,78); U.DECAY_HOLD=4.0
C=T.GrandPianoProperties
C.max_partial_hz=10000.0; C.hammer_model=True
for kv in os.environ['SETV'].split(','):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
C.strike_noise_db=tuple((h,db-22) for h,db in C.strike_noise_db)
U.DECAY=tuple(sys.argv[1].split(','))
e,v=U.fit_decay(C,0,int(sys.argv[2]),dyn=3)
for n,q in zip(U.DECAY,v): print("FIT %s = %.5g"%(n,q))
print("BEST %.2f"%e)
