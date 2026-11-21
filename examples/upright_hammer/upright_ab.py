import sys,os
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='upright'; U.FIT_KEYS=tuple(int(k) for k in os.environ.get('KEYS','29,37,45,53,61,69,77,85,93,101').split(','))
C=T.UprightPianoProperties
if sys.argv[2]=='new':
    C.max_partial_hz=10000.0; C.hammer_model=True
    for kv in os.environ['SETV'].split(','):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
    if os.environ.get('VELPTS'): C.hammer_vel_power_points=eval(open(os.environ['VELPTS']).read())
    if os.environ.get('LEVELPTS'): C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read())
    if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
    if os.environ.get('KTAB'): C.strike_noise_register_db=eval(open(os.environ['KTAB']).read())
    if os.environ.get('KVP'): C.strike_noise_vel_power_register=eval(open(os.environ['KVP']).read())
U.ab(1,sys.argv[1])
