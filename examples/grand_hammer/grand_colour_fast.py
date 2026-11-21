import sys,os,numpy as np
args=sys.argv[1:]; sys.argv=['x','none']
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'grand_hammer_fast.py')).read().split('if __name__=="__main__":')[0])
from scipy.optimize import minimize
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
def err_abs(verbose=False):
    e=[]
    for k in KEYS:
        for d in (1,3):
            m=thirds_model(k,d); r=R[(d,k)]
            w=((r>-40)|(m>-40))&np.isfinite(r)&np.isfinite(m)
            e.extend((np.maximum(m,-60)-np.maximum(r,-60))[w])
    return float(np.sqrt(np.mean(np.square(e))))
names=args[0].split(',')
B={'tonal_dampening':(0.3,2.5),'octave_dampening':(-0.3,0.3),'board_high_hz':(1500,20000),'board_low_hz':(20,300),
   'board_body_gain':(0.0,3.0),'board_body_hz':(100,1000),'board_high_order':(0.5,4.0)}
bn=[B[n] for n in names]; best=[1e9,None]
print("start %.2f"%err_abs())
def f(x):
    for n,q in zip(names,x): setattr(C,n,float(q))
    e=err_abs()
    if e<best[0]: best[:]=[e,np.array(x)]
    return e
rng=np.random.default_rng(2)
for s0 in [np.array([float(getattr(C,n)) for n in names])]+[np.array([rng.uniform(*b) for b in bn]) for _ in range(6)]:
    minimize(f,s0,method="L-BFGS-B",bounds=bn,options={"maxfun":300})
for n,q in zip(names,best[1]): setattr(C,n,float(q)); print("FIT %s = %.5g"%(n,q))
print("BEST abs %.2f"%best[0])
