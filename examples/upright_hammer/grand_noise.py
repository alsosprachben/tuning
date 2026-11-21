import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
from scipy.signal import butter,sosfiltfilt
U.REF[0]='steinway'
C=T.GrandPianoProperties
def cut(x,sr): return x[max(U.onset(x,sr)-int(.002*sr),0):]
def meas(x,sr,f0):
    seg=x[:int(.03*sr)]; n=1<<15
    X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2; f=np.fft.rfftfreq(n,1/sr)
    m=(f>200)&(f<8000); ph=(f/f0)%1.0
    gap=10*np.log10(X[m&(ph>0.3)&(ph<0.7)].mean()/X[m&((ph<0.1)|(ph>0.9))].mean())
    s=sosfiltfilt(butter(4,[25,0.7*f0],'band',fs=sr,output='sos'),x)
    sub=10*np.log10(np.mean(s[:int(.02*sr)]**2)/np.mean(x[:int(.1*sr)]**2))
    hi=sosfiltfilt(butter(4,[2000,8000],'band',fs=sr,output='sos'),x)
    hr=10*np.log10(np.mean(hi[:int(.02*sr)]**2)/np.mean(x[:int(.1*sr)]**2))
    return gap,sub,hr
mode=sys.argv[1]
if mode=='new':
    C.max_partial_hz=10000.0; C.hammer_model=True
    for kv in os.environ['SETV'].split(','):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
    if os.environ.get('SN'): C.strike_noise_db=tuple((h,db+float(os.environ['SN'])) for h,db in C.strike_noise_db)
if mode=='new_nonoise':
    C.max_partial_hz=10000.0; C.hammer_model=True
    for kv in os.environ['SETV'].split(','):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
    C.strike_noise_db=()
for d in (1,3):
    recs=U.recordings(d)
    for k in (38,54,70,86):
        f0=440*2**((k-69)/12)
        r=meas(cut(*U.load(recs[k])),U.load(recs[k])[1],f0) if False else None
        x,sr=U.load(recs[k]); x=cut(x,sr); r=meas(x,sr,f0)
        y,s2=U.render(0,k,U.vel_for(k,d),0.6); y=cut(y,s2); o=meas(y,s2,f0)
        print("%-11s %-4s dyn%d  noise-between-harmonics rec %5.1f ours %5.1f | thump rec %5.1f ours %5.1f | 2-8k first 20ms rec %5.1f ours %5.1f"%(mode,U.name(k),d,r[0],o[0],r[1],o[1],r[2],o[2]))
