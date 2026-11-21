"""A partial ladder that cannot lose the partials: f0 (within half a semitone
of the key) and B (1e-6..2e-3) searched together for the pair whose predicted
partials 1-16 land on the most energy, then each partial read at its peak."""
import numpy as np, upright_fit as U
def ladder(x,sr,key,nmax=12,a=0.03,b=0.53):
    t0=U.onset(x,sr); X,f=U.spectrum(x,sr,t0,a,b); df=f[1]-f[0]
    fk=440.0*2**((key-69)/12.0); best=(-1,None,None)
    Bs=np.concatenate([[0.0],np.logspace(-6,np.log10(2e-3),60)])
    for f0 in fk*2**(np.linspace(-0.5,0.5,41)/12):
        for B in Bs:
            n=np.arange(1,17); fn=n*f0*np.sqrt(1+B*n*n); fn=fn[fn<0.45*sr]
            idx=np.round(fn/df).astype(int)
            s=sum(X[max(i-2,0):i+3].max() for i in idx)
            if s>best[0]: best=(s,f0,B)
    _,f0,B=best; out=[]
    for n in range(1,nmax+1):
        fn=n*f0*np.sqrt(1+B*n*n); w=(f>fn*(1-0.012))&(f<fn*(1+0.012))
        out.append(10*np.log10(X[w].max()+1e-30) if w.any() else np.nan)
    out=np.array(out); return out-np.nanmax(out),f0,B
