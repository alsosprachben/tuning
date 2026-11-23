#!/usr/bin/env python3
"""The EKTARA (gopichand) from open recordings (since 2026-11-22: the
Pianobook "The Ektara" takes no longer read, licences.md L7), in
~/Documents/refs/ektara_open (fetched with yt-dlp, both CC BY):
  F6IrnHr3WhQ.wav  dchucksster, "Iktara": three Baul singers, Kolkata
  RKdUcrhzmgM.wav  Etnochowa, "Solo na jednej strunie": one string, alone

    python3 examples/ektara_open.py scoop    the Baul clip's plucks: each
        sharp >1.5 kHz onset, one bright partial (1.5-5 kHz, 15 dB over the
        band) tracked back from where it settles (0.35-0.39 s), +-150 cents a
        10 ms frame; cents against the settled pitch (a bend moves every
        partial alike, and voices sit lower)
    python3 examples/ektara_open.py solo [attr=value ...]   the solo's 13
        unbent plucks at C#4 against ours (rendered unbent): the ladder at
        0.08-0.18 s and each harmonic's decay to 0.16-0.26 s
    python3 examples/ektara_open.py body     the colour by third octave from
        the solo's ladder, five passes
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
REF = os.path.expanduser("~/Documents/refs/ektara_open")


SCOOP = "import sys, os, numpy as np\nsys.path[:0]=['examples','.']\nimport guitar12_courses as G\nfrom scipy.io import wavfile\nfrom scipy.signal import butter, sosfiltfilt, find_peaks\np=os.path.expanduser(sys.argv[1]); sr,x=wavfile.read(p); x=x.astype(float).reshape(len(x),-1).mean(1); x/=np.abs(x).max()\nh=sosfiltfilt(butter(4,1500,'hp',fs=sr,output='sos'),x)\n# onsets: sharp rises of the >1.5 kHz envelope (a pluck), 10 dB in 15 ms\nw=int(0.005*sr); e=10*np.log10(np.convolve(h*h,np.ones(w)/w,'same')[::w]+1e-12)\nrise=e[3:]-e[:-3]\npk,_=find_peaks(rise,height=10,distance=int(0.15/0.005))\non=(pk+3)*0.005\nrows=[]\nW=int(0.04*sr); N=1<<16; f=np.fft.rfftfreq(N,1/sr); band=(f>1500)&(f<5000)\nfor a in on:\n    frames=[]\n    for t in np.arange(0.01,0.40,0.01):\n        s_=x[int((a+t)*sr):int((a+t)*sr)+W]\n        if len(s_)<W: break\n        frames.append(20*np.log10(np.abs(np.fft.rfft(s_*np.hanning(W),N))+1e-12))\n    if len(frames)<39: continue\n    # the settled partial: the strongest in the band over the last 5 frames,\n    # standing 15 dB over the band's median there\n    F=np.mean(frames[-5:],0)\n    i=np.argmax(np.where(band,F,-999)); \n    if F[i]-np.median(F[band])<15: continue\n    tr=[f[i]]\n    for X in frames[-2::-1]:\n        lo,hi=tr[-1]*2**(-150/1200),tr[-1]*2**(150/1200)\n        sel=(f>lo)&(f<hi)\n        j=np.flatnonzero(sel)[np.argmax(X[sel])]\n        if X[j]-np.median(X[band])<8: break\n        tr.append(f[j])\n    tr=np.array(tr[::-1])\n    if len(tr)<30: continue\n    c=1200*np.log2(tr/np.median(tr[-5:]))\n    rows.append((a,c))\nfor a,c in rows:\n    print('%7.2f | %s'%(a,' '.join('%5.0f'%v for v in c)))\n"

SOLO = "import sys, os, numpy as np\nsys.path[:0]=['examples','.']\nimport guitar12_courses as G, pluck_fit as P, tonelib as T\nfrom scipy.io import wavfile\nC=T.GopichantProperties\nP.PROG,P.CLS,P.BANK=105,'GopichantProperties',16\nfor kv in sys.argv[1:]:\n    k,v=kv.split('=',1); setattr(C,k,eval(v))\nN=1<<18\ndef ladder_decay(x,sr,a,f1):\n    f=np.fft.rfftfreq(N,1/sr)\n    out=[]\n    for t0 in (0.08,0.16):\n        s=x[int((a+t0)*sr):int((a+t0+0.10)*sr)]\n        X=20*np.log10(np.abs(np.fft.rfft(s*np.hanning(len(s)),N))+1e-12)\n        out.append([X[np.abs(f-k*f1)<max(6,k*f1*0.01)].max() for k in range(1,25)])\n    L0,L1=np.array(out)\n    return L0-L0.max(), (L0-L1)/0.08\nsr,x=wavfile.read(os.path.join(REF, 'RKdUcrhzmgM.wav')); x=x.astype(float).reshape(len(x),-1).mean(1)\nstarts=(3.64,3.89,4.19,5.67,8.32,8.92,9.19,12.64,13.22,13.48,13.78,14.08,15.23)\non=G.onsets(x/np.abs(x).max(),sr)\nL=[];D=[]\nfor a in starts:\n    s=x[int((a+0.1)*sr):int((a+0.25)*sr)]\n    f=np.fft.rfftfreq(N,1/sr); X=np.abs(np.fft.rfft(s*np.hanning(len(s)),N)); m=(f>255)&(f<300); f1=f[np.flatnonzero(m)[np.argmax(X[m])]]\n    l,d=ladder_decay(x,sr,a,f1); L.append(l); D.append(d)\nLr=np.median(L,0); Dr=np.median(D,0)\ny,s2=P.render(277.0,1.0); y=np.asarray(y,float); y=y.mean(1) if y.ndim>1 else y\na=np.flatnonzero(np.abs(y)>0.05*np.abs(y).max())[0]/s2\nLo,Do=ladder_decay(y,s2,a,277.0)\nprint('ladder take', ' '.join('%4.0f'%v for v in Lr))\nprint('ladder ours', ' '.join('%4.0f'%v for v in Lo))\nprint('decay  take', ' '.join('%4.0f'%v for v in Dr))\nprint('decay  ours', ' '.join('%4.0f'%v for v in Do))\nprint('rms ladder %.1f dB (h2-24), decay %.1f dB/s (h1-12)'%(np.sqrt(np.mean((Lr-Lo)[1:]**2)), np.sqrt(np.mean((Dr-Do)[:12]**2))))\n"

BODY = 'import sys, os, numpy as np\nsys.argv=[sys.argv[0]]+["body_trim_db=()","tension_bend=0.0","tonal_dampening=0.3","strike_point=0.2","decay_db=36.0","harmonic_decay_db=0.0"]\nexec(SOLO.split("y,s2=P.render")[0])\nCEN=[200*2**(k/3) for k in range(0,17)]   # 200 Hz .. 8 kHz third octaves\ntrim={}\nfor it in range(5):\n    C.body_trim_db=tuple((int(round(c)),round(v,1)) for c,v in sorted(trim.items()))\n    y,s2=P.render(277.0,1.0); y=np.asarray(y,float); y=y.mean(1) if y.ndim>1 else y\n    a=np.flatnonzero(np.abs(y)>0.05*np.abs(y).max())[0]/s2\n    Lo,Do=ladder_decay(y,s2,a,277.0)\n    d=Lr-Lo; d=d-np.median(d)\n    print(\'pass %d rms %.2f dB\'%(it,np.sqrt(np.mean(d[1:]**2))),flush=True)\n    for c in CEN:\n        ks=[k for k in range(24) if c*2**(-1/6)<=277.0*(k+1)<c*2**(1/6)]\n        if ks: trim[c]=max(-24,min(24,trim.get(c,0.0)+0.6*float(np.mean(d[ks]))))\nprint(\'body_trim_db =\',C.body_trim_db)\n'


def main(argv):
    mode = argv[0] if argv else "scoop"
    g = {"__name__": mode, "REF": REF}
    if mode == "scoop":
        sys.argv = [sys.argv[0], os.path.join(REF, "F6IrnHr3WhQ.wav")]
        exec(compile(SCOOP, "scoop", "exec"), g)
    elif mode == "solo":
        sys.argv = [sys.argv[0]] + argv[1:]
        exec(compile(SOLO, "solo", "exec"), g)
    elif mode == "body":
        g["SOLO"] = SOLO
        exec(compile(BODY, "body", "exec"), g)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
