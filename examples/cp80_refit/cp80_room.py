import sys,os,numpy as np
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'cp80_variant_ab.py')).read().split("U.FIT_KEYS=")[0])
from collections import defaultdict
pts=[]
def partials(x,sr,f0,a=0.05,b=0.55,nmax=80):
    s=x[int(a*sr):int(b*sr)]; n=1<<17; X=np.abs(np.fft.rfft(s*np.hanning(len(s)),n)); f=np.fft.rfftfreq(n,1/sr)
    out={}
    B=C(f0,0,0.8,1.0).inharmonicity_coefficient_for_frequency(f0)
    for h in range(1,nmax+1):
        fh=h*f0*np.sqrt(1+B*h*h)
        if fh>9000: break
        w=(f>fh*0.985)&(f<fh*1.015); out[h]=(fh,20*np.log10(X[w].max()+1e-12))
    return out
for lay,d in (("FF",3),("MP",2)):
    recs=U.recordings(d)
    for k in sorted(recs):
        f0=440*2**((k-69)/12)
        x,sr=U.load(recs[k]); x=x[U.onset(x,sr):]
        y,s2=U.render(2,k,U.vel_for(k,d),0.7); y=y[U.onset(y,s2):]
        r,o=partials(x,sr,f0),partials(y,s2,f0)
        hs=[h for h in r if h in o and r[h][1]>max(v[1] for v in r.values())-50]
        dd=np.array([r[h][1]-o[h][1] for h in hs]); dd-=np.median(dd)
        for h,v in zip(hs,dd): pts.append((r[h][0],v,k))
pts=np.array(pts)
edges=2**np.arange(np.log2(30),np.log2(9000),1/6)
print("rec - ours by absolute frequency (each note's median removed), 1/6 octave: Hz  median  iqr  n  keys")
for lo,hi in zip(edges[:-1],edges[1:]):
    m=(pts[:,0]>=lo)&(pts[:,0]<hi)
    if m.sum()>=3:
        q=pts[m,1]; print("%6.0f %6.1f %5.1f %4d %3d"%(np.sqrt(lo*hi),np.median(q),np.subtract(*np.percentile(q,[75,25])),m.sum(),len(set(pts[m,2]))))
