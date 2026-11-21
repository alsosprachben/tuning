import sys,os
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='steinway'; U.FIT_KEYS=U.STEINWAY_KEYS
C=T.GrandPianoProperties
if sys.argv[2]=='new':
    C.max_partial_hz=10000.0; C.hammer_model=True
    for kv in (os.environ['SETV']).split(','):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
U.ab(0,sys.argv[1])
