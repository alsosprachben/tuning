import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='cp80'; M=U._cp80_map()
C=T.ElectricGrandProperties
GRAND=('a','b','c','d','e','aftersound_decay_ratio','aftersound_level_1','aftersound_level_2','aftersound_level_3',
 'attack_time','decay_db','decay_register_slope','harmonic_decay_db','harmonic_decay_dampening',
 'hammer_corner_hz','hammer_open_lo','hammer_open_slope','hammer_order','tonal_dampening','string_gain','unison_beat_scatter',
 'board_low_hz','board_high_hz','board_body_hz','board_body_gain','octave_gain')
v=sys.argv[1]
if v.startswith('grand'):
    keep=set(sys.argv[2].split(',')) if len(sys.argv)>2 else set()
    for n in GRAND:
        if n in C.__dict__ and n not in keep: delattr(C,n)
    C.bridge_peak_db=0.0; C.wound_zing_db=0.0; C.wound_decay_db=0.0
# spectrum (fit_spectrum's measure), both layers
U.FIT_KEYS=tuple(sorted(k for k,x in M.items() if 'PP' in x and 'FF' in x))
es=[]
for d in (1,3):
    recs=U.recordings(d)
    for k in U.FIT_KEYS:
        x,sr=U.load(recs[k]); r=U.thirds(x,sr,k)
        y,s2=U.render(2,k,U.vel_for(k,d),0.7); m=U.thirds(y,s2,k)
        w=(r>-40)|(m>-40); es.extend((np.maximum(m,-60)-np.maximum(r,-60))[w&np.isfinite(r)&np.isfinite(m)])
# decay: T20 per band, middle layer
ed=[]
recs=U.recordings(2)
for k in U.FIT_KEYS:
    x,sr=U.load(recs[k]); f0=440*2**((k-69)/12)
    t=np.array([q[0] for q in U.band_decay(x,sr)]); ok=np.array([hi>f0 for _,hi in U.BANDS])&np.isfinite(t)&(t>0.1)&(t<8)
    y,s2=U.render(2,k,U.vel_for(k,2),8.0); m=np.array([q[0] for q in U.band_decay(y,s2)]); m=np.where(np.isfinite(m),m,8.0)
    ed.extend(20*np.log10(np.maximum(m[ok],0.05)/t[ok]))
# attack course
sys.argv=['x']; import cp80_attack_fit as A
ea=A.err()
print("%-10s spectrum %.2f  decay(T20) %.2f  attack %.2f  dB"%(v,np.sqrt(np.mean(np.square(es))),np.sqrt(np.mean(np.square(ed))),ea))
