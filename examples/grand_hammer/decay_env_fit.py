"""The grand's decay law and aftersound fitted to each band's beat-averaged
level over 3 s (band_env.py's reading), recorded vs ours, keys KEYS at f."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
from scipy.signal import butter,sosfilt
from scipy.optimize import minimize
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.ring_db=eval(open('../gring2.txt').read()); C.ring_tuned=False
C.strike_noise_vel_power_register=eval(open('../gkvp1.txt').read())
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
if os.environ.get('SG'): C.string_gain=tuple(float(v) for v in os.environ['SG'].split('/'))
BANDS=((63,125),(125,250),(250,500),(500,1000),(1000,2000),(2000,4000),(4000,8000))
TS=(0.25,0.5,1.0,1.5,2.0,3.0)
KEYS=[int(v) for v in os.environ.get('KEYS','30,46,62,70,78,86,94').split(',')]
SOS={b:butter(4,list(b),'band',fs=44100,output='sos') for b in BANDS}
def env(x,sr):
    t0=U.onset(x,sr); x=x[t0:]; tot=np.mean(x[:int(0.25*sr)]**2)
    out=[]
    for b in BANDS:
        y=sosfilt(SOS[b],x); r0=np.mean(y[:int(0.25*sr)]**2)
        out.append([10*np.log10(r0/tot+1e-30)]+[10*np.log10(np.mean(y[int(t*sr):int((t+0.25)*sr)]**2)/r0+1e-30) for t in TS])
    return np.array(out)
REC={}
for k in KEYS:
    x,sr=U.load(U.recordings(3)[k]); REC[k]=env(x,sr)
def err(verbose=False):
    e=[]
    for k in KEYS:
        n0=len(e)
        y,sr=U.render(0,k,U.vel_for(k,3),3.5); o=env(y,sr); r=REC[k]; f0=440*2**((k-69)/12)
        for i,b in enumerate(BANDS):
            if b[1]<f0*0.9 or r[i,0]<-35: continue
            for j in range(1,len(TS)+1):
                if TS[j-1]>=0.5 and r[i,j]>-60: e.append((max(o[i,j],-110)-r[i,j]))
        if os.environ.get('PERKEY'): print("   %-4s rms %5.1f mean %+5.1f"%(U.name(k),np.sqrt(np.mean(np.square(e[n0:]))),np.mean(e[n0:])))
    return float(np.sqrt(np.mean(np.square(e))))
P=sys.argv[1].split(',')
if len(sys.argv)<3:
    print("band-envelope rms %.2f dB"%err()); sys.exit()
x0=np.array([float(getattr(C,p)) or 1.0 for p in P]); best=[1e9,None]
def f(z):
    v=np.exp(z)*x0
    for p,q in zip(P,v): setattr(C,p,float(q))
    e=err()
    if e<best[0]: best[:]=[e,v]; print("  %6.2f dB  %s"%(e," ".join("%s=%.4g"%(p,q) for p,q in zip(P,v))),flush=True)
    return e
n=len(P)
minimize(f,np.zeros(n),method="Nelder-Mead",options={"maxfev":int(sys.argv[2]),"initial_simplex":np.vstack([np.zeros(n)]+[0.5*np.eye(n)[i] for i in range(n)]),"xatol":0.02,"fatol":0.02})
for p,q in zip(P,best[1]): print("FIT %s = %.5g"%(p,q))
print("BEST %.2f"%best[0])
