"""The decay by frequency fitted to band T20s and the late tail, any piano class."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]=os.environ.get('REF','upright')
U.FIT_KEYS=tuple(int(k) for k in os.environ.get('KEYS','29,41,53,65,77,89').split(','))
U.DECAY_HOLD=float(os.environ.get("HOLD","4.0"))
C=getattr(T,os.environ.get('CLS','UprightPianoProperties')); PROG=int(os.environ.get('PROG','1'))
C.max_partial_hz=10000.0; C.hammer_model=True; C.decay_by_hz=True
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
if os.environ.get('SN'): C.strike_noise_db=tuple((h,db+float(os.environ['SN'])) for h,db in C.strike_noise_db)
U.DECAY=tuple(sys.argv[1].split(','))
e,v=U.fit_decay(C,PROG,int(sys.argv[2]),dyn=int(os.environ.get('DYN','3')))
for n,q in zip(U.DECAY,v): print("FIT %s = %.5g"%(n,q))
print("BEST %.2f"%e)
