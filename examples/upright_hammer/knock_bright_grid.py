"""The knock's level and velocity law on the attack's 2-8 kHz share (first
20 ms), recorded vs ours, over KEYS at soft and hard."""
import sys,os,numpy as np
exec(open('../grand_noise.py').read().split("mode=sys.argv[1]")[0])
U.REF[0]='upright'; C=T.UprightPianoProperties
C.max_partial_hz=10000.0; C.hammer_model=True
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
if os.environ.get('VELPTS'): C.hammer_vel_power_points=eval(open(os.environ['VELPTS']).read())
if os.environ.get('LEVELPTS'): C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read())
if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
if os.environ.get('KTAB'): C.strike_noise_register_db=eval(open(os.environ['KTAB']).read())
if os.environ.get('KVP'): C.strike_noise_vel_power_register=eval(open(os.environ['KVP']).read())
base=tuple(C.strike_noise_db)
KEYS=[int(k) for k in os.environ['KEYS'].split(',')]
REC={}
for d in (1,3):
    for k in KEYS:
        x,sr=U.load(U.recordings(d)[k]); REC[(d,k)]=meas(cut(x,sr),sr,440*2**((k-69)/12))[2]
for sn in [float(v) for v in os.environ.get('SNS','-12,-6,0').split(',')]:
    for vp in [float(v) for v in os.environ.get('VPS','0.3,1.0,2.0').split(',')]:
        C.strike_noise_db=tuple((h,db+sn) for h,db in base); C.strike_noise_vel_power=vp
        e={1:[],3:[]}
        for (d,k),r in REC.items():
            y,s2=U.render(1,k,U.vel_for(k,d),0.6); e[d].append(meas(cut(y,s2),s2,440*2**((k-69)/12))[2]-r)
        a=np.array(e[1]+e[3])
        print("offset %+3d dB, velocity power %.1f: 2-8k rms %.2f (soft mean %+.1f, hard mean %+.1f)"%(sn,vp,np.sqrt(np.mean(a**2)),np.mean(e[1]),np.mean(e[3])),flush=True)
