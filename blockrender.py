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
    ctrl = {}  # (ch)->{cc:val} current, snapshotted at note-on
    def cv(ch):
        c = ctrl.get(ch, {}); return (c.get(7,127)/127.0, c.get(11,127)/127.0, (c.get(10,64)-64)/63.0)
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
    ranks = prop.stop_ranks; order = getattr(prop, 'crescendo_order', [r[0] for r in ranks])
    # 14-bit stop word: CC11 (low 7 bits 0..6) | CC43 (high bits 7..13) -- lets a
    # Mixtur and other stops past bit 6 be drawn. CC43=0 -> the old 7-bit behaviour.
    ev = sorted(ccs.get(ch, [])); mlo = 1; mhi = 0; cres = 0.0; vol = 1.0
    rank_ev = {r[0]: [] for r in ranks}; swell_ev = []
    def emit(t):
        mask = mlo | (mhi << 7)
        nd = int(cres*len(order)+1e-9); drawn = set(order[:nd])
        for i, r in enumerate(ranks):
            k = r[0]; rank_ev[k].append((t, 1.0 if ((mask>>i)&1 or k in drawn) else 0.0))
        swell_ev.append((t, vol))
    emit(0.0)
    for t, cc, val in ev:
        if cc==11: mlo=val
        elif cc==43: mhi=val
        elif cc==4: cres=val/127.0
        elif cc==7: vol=val/127.0
        else: continue
        emit(t)
    gate = {r[0]: onepole_blocks(rank_ev[r[0]][1:], nblk, rank_ev[r[0]][0][1]) for r in ranks}
    swell = onepole_blocks(swell_ev[1:], nblk, swell_ev[0][1])
    return gate, swell, rank_ev   # rank_ev = per-rank [(t, target 0/1)] for draw-time (speak) lookup

def rank_speak_sec(events, on_sec, aj):
    """When a rank first speaks for a note starting at on_sec: the note attack if
    the rank is already drawn, else the first draw after onset (matching the
    reference, where hammer_down -- and so the phase + attack fade -- fires the
    moment the gated-off partial is first summed). None if never drawn."""
    cur = 0.0
    for t, tg in events:
        if t <= on_sec: cur = tg
        else: break
    if cur >= 0.5: return on_sec + aj
    for t, tg in events:
        if t > on_sec and tg >= 0.5: return t + aj
    return None

def prepare(path, tuner='hybrid'):
    """Parse + tune + build the full partial table (the one-time cost). Returns a
    dict of contiguous arrays ready for synth_window(); reused by render() (one
    full window) and play.py (streamed windows)."""
    lib = ensure_lib(); lib.synth_voice.restype = None
    import random; random.seed(0)   # per-note pitch/timing jitter, deterministic (as the reference seeds)
    FREQ = tuning_table(tuner)
    ch_prog, notes, ccs, total = parse(path)
    N = int(total*SR) + SR; nblk = N // BLK + 2
    # organ registration rows
    Grows=[]; Srows=[]; grow_of={}; crow_of={}; rankev_of={}; sh=(0.06,1.6,3.5,1500.0)
    for ch, prog in ch_prog.items():
        pc = property_class_for_program(prog)
        if not getattr(pc,'registerable',False): continue
        pr = pc(261.6,0,1,1); g,s,rev = registration_blocks(ch, pr, ccs, nblk)
        rankev_of[ch]=rev
        crow_of[ch]=len(Srows); Srows.append(s)
        for r in pr.stop_ranks: k=r[0]; grow_of[(ch,k)]=len(Grows); Grows.append(g[k])
        sh=(pr.swell_floor,pr.swell_gain_power,pr.swell_hf_max,pr.swell_hf_ref_hz)
    G = np.ascontiguousarray(np.array(Grows if Grows else [[1.0]],np.float32))
    S = np.ascontiguousarray(np.array(Srows if Srows else [[1.0]],np.float32))
    # partial table
    cols = {k:[] for k in ("om","p0","aL","aR","nf","non","noff","fa","re","ch","logr","logrA","aft","sus","cv","cc","crl","sj","csc","tbav","tau","tcut","delL","delR","gr","cr")}
    A = cols  # alias
    _TB = [0.0, 0.28, 1.8]   # per-note [tension_bend*attack_volume, settle_time, settle_cutoff]
    _PJ = [1.0]              # per-note pitch-jitter frequency scale (1 + pitch_jitter)
    _DL = [0.0, 0.0]         # per-note per-ear HRTF envelope delay in samples (ITD)
    def emit_partial(om, ampL, ampR, nomf, non, noff, fa, re, ch, logr, logrA, aft, sus, cv, cc, crl, sj, csc, gr, cr):
        om = om * _PJ[0]
        A["om"].append(om); A["p0"].append(-om*non); A["aL"].append(ampL); A["aR"].append(ampR)
        A["nf"].append(nomf); A["non"].append(non); A["noff"].append(noff); A["fa"].append(fa); A["re"].append(re); A["ch"].append(ch)
        A["logr"].append(logr); A["logrA"].append(logrA); A["aft"].append(aft); A["sus"].append(sus)
        A["cv"].append(cv); A["cc"].append(cc); A["crl"].append(crl); A["sj"].append(sj); A["csc"].append(csc)
        A["tbav"].append(_TB[0]); A["tau"].append(_TB[1]); A["tcut"].append(_TB[2])
        A["delL"].append(_DL[0]); A["delR"].append(_DL[1])
        A["gr"].append(gr); A["cr"].append(cr)
    for ch, note, on, off, vel, (v7, v11, pan) in notes:
        pc = property_class_for_program(ch_prog.get(ch,0))
        organ = getattr(pc,'registerable',False)
        chan_vol = 1.0 if organ else (v7*v11)**2
        f0 = FREQ[note]; props = pc(f0, pan, (vel/127.0)**2, chan_vol)   # pan = CC10 -> HRTF placement
        if props.inharmonicity_dynamic:
            props.inharmonicity_coefficient = props.inharmonicity_coefficient_for_frequency(f0)
        B = props.inharmonicity_coefficient; dur = off-on
        at = props.attack_time if props.attack_time is not None else props.chiff_max_valve_time
        rt = props.release_valve_time if props.release_valve_time is not None else props.chiff_max_valve_time
        # Pipe speech scales with wavelength: add speech_cycles periods of the
        # fundamental to the fixed floor (mirrors tonelib.speech_time -- bass
        # pipes speak slowly, trebles promptly).
        at = props.speech_time(at, f0); rt = props.speech_time(rt, f0)
        fade = max(1e-4, min(at, 0.45*dur))*SR; rel = max(1e-4, min(rt, 0.45*dur))*SR
        # chiff burst width: short/capped, decoupled from the slow speech fade
        chiff = max(1e-4, min(props.chiff_time(f0, at), 0.45*dur))*SR
        # per-note timing jitter delays the strike; pitch jitter detunes the whole note
        non = (on + getattr(props,'attack_jitter',0.0))*SR; noff = off*SR
        _PJ[0] = 1.0 + getattr(props,'pitch_jitter',0.0)
        _DL[0] = getattr(props,'left_hrtf_delay',0.0)*SR; _DL[1] = getattr(props,'right_hrtf_delay',0.0)*SR
        li, ri = props.left_incidence, props.right_incidence
        cv = props.chiff_volume; cc = props.chiff_cycle
        crl = getattr(props,'chiff_release',1.0) or 0.0; sjit = props.sustain_jitter; csc = f0/440.0
        _TB[0] = getattr(props,'tension_bend',0.0) * props.attack_volume
        _TB[1] = getattr(props,'tension_settle_time',0.28) or 0.28
        _TB[2] = getattr(props,'tension_settle_cutoff',1.8)
        stops = props.stop_ranks if organ else [("_",1.0,1.0)]
        transverse = []   # (freq, raw gain, decay dbps) of the main partials, for phantom pairing
        for key, ratio, gain, *rest in stops:
            spec_cls = rest[0] if rest else None   # cross-family stop: borrow this voice's spectrum only
            dyn = rest[1] if len(rest) > 1 else False   # force flue-dynamic inharmonicity (hybrid-lock)
            spv = spec_cls(f0, pan, (vel/127.0)**2, chan_vol) if spec_cls else None
            hv_fn = spv.harmonic_volume if spv else props.harmonic_volume
            rank_B = (spv or props).inharmonicity_coefficient_for_frequency(f0) if dyn else B
            gr = grow_of[(ch,key)] if organ else -1; cr = crow_of[ch] if organ else 0
            # A drawn stop speaks (phase + attack fade start) at its draw time, not
            # the note onset -- a fresh pipe, matching the reference. Non-organ voices
            # always speak at note onset.
            if organ:
                sp = rank_speak_sec(rankev_of[ch][key], on, getattr(props,'attack_jitter',0.0))
                non_r = sp*SR if sp is not None else non
            else:
                non_r = non
            # Place this drawstop at its case position (shared across a compound rank).
            if organ and getattr(props,'spiral_spatial',False):
                li,ri,_ld,_rd = props.hrtf_at(props.rank_position_x(key))
                _DL[0] = _ld*SR; _DL[1] = _rd*SR
            ceiling = getattr(props,'pipe_ceiling_hz',None); bmode = getattr(props,'pipe_break_mode','fold')
            # Compound rank (Mixtur): ratio is a LIST of footages; else a scalar. Each
            # sub-footage breaks back on the note's grid past the ceiling (mirrors
            # tonelib._build_registered_partials); only upperwork (>=2) breaks.
            for sub in (ratio if isinstance(ratio,(list,tuple)) else [ratio]):
                eff_ratio = sub
                if ceiling and sub >= 2.0 and f0*sub > ceiling:
                    if bmode == 'truncate': continue
                    while f0*eff_ratio > ceiling and eff_ratio >= 2.0: eff_ratio *= 0.5
                for m in range(1, props.max_harmonic+1):
                    h = eff_ratio*m; stretch = (1.0+0.5*(h*h-1.0)*rank_B) if rank_B>0 else 1.0; hf = f0*h*stretch
                    if hf > SR/2: break
                    hv = hv_fn(m)
                    if hv == 0.0: continue
                    dbps = props.harmonic_decay(m); logr = math.log(T.db_ratio(dbps)) if dbps>0 else 0.0
                    aftL, adbps = props.aftersound(f0, dbps); logrA = math.log(T.db_ratio(adbps)) if adbps>0 else 0.0
                    gL = hv*gain*props.hrtf_gain(hf, li); gR = hv*gain*props.hrtf_gain(hf, ri)
                    cvp = cv * props.chiff_harmonic_gain(h)   # roll chiff off the upper harmonics
                    emit_partial(2*math.pi*hf/SR, gL, gR, hf, non_r, noff, fade, rel, chiff,
                                 logr, logrA, aftL, props.sustain_level, cvp, cc, crl, sjit, csc, gr, cr)
                    transverse.append((hf, hv, dbps))
                    for gm, off_hz, dr, ud in props.unison_voices(f0, m, dbps):
                        uf = hf*(1.0+dr) + off_hz
                        if uf <= 0 or uf > SR/2: continue
                        ulr = math.log(T.db_ratio(ud)) if ud>0 else 0.0
                        emit_partial(2*math.pi*uf/SR, gL*gm, gR*gm, uf, non_r, noff, fade, rel, chiff,
                                     ulr, logrA, aftL, props.sustain_level, cvp, cc, crl, sjit, csc, gr, cr)
        # Phantom (longitudinal / Conklin) sum-tones for the wound bass: f_i+f_j of
        # the transverse partials, gain ~ coupling * v_i*v_j, decay d_i+d_j; centred
        # (no HRTF gain, like the reference). Off unless phantom_coupling > 0 (piano
        # bass, note <= phantom_note_max_hz).
        coupling = getattr(props,'phantom_coupling',0.0)
        power = getattr(props,'phantom_register_power',0.0)
        if power > 0.0: coupling *= (getattr(props,'phantom_ref_hz',65.0)/f0)**power
        if coupling > 0.0 and f0 <= getattr(props,'phantom_note_max_hz',0.0) and transverse:
            parents = transverse[:getattr(props,'phantom_max_order',16)]
            floor = getattr(props,'phantom_gain_floor',3e-3)*max(v for _,v,_ in parents)
            for a in range(len(parents)):
                fa,va,da = parents[a]
                for bb in range(a,len(parents)):
                    fb,vb,db_ = parents[bb]
                    fph = fa+fb
                    if fph >= SR/2: break
                    g = coupling*va*vb*(1.0 if a==bb else 2.0)
                    if g < floor: continue
                    dph = da+db_; lrp = math.log(T.db_ratio(dph)) if dph>0 else 0.0
                    aftp, adbp = props.aftersound(f0, dph); lrAp = math.log(T.db_ratio(adbp)) if adbp>0 else 0.0
                    emit_partial(2*math.pi*fph/SR, g, g, fph, non, noff, fade, rel, chiff,
                                 lrp, lrAp, aftp, props.sustain_level, 0.0, 0.0, 0.0, 0.0, csc, -1, 0)
    P = len(A["om"])
    def arr(k,dt): return np.ascontiguousarray(np.array(A[k], dt))
    prep = dict(lib=lib, P=P, N=N, nblk=nblk, total=total, sh=sh, G=G, S=S,
                ent=np.ascontiguousarray(np.array(T.entropy, np.float64)))
    for k,dt in (("om","f8"),("p0","f8"),("aL","f4"),("aR","f4"),("nf","f4"),
                 ("non","i8"),("noff","i8"),("fa","f4"),("re","f4"),("ch","f4"),
                 ("logr","f4"),("logrA","f4"),("aft","f4"),("sus","f4"),
                 ("cv","f4"),("cc","f4"),("crl","f4"),("sj","f4"),("csc","f4"),
                 ("tbav","f4"),("tau","f4"),("tcut","f4"),("delL","f4"),("delR","f4"),
                 ("gr","i4"),("cr","i4")):
        prep[k] = arr(k, dt)
    return prep

def synth_window(prep, n0, winlen):
    """Synthesise absolute samples [n0, n0+winlen) -> (L, R) float32, gained and
    clipped. Stateless (analytic phase), so a player calls it per audio block."""
    a=prep; lib=a['lib']
    dp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_double)); fp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    lp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_long)); ip=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    L=np.zeros(winlen,np.float32); R=np.zeros(winlen,np.float32)
    lib.synth_voice(fp(L),fp(R),ctypes.c_long(n0),ctypes.c_long(winlen),BLK,a['nblk'],a['P'],
                    dp(a['om']),dp(a['p0']),dp(a['p0']),fp(a['aL']),fp(a['aR']),fp(a['nf']),
                    lp(a['non']),lp(a['noff']),fp(a['fa']),fp(a['re']),fp(a['ch']),fp(a['logr']),fp(a['logrA']),fp(a['aft']),fp(a['sus']),
                    fp(a['cv']),fp(a['cc']),fp(a['crl']),fp(a['sj']),fp(a['csc']),dp(a['ent']),ctypes.c_long(len(a['ent'])),
                    fp(a['tbav']),fp(a['tau']),fp(a['tcut']),fp(a['delL']),fp(a['delR']),
                    ip(a['gr']),ip(a['cr']),fp(a['G']),fp(a['S']),
                    ctypes.c_float(a['sh'][0]),ctypes.c_float(a['sh'][1]),ctypes.c_float(a['sh'][2]),ctypes.c_float(a['sh'][3]),ctypes.c_long(SR))
    L*=T.master_gain; R*=T.master_gain; np.clip(L,-1,1,L); np.clip(R,-1,1,R)
    return L,R

def render(path, tuner='hybrid'):
    prep = prepare(path, tuner)
    t0=time.time(); L,R = synth_window(prep, 0, prep['N']); kdt=time.time()-t0
    return L,R,prep['total'],prep['P'],kdt

if __name__=="__main__":
    inp,outp=sys.argv[1],sys.argv[2]; tuner=sys.argv[3] if len(sys.argv)>3 else 'hybrid'
    t0=time.time(); L,R,total,P,kdt=render(inp,tuner); dt=time.time()-t0
    st=np.empty(len(L)*2,np.float64); st[0::2]=L; st[1::2]=R
    # 32-bit signed int: keep full dynamic range for the downstream reverb/normalise
    # pipeline (16-bit at the low pre-normalisation peak would waste ~half the bits).
    w=wave.open(outp,'wb'); w.setnchannels(2); w.setsampwidth(4); w.setframerate(SR)
    w.writeframes((np.clip(st,-1,1)*2147483647.0).astype('<i4').tobytes()); w.close()
    print("blockrender: %.1fs audio, %d partials, kernel %.2fs, total %.2fs = %.1fx realtime -> %s"%(total,P,kdt,dt,total/dt,outp))
