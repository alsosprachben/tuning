import sys,os,numpy as np,json
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; M=U._cp80_map()
C=T.ElectricGrandProperties
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'cp80_score.py')).read().split("v=sys.argv[1]")[0].split("C=T.ElectricGrandProperties")[1])
for n in GRAND:
    if n in C.__dict__: delattr(C,n)
C.bridge_peak_db=0.0; C.wound_zing_db=0.0; C.wound_decay_db=0.0
for kv in filter(None,sys.argv[1].split(',')):   # fitted values name:value
    n,v=kv.split(':'); setattr(C,n,float(v))
C.string_break_hz=(95.0,1.0e6)
recs=U.recordings(3)
def mw(x,sr,k):
    b=U.beating(x,sr,k); return float(np.mean([d for _,d,_ in b])) if b else np.nan
R={k:mw(*U.load(recs[k]),k) for k in sorted(recs)}
for g in [float(v) for v in sys.argv[2].split(',')]:
    C.string_gain=(g,0.0)
    e=[];row=[]
    for k in sorted(recs):
        y,sr=U.render(2,k,U.vel_for(k,3),3.5); o=mw(y,sr,k); e.append(o-R[k]); row.append("%s %.1f/%.1f"%(U.name(k),R[k],o))
    print("second string %.2f: wobble err rms %.2f, mean %.2f | %s"%(g,np.sqrt(np.nanmean(np.square(e))),np.nanmean(e)," ".join(row[::3])),flush=True)
