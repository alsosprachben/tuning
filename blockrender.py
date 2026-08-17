#!/usr/bin/env python3
"""Fast block/phasor renderer (an alternative to midi.py).

Reuses tonelib/tunelib for every physical-model parameter (harmonic_volume,
inharmonic stretch, HRTF gains, decay/aftersound, unison detuning, chiff, the
drawn-stop gate + swell shutter) and the static hybrid/stretch tuning table,
computed once in Python, then synthesises with a compiled phasor kernel
(synthkernel.c) instead of the per-sample loop -- ~40x faster end to end.

Covers all sustained/decaying voices: piano (two-stage decay + unison "dance" +
strike comb + inharmonicity), flue/reed organ (drawn stops + swell), pipes /
strings / brass (attack + sustain chiff, decay-to-sustain bloom). Each partial is
a constant-frequency phasor; the decay envelope, gate/swell and chiff modulate
its amplitude. Omitted (documented, small): the piano tension-bend attack pitch
transient, per-note pitch/timing jitter, and the ~0.06 ms onset ITD. Verify by
spectrum, not byte-diff.

Usage: python3 blockrender.py IN.mid OUT.wav [tuner]
"""
import sys, os, time, ctypes, subprocess, wave, math
import numpy as np, mido
import tonelib as T, midilib
from patch_map import property_class_for_program

SR = 44100; TAU = 0.015; BLK = 512
HERE = os.path.dirname(os.path.abspath(__file__)); LIB = os.path.join(HERE, "libsynth.so")

def ensure_lib():
    src = os.path.join(HERE, "synthkernel.c")
    if (not os.path.exists(LIB)) or os.path.getmtime(src) > os.path.getmtime(LIB):
        subprocess.check_call(["gcc","-O3","-march=native","-ffast-math","-fopenmp","-shared","-fPIC",src,"-o",LIB,"-lm"])
    return ctypes.CDLL(LIB)

def tuning_table(name):
    midilib.set_tuner(name); mc = midilib.middle_c; tuner = midilib.tuner_class()
    for n in range(128): tuner.addNote(n - mc)
    tuner.tune(1000, 30000); pairs = dict(tuner.noteFrequencies())
    return {n: pairs[n - mc] for n in range(128) if (n - mc) in pairs}

def parse(path):
    mid = mido.MidiFile(path); ch_prog = {}; notes = []; ccs = {}; on = {}; t = 0.0
    ctrl = {}  # (ch)->{7:val,11:val} current, snapshotted at note-on for non-organ channel_volume
    def cv(ch):
        c = ctrl.get(ch, {}); return (c.get(7,127)/127.0), (c.get(11,127)/127.0)
    for msg in mid:
        t += msg.time
        if msg.type == 'program_change': ch_prog[msg.channel] = msg.program
        elif msg.type == 'control_change':
            ccs.setdefault(msg.channel, []).append((t, msg.control, msg.value))
            ctrl.setdefault(msg.channel, {})[msg.control] = msg.value
        elif msg.type == 'note_on' and msg.velocity > 0:
            on.setdefault((msg.channel, msg.note), []).append((t, msg.velocity, cv(msg.channel)))
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            q = on.get((msg.channel, msg.note))
            if q: s, v, cvv = q.pop(0); notes.append((msg.channel, msg.note, s, t, v, cvv))
    return ch_prog, notes, ccs, t

def onepole_blocks(events, nblk, default):
    bc = (np.arange(nblk) + 0.5) * BLK / SR
    out = np.empty(nblk, np.float32); segs = [(0.0, default)] + list(events); v = default
    for k, (t0, target) in enumerate(segs):
        t1 = segs[k + 1][0] if k + 1 < len(segs) else 1e18
        m = (bc >= t0) & (bc < t1); out[m] = target + (v - target) * np.exp(-(bc[m] - t0) / TAU)
        if t1 < 1e17: v = target + (v - target) * np.exp(-(t1 - t0) / TAU)
    return out

def registration_blocks(ch, prop, ccs, nblk):
    ranks = prop.stop_ranks; order = getattr(prop, 'crescendo_order', [k for k,_,_ in ranks])
    ev = sorted(ccs.get(ch, [])); mask = 1; cres = 0.0; vol = 1.0
    rank_ev = {k: [] for k,_,_ in ranks}; swell_ev = []
    def emit(t):
        nd = int(cres*len(order)+1e-9); drawn = set(order[:nd])
        for i,(k,_,_) in enumerate(ranks): rank_ev[k].append((t, 1.0 if ((mask>>i)&1 or k in drawn) else 0.0))
        swell_ev.append((t, vol))
    emit(0.0)
    for t, cc, val in ev:
        if cc==11: mask=val
        elif cc==4: cres=val/127.0
        elif cc==7: vol=val/127.0
        else: continue
        emit(t)
    gate = {k: onepole_blocks(rank_ev[k][1:], nblk, rank_ev[k][0][1]) for k,_,_ in ranks}
    swell = onepole_blocks(swell_ev[1:], nblk, swell_ev[0][1])
    return gate, swell

def render(path, tuner='hybrid'):
    lib = ensure_lib(); lib.synth_voice.restype = None
    FREQ = tuning_table(tuner)
    ch_prog, notes, ccs, total = parse(path)
    N = int(total*SR) + SR; nblk = N // BLK + 2
    # organ registration rows
    Grows=[]; Srows=[]; grow_of={}; crow_of={}; sh=(0.06,1.6,3.5,1500.0)
    for ch, prog in ch_prog.items():
        pc = property_class_for_program(prog)
        if not getattr(pc,'registerable',False): continue
        pr = pc(261.6,0,1,1); g,s = registration_blocks(ch, pr, ccs, nblk)
        crow_of[ch]=len(Srows); Srows.append(s)
        for k,_,_ in pr.stop_ranks: grow_of[(ch,k)]=len(Grows); Grows.append(g[k])
        sh=(pr.swell_floor,pr.swell_gain_power,pr.swell_hf_max,pr.swell_hf_ref_hz)
    G = np.ascontiguousarray(np.array(Grows if Grows else [[1.0]],np.float32))
    S = np.ascontiguousarray(np.array(Srows if Srows else [[1.0]],np.float32))
    # partial table
    cols = {k:[] for k in ("om","p0","aL","aR","nf","non","noff","fa","re","logr","logrA","aft","sus","cv","cc","crl","sj","csc","gr","cr")}
    A = cols  # alias
    def emit_partial(om, ampL, ampR, nomf, non, noff, fa, re, logr, logrA, aft, sus, cv, cc, crl, sj, csc, gr, cr):
        A["om"].append(om); A["p0"].append(-om*non); A["aL"].append(ampL); A["aR"].append(ampR)
        A["nf"].append(nomf); A["non"].append(non); A["noff"].append(noff); A["fa"].append(fa); A["re"].append(re)
        A["logr"].append(logr); A["logrA"].append(logrA); A["aft"].append(aft); A["sus"].append(sus)
        A["cv"].append(cv); A["cc"].append(cc); A["crl"].append(crl); A["sj"].append(sj); A["csc"].append(csc)
        A["gr"].append(gr); A["cr"].append(cr)
    for ch, note, on, off, vel, (v7, v11) in notes:
        pc = property_class_for_program(ch_prog.get(ch,0))
        organ = getattr(pc,'registerable',False)
        chan_vol = 1.0 if organ else (v7*v11)**2
        f0 = FREQ[note]; props = pc(f0, 0.0, (vel/127.0)**2, chan_vol)
        if props.inharmonicity_dynamic:
            props.inharmonicity_coefficient = props.inharmonicity_coefficient_for_frequency(f0)
        B = props.inharmonicity_coefficient; dur = off-on
        at = props.attack_time if props.attack_time is not None else props.chiff_max_valve_time
        rt = props.release_valve_time if props.release_valve_time is not None else props.chiff_max_valve_time
        fade = max(1e-4, min(at, 0.45*dur))*SR; rel = max(1e-4, min(rt, 0.45*dur))*SR
        non = on*SR; noff = off*SR
        li, ri = props.left_incidence, props.right_incidence
        cv = props.chiff_volume; cc = props.chiff_cycle
        crl = getattr(props,'chiff_release',1.0) or 0.0; sjit = props.sustain_jitter; csc = f0/440.0
        stops = props.stop_ranks if organ else [("_",1.0,1.0)]
        for key, ratio, gain in stops:
            gr = grow_of[(ch,key)] if organ else -1; cr = crow_of[ch] if organ else 0
            for m in range(1, props.max_harmonic+1):
                h = ratio*m; stretch = (1.0+0.5*(h*h-1.0)*B) if B>0 else 1.0; hf = f0*h*stretch
                if hf > SR/2: break
                hv = props.harmonic_volume(m)
                if hv == 0.0: continue
                dbps = props.harmonic_decay(m); logr = math.log(T.db_ratio(dbps)) if dbps>0 else 0.0
                aftL, adbps = props.aftersound(f0, dbps); logrA = math.log(T.db_ratio(adbps)) if adbps>0 else 0.0
                gL = hv*gain*props.hrtf_gain(hf, li); gR = hv*gain*props.hrtf_gain(hf, ri)
                emit_partial(2*math.pi*hf/SR, gL, gR, hf, non, noff, fade, rel,
                             logr, logrA, aftL, props.sustain_level, cv, cc, crl, sjit, csc, gr, cr)
                for gm, off_hz, dr, ud in props.unison_voices(f0, m, dbps):
                    uf = hf*(1.0+dr) + off_hz
                    if uf <= 0 or uf > SR/2: continue
                    ulr = math.log(T.db_ratio(ud)) if ud>0 else 0.0
                    emit_partial(2*math.pi*uf/SR, gL*gm, gR*gm, uf, non, noff, fade, rel,
                                 ulr, logrA, aftL, props.sustain_level, cv, cc, crl, sjit, csc, gr, cr)
    P = len(A["om"])
    def arr(k,dt): return np.ascontiguousarray(np.array(A[k], dt))
    om=arr("om",np.float64); p0=arr("p0",np.float64)
    aL=arr("aL",np.float32); aR=arr("aR",np.float32); nf=arr("nf",np.float32)
    non=arr("non",np.int64); noff=arr("noff",np.int64); fa=arr("fa",np.float32); re=arr("re",np.float32)
    logr=arr("logr",np.float32); logrA=arr("logrA",np.float32); aft=arr("aft",np.float32); sus=arr("sus",np.float32)
    cv=arr("cv",np.float32); cc=arr("cc",np.float32); crl=arr("crl",np.float32); sj=arr("sj",np.float32); csc=arr("csc",np.float32)
    gr=arr("gr",np.int32); cr=arr("cr",np.int32)
    ent=np.ascontiguousarray(np.array(T.entropy, np.float64))
    outL=np.zeros(N,np.float32); outR=np.zeros(N,np.float32)
    dp=lambda a:a.ctypes.data_as(ctypes.POINTER(ctypes.c_double)); fp=lambda a:a.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    lp=lambda a:a.ctypes.data_as(ctypes.POINTER(ctypes.c_long)); ip=lambda a:a.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    t0=time.time()
    lib.synth_voice(fp(outL),fp(outR),ctypes.c_long(N),BLK,nblk,P,dp(om),dp(p0),dp(p0),fp(aL),fp(aR),fp(nf),
                    lp(non),lp(noff),fp(fa),fp(re),fp(logr),fp(logrA),fp(aft),fp(sus),
                    fp(cv),fp(cc),fp(crl),fp(sj),fp(csc),dp(ent),ctypes.c_long(len(ent)),
                    ip(gr),ip(cr),fp(G),fp(S),
                    ctypes.c_float(sh[0]),ctypes.c_float(sh[1]),ctypes.c_float(sh[2]),ctypes.c_float(sh[3]),ctypes.c_long(SR))
    kdt=time.time()-t0
    outL*=T.master_gain; outR*=T.master_gain; np.clip(outL,-1,1,outL); np.clip(outR,-1,1,outR)
    return outL,outR,total,P,kdt

if __name__=="__main__":
    inp,outp=sys.argv[1],sys.argv[2]; tuner=sys.argv[3] if len(sys.argv)>3 else 'hybrid'
    t0=time.time(); L,R,total,P,kdt=render(inp,tuner); dt=time.time()-t0
    st=np.empty(len(L)*2,np.float32); st[0::2]=L; st[1::2]=R
    w=wave.open(outp,'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(st,-1,1)*32767).astype('<i2').tobytes()); w.close()
    print("blockrender: %.1fs audio, %d partials, kernel %.2fs, total %.2fs = %.1fx realtime -> %s"%(total,P,kdt,dt,total/dt,outp))
