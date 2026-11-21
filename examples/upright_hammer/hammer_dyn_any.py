"""The grand's hammer fitted to how each key's spectrum CHANGES from its soft
layer to its hard one (VCSL Steinway B): the microphone and the room cancel."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
from scipy.optimize import minimize
U.REF[0]=os.environ.get('REF','steinway'); KEYS=tuple(int(k) for k in os.environ['KEYS'].split(',')) if os.environ.get('KEYS') else U.STEINWAY_KEYS
C=getattr(T,os.environ.get('CLS','GrandPianoProperties')); PROG=int(os.environ.get('PROG','0'))
mode=sys.argv[1]
C.max_partial_hz=10000.0
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
if mode!='old': C.hammer_model=True
R={}
for d in (1,3):
    recs=U.recordings(d)
    for k in KEYS: R[(d,k)]=U.thirds(*U.load(recs[k]),k)
REC={k:R[(3,k)]-R[(1,k)] for k in KEYS}
def err(verbose=False):
    e=[];rows=[]
    for k in KEYS:
        o=[U.thirds(*U.render(PROG,k,U.vel_for(k,d),0.7),k) for d in (1,3)]
        od=o[1]-o[0]; r=REC[k]
        w=np.isfinite(od)&np.isfinite(r)&(R[(3,k)]>-45)&(o[1]>-45)
        e.extend(od[w]-r[w]); rows.append((k,od,r))
    if verbose:
        print("  hard minus soft, ours - rec, by third octave from the fundamental (every 2nd):")
        for k,od,r in rows:
            q=(od-r); q=q[np.isfinite(q)]
            print("   %-4s %s"%(U.name(k)," ".join("%4.0f"%v for v in q[::2])))
    return float(np.sqrt(np.mean(np.square(e))))
names=sys.argv[2].split(',') if len(sys.argv)>2 else []
if not names:
    print("%s: hard-minus-soft rms %.2f dB"%(mode,err(True))); sys.exit()
x0=np.array([float(getattr(C,n)) for n in names]); best=[1e9,x0]
def f(z):
    v=x0+z
    for n,q in zip(names,v):
        if n.startswith('hammer_p_') and not 1.8<=q<=4.0: return 99.0
        if n.startswith('hammer_speed') and not 0.1<=q<=12.0: return 99.0
        if n=='hammer_alpha' and not 0.0<=q<=0.95: return 99.0
        if n=='hammer_log_tau' and not -6.0<=q<=-3.0: return 99.0
        setattr(C,n,float(q))
    e=err()
    if e<best[0]: best[:]=[e,v]; print("  %.2f dB  %s"%(e," ".join("%s=%.4g"%(n,q) for n,q in zip(names,v))),flush=True)
    return e
n=len(names)
minimize(f,np.zeros(n),method="Nelder-Mead",options={"maxfev":int(sys.argv[3]),"xatol":0.02,"fatol":0.02,
    "initial_simplex":np.vstack([np.zeros(n)]+[np.eye(n)[i]*float(sys.argv[4]) for i in range(n)])})
for nm,q in zip(names,best[1]): setattr(C,nm,float(q)); print("FIT %s = %.5g"%(nm,q))
print("BEST %.2f"%err(True))
