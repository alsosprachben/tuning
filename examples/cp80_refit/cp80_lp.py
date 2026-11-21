import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0")
import upright_fit as U
U.REF[0]='cp80'; M=U._cp80_map()
F=[1000,1600,2500,3150,4000,5000,6300,8000,10000,12500,16000,20000]
def spec(x,sr):
    s=x[:int(0.5*sr)]; X=np.abs(np.fft.rfft(s*np.hanning(len(s)),1<<16))**2; f=np.fft.rfftfreq(1<<16,1/sr)
    return np.array([10*np.log10(X[(f>=c/2**(1/6))&(f<c*2**(1/6))].sum()+1e-20) for c in F])
R=[];O=[]
for k in sorted(M):
    if k<45 or k>80 or "FF" not in M[k]: continue
    x,sr=U.load(M[k]["FF"]); x=x[U.onset(x,sr):]
    y,s2=U.render(2,k,115,0.6); y=y[U.onset(y,s2):]
    r,o=spec(x,sr),spec(y,s2); r-=r[0]; o-=o[0]; R.append(r);O.append(o)
R=np.median(R,0);O=np.median(O,0)
print("third-octave, first 0.5 s, FF, keys A2-G#5, median, dB re 1 kHz")
print("Hz   "+" ".join("%6d"%c for c in F)); print("rec  "+" ".join("%6.1f"%v for v in R)); print("ours "+" ".join("%6.1f"%v for v in O))
print("diff "+" ".join("%6.1f"%v for v in O-R))
# the noise floor: a take's last 0.3 s
x,sr=U.load(M[60]["FF"]); print("rec C4 FF tail (floor) "+" ".join("%6.1f"%v for v in spec(x[-int(.5*sr):],sr)-spec(x[U.onset(x,sr):],sr)[0]))
