import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0")
import upright_fit as U
from scipy.signal import butter,sosfiltfilt
U.REF[0]='cp80'; M=U._cp80_map()
W=[(0,.01),(.01,.02),(.02,.04),(.04,.08),(.08,.16)]
def cut(x,sr): return x[max(U.onset(x,sr)-int(.002*sr),0):]
def sub(x,sr,f0):
    s=sosfiltfilt(butter(4,[25,0.7*f0],'band',fs=sr,output='sos'),x)
    ref=10*np.log10(np.mean(x[int(.0*sr):int(.1*sr)]**2))
    return [10*np.log10(np.mean(s[int(a*sr):int(b*sr)]**2)+1e-20)-ref for a,b in W]
def between(x,sr,f0,a=0,b=.03):
    seg=x[int(a*sr):int(b*sr)]; n=1<<15
    X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2; f=np.fft.rfftfreq(n,1/sr)
    m=(f>200)&(f<6000)
    ph=(f/f0)%1.0; gap=m&(ph>0.3)&(ph<0.7); on=m&((ph<0.1)|(ph>0.9))
    return 10*np.log10(X[gap].mean()/X[on].mean())
print("sub-f0 band (25 Hz-0.7 f0) by window 0-10,10-20,20-40,40-80,80-160 ms, dB re the note's first 100 ms; 'gap' = between-harmonics / on-harmonics power, first 30 ms")
for k in sorted(M):
    if k>90: continue
    f0=440*2**((k-69)/12)
    for lay in ("MP","FF"):
        if lay not in M[k]: continue
        x,sr=U.load(M[k][lay]); x=cut(x,sr)
        y,s2=U.render(2,k,U.CP80_LAYERS[lay],0.5); y=cut(y,s2)
        print("%-4s %-2s sub rec %s | ours %s   gap rec %5.1f ours %5.1f"%(U.name(k),lay," ".join("%4.0f"%v for v in sub(x,sr,f0))," ".join("%4.0f"%v for v in sub(y,s2,f0)),between(x,sr,f0),between(y,s2,f0)))
