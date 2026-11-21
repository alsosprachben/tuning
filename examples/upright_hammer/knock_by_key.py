import sys,os,numpy as np
exec(open('../grand_noise.py').read().split("mode=sys.argv[1]")[0])
U.REF[0]='upright'; C=T.UprightPianoProperties
C.max_partial_hz=10000.0; C.hammer_model=True
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
if os.environ.get('VELPTS'): C.hammer_vel_power_points=eval(open(os.environ['VELPTS']).read())
if os.environ.get('LEVELPTS'): C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read())
if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
if os.environ.get('NOKNOCK'): C.strike_noise_db=()
if os.environ.get('NORING'): C.ring_db=()
print("key dyn | between-partials rec ours | thump rec ours | 2-8k rec ours")
for k in [int(v) for v in os.environ.get('KEYS','69,73,77,81,85,89,93,97,101').split(',')]:
    for d in (1,3):
        recs=U.recordings(d)
        if k not in recs: continue
        f0=440*2**((k-69)/12); x,sr=U.load(recs[k]); r=meas(cut(x,sr),sr,f0)
        y,s2=U.render(1,k,U.vel_for(k,d),0.6); o=meas(cut(y,s2),s2,f0)
        print("%-4s %d | %6.1f %6.1f | %6.1f %6.1f | %6.1f %6.1f"%(U.name(k),d,r[0],o[0],r[1],o[1],r[2],o[2]),flush=True)
