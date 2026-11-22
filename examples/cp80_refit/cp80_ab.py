import sys,os
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; U.FIT_KEYS=tuple(int(k) for k in os.environ['KEYS'].split(','))
C=T.ElectricGrandProperties
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,eval(v_))
U.ab(2,sys.argv[1])
