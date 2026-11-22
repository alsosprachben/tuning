"""The CP-80's hammer as LEATHER, fitted on renders against Sullivan's takes:
soft-to-hard third-octave change + absolute spectrum (all keys) + partial
ladders (lower keys, where the strike point's nodes show)."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples');sys.path.insert(0,'..')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T, robust_ladder as RL
from scipy.optimize import minimize
U.REF[0]='cp80'; C=T.ElectricGrandProperties
C.hammer_model=True; C.max_partial_hz=10000.0
for n_,v_ in (('hammer_core_mm',0.0),('hammer_core_edge_mm',0.0),('hammer_alpha',0.05),('strike_fill_fraction',0.0)): setattr(C,n_,v_)
KS=(27,42,50,57,63,68,72,80,91,102); LK=(27,42,50,57,63)
REC={}
for d in (1,3):
    for k in KS:
        x,sr=U.load(U.recordings(d)[k]); REC[(d,k)]=(U.thirds(x,sr,k), np.maximum(RL.ladder(x,sr,k,nmax=12)[0],-50) if k in LK else None)
def err(verbose=False):
    ed=[];ea=[];el=[]
    O={}
    for (d,k),(r,rl) in REC.items():
        y,sr=U.render(2,k,U.vel_for(k,d),0.7); O[(d,k)]=U.thirds(y,sr,k)
        w=((r>-40)|(O[(d,k)]>-40))&np.isfinite(r)&np.isfinite(O[(d,k)])
        ea.extend((np.maximum(O[(d,k)],-60)-np.maximum(r,-60))[w])
        if rl is not None:
            q=np.maximum(RL.ladder(y,sr,k,nmax=12)[0],-50)-rl; el.extend(q[np.isfinite(q)])
    for k in KS:
        od=O[(3,k)]-O[(1,k)]; rd=REC[(3,k)][0]-REC[(1,k)][0]
        w=np.isfinite(od)&np.isfinite(rd)&(REC[(3,k)][0]>-45)&(O[(3,k)]>-45); ed.extend((od-rd)[w])
    r=lambda a: float(np.sqrt(np.mean(np.square(a))))
    e=float(np.sqrt(r(ed)**2+r(ea)**2+0.5*r(el)**2))
    if verbose: print("change %.2f  absolute %.2f  ladders %.2f  -> %.2f"%(r(ed),r(ea),r(el),e))
    return e
P=['hammer_logk','hammer_logk_slope','hammer_p_lo','hammer_p_hi','tonal_dampening','hammer_speed_lo']
for n_,v_ in (('strike_depth',0.84976),('strike_point',0.12309),('bridge_corner_hz',2970.0),('bridge_order',1.5959),('bridge_peak_db',-8.5287),('bridge_peak_hz',800.44)): setattr(C,n_,v_)
x0=np.array([float(v) for v in sys.argv[1].split(',')])
lo=np.array([8.0,0.0,1.0,1.0,0.3,0.1]); hi=np.array([13.0,0.8,3.0,3.0,1.6,1.0])
for p,v in zip(P,x0): setattr(C,p,v)
if len(sys.argv)<3: err(True); sys.exit()
best=[1e9,None]
def f(z):
    v=np.clip(x0+z*(hi-lo)*0.1,lo,hi)
    for p,q in zip(P,v): setattr(C,p,float(q))
    e=err()
    if e<best[0]: best[:]=[e,v]; print("%.2f %s"%(e," ".join("%s=%.4g"%(p[:12],q) for p,q in zip(P,v))),flush=True)
    return e
n=len(P); minimize(f,np.zeros(n),method="Nelder-Mead",options={"maxfev":int(sys.argv[2]),"initial_simplex":np.vstack([np.zeros(n)]+[np.eye(n)[i] for i in range(n)]),"xatol":0.02,"fatol":0.02})
for p,q in zip(P,best[1]): setattr(C,p,float(q)); print("FIT %s = %.5g"%(p,q))
err(True)
