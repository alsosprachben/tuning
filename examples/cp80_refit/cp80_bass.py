import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; M=U._cp80_map()
F=[250,500,1000,1600,2500,3150,4000,5000,6300,8000,10000]
def spec(x,sr):
    s=x[:int(0.5*sr)]; X=np.abs(np.fft.rfft(s*np.hanning(len(s)),1<<16))**2; f=np.fft.rfftfreq(1<<16,1/sr)
    return np.array([10*np.log10(X[(f>=c/2**(1/6))&(f<c*2**(1/6))].sum()+1e-20) for c in F])
print("Hz        "+" ".join("%6d"%c for c in F))
for k in sorted(M):
    if k>57 or "FF" not in M[k]: continue
    x,sr=U.load(M[k]["FF"]); x=x[U.onset(x,sr):]
    y,s2=U.render(2,k,115,0.6); y=y[U.onset(y,s2):]
    r,o=spec(x,sr),spec(y,s2); r-=r[2]; o-=o[2]
    print("%-4s ours-rec "%U.name(k)+" ".join("%6.1f"%v for v in o-r))
