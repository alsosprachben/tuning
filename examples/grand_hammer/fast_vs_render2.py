import sys,os,numpy as np
sys.argv=['x','none']
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'grand_hammer_fast.py')).read().split('if __name__=="__main__":')[0])
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
ef=[];er=[]
for k in KEYS:
    fm=[thirds_model(k,d) for d in (1,3)]
    rn=[U.thirds(*U.render(0,k,U.vel_for(k,d),0.7),k) for d in (1,3)]
    r=REC[k]
    for o,e in ((fm,ef),(rn,er)):
        od=o[1]-o[0]; w=np.isfinite(od)&np.isfinite(r)&(R[(3,k)]>-45)&(o[1]>-45); e.extend(od[w]-r[w])
    q=(rn[1]-rn[0])-(fm[1]-fm[0]); q=q[np.isfinite(q)]
    print("%-4s render-fast %s"%(U.name(k)," ".join("%4.0f"%v for v in q)))
print("fast %.2f  render %.2f"%(np.sqrt(np.mean(np.square(ef))),np.sqrt(np.mean(np.square(er)))))
