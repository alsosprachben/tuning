"""How far each partial sits off the stiff string's law: partial peaks from a
long, fine spectrum (0.1-2.6 s, zero-padded, peak interpolated), the law
n f0 sqrt(1 + B n^2) fitted to them, each partial's offset in cents."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples');sys.path.insert(0,'..')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T, robust_ladder as RL
from scipy.optimize import least_squares
U.REF[0]='steinway'; C=T.GrandPianoProperties
if os.environ.get('PCS'): C.partial_cents_scatter=float(os.environ['PCS'])
k=int(os.environ.get('KEY','22')); d=int(os.environ.get('DYN','1')); lab=os.environ.get('LAB','')
x,sr=U.load(U.recordings(d)[k]) if lab=='rec' else U.render(0,k,U.vel_for(k,d),2.8)
_,f0,B=RL.ladder(x,sr,k); t0=U.onset(x,sr); seg=x[t0+int(0.1*sr):t0+int(2.6*sr)]
n=1<<20; X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n)); f=np.fft.rfftfreq(n,1/sr); df=f[1]
ns=[];fs=[]
for h in range(2,int(os.environ.get('NMAX','30'))+1):
    fh=h*f0*np.sqrt(1+B*h*h); w=np.flatnonzero((f>fh*0.995)&(f<fh*1.005))
    if not len(w): continue
    i=w[np.argmax(X[w])]
    if X[i]<X[w].mean()*3: continue
    a,b_,c=np.log(X[i-1:i+2]+1e-30); p=0.5*(a-c)/(a-2*b_+c)
    ns.append(h); fs.append(f[i]+p*df)
ns=np.array(ns,float); fs=np.array(fs)
r=least_squares(lambda q: 1200*np.log2(fs/(ns*q[0]*np.sqrt(1+q[1]*ns*ns))),[f0,max(B,1e-6)])
res=1200*np.log2(fs/(ns*r.x[0]*np.sqrt(1+r.x[1]*ns*ns)))
print("%-6s f0 %.3f B %.2e  offsets off the law, cents (partials 2-%d): std %.2f, max %.1f"%(lab,r.x[0],r.x[1],int(ns.max()),np.std(res),np.abs(res).max()))
print("        "+" ".join("%+.1f"%v for v in res))
