#!/usr/bin/env python3
"""Fast block/phasor renderer for the registerable organ voices (flue/reed).

An alternative backend to midi.py for CC-registered organ pieces: reuses
tonelib/tunelib for the physical-model parameters (harmonic_volume, shutter,
inharmonic stretch, HRTF gains) and the static hybrid/stretch tuning table, then
synthesises with a compiled AVX-512 phasor kernel (synthkernel.c) instead of the
per-sample Python loop -- ~10-30x faster end to end.

Scope: FlueOrgan (prog 19) / ReedOrgan (prog 20). Stereo via per-ear HRTF gain
(ILD); the ~0.06 ms onset ITD and the attack chiff are omitted (documented).
Frequencies are constant, sustain is flat, jitter is 0, so the sustained sound
matches the pypy engine closely; verify by spectrum, not byte-diff.

Usage: python3 blockrender.py IN.mid OUT.wav [hybrid]
"""
import sys, os, time, ctypes, subprocess, wave
import numpy as np, mido
import tonelib as T, midilib
from patch_map import property_class_for_program

SR = 44100; TAU = 0.015; BLK = 512
HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "libsynth.so")

def ensure_lib():
    src = os.path.join(HERE, "synthkernel.c")
    if (not os.path.exists(LIB)) or os.path.getmtime(src) > os.path.getmtime(LIB):
        subprocess.check_call(["gcc", "-O3", "-march=native", "-ffast-math",
                               "-fopenmp", "-shared", "-fPIC", src, "-o", LIB, "-lm"])
    return ctypes.CDLL(LIB)

def tuning_table(name):
    midilib.set_tuner(name); mc = midilib.middle_c
    tuner = midilib.tuner_class()
    for n in range(128): tuner.addNote(n - mc)
    tuner.tune(1000, 30000); pairs = dict(tuner.noteFrequencies())
    return {n: pairs[n - mc] for n in range(128) if (n - mc) in pairs}

def parse(path):
    mid = mido.MidiFile(path); ch_prog = {}; notes = []; ccs = {}; on = {}; t = 0.0
    for msg in mid:
        t += msg.time
        if msg.type == 'program_change': ch_prog[msg.channel] = msg.program
        elif msg.type == 'control_change': ccs.setdefault(msg.channel, []).append((t, msg.control, msg.value))
        elif msg.type == 'note_on' and msg.velocity > 0: on.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            q = on.get((msg.channel, msg.note))
            if q: s, v = q.pop(0); notes.append((msg.channel, msg.note, s, t, v))
    return ch_prog, notes, ccs, t

def onepole_blocks(events, nblk, default):
    """Value of the one-pole-smoothed step function at each block centre."""
    bc = (np.arange(nblk) + 0.5) * BLK / SR
    out = np.empty(nblk, np.float32); segs = [(0.0, default)] + list(events); v = default
    for k, (t0, target) in enumerate(segs):
        t1 = segs[k + 1][0] if k + 1 < len(segs) else 1e18
        m = (bc >= t0) & (bc < t1)
        out[m] = target + (v - target) * np.exp(-(bc[m] - t0) / TAU)
        # value at segment end (for next segment's v0)
        if t1 < 1e17: v = target + (v - target) * np.exp(-(t1 - t0) / TAU)
    return out

def registration_blocks(ch, prop, ccs, nblk):
    ranks = prop.stop_ranks; order = getattr(prop, 'crescendo_order', [k for k, _, _ in ranks])
    ev = sorted(ccs.get(ch, [])); mask = 1; cres = 0.0; vol = 1.0
    rank_ev = {k: [] for k, _, _ in ranks}; swell_ev = []
    def emit(t):
        nd = int(cres * len(order) + 1e-9); drawn = set(order[:nd])
        for i, (k, _, _) in enumerate(ranks):
            rank_ev[k].append((t, 1.0 if ((mask >> i) & 1 or k in drawn) else 0.0))
        swell_ev.append((t, vol))
    emit(0.0)
    for t, cc, val in ev:
        if cc == 11: mask = val
        elif cc == 4: cres = val / 127.0
        elif cc == 7: vol = val / 127.0
        else: continue
        emit(t)
    gate = {k: onepole_blocks(rank_ev[k][1:], nblk, rank_ev[k][0][1]) for k, _, _ in ranks}
    swell = onepole_blocks(swell_ev[1:], nblk, swell_ev[0][1])
    return gate, swell

def render(path, tuner='hybrid'):
    lib = ensure_lib()
    lib.synth_organ.restype = None
    FREQ = tuning_table(tuner)
    ch_prog, notes, ccs, total = parse(path)
    N = int(total * SR) + SR; nblk = N // BLK + 2
    # per-channel registration (block rate) + shutter params (organ-global)
    reg_g = {}; reg_s = {}; sh = None; crow_of = {}; grow_of = {}
    Grows = []; Srows = []
    for ch, prog in ch_prog.items():
        pc = property_class_for_program(prog)
        if not getattr(pc, 'registerable', False): continue
        pr = pc(261.6, 0, 1, 1)
        g, s = registration_blocks(ch, pr, ccs, nblk); reg_g[ch] = g; reg_s[ch] = s
        crow_of[ch] = len(Srows); Srows.append(s)
        for k, _, _ in pr.stop_ranks:
            grow_of[(ch, k)] = len(Grows); Grows.append(g[k])
        sh = (pr.swell_floor, pr.swell_gain_power, pr.swell_hf_max, pr.swell_hf_ref_hz)
    if sh is None:
        raise SystemExit("no registerable organ channels (prog 19/20) in this MIDI")
    G = np.ascontiguousarray(np.array(Grows), np.float32)
    S = np.ascontiguousarray(np.array(Srows), np.float32)
    # build partial table
    OM=[];P0=[];AL=[];AR=[];NF=[];NON=[];NOFF=[];FA=[];RE=[];GR=[];CR=[]
    for ch, note, on, off, vel in notes:
        pc = property_class_for_program(ch_prog.get(ch, 0))
        if not getattr(pc, 'registerable', False): continue
        f0 = FREQ[note]; props = pc(f0, 0.0, (vel / 127.0) ** 2, 1.0)
        if props.inharmonicity_dynamic:
            props.inharmonicity_coefficient = props.inharmonicity_coefficient_for_frequency(f0)
        B = props.inharmonicity_coefficient; dur = off - on
        at = props.attack_time if props.attack_time is not None else props.chiff_max_valve_time
        rt = props.release_valve_time if props.release_valve_time is not None else props.chiff_max_valve_time
        fade = max(1e-4, min(at, 0.45 * dur)); rel = max(1e-4, min(rt, 0.45 * dur))
        non = on * SR; noff = off * SR
        li, ri = props.left_incidence, props.right_incidence
        for key, ratio, gain in props.stop_ranks:
            grp = grow_of[(ch, key)]
            for m in range(1, props.max_harmonic + 1):
                h = ratio * m; stretch = (1.0 + 0.5 * (h * h - 1.0) * B) if B > 0 else 1.0; hf = f0 * h * stretch
                if hf > SR / 2: break
                hv = props.harmonic_volume(m)
                if hv == 0.0: continue
                om = 2 * np.pi * hf / SR
                OM.append(om); P0.append(-om * non)          # phase 0 at n=0 (phase resets to 0 at note on)
                AL.append(hv * gain * props.hrtf_gain(hf, li))
                AR.append(hv * gain * props.hrtf_gain(hf, ri))
                NF.append(hf); NON.append(non); NOFF.append(noff)
                FA.append(fade * SR); RE.append(rel * SR); GR.append(grp); CR.append(crow_of[ch])
    P = len(OM)
    om=np.array(OM,np.float64); p0=np.array(P0,np.float64)
    aL=np.array(AL,np.float32); aR=np.array(AR,np.float32); nf=np.array(NF,np.float32)
    non=np.array(NON,np.int64); noff=np.array(NOFF,np.int64)
    fa=np.array(FA,np.float32); re=np.array(RE,np.float32)
    gr=np.array(GR,np.int32); cr=np.array(CR,np.int32)
    outL=np.zeros(N,np.float32); outR=np.zeros(N,np.float32)
    dptr=lambda a:a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    fptr=lambda a:a.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    lptr=lambda a:a.ctypes.data_as(ctypes.POINTER(ctypes.c_long))
    iptr=lambda a:a.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    t0=time.time()
    lib.synth_organ(fptr(outL),fptr(outR),ctypes.c_long(N),BLK,nblk,P,
                    dptr(om),dptr(p0),dptr(p0),fptr(aL),fptr(aR),fptr(nf),
                    lptr(non),lptr(noff),fptr(fa),fptr(re),iptr(gr),iptr(cr),
                    fptr(G),fptr(S),
                    ctypes.c_float(sh[0]),ctypes.c_float(sh[1]),ctypes.c_float(sh[2]),ctypes.c_float(sh[3]),
                    ctypes.c_long(SR))
    kdt=time.time()-t0
    outL*=T.master_gain; outR*=T.master_gain
    np.clip(outL,-1,1,outL); np.clip(outR,-1,1,outR)
    return outL,outR,total,P,kdt

if __name__=="__main__":
    inp,outp=sys.argv[1],sys.argv[2]; tuner=sys.argv[3] if len(sys.argv)>3 else 'hybrid'
    t0=time.time(); L,R,total,P,kdt=render(inp,tuner); dt=time.time()-t0
    st=np.empty(len(L)*2,np.float32); st[0::2]=L; st[1::2]=R
    w=wave.open(outp,'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(st,-1,1)*32767).astype('<i2').tobytes()); w.close()
    print("blockrender: %.1fs audio, %d partials, kernel %.2fs, total %.2fs = %.1fx realtime -> %s"
          %(total,P,kdt,dt,total/dt,outp))
