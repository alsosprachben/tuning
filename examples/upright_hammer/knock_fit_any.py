"""The knock's level offset and velocity power, any piano class, against its
recordings' attack measures (noise between harmonics, thump, 2-8 kHz)."""
import sys,os,numpy as np
exec(open('../grand_noise.py').read().split("mode=sys.argv[1]")[0])
U.REF[0]=os.environ.get('REF','upright')
C=getattr(T,os.environ.get('CLS','UprightPianoProperties')); PROG=int(os.environ.get('PROG','1'))
C.max_partial_hz=10000.0; C.hammer_model=True
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
if os.environ.get('VELPTS'): C.hammer_vel_power_points=eval(open(os.environ['VELPTS']).read())
if os.environ.get('LEVELPTS'): C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read())
if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
_RB=tuple(C.ring_db)
base=tuple(C.strike_noise_db)
KEYS=tuple(int(k) for k in os.environ.get('KEYS','41,49,57,65,73,81,89').split(','))
REC={}
for d in (1,3):
    recs=U.recordings(d)
    for k in KEYS:
        x,sr=U.load(recs[k]); REC[(d,k)]=meas(cut(x,sr),sr,440*2**((k-69)/12))
n=len(KEYS)
for sn,ro in [(float(a),float(b)) for a in os.environ.get('SNS','-12,-6,0,6').split(',') for b in os.environ.get('ROFFS','0').split(',')]:
    C.ring_db=tuple((r[0],r[1]+ro)+tuple(r[2:]) for r in _RB)
    for vp in [float(v) for v in os.environ.get('VPS','0.0,0.3,0.6,1.0').split(',')]:
        C.strike_noise_db=tuple((h,db+sn) for h,db in base); C.strike_noise_vel_power=vp
        e=[]
        for (d,k),r in REC.items():
            y,s2=U.render(PROG,k,U.vel_for(k,d),0.6); o=meas(cut(y,s2),s2,440*2**((k-69)/12))
            e.extend([o[0]-r[0],o[1]-r[1]])
        e=np.array(e); print("ring %+d dB, offset %+d dB, velocity power %.1f: rms %.2f, mean %.2f (soft %.1f, hard %.1f)"%(ro,sn,vp,np.sqrt(np.mean(e**2)),e.mean(),e[:2*n].mean(),e[2*n:].mean()),flush=True)
