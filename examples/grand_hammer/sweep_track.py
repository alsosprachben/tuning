"""A sweeping notch in a note's partials: each partial's level every 50 ms
(0.2-3 s) minus its own straight-line decay; per frame, the log2 harmonic
number weighted by how far each partial sits UNDER its line (the dip's
centre); the dip's speed in octaves a second (a line through the centres),
and how well a line fits (r)."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples');sys.path.insert(0,'..')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T, robust_ladder as RL
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.ring_db=eval(open('../gring2.txt').read()); C.ring_tuned=False
C.strike_noise_vel_power_register=eval(open('../gkvp1.txt').read()); C.string_gain=(0.4,0.3)
if os.environ.get('SC'): C.strike_curve=tuple(float(x) for x in os.environ['SC'].split('/'))
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
if os.environ.get('HPHASE'):
    import hphase; hphase.install(C)
k=int(os.environ.get('KEY','22')); d=int(os.environ.get('DYN','1')); lab=os.environ.get('LAB','')
x,sr=U.load(U.recordings(d)[k]) if lab=='rec' else U.render(0,k,U.vel_for(k,d),3.2)
_,f0,B=RL.ladder(x,sr,k)
t0=U.onset(x,sr); x=x[t0:]
N=40; ts=np.arange(0.2,3.0,0.05); W=int(0.1*sr); n=1<<16; f=np.fft.rfftfreq(n,1/sr)
M=np.zeros((N,len(ts)))
for j,t in enumerate(ts):
    seg=x[int(t*sr):int(t*sr)+W]; X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2
    for h in range(1,N+1):
        fh=h*f0*np.sqrt(1+B*h*h); w=(f>fh*0.99)&(f<fh*1.01)
        M[h-1,j]=10*np.log10(X[w].max()+1e-30)
R=np.array([row-np.polyval(np.polyfit(ts,row,1),ts) for row in M])
R=R[3:]   # from h4 up
lh=np.log2(np.arange(4,N+1))
cen=[]
for j in range(len(ts)):
    w=np.maximum(-R[:,j],0)**2
    cen.append(np.sum(w*lh)/np.sum(w) if w.sum()>0 else np.nan)
cen=np.array(cen); ok=np.isfinite(cen)
sl=np.polyfit(ts[ok],cen[ok],1)[0]; r=np.corrcoef(ts[ok],cen[ok])[0,1]
print("%-14s dip centre moves %+.2f octaves/s (line fit r %+.2f); centre at 0.5 s h%.0f, 2.5 s h%.0f"%(lab,sl,r,2**np.interp(0.5,ts,cen),2**np.interp(2.5,ts,cen)))
if os.environ.get('SHOW'):
    print("partial:   "+" ".join("%3d"%h for h in range(4,N+1,2)))
    for t in (0.3,0.8,1.3,1.8,2.3,2.8):
        j=int(round((t-0.2)/0.05)); print("t %.1f s:  "%t+" ".join("%3.0f"%v for v in R[::2,j]))
