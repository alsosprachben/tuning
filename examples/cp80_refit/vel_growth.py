"""Velocity 40 -> 120: growth of the whole note (K-weighted, sfx_levels) and of
its fundamental (first 100 ms peak), for ours, VSCO's takes and GU's upright."""
import sys,os,tempfile,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T, sfx_levels as S
from scipy.io import wavfile
U.REF[0]=os.environ.get('REF','upright'); C=getattr(T,os.environ.get('CLS','UprightPianoProperties')); PROG=int(os.environ.get('PROG','1'))
if os.environ.get('VPTS'): C.hammer_vel_power_points=eval(os.environ['VPTS'])
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,eval(v_))
if os.environ.get('LEVELPTS'): C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read())
if os.environ.get('VELPTS'): C.hammer_vel_power_points=eval(open(os.environ['VELPTS']).read())
if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
KEYS=[int(k) for k in os.environ.get('KEYS','45,57,69,77,81,85,89,93,97,101').split(',')]
n=1<<15
def fund(x,sr,f0):
    t0=U.onset(x,sr); seg=x[t0:t0+int(0.1*sr)]
    X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2; f=np.fft.rfftfreq(n,1/sr)
    return 10*np.log10(X[(f>f0*0.97)&(f<f0*1.03)].max()+1e-20)
def klev(x,sr): return S.k_level([np.asarray(x,float)],sr)[1] if np.ndim(S.k_level([np.asarray(x,float)],sr)) else S.k_level([np.asarray(x,float)],sr)
d=tempfile.mkdtemp(); S.REF=(PROG,60)
gu={v:S.sf_levels(S.gu_path(),tuple((PROG,k) for k in KEYS),v,d) for v in (40,120)}
print("key   | whole note dB: ours  rec  GU | fundamental dB: ours  rec")
for k in KEYS:
    f0=440*2**((k-69)/12); o=[];r=[]
    for D,v in ((1,40),(3,120)):
        y,sr=U.render(PROG,k,v,1.0); o.append((S.levels([np.asarray(y,float)],sr)[1],fund(y,sr,f0)))
        rk=U.recordings(D)
        if k in rk: x,sr2=U.load(rk[k]); x=np.asarray(x,float); r.append((S.levels([x],sr2)[1],fund(x,sr2,f0)))
        else: r.append((np.nan,np.nan))
    g=gu[120][(PROG,k)][1]-gu[40][(PROG,k)][1]
    print("%-5s | %5.1f %5.1f %5.1f | %5.1f %5.1f"%(U.name(k),o[1][0]-o[0][0],r[1][0]-r[0][0],g,o[1][1]-o[0][1],r[1][1]-r[0][1]),flush=True)
