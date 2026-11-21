"""Peaks in the attack's noise between the partials, common across keys
(fixed in Hz, whatever the note): the case's modes, if the knock rings them."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
import upright_fit as U
from scipy.signal import find_peaks
U.REF[0]=os.environ.get('REF','upright')
KEYS=[int(k) for k in os.environ.get('KEYS','57,61,65,69,73,77,81,85,89,93,97,101').split(',')]
D=int(os.environ.get('DYN','3'))
n=1<<14; sr0=None; acc=[]; masks=[]
recs=U.recordings(D)
for k in KEYS:
    if k not in recs: continue
    x,sr=U.load(recs[k]); t0=U.onset(x,sr)
    a,b=float(os.environ.get('A','0.0')),float(os.environ.get('B','0.08'))
    seg=x[t0+int(a*sr):t0+int(b*sr)]
    X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2; f=np.fft.rfftfreq(n,1/sr)
    f0=440*2**((k-69)/12); B=0.0
    # away from the partials (within 4% of f0 of any harmonic: out)
    ph=(f/f0)%1.0; m=(ph>0.12)&(ph<0.88)
    acc.append(10*np.log10(X+1e-20)); masks.append(m)
A=np.array(acc); M=np.array(masks)
# normalise each key by its median between-partial level 200-6000 Hz
band=(f>80)&(f<8000)
for i in range(len(A)):
    A[i]-=np.median(A[i][M[i]&band])
S=np.where(M,A,np.nan)
with np.errstate(all='ignore'):
    import warnings; warnings.simplefilter('ignore')
    med=np.nanmedian(S,0); cnt=np.sum(M,0)
ok=band&(cnt>=len(A)//2)
sm=np.convolve(np.nan_to_num(med),np.ones(3)/3,'same')
pk,pr=find_peaks(np.where(ok,sm,-99),prominence=4,distance=3)
print("keys %d, dyn %d, window %.0f-%.0f ms; peaks common across keys (median between-partial level, dB re median):"%(len(A),D,a*1e3,b*1e3))
for p in sorted(pk,key=lambda p:-pr['prominences'][list(pk).index(p)])[:20]:
    # how many keys show a local peak there
    hits=sum(1 for i in range(len(A)) if M[i][p] and A[i][p]>np.nanmedian(A[i][max(0,p-12):p+12]) + 3)
    print("  %7.0f Hz  %+5.1f dB  prominence %4.1f  keys showing it %d/%d"%(f[p],sm[p],pr['prominences'][list(pk).index(p)],hits,int(cnt[p])))
