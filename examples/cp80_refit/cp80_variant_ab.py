import sys,os
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; M=U._cp80_map()
C=T.ElectricGrandProperties
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'cp80_score.py')).read().split("v=sys.argv[1]")[0].split("C=T.ElectricGrandProperties")[1])
for n in GRAND:
    if n in C.__dict__: delattr(C,n)
C.wound_zing_db=0.31; C.wound_decay_db=0.0
for kv in "hammer_corner_hz:363.07,hammer_open_slope:17.836,hammer_register_slope:0.11605,bridge_corner_hz:3000,bridge_peak_db:-8.8,bridge_peak_hz:790,bridge_peak_width:0.75".split(","):
    n,v=kv.split(":"); setattr(C,n,float(v))
C.bridge_order=1.27
C.string_break_hz=(95.0,1.0e6); C.string_gain=(0.82,0.0)
U.FIT_KEYS=tuple(sorted(M))[::2]
U.ab(2,sys.argv[1])
