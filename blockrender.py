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

Usage: python3 blockrender.py IN.mid OUT.wav [tuner] [a=432|c=256]
"""
import sys, os, time, ctypes, subprocess, wave, math
import numpy as np, mido
import tonelib as T, midilib

# Mirrors RAND_GRAN in synthkernel.c: the chiff phase is redrawn at this many
# times the partial's frequency per second, which at 100000 is every sample --
# a white wash. See chiff_bandwidth.
RAND_GRAN = 100000.0
from patch_map import property_class_for_program, property_class_for_note
from brass_fingering import cents_offset as brass_cents, INSTRUMENTS as BRASS_KIND
from percussion_map import percussion_for_note, choke_group, rasp_strokes, GM_PERCUSSION_CHANNEL

# SR is the engine's sample rate. It used to be hardcoded here AND as six literal
# 44100s inside the kernel, so it could not actually be changed; the kernel now
# takes it as a parameter. Offline rendering stays at 44100 (the whole corpus is
# rendered there); a live front end sets it to match the audio device -- PipeWire
# on this machine runs the graph at 48000, and resampling in the path is both
# latency and a filter we did not choose.
SR = 44100
TAU = 0.015; BLK = 512


def set_sample_rate(sr):
    """Set the engine sample rate. Call before prepare(); everything downstream
    (note-on/off sample indices, fades, the kernel's own time base) reads it."""
    global SR
    SR = int(sr)
HERE = os.path.dirname(os.path.abspath(__file__)); LIB = os.path.join(HERE, "libsynth.so")

def ensure_lib():
    src = os.path.join(HERE, "synthkernel.c")
    # One .so per sample rate: SRATE is a compile-time constant in the kernel, so
    # that -ffast-math can fold the divisions exactly as it always did (see the
    # note above SRATE in synthkernel.c).
    lib = os.path.join(HERE, "libsynth_%d.so" % SR)
    if (not os.path.exists(lib)) or os.path.getmtime(src) > os.path.getmtime(lib):
        subprocess.check_call(["gcc","-O3","-march=native","-ffast-math","-fopenmp","-shared","-fPIC",
                               "-DSRATE=%d" % SR, src,"-o",lib,"-lm"])
    return ctypes.CDLL(lib)

def tuning_table(name):
    midilib.set_tuner(name); mc = midilib.middle_c; tuner = midilib.tuner_class()
    for n in range(128): tuner.addNote(n - mc)
    tuner.tune(1000, 30000); pairs = dict(tuner.noteFrequencies())
    return {n: pairs[n - mc] for n in range(128) if (n - mc) in pairs}

def parse(path):
    # `path` may also be an already-built mido.MidiFile, so a caller can hand in
    # a MIDI object it constructed in memory. live.py builds its note templates
    # that way, which keeps them on exactly this code path -- brass fingering,
    # jitter, HRTF, unison voices and all -- rather than a second one that could
    # drift from it.
    mid = path if isinstance(path, mido.MidiFile) else mido.MidiFile(path)
    ch_prog = {}; ch_progs = {}; notes = []; ccs = {}; on = {}; t = 0.0
    ctrl = {}  # (ch)->{cc:val} current, snapshotted at note-on
    def cv(ch):
        c = ctrl.get(ch, {}); return (c.get(7,127)/127.0, c.get(11,127)/127.0, (c.get(10,64)-64)/63.0)
    for msg in mid:
        t += msg.time
        if msg.type == 'program_change':
            ch_prog[msg.channel] = msg.program
            ch_progs.setdefault(msg.channel, []).append(msg.program)
        elif msg.type == 'control_change':
            ccs.setdefault(msg.channel, []).append((t, msg.control, msg.value))
            ctrl.setdefault(msg.channel, {})[msg.control] = msg.value
        elif msg.type == 'note_on' and msg.velocity > 0:
            # THE PATCH IS SNAPSHOTTED AT NOTE-ON, like the CCs beside it. It
            # used to be read from ch_prog at render time, which holds only the
            # LAST program change on each channel -- so a file that changes
            # patch mid-piece rendered every note with whatever it happened to
            # end on. passac.mid cycles channel 0 through strings, recorder,
            # clarinet, trumpet, organ and music box, and all 2161 notes came
            # out as strings.
            on.setdefault((msg.channel, msg.note), []).append(
                (t, msg.velocity, cv(msg.channel), ch_prog.get(msg.channel, 0)))
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            q = on.get((msg.channel, msg.note))
            if q:
                s, v, cvv, pg = q.pop(0)
                notes.append((msg.channel, msg.note, s, t, v, cvv, pg))
    # ch_progs is EVERY program a channel used, which the organ registration
    # pass needs: a channel that is an organ only part of the way through still
    # needs its registration rows built, and ch_prog alone (the last program)
    # would miss it -- a KeyError at render time once notes carry their own
    # patch. Channel 0 of passac.mid is a drawbar organ for exactly one section.
    for _c, _p in ch_prog.items(): ch_progs.setdefault(_c, []).append(_p)
    return ch_prog, ch_progs, notes, ccs, t

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
    ch_prog, ch_progs, notes, ccs, total = parse(path)
    N = int(total*SR) + SR; nblk = N // BLK + 2
    # organ registration rows
    Grows=[]; Srows=[]; grow_of={}; crow_of={}; rankev_of={}; sh=(0.06,1.6,3.5,1500.0)
    for ch, _plist in ch_progs.items():
        prog = next((q for q in dict.fromkeys(_plist)
                     if getattr(property_class_for_program(q), 'registerable', False)), None)
        if prog is None: continue
        pc = property_class_for_program(prog)
        pr = pc(261.6,0,1,1); g,s,rev = registration_blocks(ch, pr, ccs, nblk)
        rankev_of[ch]=rev
        crow_of[ch]=len(Srows); Srows.append(s)
        for r in pr.stop_ranks: k=r[0]; grow_of[(ch,k)]=len(Grows); Grows.append(g[k])
        sh=(pr.swell_floor,pr.swell_gain_power,pr.swell_hf_max,pr.swell_hf_ref_hz)
    G = np.ascontiguousarray(np.array(Grows if Grows else [[1.0]],np.float32))
    S = np.ascontiguousarray(np.array(Srows if Srows else [[1.0]],np.float32))
    # partial table
    cols = {k:[] for k in ("om","p0","aL","aR","nf","non","noff","fa","re","ch","logr","logrA","aft","sus","cv","cc","crl","sj","csc","cbw","tbav","tau","tcut","vd","vr","vp","delL","delR","gr","cr","p0R","pl")}
    A = cols  # alias
    _TB = [0.0, 0.28, 1.8]   # per-note [tension_bend*attack_volume, settle_time, settle_cutoff]
    _VB = [0.0, 5.5, 0.0]    # per-VOICE vibrato [depth fraction, rate Hz, phase rad]
    _PJ = [1.0]              # per-note pitch-jitter frequency scale (1 + pitch_jitter)
    _DL = [0.0, 0.0]         # per-note per-ear HRTF envelope delay in samples (ITD)
    _PL = [0]                # which player of a section this partial belongs to
    _CBW = [RAND_GRAN, 0.0]  # wash bandwidth: [fraction of partial f, absolute Hz]
    def emit_partial(om, ampL, ampR, nomf, non, noff, fa, re, ch, logr, logrA, aft, sus, cv, cc, crl, sj, csc, gr, cr, ph0=0.0):
        om = om * _PJ[0]
        # THE EAR DELAY MOVES THE CARRIER, NOT JUST THE ENVELOPE. A path length
        # delays the whole signal; delaying only the envelope leaves both ears
        # with identical carrier phase, so a held note has no interaural time
        # difference at all -- and below ~500 Hz, where the head casts no shadow
        # (0.01 dB at C2), ITD is the ONLY cue there is. Measured on a C2 string
        # chord, sustain-only peak IACC: 0.9978 as a point source, 0.9926 with
        # the players seated but the carrier shared, 0.8382 with both. The seats
        # supply the positions; this is what turns a position into an arrival.
        # p0 = -om*(non + d) + ph0, i.e. exactly "this partial, delayed by d".
        A["om"].append(om)
        A["p0"].append(-om*(non + _DL[0]) + ph0)
        A["p0R"].append(-om*(non + _DL[1]) + ph0)
        A["aL"].append(ampL); A["aR"].append(ampR)
        A["nf"].append(nomf); A["non"].append(non); A["noff"].append(noff); A["fa"].append(fa); A["re"].append(re); A["ch"].append(ch)
        A["logr"].append(logr); A["logrA"].append(logrA); A["aft"].append(aft); A["sus"].append(sus)
        A["cv"].append(cv); A["cc"].append(cc); A["crl"].append(crl); A["sj"].append(sj); A["csc"].append(csc)
        # index is t*f*gran, so gran IS the fractional width; an absolute
        # width in Hz is that same number divided by where the partial sits.
        A["cbw"].append(_CBW[1]/max(1e-6,nomf) if _CBW[1] > 0.0 else _CBW[0])
        A["tbav"].append(_TB[0]); A["tau"].append(_TB[1]); A["tcut"].append(_TB[2])
        A["vd"].append(_VB[0]); A["vr"].append(_VB[1]); A["vp"].append(_VB[2])
        A["delL"].append(_DL[0]); A["delR"].append(_DL[1])
        A["gr"].append(gr); A["cr"].append(cr); A["pl"].append(_PL[0])
    # SCRAPED instruments expand into their individual ridge impacts before
    # anything else looks at the note list, so the choke and the envelopes all
    # see the real strokes.
    expanded = []
    inner_ridge = set()          # ridges after the first, which must not choke each other
    stroke_pitch = {}            # (note, t) -> frequency scale, for swept instruments
    for ev in notes:
        ch, note, on, off, vel, rest, pg = ev
        strokes = rasp_strokes(note, on, off) if ch == GM_PERCUSSION_CHANNEL else None
        if strokes is None:
            expanded.append(ev); continue
        for k, st in enumerate(strokes):
            t0, t1, lvl = st[0], st[1], st[2]
            # A swept instrument gives each stroke its own PITCH -- a bell tree's
            # rod crosses graduated bars. Carried alongside the note list the way
            # inner_ridge is, so the event tuple keeps its shape.
            if len(st) > 3 and st[3] != 1.0:
                stroke_pitch[(note, t0)] = st[3]
            expanded.append((ch, note, t0, t1, max(1, int(vel * lvl)), rest, pg))
            if k: inner_ridge.add((note, t0))
    notes = expanded

    # EXCLUSIVE CLASSES: a closed hi-hat stroke damps a ringing open one. Applied
    # here, on the note list, because it is a fact about the instrument rather
    # than about the envelope -- the open hat simply stops.
    drum_ons = {}
    for ch, note, on, off, vel, _, _pg in notes:
        if ch == GM_PERCUSSION_CHANNEL and choke_group(note) is not None:
            # A ridge WITHIN a scrape is not a new stroke: the gourd goes on
            # ringing as the stick moves to the next ridge, so only the start of
            # a scrape damps what came before it.
            if (note, on) in inner_ridge: continue
            drum_ons.setdefault(note, []).append(on)
    choke_at = {}
    for note, ons in drum_ons.items():
        grp = choke_group(note)
        later = sorted(t for n2, ts in drum_ons.items() if n2 in grp for t in ts)
        choke_at[note] = later

    # EFFORT BASELINE, PER CHANNEL. Velocity in a real file is largely used to
    # BALANCE one instrument against the others, not to say how hard the player
    # is blowing -- so absolute velocity is the wrong signal. What carries effort
    # is the DEVIATION: this note against how this part is normally played. The
    # median is used rather than the mean so a few accents do not move the
    # reference they are supposed to be measured against.
    _vbase = {}
    for _ch in {n[0] for n in notes}:
        _vs = sorted(n[4] for n in notes if n[0] == _ch)
        if _vs: _vbase[_ch] = _vs[len(_vs)//2]
    for ch, note, on, off, vel, (v7, v11, pan), prog in notes:
        choked = None
        if ch == GM_PERCUSSION_CHANNEL and note in choke_at:
            choked = next((t for t in choke_at[note] if t > on + 1e-4), None)
        # PERCUSSION (GM channel 10). The note number selects a drum, not a
        # pitch: it takes a fixed base frequency and its own property class, and
        # the tuner never sees it. Without this the whole kit was routed through
        # property_class_for_program and played as PITCHED notes -- a Steinway
        # sounding drum note-numbers -- which is what a GM game cue exposed.
        # The reference (midilib) has always done this; only the block engine
        # did not, so the two disagreed on any file with a drum track.
        drum = percussion_for_note(note) if ch == GM_PERCUSSION_CHANNEL else None
        if ch == GM_PERCUSSION_CHANNEL and drum is None:
            continue                      # unmapped drum: the reference drops it
        if drum is not None:
            _, pc, f0, dpan = drum
            f0 *= stroke_pitch.get((note, on), 1.0)   # bell tree: this bar, not the lowest
            organ = False; chan_vol = (v7*v11)**2
            pan = max(-1.0, min(1.0, pan + dpan))   # kit position + channel pan
        else:
            pc = property_class_for_note(prog, note)
            organ = getattr(pc,'registerable',False)
            chan_vol = 1.0 if organ else (v7*v11)**2
            f0 = FREQ[note]
            # BRASS INTONATION FROM THE HORN, not from the temperament. The
            # fingering a player would choose determines the tube length, and
            # that tube does not sound the tempered pitch: valve combinations
            # run sharp (1+3 by 30 cents, 1+2+3 by 54) because each slide is cut
            # for the open horn, and the 5th and 7th partials sit flat of the
            # scale. What survives after the player lips and slides is a
            # tendency of a few cents -- which is part of why a brass section
            # sounds like one and not like an organ.
            kind = ('tuba' if 'Dark' in pc.__name__ else 'trumpet') \
                   if pc.__name__.endswith('BrassProperties') else None
            if kind:
                f0 *= 2.0 ** (brass_cents(f0, kind) / 1200.0)
        # attack_volume is (vel/127)^2, so the level deviation in dB is
        # 40*log10(vel/baseline) -- effort in the units effort_tilt expects.
        # Clamped to the range a real dynamic covers (Iowa's pp..ff spans about
        # 20 dB): past that a MIDI velocity is expressing something else.
        _vb = _vbase.get(ch) or vel
        _eff = 0.0
        if getattr(pc, 'effort_tilt', 0.0) and vel and _vb:
            _eff = max(-12.0, min(12.0, 40.0*math.log10(vel/float(_vb))))
        props = pc(f0, pan, (vel/127.0)**2, chan_vol, _eff)   # pan = CC10 -> HRTF placement
        # A one-shot voice (cymbal, struck drum) ignores note-off and rings out
        # on its own decay; the reference skips release() for these.
        if getattr(pc, 'one_shot', False):
            off = max(off, on + 8.0)
        # ...but an exclusive class OVERRIDES the ring-out: the point of a choke
        # is that the instrument is physically damped, so it stops even though
        # nothing about its own decay would have stopped it. Applied after the
        # one-shot extension, which would otherwise put the note-off back.
        if choked is not None and choked < off:
            off = choked
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
        # A SECTION IS PEOPLE IN CHAIRS, not a point. Each player is a separate
        # source and gets its own ears; the kernel already carries per-partial
        # aL/aR and delL/delR, so this costs nothing to render -- it is paid once
        # here, at build time. None for anything that is one body (a piano's
        # three strings share a hammer; a drum head's modes share a membrane).
        onsets = (props.section_onsets_at(f0)
                  if hasattr(props, 'section_onsets_at') else None)
        seats = props.section_seats() if hasattr(props,'section_seats') else None
        if seats:
            li, ri, _sd0, _sd1 = seats[0]
            _DL[0] = _sd0*SR; _DL[1] = _sd1*SR
        cv = props.chiff_volume; cc = props.chiff_cycle
        crl = getattr(props,'chiff_release',1.0) or 0.0; sjit = props.sustain_jitter; csc = f0/440.0
        _CBW[0] = getattr(props,'chiff_bandwidth',None) or RAND_GRAN
        _CBW[1] = getattr(props,'chiff_bandwidth_hz',None) or 0.0
        _TB[0] = getattr(props,'tension_bend',0.0) * props.attack_volume
        _TB[1] = getattr(props,'tension_settle_time',0.28) or 0.28
        _TB[2] = getattr(props,'tension_settle_cutoff',1.8)
        _TBN = (_TB[0], _TB[1], _TB[2])   # note-level bend, restored per partial
        # A pipe's passive modes start sharp and are pulled into lock by the drive
        # (mirrors tonelib: mode_lock_offset_for / mode_lock_time). It reuses the
        # kernel's per-partial pitch-bend slot -- a voice never needs both, since
        # tension bend is a struck string and mode lock is a driven air column.
        mls = getattr(props,'mode_lock_spread',0.0)
        stops = props.stop_ranks if organ else [("_",1.0,1.0)]
        transverse = []   # (freq, raw gain, decay dbps) of the main partials, for phantom pairing
        for key, ratio, gain, *rest in stops:
            spec_cls = rest[0] if rest else None   # cross-family stop: borrow this voice's spectrum only
            dyn = rest[1] if len(rest) > 1 else False   # force flue-dynamic inharmonicity (hybrid-lock)
            spv = T.rank_spectrum(spec_cls)(f0, pan, (vel/127.0)**2, chan_vol) if spec_cls else None
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
                    mr = props.mode_ratio(m)
                    if mr <= 0.0: break
                    h = eff_ratio*mr; stretch = (1.0+0.5*(h*h-1.0)*rank_B) if rank_B>0 else 1.0; hf = f0*h*stretch
                    if hf > SR/2: break
                    hv = hv_fn(m)
                    if hv == 0.0: continue
                    # PER-PARTIAL ARRIVAL. A struck plate's middle spectrum
                    # arrives hundreds of ms after the strike (see
                    # SynthProperties.bloom_delay_for). This DELAYS the partial --
                    # its fade and its decay together -- rather than stretching
                    # its fade, which would leave it decaying while it faded in.
                    pdelay = props.bloom_delay_for(hf)*SR
                    pfade = fade
                    dbps = props.harmonic_decay(m); logr = math.log(T.db_ratio(dbps)) if dbps>0 else 0.0
                    aftL, adbps = props.aftersound(f0, dbps); logrA = math.log(T.db_ratio(adbps)) if adbps>0 else 0.0
                    gL = hv*gain*props.hrtf_gain(hf, li); gR = hv*gain*props.hrtf_gain(hf, ri)
                    cvp = cv * props.chiff_harmonic_gain(h)   # roll chiff off the upper harmonics
                    if mls > 0.0:
                        mlo = props.mode_lock_offset_for(m)
                        _TB[0], _TB[1], _TB[2] = (mlo, props.mode_lock_time, props.mode_lock_time*6.0) \
                                                 if mlo else _TBN
                    vb = props.voice_vibrato(f0, 0)
                    _VB[0], _VB[1], _VB[2] = vb if vb else (0.0, 5.5, 0.0)
                    # Each player enters at their own instant. `non` is already a
                    # PER-PARTIAL column -- the organ has always used it that way,
                    # giving each drawn rank its own speech time -- so a section's
                    # entry scatter costs nothing but the offset. Capped at a
                    # quarter of the note so a short one cannot start after it ends.
                    _PL[0] = 0
                    non_m = non_r + (min(onsets[0], 0.25*dur)*SR if onsets else 0.0)
                    # Each mode's sign comes from where the stick landed relative
                    # to its nodes; see SynthProperties.strike_phase_spread.
                    sps = props.strike_phase_spread
                    mph = (math.pi*random.getrandbits(1)*sps) if sps > 0.0 else 0.0
                    emit_partial(2*math.pi*hf/SR, gL, gR, hf, non_m, noff, pfade, rel, chiff,
                                 logr, logrA, aftL, props.sustain_level, cvp, cc, crl, sjit, csc,
                                 gr, cr, ph0=mph)
                    # THE LATE ARRIVAL. A second copy of this partial, quieter
                    # and starting pdelay later: the cascade adds energy to the
                    # middle of the spectrum rather than holding the middle back.
                    # See SynthProperties.bloom_gain.
                    if pdelay > 0.0 and props.bloom_gain > 0.0:
                        bg = props.bloom_gain
                        # It SWELLS, it does not spike. Given the same fast onset
                        # as the partial it accompanies, a copy loud enough to
                        # matter simply becomes the loudest thing in the note and
                        # the envelope's peak moves off the hit -- the laggy start
                        # again. Fading it in over its own arrival time lets it
                        # add energy late without ever being an event of its own.
                        # Each late arrival on its own schedule: a band that
                        # rises together is a filter sweep, not a cascade.
                        sc = props.bloom_scatter
                        pd = pdelay*(1.0 - sc + 2.0*sc*random.random()) if sc > 0.0 else pdelay
                        bfade = max(1e-4, min(props.bloom_swell*pd/SR, 0.45*dur))*SR
                        emit_partial(2*math.pi*hf/SR, gL*bg, gR*bg, hf, non_m+pd, noff,
                                     bfade, rel, chiff, logr, logrA, aftL, props.sustain_level,
                                     cvp, cc, crl, sjit, csc, gr, cr)
                    transverse.append((hf, hv, dbps))
                    for ui, (gm, off_hz, dr, ud, uph) in enumerate(props.unison_voices(f0, m, dbps)):
                        vb = props.voice_vibrato(f0, ui + 1)
                        _VB[0], _VB[1], _VB[2] = vb if vb else (0.0, 5.5, 0.0)
                        uf = hf*(1.0+dr) + off_hz
                        if uf <= 0 or uf > SR/2: continue
                        ulr = math.log(T.db_ratio(ud)) if ud>0 else 0.0
                        ugL, ugR = gL*gm, gR*gm
                        if seats and ui + 1 < len(seats):
                            # this player's chair, not the section's centre. The
                            # shadow is read at the NOMINAL harmonic, as the main
                            # voice's is -- a few cents of detune moves it by
                            # nothing, and the two renderers must agree.
                            sli, sri, sld, srd = seats[ui + 1]
                            ugL = hv*gain*gm*props.hrtf_gain(hf, sli)
                            ugR = hv*gain*gm*props.hrtf_gain(hf, sri)
                            _DL[0] = sld*SR; _DL[1] = srd*SR
                        _PL[0] = ui + 1
                        non_u = non_r + (min(onsets[ui+1], 0.25*dur)*SR
                                         if (onsets and ui+1 < len(onsets)) else 0.0)
                        emit_partial(2*math.pi*uf/SR, ugL, ugR, uf, non_u, noff, pfade, rel, chiff,
                                     ulr, logrA, aftL, props.sustain_level, cvp, cc, crl, sjit, csc, gr, cr,
                                     2*math.pi*uph)
                    _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0    # main voice only within this harmonic
                    _PL[0] = 0
                    if seats:
                        _DL[0] = seats[0][2]*SR; _DL[1] = seats[0][3]*SR
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
    prep = dict(lib=lib, P=P, N=N, nblk=nblk, total=total, sh=sh, G=G, S=S)
    for k,dt in (("om","f8"),("p0","f8"),("aL","f4"),("aR","f4"),("nf","f4"),
                 ("non","i8"),("noff","i8"),("fa","f4"),("re","f4"),("ch","f4"),
                 ("logr","f4"),("logrA","f4"),("aft","f4"),("sus","f4"),
                 ("cv","f4"),("cc","f4"),("crl","f4"),("sj","f4"),("csc","f4"),("cbw","f4"),
                 ("tbav","f4"),("tau","f4"),("tcut","f4"),("vd","f4"),("vr","f4"),("vp","f4"),("delL","f4"),("delR","f4"),
                 ("gr","i4"),("cr","i4"),("p0R","f8"),("pl","i4")):
        prep[k] = arr(k, dt)
    return prep

def synth_window(prep, n0, winlen):
    """Synthesise absolute samples [n0, n0+winlen) -> (L, R) float32, gained and
    clipped. Stateless (analytic phase), so a player calls it per audio block."""
    L=np.zeros(winlen,np.float32); R=np.zeros(winlen,np.float32)
    synth_partials(prep, n0, winlen, 0, prep['P'], L, R)
    L*=T.master_gain; R*=T.master_gain; np.clip(L,-1,1,L); np.clip(R,-1,1,R)
    return L,R

def synth_partials(prep, n0, winlen, i0, i1, L, R):
    """Render partials [i0,i1) of `prep` into L/R, with no master gain and no
    clip. Partials are independent and the kernel accumulates into the buffers,
    so a caller can split the table across threads and sum the results -- which
    is what live.py does, because ctypes releases the GIL. Splitting changes the
    ORDER of the float sum and so the last bits of the output; render() takes the
    whole table in one call and is unaffected."""
    a=prep; lib=a['lib']
    dp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_double)); fp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    lp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_long)); ip=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    if i0 or i1 != a['P']:
        sl = lambda k: a[k][i0:i1]
    else:
        sl = lambda k: a[k]
    lib.synth_voice(fp(L),fp(R),ctypes.c_long(n0),ctypes.c_long(winlen),BLK,a['nblk'],i1-i0,
                    dp(sl('om')),dp(sl('p0')),dp(sl('p0R')),fp(sl('aL')),fp(sl('aR')),fp(sl('nf')),
                    lp(sl('non')),lp(sl('noff')),fp(sl('fa')),fp(sl('re')),fp(sl('ch')),fp(sl('logr')),fp(sl('logrA')),fp(sl('aft')),fp(sl('sus')),
                    fp(sl('cv')),fp(sl('cc')),fp(sl('crl')),fp(sl('sj')),fp(sl('csc')),fp(sl('cbw')),
                    fp(sl('tbav')),fp(sl('tau')),fp(sl('tcut')),fp(sl('vd')),fp(sl('vr')),fp(sl('vp')),fp(sl('delL')),fp(sl('delR')),
                    ip(sl('gr')),ip(sl('cr')),fp(a['G']),fp(a['S']),
                    ctypes.c_float(a['sh'][0]),ctypes.c_float(a['sh'][1]),ctypes.c_float(a['sh'][2]),ctypes.c_float(a['sh'][3]),
                    ctypes.c_long(SR))

def render(path, tuner='hybrid'):
    prep = prepare(path, tuner)
    t0=time.time(); L,R = synth_window(prep, 0, prep['N']); kdt=time.time()-t0
    return L,R,prep['total'],prep['P'],kdt

def write_wav(path, L, R):
    """Write a stereo render to WAV **at the rate it was rendered at**.

    Use this rather than saving raw and naming the rate by hand. SR is 44100
    offline and 48000 only when a live front end has set it, and the two are
    8.8% apart -- a semitone and a half of pitch, an eighth of every duration.
    Saved through here the rate travels with the file and cannot be got wrong.
    """
    st=np.empty(len(L)*2,np.float64); st[0::2]=L; st[1::2]=R
    # 32-bit signed int: keep full dynamic range for the downstream reverb/normalise
    # pipeline (16-bit at the low pre-normalisation peak would waste ~half the bits).
    w=wave.open(path,'wb'); w.setnchannels(2); w.setsampwidth(4); w.setframerate(SR)
    w.writeframes((np.clip(st,-1,1)*2147483647.0).astype('<i4').tobytes()); w.close()


if __name__=="__main__":
    inp,outp=sys.argv[1],sys.argv[2]; tuner=sys.argv[3] if len(sys.argv)>3 else 'hybrid'
    # Optional 4th argument sets the pitch everything tunes to: "a=432" names the
    # frequency of A4, "c=256" the frequency of middle C. Which end you give
    # matters -- a temperament's own A-to-C ratio is not equal temperament's, so
    # c=256 lands on a different A in each one. Omit it to keep each
    # temperament's own reference. See tunelib.set_reference.
    if len(sys.argv)>4:
        k,_,v = sys.argv[4].partition('=')
        if k.strip().lower() not in ('a','c') or not v:
            raise SystemExit("pitch reference must be a=<hz> or c=<hz>, e.g. a=432")
        midilib.set_reference(**{k.strip().lower(): float(v)})
    t0=time.time(); L,R,total,P,kdt=render(inp,tuner); dt=time.time()-t0
    write_wav(outp, L, R)
    print("blockrender: %.1fs audio, %d partials, kernel %.2fs, total %.2fs = %.1fx realtime -> %s"%(total,P,kdt,dt,total/dt,outp))
