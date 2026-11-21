"""The grand's strike curve (ratio a + b o + c o^2) fitted to the Steinway's
partial ladders (1-12, dB re the strongest, 30-530 ms) at p and f."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
sys.path.insert(0,'..'); import robust_ladder as RL
from scipy.optimize import minimize
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.ring_db=eval(open('../gring2.txt').read()); C.ring_tuned=False
C.strike_noise_vel_power_register=eval(open('../gkvp1.txt').read()); C.string_gain=(0.4,0.3)
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
KEYS=[int(v) for v in os.environ.get('KEYS','22,28,34,40,46,52,58,64,70,76,82,88,94').split(',')]
def lad(x,sr,k):
    return np.maximum(RL.ladder(x,sr,k)[0],-50)
REC={(d,k):lad(*U.load(U.recordings(d)[k]),k) for d in (1,3) for k in KEYS}
def err(v=None,verbose=False):
    if v is not None: C.strike_curve=tuple(float(x) for x in v)
    e=[]
    for (d,k),r in REC.items():
        q=lad(*U.render(0,k,U.vel_for(k,d),0.7),k)-r; e.extend(q[np.isfinite(q)])
        if verbose: print("  dyn%d %-4s %s"%(d,U.name(k)," ".join("%+4.0f"%x for x in q)))
    return float(np.sqrt(np.mean(np.square(e))))
if sys.argv[1]=='check':
    if len(sys.argv)>2: C.strike_curve=tuple(float(x) for x in sys.argv[2].split('/'))
    print("ladder rms %.2f"%err(verbose=True)); sys.exit()
best=[1e9,None]
def f(v):
    if not (3.0<v[0]<14.0): return 99.0
    e=err(v)
    if e<best[0]: best[:]=[e,v.copy()]; print("  %.2f dB  ratio %.3f %+.3f o %+.3f o^2"%(e,*v),flush=True)
    return e
x0=np.array([float(x) for x in sys.argv[2].split('/')])
minimize(f,x0,method="Nelder-Mead",options={"maxfev":int(sys.argv[3]),"initial_simplex":np.vstack([x0,x0+[1.5,0,0],x0+[0,0.6,0],x0+[0,0,0.3]]),"xatol":0.02,"fatol":0.02})
print("FIT strike_curve = (%.4f, %.4f, %.4f)"%tuple(best[1])); print("BEST %.2f"%best[0])
