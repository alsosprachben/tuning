import sys,os,tempfile,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
import sfx_levels as S, tonelib as T
mode=sys.argv[1]
C=T.GrandPianoProperties
if mode=='new':
    C.max_partial_hz=10000.0
    for kv in os.environ['SETV'].split(','):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
    C.strike_noise_db=tuple((h,db-22) for h,db in C.strike_noise_db)
    if os.environ.get('LEVELPTS'): C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read())
KEYS=(21,28,33,40,45,52,57,64,69,76,81,88,96)
progs=tuple((0,k) for k in KEYS)
d=tempfile.mkdtemp()
for vel in (64,100):
    for nm,fn in (("K-weighted",S.k_level),("40-400 Hz",S.low_level)):
        S.LEVEL[0]=fn
    S.LEVEL[0]=S.k_level
    gu=S.sf_levels(S.gu_path(),progs,vel,d); us=S.ours(progs,vel,d)
    ref=(S.REF[0],S.REF[1])
    def rel(D,k): return D[(0,k)][1]-D[ref][1]
    print("%s vel %d, K-weighted, dB re its own C4:"%(mode,vel))
    print("  key   "+" ".join("%5s"%__import__('upright_fit').name(k) for k in KEYS))
    print("  GU    "+" ".join("%5.1f"%rel(gu,k) for k in KEYS))
    print("  ours  "+" ".join("%5.1f"%rel(us,k) for k in KEYS))
    print("  diff  "+" ".join("%5.1f"%(rel(us,k)-rel(gu,k)) for k in KEYS),flush=True)
