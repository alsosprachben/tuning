"""Spectral motion of loud bass notes: in third-octave bands 0.5-4 kHz, the
level every 25 ms over 0.3-2.5 s, detrended (a line per band), its std (dB) --
a phaser's sweeping notches read as large wobble; the Steinway's for reference."""
import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0"); os.environ.setdefault("TUNING_MASTER_DB","-14")
import upright_fit as U, tonelib as T
from scipy.signal import butter,sosfilt
U.REF[0]='steinway'; C=T.GrandPianoProperties
C.ring_db=eval(open('../gring2.txt').read()); C.ring_tuned=False
C.strike_noise_vel_power_register=eval(open('../gkvp1.txt').read()); C.string_gain=(0.4,0.3)
if os.environ.get('SG'): C.string_gain=tuple(float(v) for v in os.environ['SG'].split('/'))
if os.environ.get('SC'): C.strike_curve=tuple(float(x) for x in os.environ['SC'].split('/'))
for kv in filter(None,os.environ.get('SETV','').split(',')):
    n_,v_=kv.split(':'); setattr(C,n_,float(v_) if '.' in v_ else int(v_))
if os.environ.get('HPHASE'):
    import hammer as H, math
    def _mode_phase(self, m):
        got = self.__dict__.get('_hph')
        if got is None:
            fn, mass, K, p = self._hammer_felt()
            vel = int(round(127.0 * self.attack_volume ** 0.5))
            v0 = self.hammer_speed_lo * (self.hammer_speed_hi / self.hammer_speed_lo) ** ((max(1, min(127, vel)) - 1) / 126.0)
            L, Tn, Z = H.string_of(fn, *self._string_scale())
            F, dt = H.contact(fn, v0, mass, K, p, self.strike_point, L, Z, alpha=self.hammer_alpha,
                              tau=10.0 ** self.hammer_log_tau, core_x=self._core_mm(fn) * 1e-3,
                              core_K=10.0 ** self.hammer_core_logk)
            got = []
            for h in range(1, 401):
                w = 2 * math.pi * fn * h * dt; re = im = 0.0
                for i, x in enumerate(F):
                    re += x * math.cos(w * i); im += x * math.sin(w * i)
                got.append(-math.atan2(im, re))
                if fn * h > 12000: break
            self._hph = got
        return got[m - 1] if m - 1 < len(got) else 0.0
    C.mode_phase = _mode_phase
ED=2**np.arange(np.log2(float(os.environ.get('LO','500'))),np.log2(4000)+0.01,1/3)
def wob(x,sr):
    t0=U.onset(x,sr); x=x[t0:t0+int(2.6*sr)]; out=[]; S=[]
    for lo,hi in zip(ED[:-1],ED[1:]):
        y=sosfilt(butter(4,[lo,hi],'band',fs=sr,output='sos'),x)
        h=int(0.025*sr); fr=np.arange(int(0.3*sr),int(2.5*sr)-h,h)
        L=np.array([10*np.log10(np.mean(y[i:i+h]**2)+1e-30) for i in fr]); t=fr/sr
        d=L-np.polyval(np.polyfit(t,L,1),t); out.append(np.std(d)); S.append(d/(np.std(d)+1e-9))
    # a sweep: each band's wobble matching its upper neighbour's a few frames later
    cs=[];lags=[]
    for a,b in zip(S[:-1],S[1:]):
        best=(0,0)
        for lag in range(-8,9):
            if lag==0: continue
            c=np.mean(a[max(0,-lag):len(a)-max(0,lag)]*b[max(0,lag):len(b)-max(0,-lag)])
            if c>best[0]: best=(c,lag)
        cs.append(best[0]); lags.append(best[1])
    return np.mean(out),np.mean(cs),np.mean(np.sign(lags))
lab=os.environ.get('LAB','')
r=[]
for k in [int(v) for v in os.environ.get('KEYS','22,26,30,34,38').split(',')]:
    x,sr=(U.load(U.recordings(int(os.environ.get('DYN','3')))[k]) if lab=='rec' else U.render(0,k,U.vel_for(k,int(os.environ.get('DYN','3'))),2.7))
    r.append(wob(x,sr))
r=np.array(r)
print("%-12s wobble %.2f dB | neighbour match at a shift %.2f | sweep direction %+.2f (per key: %s)"%(lab,r[:,0].mean(),r[:,1].mean(),r[:,2].mean()," ".join("%.2f"%v for v in r[:,1])))
