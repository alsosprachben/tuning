import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='steinway'; U.FIT_KEYS=U.STEINWAY_KEYS
C=T.GrandPianoProperties
mode=sys.argv[1]
C.max_partial_hz=10000.0
if mode!='old': C.hammer_model=True
for kv in filter(None,os.environ.get("SETV","").split(",")):
    n_,v_=kv.split(":"); setattr(C,n_,float(v_))
if len(sys.argv)>2:
    U.SPECTRUM=tuple(sys.argv[2].split(','))
    e,v=U.fit_spectrum(C,0,int(sys.argv[3]))
    for n,q in zip(U.SPECTRUM,v): setattr(C,n,float(q)); print("FIT %s = %.5g"%(n,q))
    print("BEST %.2f"%e)
else:
    U.SPECTRUM=('tonal_dampening',)
    e,v=U.fit_spectrum(C,0,1); print("%s spectrum %.2f"%(mode,e))
U.residuals(C,0)
