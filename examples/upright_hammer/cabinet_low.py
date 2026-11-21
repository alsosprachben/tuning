"""Treble notes (f0 >= A5): the spectrum BELOW the fundamental -- no partial
lives there, so what is there is the knock and what it rings (the case, the
board). Peaks that repeat in Hz across keys, with their ring time."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
import upright_fit as U
from scipy.signal import find_peaks
U.REF[0]=os.environ.get('REF','upright')
KEYS=[int(k) for k in os.environ.get('KEYS','81,85,89,93,97,101').split(',')]
n=1<<15
for D in (1,3):
    recs=U.recordings(D); rows=[]
    for k in KEYS:
        if k not in recs: continue
        x,sr=U.load(recs[k]); t0=U.onset(x,sr); f0=440*2**((k-69)/12)
        def spec(a,b):
            seg=x[t0+int(a*sr):t0+int(b*sr)]
            X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2; return 10*np.log10(X+1e-20)
        f=np.fft.rfftfreq(n,1/sr); s0=spec(0,0.06); s1=spec(0.06,0.12); s2=spec(0.15,0.25)
        m=(f>50)&(f<0.8*f0)
        ref=np.max(spec(0,0.06)[(f>0.9*f0)&(f<1.1*f0)])
        pk,pr=find_peaks(s0[m],prominence=6,distance=int(15/(f[1])))
        top=sorted(pk,key=lambda p:-s0[m][p])[:6]
        rows.append((k,[(f[m][p],s0[m][p]-ref,(s0[m][p]-s1[m][p]),(s0[m][p]-s2[m][p])) for p in sorted(top)]))
    print("dyn %d: peaks under the fundamental, first 60 ms: Hz (dB re fundamental; fall by 60-120 ms / 150-250 ms)"%D)
    for k,pp in rows:
        print("  %-4s "%U.name(k)+"  ".join("%5.0f(%+.0f;%.0f/%.0f)"%q for q in pp))
