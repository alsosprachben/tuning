"""A piano program's register levels against GeneralUser GS's (K-weighted,
each key re its own C4, velocities 64 and 100), with SETV / LEVELPTS overrides.
Prints the points (Hz, -diff averaged) to correct by."""
import sys,os,tempfile,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
import sfx_levels as S, tonelib as T, upright_fit as U
PROG=int(os.environ.get('PROG','1')); C=getattr(T,os.environ.get('CLS','UprightPianoProperties'))
if os.environ.get('HAMMER'): C.max_partial_hz=10000.0; C.hammer_model=True
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_))
if os.environ.get('VELPTS'): C.hammer_vel_power_points=eval(open(os.environ['VELPTS']).read())
C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read()) if os.environ.get('LEVELPTS') else ()
if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
if os.environ.get('KTAB'): C.strike_noise_register_db=eval(open(os.environ['KTAB']).read())
if os.environ.get('KVP'): C.strike_noise_vel_power_register=eval(open(os.environ['KVP']).read())
KEYS=(21,28,33,40,45,52,57,64,69,76,81,88,96)
progs=tuple((PROG,k) for k in KEYS); S.REF=(PROG,60); S.LEVEL[0]=S.k_level
d=tempfile.mkdtemp(); diffs=[]
for vel in (64,100):
    gu=S.sf_levels(S.gu_path(),progs,vel,d); us=S.ours(progs,vel,d)
    def rel(D,k): return D[(PROG,k)][1]-D[(PROG,60)][1]
    df=np.array([rel(us,k)-rel(gu,k) for k in KEYS]); diffs.append(df)
    print("vel %d  key  "%vel+" ".join("%5s"%U.name(k) for k in KEYS))
    print("        GU   "+" ".join("%5.1f"%rel(gu,k) for k in KEYS))
    print("        ours "+" ".join("%5.1f"%rel(us,k) for k in KEYS))
    print("        diff "+" ".join("%5.1f"%v for v in df),flush=True)
m=np.mean(diffs,0); print("rms diff %.2f dB"%np.sqrt(np.mean(m**2)))
old=dict(C.hammer_level_points)
pts=tuple((round(440*2**((k-69)/12),1),round(old.get(round(440*2**((k-69)/12),1),0.0)-v,1)) for k,v in zip(KEYS,m))
print("POINTS",pts)
