"""The Spectra-Tone's rotor rate through the speed changes (st_change.wav): the
fundamental of each 4 s window's level swing and pitch swing (harmonics 1-6),
1 s apart. The two readings agree wherever the rotor is steady."""
import sys,os,numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import spectratone_fit as F
x,sr=F.load('st_change.wav')
def rot(z,lo=0.4,hi=3.5):
    z=z-z.mean(); a=10**(z/20); a=a/a.mean()-1
    nfft=1<<14; P=np.abs(np.fft.rfft(a*np.hanning(len(a)),nfft)); f=np.fft.rfftfreq(nfft,1/F.FS_ENV)
    cand=np.linspace(lo,hi,600); sc=[sum(np.interp(k*c,f,P) for k in range(1,7) if k*c<20) for c in cand]
    # prefer the lowest rate that explains the pattern: penalise rates whose half also scores as well
    return cand[int(np.argmax(sc))]
for o,(lo,hi) in ((6,(28.0,100.0)),(7,(101.0,189.0))):
    y=F.band(x[int(lo*sr):int(hi*sr)],sr,F.C[o]); z=F.env_db(y,sr)
    cents=F.inst_cents(y,sr,F.C[o])
    w,s=int(4*F.FS_ENV),int(1*F.FS_ENV); row=[]
    for i in range(0,len(z)-w,s):
        r1=rot(z[i:i+w]); r2=rot(cents[i:i+w])
        row.append("%.0f:%.2f/%.2f"%(lo+(i+w/2)/F.FS_ENV,r1,r2))
    print("C%d (time: rate from level / from pitch)"%o); print("  "+" ".join(row))
