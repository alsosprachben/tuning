import sys,os,numpy as np
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'grand_noise.py')).read().split("mode=sys.argv[1]")[0])
C.max_partial_hz=10000.0; C.hammer_model=True
for kv in os.environ['SETV'].split(','):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
base=tuple(C.strike_noise_db)
REC={}
for d in (1,3):
    recs=U.recordings(d)
    for k in (38,46,54,62,70,78,86):
        x,sr=U.load(recs[k]); REC[(d,k)]=meas(cut(x,sr),sr,440*2**((k-69)/12))
for sn in (-26,-22,-18):
    for vp in (0.0,0.5,1.0,1.5):
        C.strike_noise_db=tuple((h,db+sn) for h,db in base); C.strike_noise_vel_power=vp
        e=[]
        for (d,k),r in REC.items():
            y,s2=U.render(0,k,U.vel_for(k,d),0.6); o=meas(cut(y,s2),s2,440*2**((k-69)/12))
            e.extend([o[0]-r[0],o[1]-r[1]])
        e=np.array(e); print("offset %d dB, velocity power %.1f: rms %.2f, mean %.2f (soft %.1f, hard %.1f)"%(sn,vp,np.sqrt(np.mean(e**2)),e.mean(),e[:14].mean(),e[14:].mean()),flush=True)
