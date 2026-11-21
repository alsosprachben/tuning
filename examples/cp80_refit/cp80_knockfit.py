import sys,os,io,contextlib,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'cp80_knock.py')).read().split('print("sub-f0')[0].split("U.REF[0]='cp80'")[1].split("\n",1)[1])
U.REF[0]='cp80'; M=U._cp80_map()
from scipy.signal import butter,sosfiltfilt
C=T.ElectricGrandProperties
dbs=float(sys.argv[1]); C.strike_noise_dbs=dbs
U.fit_strike(C,2,passes=int(os.environ.get('PASSES','3')))
e=[]
for k in sorted(M):
    if k<50 or k>90: continue
    f0=440*2**((k-69)/12)
    for lay in ("MP","FF"):
        if lay not in M[k]: continue
        x,sr=U.load(M[k][lay]); y,s2=U.render(2,k,U.CP80_LAYERS[lay],0.5)
        e.extend(np.array(sub(cut(y,s2),s2,f0))[:3]-np.array(sub(cut(x,sr),sr,f0))[:3])
print("DBS %.0f knock rms %.2f dB, mean %.2f"%(dbs,np.sqrt(np.mean(np.square(e))),np.mean(e)))
