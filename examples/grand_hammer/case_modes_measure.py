"""Each case mode on treble takes (below the fundamental): its peak in the
first 40 ms re the fundamental's, and its decay (dB/s, a line through its
level every 20 ms over 20-260 ms). REC=1 the takes; else our render (SETV)."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]=os.environ.get('REF','upright')
C=getattr(T,os.environ.get('CLS','UprightPianoProperties')); PROG=int(os.environ.get('PROG','1'))
if not os.environ.get('REC'):
    for kv in filter(None,os.environ.get('SETV','').split(',')):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
    if os.environ.get('VELPTS'): C.hammer_vel_power_points=eval(open(os.environ['VELPTS']).read())
    if os.environ.get('LEVELPTS'): C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read())
    if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
    if os.environ.get('RINGVP'): C.ring_vel_power=float(os.environ['RINGVP'])
MODES=[float(m) for m in os.environ.get('MODES','143,240,322,377,522,598,640,955').split(',')]
KEYS=[int(k) for k in os.environ.get('KEYS','81,85,89,93,97,101').split(',')]
W=int(0.04*44100); n=1<<15
def lv(x,sr,t0,t,f0s):
    seg=x[t0+int(t*sr):t0+int(t*sr)+W]
    X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2; f=np.fft.rfftfreq(n,1/sr)
    return [10*np.log10(X[(f>m*0.98)&(f<m*1.02)].max()+1e-20) for m in f0s]
out={}
for D in (1,3):
    recs=U.recordings(D)
    for k in KEYS:
        f0=440*2**((k-69)/12)
        if os.environ.get('REC'): x,sr=U.load(recs[k])
        else: x,sr=U.render(PROG,k,U.vel_for(k,D),0.6)
        t0=U.onset(x,sr)
        ms=[m for m in MODES if m<0.8*f0]
        ref=lv(x,sr,t0,0.0,[f0])[0]
        ts=np.arange(0.02,0.26,0.02); L=np.array([lv(x,sr,t0,t,ms) for t in ts])
        l0=lv(x,sr,t0,0.0,ms); l1=lv(x,sr,t0,0.12,ms)
        for i,m in enumerate(ms):
            s=np.polyfit(ts,L[:,i],1)[0]
            out.setdefault(m,[]).append((D,k,l0[i]-ref,-s,l1[i]-ref))
print("mode Hz: first 40 ms soft | hard (dB re fundamental) | at 120 ms soft | hard | decay dB/s (median)")
for m in MODES:
    r=out.get(m,[])
    if not r: continue
    s=[q[2] for q in r if q[0]==1]; h=[q[2] for q in r if q[0]==3]; d=[q[3] for q in r]
    s2=[q[4] for q in r if q[0]==1]; h2=[q[4] for q in r if q[0]==3]
    print("  %5.0f  %6.1f | %6.1f | %6.1f | %6.1f | %6.0f"%(m,np.median(s),np.median(h),np.median(s2),np.median(h2),np.median(d)))
