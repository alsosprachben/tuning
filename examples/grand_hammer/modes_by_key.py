"""Each case mode's level at 120 ms re the note's fundamental at onset, key by
key (treble), the Steinway's vs ours (SETV etc.), hard."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.ring_db=eval(open('../gring2.txt').read()); C.ring_tuned=False
C.strike_noise_vel_power_register=eval(open('../gkvp1.txt').read()); C.string_gain=(0.4,0.3)
if os.environ.get('SC'): C.strike_curve=tuple(float(x) for x in os.environ['SC'].split('/'))
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
if os.environ.get('RREG'): C.ring_register_db=eval(os.environ['RREG'])
MODES=(110,218,345,583,960,1305); W=int(0.04*44100); n=1<<15
def lv(x,sr,t0,t,fs):
    seg=x[t0+int(t*sr):t0+int(t*sr)+W]; X=np.abs(np.fft.rfft(seg*np.hanning(len(seg)),n))**2; f=np.fft.rfftfreq(n,1/sr)
    return [10*np.log10(X[(f>m*0.98)&(f<m*1.02)].max()+1e-20) for m in fs]
D=int(os.environ.get('DYN','3'))
print("dyn%d: mode level at 120 ms re fundamental at onset; Steinway / ours"%D)
print("key   "+"  ".join("%9d"%m for m in MODES))
for k in (70,74,78,82,86,90,94,98,102):
    f0=440*2**((k-69)/12); row=[]
    for src in ('rec','ours'):
        x,sr=U.load(U.recordings(D)[k]) if src=='rec' else U.render(0,k,U.vel_for(k,D),0.6)
        t0=U.onset(x,sr); ref=lv(x,sr,t0,0.0,[f0])[0]; row.append(np.array(lv(x,sr,t0,0.12,MODES))-ref)
    print("%-5s "%U.name(k)+"  ".join("%4.0f/%4.0f"%(a,b) for a,b in zip(*row)))
