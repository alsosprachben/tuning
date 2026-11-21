"""The grand's hammer fitted FAST: the hard-minus-soft third-octave change
computed from the voice's own partial levels (harmonic_volume: the comb's
filling, the simulated hammer, the board) and decays, no render."""
import sys,os,time,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
from scipy.optimize import minimize
U.REF[0]='steinway'; KEYS=tuple(int(k) for k in os.environ['KEYS'].split(',')) if os.environ.get('KEYS') else U.STEINWAY_KEYS
C=T.GrandPianoProperties
C.max_partial_hz=10000.0; C.hammer_model=True
E3=U.E3
R={}
for d in (1,3):
    recs=U.recordings(d)
    for k in KEYS: R[(d,k)]=U.thirds(*U.load(recs[k]),k)
REC={k:R[(3,k)]-R[(1,k)] for k in KEYS}
def thirds_model(k,d):
    f0=440*2**((k-69)/12); vel=U.vel_for(k,d)
    p=C(f0,0.0,(vel/127.0)**2,1.0)
    B=p.inharmonicity_coefficient_for_frequency(f0)
    n=np.arange(1,int(10000/f0)+1)
    a=np.array([p.harmonic_volume(int(h)) for h in n])
    dd=np.array([p.harmonic_decay(int(h)) for h in n])          # dB/s
    r=dd*np.log(10)/10.0                                          # power decay rate
    w=(np.exp(-r*0.03)-np.exp(-r*0.53))/np.maximum(r,1e-9)
    fn=n*f0*np.sqrt(1+B*n*n)
    P=a*a*w
    b=np.array([P[(fn>=lo)&(fn<hi)].sum() for lo,hi in zip(E3[:-1],E3[1:])])
    b=10*np.log10(b+1e-30); b=np.maximum(b-b.max(),-50.0)
    return np.where(E3[1:]>f0*0.89,b,np.nan)
W_ABS=float(os.environ.get('W_ABS','0'))
def err(verbose=False):
    if W_ABS:
        ea=[]
        for k in KEYS:
            for d in (1,3):
                m=thirds_model(k,d); r=R[(d,k)]
                w=((r>-40)|(m>-40))&np.isfinite(r)&np.isfinite(m)
                ea.extend((np.maximum(m,-60)-np.maximum(r,-60))[w])
        ed=err_dyn(verbose)
        return float(np.sqrt(ed**2+W_ABS*np.mean(np.square(ea))))
    return err_dyn(verbose)
def err_dyn(verbose=False):
    e=[]
    for k in KEYS:
        o1,o3=thirds_model(k,1),thirds_model(k,3); od=o3-o1; r=REC[k]
        w=np.isfinite(od)&np.isfinite(r)&(R[(3,k)]>-45)&(o3>-45)
        e.extend(od[w]-r[w])
        if verbose:
            q=(od-r)[np.isfinite(od-r)]; print("   %-4s %s"%(U.name(k)," ".join("%4.0f"%v for v in q[::2])))
    return float(np.sqrt(np.mean(np.square(e))))
if __name__=="__main__":
    for kv in filter(None,os.environ.get('SETV','').split(',')):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
    if sys.argv[1]=="check":
        t=time.time(); print("fast hard-minus-soft rms %.2f (%.1fs)"%(err(True),time.time()-t)); sys.exit()
    names=sys.argv[2].split(',')
    BOUNDS={'hammer_logk':(8.0,13.0),'hammer_logk_slope':(0.15,0.6),'hammer_logk_curve':(-0.08,0.08),'hammer_p_lo':(1.8,4.0),'hammer_p_hi':(1.8,4.0),
            'hammer_speed_lo':(0.2,1.0),'hammer_speed_hi':(2.0,12.0),'hammer_alpha':(0.0,0.95),'hammer_log_tau':(-6.0,-3.0),
            'tonal_dampening':(0.5,2.0),'strike_depth':(0.0,1.0),'strike_fill_fraction':(0.0,1.0)}
    bnds=[BOUNDS[n] for n in names]; ev=[0]; best=[1e9,None]
    def f(x):
        for n,q in zip(names,x): setattr(C,n,float(q))
        e=err(); ev[0]+=1
        if e<best[0]: best[:]=[e,np.array(x)]; print("  %5d  %.3f  %s"%(ev[0],e," ".join("%s=%.4g"%(n,q) for n,q in zip(names,x))),flush=True)
        return e
    rng=np.random.default_rng(1)
    starts=[np.array([float(getattr(C,n)) for n in names])]+[np.array([rng.uniform(*b) for b in bnds]) for _ in range(int(sys.argv[3]))]
    for s0 in starts:
        minimize(f,s0,method="L-BFGS-B",bounds=bnds,options={"maxfun":int(sys.argv[4]),"eps":1e-3})
    for n,q in zip(names,best[1]): setattr(C,n,float(q)); print("FIT %s = %.5g"%(n,q))
    print("BEST %.3f after %d evaluations"%(err(True),ev[0]))
