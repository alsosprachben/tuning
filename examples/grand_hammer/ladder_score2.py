"""Bass partial ladders (1-12, dB re the strongest, 30-530 ms), ours - the
Steinway's, A#0-A#2 at p and f: rms, and the fundamental's mean."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
sys.path.insert(0,'..'); import robust_ladder as RL
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.ring_db=eval(open('../gring2.txt').read()); C.ring_tuned=False
C.strike_noise_vel_power_register=eval(open('../gkvp1.txt').read()); C.string_gain=(0.4,0.3)
if os.environ.get('SC'): C.strike_curve=tuple(float(x) for x in os.environ['SC'].split('/'))
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
def lad(x,sr,k):
    return np.maximum(RL.ladder(x,sr,k)[0],-50)
e=[];h1=[];rows=[]
for d in (1,3):
  for k in [int(v) for v in os.environ.get('KEYS','22,26,30,34,38,42,46').split(',')]:
    r=lad(*U.load(U.recordings(d)[k]),k); o=lad(*U.render(0,k,U.vel_for(k,d),0.7),k); q=o-r
    e.extend(q[np.isfinite(q)]); h1.append(q[0]); rows.append((d,k,q))
if os.environ.get('V'):
    for d,k,q in rows: print("  dyn%d %-4s %s"%(d,U.name(k)," ".join("%+4.0f"%v for v in q)))
print("ladder rms %.2f dB, fundamental %+.1f dB (mean, ours - Steinway)"%(np.sqrt(np.nanmean(np.square(e))),np.nanmean(h1)))
