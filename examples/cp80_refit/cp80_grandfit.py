import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; M=U._cp80_map()
C=T.ElectricGrandProperties
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'cp80_score.py')).read().split("v=sys.argv[1]")[0].split("C=T.ElectricGrandProperties")[1])
for n in GRAND:
    if n in C.__dict__: delattr(C,n)
C.bridge_peak_db=1.0; C.bridge_peak_hz=3000.0; C.bridge_peak_width=0.6; C.wound_zing_db=1.0; C.wound_decay_db=0.0
C.phantom_coupling=float(os.environ.get("PH",C.phantom_coupling))
for kv in filter(None,os.environ.get("SETV","").split(",")):
    n_,v_=kv.split(":"); setattr(C,n_,float(v_))
# THE CP80'S STRINGING: one string to F#2, two above (the takes' beating)
C.string_break_hz=(95.0,1.0e6)
if os.environ.get("SG"): C.string_gain=(float(os.environ["SG"]),0.0)
U.FIT_KEYS=tuple(sorted(k for k,x in M.items() if 'PP' in x and 'FF' in x))
U.SPECTRUM=tuple(sys.argv[1].split(','))
e,v=U.fit_spectrum(C,2,int(sys.argv[2]))
for n,q in zip(U.SPECTRUM,v): setattr(C,n,float(q))
print("BEST %.2f"%e); U.residuals(C,2)
for n in U.SPECTRUM: print("FIT %s = %.5g"%(n,getattr(C,n)))
