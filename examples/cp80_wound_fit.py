#!/usr/bin/env python3
"""The CP80 wound strings' zing (tonelib.ElectricGrandProperties.wound_*), by grid:
    cp80_wound_fit.py DECAYS CORNERS ZINGS   (comma lists; probe DECAY to try one)
Run from the tuning root."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0")
import upright_fit as U, tonelib as T
from scipy.signal import butter,sosfiltfilt
U.REF[0]='cp80'; M=U._cp80_map()
W=[(.005,.01),(.01,.02),(.02,.04),(.04,.08),(.08,.16),(.16,.32),(.32,.64)]
BANDS=[(1600,3200),(3200,8000)]
def course(x,sr,k):
    out=[]; f0=440*2**((k-69)/12)
    for lo,hi in BANDS:
        s=sosfiltfilt(butter(4,[max(lo,1.5*f0),hi],'band',fs=sr,output='sos'),x)
        ref=10*np.log10(np.mean(x[int(.3*sr):int(.6*sr)]**2)+1e-20)   # the whole note's level, not the band's
        out.append(np.array([10*np.log10(np.mean(s[int(a*sr):int(b*sr)]**2)+1e-20) for a,b in W])-ref)
    return np.concatenate(out)
KEYS=[k for k in sorted(M) if k<=57]
REC={}
for k in KEYS:
    for lay in ("MP","FF"):
        if lay in M[k]:
            x,sr=U.load(M[k][lay]); x=x[max(U.onset(x,sr)-int(.001*sr),0):]
            REC[(k,lay)]=course(x,sr,k)
def err(verbose=False):
    e=[];rows=[]
    for (k,lay),r in REC.items():
        y,s2=U.render(2,k,U.CP80_LAYERS[lay],1.0); y=y[max(U.onset(y,s2)-int(.001*s2),0):]
        o=course(y,s2,k); e.append(o-r); rows.append((k,lay,np.sqrt(np.mean((o-r)**2))))
    if verbose:
        for k,l,v in rows: print("   %s %s %.1f"%(U.name(k),l,v))
    return float(np.sqrt(np.mean(np.concatenate(e)**2)))
C=T.ElectricGrandProperties
if sys.argv[1:2]==["probe"]:
    print("off", round(err(True),2))
    C.wound_below_hz=200.0; C.wound_zing_db=30.0; C.wound_decay_db=float(sys.argv[2])
    print("zing30 decay",sys.argv[2], round(err(True),2)); sys.exit()
C.wound_below_hz=200.0
best=None
for wc in tuple(float(v) for v in sys.argv[2].split(',')):
  for z in tuple(float(v) for v in sys.argv[3].split(',')):
    for d in (float(v) for v in sys.argv[1].split(",")):
        C.wound_corner_hz,C.wound_zing_db,C.wound_decay_db=wc,z,d
        e=err(); print("corner %5.0f zing %4.1f decay %6.1f -> %.2f"%(wc,z,d,e),flush=True)
        if best is None or e<best[0]: best=(e,wc,z,d)
print("BEST",best)
C.wound_corner_hz,C.wound_zing_db,C.wound_decay_db=best[1:]
err(True)
