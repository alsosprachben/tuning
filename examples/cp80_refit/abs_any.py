"""Absolute third-octave residuals for a piano class, with SETV overrides."""
import sys,os
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T, numpy as np
U.REF[0]=os.environ.get('REF','upright')
C=getattr(T,os.environ.get('CLS','UprightPianoProperties')); PROG=int(os.environ.get('PROG','1'))
if os.environ.get('HAMMER'): C.max_partial_hz=10000.0; C.hammer_model=True
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
if os.environ.get('KEYS'): U.FIT_KEYS=tuple(int(k) for k in os.environ['KEYS'].split(','))
e=[]
for d in U.FIT_DYNS:
    recs=U.recordings(d)
    for k in U.FIT_KEYS:
        r=U.thirds(*U.load(recs[k]),k); m=U.thirds(*U.render(PROG,k,U.vel_for(k,d),0.7),k)
        w=((r>-40)|(m>-40))&np.isfinite(r)&np.isfinite(m)
        e.extend((np.maximum(m,-60)-np.maximum(r,-60))[w])
print("absolute rms %.2f dB, mean %+.2f"%(np.sqrt(np.mean(np.square(e))),np.mean(e)))
U.residuals(C,PROG)
