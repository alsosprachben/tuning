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
its amplitude.

WHAT ACTUALLY DIFFERS FROM THE REFERENCE. This used to list three omissions --
the piano's tension-bend attack transient, per-note pitch/timing jitter, and the
~0.06 ms onset ITD -- and all three have since been implemented here (_TB, _PJ
and attack_jitter, _DL). The list outlived the omissions, which is worse than no
list: it invited the assumption that a measured difference was one of them.

The one structural difference left is the synthesis model. Both sides compute
every physical parameter from the same tonelib code; this renderer then holds
each partial at a CONSTANT frequency and modulates its amplitude, where the
reference evaluates the partial per sample. So anything that moves a partial's
frequency continuously within a note is approximated rather than integrated,
and small phase-sensitive differences follow from that.

Measured, matched (both at the same TUNING_MASTER_DB, band error weighted by
the energy each band carries): a bowed string SECTION agrees to 0.03 dB, peak
+0.18 dB. Two cautions for anyone repeating that measurement, both of which
produced confident wrong answers here: the master gain is read from the
environment by BOTH renderers (tonelib.master_gain), so an unset variable on one
side is a flat offset that looks like a model difference; and an unweighted RMS
over octave bands lets a near-silent octave dominate -- the same section reads
14.7 dB that way. Verify by spectrum, weighted, not by byte-diff.

Usage: python3 blockrender.py IN.mid OUT.wav [tuner] [a=432|c=256]
"""
import sys, os, time, ctypes, subprocess, wave, math
import numpy as np, mido
import bisect as _bisect
import noisegen as _NG

# THE TUBE IS USED WHERE IT HAS INFORMATION, and not where it does not.
#
# Velars and labials: yes. A velar's burst is set by a long front cavity cut
# out of the following vowel's own tract, and that cavity's length is what the
# vowel's formants are largely about -- so the fit constrains it, and the peak
# runs 2835 Hz before /i/ down to 676 before /u/ with no rule for it. A labial
# has no front cavity at all, which is a fact about anatomy and needs no fit.
#
# Alveolars: NO, they keep their measured band. Three formants cannot
# determine a 44-section tube; the fit is regularised toward the neutral tube,
# which is a choice rather than a measurement. It recovers /u/'s lip rounding
# because rounding MOVES FORMANTS, and says nothing reliable about the 2.5 cm
# in front of an alveolar closure because that geometry barely touches F1-F3.
# Asked anyway, it puts the /t/ resonance at 7581 Hz before /i/ against a
# measured 4000, and no source band then leaves /t/ bright and /k/ dark at the
# same time. A measured 3800 is better knowledge than a fitted 7581.
_STOPS = frozenset('kgpb')
_SHAPE_N = 512
_SHAPE_CACHE = {}


def _stop_shape(consonant, vowel):
    """(freqs, gains) for a stop released before `vowel`, from the tube.

    Only the STOPS. A fricative is held turbulence at the constriction with a
    measured band of its own, and /s/ at 6200 Hz is better known than anything
    this would predict for it; a stop burst is a transient whose spectrum is
    the front cavity's, and that is exactly what the tube gives.
    """
    if consonant not in _STOPS:
        return None
    key = (consonant, vowel)
    if key in _SHAPE_CACHE:
        return _SHAPE_CACHE[key]
    try:
        import vocaltube as _VT
        import vowels as _W
        place = _W.PLACE.get(consonant)
        coeffs = _VT.SHAPES.get(vowel)
        if place is None or coeffs is None:
            _SHAPE_CACHE[key] = None
            return None
        f = np.linspace(0.0, 11025.0, _SHAPE_N)
        g = _VT.burst(np.asarray(coeffs, float), place, f)
        g = g / max(float(g.max()), 1e-12)
        _SHAPE_CACHE[key] = (f, g)
    except Exception:
        _SHAPE_CACHE[key] = None
    return _SHAPE_CACHE[key]
CONSONANT_GAIN = float(os.environ.get('TUNING_CONSONANT_GAIN', '0.0175'))
# The rhythmic unit the nominal consonant widths were chosen against:
# a syllable rate of about 3.3/s, which is ordinary speech.
# How far apart a section's singers release a consonant, as a standard
# deviation in seconds. A choir does NOT release together -- getting a /t/
# together is one of the hardest things a chorus master asks for, and even a
# good chorus spreads over tens of milliseconds. Modelled normal rather than
# uniform: most of them near the beat with a tail of late ones, which is what
# a conductor is actually fighting.
CONSONANT_SCATTER = float(os.environ.get('TUNING_CONSONANT_SCATTER', '0.015'))
CONSONANT_REF = float(os.environ.get('TUNING_CONSONANT_REF', '0.30'))
_CONS = os.environ.get('TUNING_CONSONANTS', '1') != '0'
import tonelib as T, midilib, vowels as _VOW

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


def _lyric_vowels(path, language=None):
    """{channel: [(second, vowel_key)]} from the file's own lyrics.

    A choir that knows its text can sing the text: a vowel IS a formant triple,
    so the only thing standing between "aah for eleven minutes" and the actual
    words is knowing which vowel each note carries. MuseScore writes lyrics into
    its MIDI export as meta events, syllable by syllable, at the tick of the
    note they belong to -- so the alignment is given and does not have to be
    guessed.

    Only the NUCLEUS is taken. The consonants belong around the note (before the
    beat at the front), not on it, and are not modelled yet.
    """
    language = language or os.environ.get('TUNING_LYRIC_LANG', '')
    if not language:
        return {}
    try:
        import mido, vowels as V
        mid = mido.MidiFile(path)
    except Exception:
        return {}
    tpb = mid.ticks_per_beat
    tempo = [(0, 500000)]
    for tr in mid.tracks:
        t = 0
        for x in tr:
            t += x.time
            if x.type == 'set_tempo':
                tempo.append((t, x.tempo))
    tempo.sort()

    def secs(tick):
        out = 0.0; last = 0; cur = 500000
        for tk, tp in tempo:
            if tk >= tick: break
            out += (tk - last) * cur / 1e6 / tpb; last = tk; cur = tp
        return out + (tick - last) * cur / 1e6 / tpb

    out = {}
    for tr in mid.tracks:
        chans = {x.channel for x in tr if x.type == 'note_on' and x.velocity > 0}
        if len(chans) != 1:
            continue
        ch = chans.pop(); t = 0; seen = set(); rows = []
        for x in tr:
            t += x.time
            if x.type in ('lyrics', 'text') and str(getattr(x, 'text', '')).strip():
                if t in seen:        # a second verse at the same tick
                    continue
                v = V.vowel_of(x.text, language)
                if v:
                    seen.add(t)
                    rows.append((secs(t), v, V.onset_of(x.text, language),
                                 V.coda_of(x.text, language)))
        if rows:
            out[ch] = sorted(rows)
    return out


def _vocalise():
    """TUNING_VOCALISE="8=V,10=V" -- a constant vowel for a part with no text.

    A wordless chorus is not a part we failed to find lyrics for; it is a part
    that HAS no lyrics and still has a vowel. Holst's Neptune is the case, and
    the vowel is documented (Imogen Holst, 1971): 'u' in 'sun'.
    """
    out = {}
    for item in os.environ.get('TUNING_VOCALISE', '').replace(';', ',').split(','):
        if '=' not in item: continue
        ch, _, v = item.partition('=')
        v = v.strip()
        if v in _VOW.VOWELS:
            try: out[int(ch)] = v
            except ValueError: pass
    return out


def _declared_voice_parts():
    """TUNING_VOICE_PARTS="8=soprano,10=alto" -- registration for files that
    name nothing.

    Neptune is the case: Holst asks for an offstage chorus of women, two
    three-part choruses with no men in them at all, and the MIDI carries no
    track names whatsoever. Its medians happen to land above the crossover so
    the inference gets it right by luck; an alto part sitting a little lower
    would have been sung by men. A score that specifies its forces should be
    able to say so.
    """
    spec = os.environ.get('TUNING_VOICE_PARTS', '')
    out = {}
    for item in spec.replace(';', ',').split(','):
        if '=' not in item: continue
        ch, _, part = item.partition('=')
        part = part.strip().lower()
        if part in T.VOICE_BODIES:
            try: out[int(ch)] = part
            except ValueError: pass
    return out


def _voice_parts(path):
    """{channel: part name} from track/instrument names.

    A part that says what it is beats any inference from its notes: a
    countertenor sings the alto line on a male tract, a treble is a boy and not
    a small woman. Tessitura is the fallback for files that say nothing.
    """
    try:
        import mido
        mid = mido.MidiFile(path)
    except Exception:
        return {}
    out = {}
    for tr in mid.tracks:
        name = None
        for x in tr:
            if x.type in ('track_name', 'instrument_name') and not name:
                name = x.name
            ch = getattr(x, 'channel', None)
            if ch is not None and name and ch not in out:
                part = T.voice_body(name)
                if part:
                    out[ch] = part
    out.update(_declared_voice_parts())      # an explicit registration wins
    return out


def _legato_ticks(mid):
    """{(channel, note, k)} for notes that begin CONTIGUOUSLY with whatever the
    channel was playing before, judged in the file's own tick grid.

    Ticks and not milliseconds, because a millisecond is a different musical
    amount at every tempo and cannot tell a sequencer's one-tick nudge from a
    real articulation gap. And a FRACTION of a beat rather than a fixed number
    of ticks, because the corpus does not share a convention -- measured over
    the adjacent-note gaps of four pieces:

        Jupiter    tpb=120   4381 pairs at exactly 0 ticks (23%)
        Neptune    tpb=480     42 at 0, but 4720 at +1 -- one tick IS its legato
        Vivaldi    tpb=480    340 at 0, 948 at +5 (1/96 beat, a note-off nudge)
        Valkyries  tpb=48      75 at 0; its 3-4 tick gaps are 1/16 of a beat
                              and deliberate, so its slurs are the overlaps

    Exact contiguity would have been right for Jupiter and wrong for the other
    three -- and treating Neptune's one-tick gaps as detached would have made
    the most sustained piece in the corpus entirely detache.

    tpb/64 is a 64th of a beat, floored at one tick so a coarse file (Valkyries
    at 48 ticks per beat) does not sweep in gaps it meant.
    """
    tol = max(1.0, mid.ticks_per_beat / 64.0)
    spans = []
    for tr in mid.tracks:
        t = 0; held = {}
        for x in tr:
            t += x.time
            if x.type == 'note_on' and x.velocity > 0:
                held.setdefault((x.channel, x.note), []).append(t)
            elif x.type == 'note_off' or (x.type == 'note_on' and x.velocity == 0):
                q = held.get((x.channel, x.note))
                if q:
                    spans.append((q.pop(0), t, x.channel, x.note))
    spans.sort()
    # k indexes the occurrences of one (channel, note) in onset order, which is
    # how prepare() finds the same note again from the seconds-based list.
    seen = {}
    out = set()
    per = {}
    for s in spans:
        per.setdefault(s[2], []).append(s)
    for ch, v in per.items():
        # COMPARE AGAINST THE NOTE THIS ONE FOLLOWS, not against whatever is
        # still ringing on the channel. Taking the channel's latest end instead
        # gets two things wrong, and both are common: a held bass note under a
        # moving line makes every note above it look contiguous, and the members
        # of one chord disagree with each other -- the first gets a full onset
        # and the rest a slurred one, because by then the first is "still
        # sounding". Measured on the corpus, that mislabelled 82% of Valkyries'
        # contiguous notes and 64% of Jupiter's.
        #
        # So: notes sharing an onset are one event and take one answer, judged
        # on what came before the whole group.
        prev = None
        i = 0
        while i < len(v):
            j = i
            while j < len(v) and v[j][0] == v[i][0]:
                j += 1
            on_t = v[i][0]
            slur = prev is not None and on_t - prev <= tol
            for on2, off2, c, n in v[i:j]:
                k = seen.get((c, n), 0); seen[(c, n)] = k + 1
                if slur:
                    out.add((c, n, k))
            prev = max(s[1] for s in v[i:j])
            i = j
    return out


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
    return ch_prog, ch_progs, notes, ccs, t, _legato_ticks(mid)

def onepole_blocks(events, nblk, default):
    bc = (np.arange(nblk) + 0.5) * BLK / SR
    out = np.empty(nblk, np.float32); segs = [(0.0, default)] + list(events); v = default
    for k, (t0, target) in enumerate(segs):
        t1 = segs[k + 1][0] if k + 1 < len(segs) else 1e18
        m = (bc >= t0) & (bc < t1); out[m] = target + (v - target) * np.exp(-(bc[m] - t0) / TAU)
        if t1 < 1e17: v = target + (v - target) * np.exp(-(t1 - t0) / TAU)
    return out

# How long a voice takes to get out of the way when its own pitch is struck
# again. Not a cut: a cut is a step and a step is a click. Samplers call this
# stealing and give it a few milliseconds for exactly this reason.
RETRIGGER_FADE = 0.004


def registration_blocks(ch, prop, ccs, nblk):
    ranks = prop.stop_ranks; order = getattr(prop, 'crescendo_order', [r[0] for r in ranks])
    # 14-bit stop word: CC11 (low 7 bits 0..6) | CC43 (high bits 7..13) -- lets a
    # Mixtur and other stops past bit 6 be drawn. CC43=0 -> the old 7-bit behaviour.
    ev = sorted(ccs.get(ch, [])); ds = getattr(prop,'default_stops',1); mlo = ds & 0x7F; mhi = (ds >> 7) & 0x7F; cres = 0.0; vol = 1.0
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

# Every per-partial column, in the order the table is built. subset() slices
# exactly these and nothing else.
PARTIAL_COLS = ("om","p0","aL","aR","aM","mch","px","pz","nf","non","noff","fa","re","ch",
                "logr","logrA","aft","sus","cv","cc","crl","sj","csc","cbw",
                "tbav","tau","tcut","vd","vr","vp","delL","delR","gr","cr","p0R","pl")


def prepare(path, tuner='hybrid440'):
    """Parse + tune + build the full partial table (the one-time cost). Returns a
    dict of contiguous arrays ready for synth_window(); reused by render() (one
    full window) and play.py (streamed windows)."""
    lib = ensure_lib(); lib.synth_voice.restype = None
    import random; random.seed(0)   # per-note pitch/timing jitter, deterministic (as the reference seeds)
    FREQ = tuning_table(tuner)
    ch_prog, ch_progs, notes, ccs, total, legato = parse(path)
    N = int(total*SR) + SR; nblk = N // BLK + 2
    # A CHOIR'S BODY BELONGS TO THE PART, NOT THE NOTE. Alto and tenor overlap
    # by a fourth, yet one section is women and the other men -- tracts 17%
    # apart -- so a per-note pitch rule cannot separate them and would flip the
    # body inside a line. A part's TESSITURA can: take each channel's median
    # pitch once and let every note of that channel be sung by the same people.
    _parts = _voice_parts(path)
    _lyr = _lyric_vowels(path)
    for _c, _v in _vocalise().items():          # a wordless part still has a vowel
        _lyr.setdefault(_c, [(0.0, _v, None, None)])
    _tess = {}
    for _e in notes:
        _tess.setdefault(_e[0], []).append(_e[1])
    _tess = {c: 440.0 * 2.0 ** ((sorted(v)[len(v) // 2] - 69) / 12.0)
             for c, v in _tess.items() if v}
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
    cols = {k:[] for k in ("az","dr","om","p0","aL","aR","aM","mch","px","pz","nf","non","noff","fa","re","ch","logr","logrA","aft","sus","cv","cc","crl","sj","csc","cbw","tbav","tau","tcut","vd","vr","vp","delL","delR","gr","cr","p0R","pl")}
    A = cols  # alias
    _TB = [0.0, 0.28, 1.8]   # per-note [tension_bend*attack_volume, settle_time, settle_cutoff]
    _VB = [0.0, 5.5, 0.0]    # per-VOICE vibrato [depth fraction, rate Hz, phase rad]
    _PJ = [1.0]              # per-note pitch-jitter frequency scale (1 + pitch_jitter)
    _DL = [0.0, 0.0]         # per-note per-ear HRTF envelope delay in samples (ITD)
    _PL = [0]                # which player of a section this partial belongs to
    _CBW = [RAND_GRAN, 0.0]  # wash bandwidth: [fraction of partial f, absolute Hz]
    # Reflections cost about 7x the partials, since every one of them is
    # audible and nothing prunes. Worth it for a render you will listen to,
    # not for a batch. --no-reflect on the command line, or TUNING_REFLECT=0.
    REFLECT = (os.environ.get('TUNING_REFLECT', '1') not in ('0', 'off', '')
               and '--no-reflect' not in sys.argv)
    _MCH = [0]               # MIDI channel of the note being emitted (stem/object export)
    # Where this partial is actually radiating FROM. A section is not one
    # source: section_position_x seats each player at their own desk, and
    # rank_position_x stands each drawstop at its own place in the case. The
    # binaural mix has always honoured that -- it is where the interaural
    # delays come from -- so an object export that collapses a channel to one
    # point throws away placement the model already has.
    _PX = [0.0]; _PZ = [0.0]  # metres, + = right / up
    # Azimuth of the receiver this partial is travelling to, radians. The
    # listener for a direct partial, the MIRRORED listener for an image. Only
    # the rotating speaker uses it, and only it knows the difference matters.
    _AZ = [0.0]
    _radius = [None]         # radiating aperture for THIS partial (organ ranks vary)
    # How much power the sources actually put INTO the room, per octave, which
    # is what the diffuse tail is excited by. Accumulated on the direct partials
    # only: a reflection is that same power heard again, not more of it.
    ROOM_BANDS = (63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0)
    _QACC = [[0.0, 0.0] for _ in ROOM_BANDS]   # [sum a^2, sum a^2/Q] per band
    def emit_partial(om, ampL, ampR, ampM, nomf, non, noff, fa, re, ch, logr, logrA, aft, sus, cv, cc, crl, sj, csc, gr, cr, ph0=0.0,
                     _place=None):
        # _place is (delL, delR, px, pz) for an image source; None means the
        # direct sound, which also emits the images.
        om = om * _PJ[0]
        dl, dr, px, pz = _place if _place else (_DL[0], _DL[1], _PX[0], _PZ[0])
        if _place is None:
            _AZ[0] = math.atan2(px, max(props.radiation_distance, 1e-6))
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
        A["p0"].append(-om*(non + dl) + ph0)
        A["p0R"].append(-om*(non + dr) + ph0)
        A["aL"].append(ampL); A["aR"].append(ampR)
        # ampM is this partial BEFORE the head model -- what the instrument
        # radiates, not what an ear receives. aL/aR are ampM times a per-ear
        # hrtf_gain, so keeping it costs one column and makes a source-referenced
        # (object) render exact rather than an un-mixing of the binaural one.
        A["aM"].append(ampM); A["mch"].append(_MCH[0])
        A["px"].append(px); A["pz"].append(pz); A["az"].append(_AZ[0])
        # 1 for the sound that goes straight to the listener, 0 for an image.
        # The amplifier distorts BEFORE anything radiates, so its products are
        # formed from the direct signal only -- a product between a direct
        # partial and its own reflection would be two copies of one voltage
        # beating against each other, which happens in the room and not in the
        # valve.
        A["dr"].append(1.0 if _place is None else 0.0)
        A["nf"].append(nomf); A["non"].append(non); A["noff"].append(noff); A["fa"].append(fa); A["re"].append(re); A["ch"].append(ch)
        A["logr"].append(logr); A["logrA"].append(logrA); A["aft"].append(aft); A["sus"].append(sus)
        A["cv"].append(cv); A["cc"].append(cc); A["crl"].append(crl); A["sj"].append(sj); A["csc"].append(csc)
        # index is t*f*gran, so gran IS the fractional width; an absolute
        # width in Hz is that same number divided by where the partial sits.
        A["cbw"].append(_CBW[1]/max(1e-6,nomf) if _CBW[1] > 0.0 else _CBW[0])
        A["tbav"].append(_TB[0]); A["tau"].append(_TB[1]); A["tcut"].append(_TB[2])
        A["vd"].append(_VB[0]); A["vr"].append(_VB[1]); A["vp"].append(_VB[2])
        A["delL"].append(dl); A["delR"].append(dr)
        A["gr"].append(gr); A["cr"].append(cr); A["pl"].append(_PL[0])
        if _place is None and ampM > 0.0:
            # Q is how much louder this partial is toward the listener than its
            # own spherical average, so ampM^2/Q is the power it feeds the room.
            # Read at the band centre: the sphere integral is cached per radius
            # and frequency, and per-partial resolution buys nothing here.
            bi = min(range(len(ROOM_BANDS)),
                     key=lambda i: abs(math.log(max(nomf, 1e-6) / ROOM_BANDS[i])))
            try:
                q = props.directivity_factor(ROOM_BANDS[bi], px, pz, _radius[0])
            except Exception:
                q = 1.0
            e = ampM * ampM
            _QACC[bi][0] += e
            _QACC[bi][1] += e / max(q, 1e-6)
        if _place is not None or not REFLECT:
            return
        _direct_az = math.atan2(px, max(props.radiation_distance, 1e-6))
        # THE REFLECTIONS. Each is this same partial heard again off one
        # surface, and every term in it is frequency-dependent, which is why it
        # belongs here and not in a reverb: how much the instrument sent that
        # way (its directivity at the departure angle, not at the listener),
        # what the surface kept, and what the longer path cost in air. A
        # sampled instrument has one radiation pattern and can only delay a
        # copy of it; this sends a different spectrum at the ceiling than at
        # the audience, because that is what the instrument does.
        # The room is a hall, so the source sits at radiation_distance, not at
        # the 2 m listener_distance -- that one is a stage image chosen to give
        # the head model sensible interaural cues, not a claim about where the
        # players are (see the radiation comment in tonelib).
        for rg, rdelay, image in props.reflection_terms(
                nomf, px, props.radiation_distance, pz, _radius[0]):
            ix, iy, iz = image
            _AZ[0] = math.atan2(ix, max(iy, 1e-6))
            rli, rri, rld, rrd = props.hrtf_at(ix, iz, iy)
            gm = ampM * rg
            emit_partial(om/_PJ[0], gm*props.hrtf_gain(nomf, rli),
                         gm*props.hrtf_gain(nomf, rri), gm, nomf,
                         non + rdelay*SR, noff + rdelay*SR, fa, re, ch,
                         logr, logrA, aft, sus, cv, cc, crl, sj, csc, gr, cr, ph0,
                         _place=(rld*SR, rrd*SR, ix, iz))
        _AZ[0] = _direct_az
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

    # ONE STRING PER NOTE. When a pitch is played again, it is the SAME string:
    # the damper lands, the key comes back down, and the plectrum plucks what it
    # just stopped. Two copies of one pitch cannot sound at once on one
    # instrument, and summing them is not a small error -- they beat against
    # each other and the new attack emerges out of the old note instead of out
    # of silence.
    #
    # It only became audible when the harpsichord's release grew from a 7 ms
    # gate to a 55 ms damper: repeated notes in Bach's writing land 3 ms after
    # their own note-off, so the old release ran 50 ms into the new note. Ben
    # heard it as "every other note having their attack/release squashed", which
    # is exactly what alternating repeated pitches would sound like.
    #
    # Only the RELEASE is clipped, never the note: the player has already lifted
    # the key, so what is cut is a tail the instrument would not have sustained
    # through a re-pluck anyway.
    _next_same = {}
    _seen = {}
    for _n in sorted(notes, key=lambda e: -e[2]):
        _k = (_n[0], _n[1])
        if _k in _seen: _next_same[(_k, _n[2])] = _seen[_k]
        _seen[_k] = _n[2]
    # Occurrence index per (channel, note) in ONSET order -- the same key
    # _legato_ticks used, so a note found in seconds here is the note it judged
    # in ticks there.
    _occ = {}
    # CONSONANTS AS THEIR OWN EVENTS. They cannot ride the vowel's partials --
    # a voice has nothing at 6 kHz to scatter into an /s/ -- so each onset
    # consonant becomes a short band of noise of its own, ENDING where the vowel
    # begins. That placement is the point: a singer puts the consonant before
    # the beat so the vowel lands on it, and a consonant played ON the beat
    # drags the whole line late.
    cons_bursts = []
    _CONS_SRC = {}
    _LESLIE_CH = {}
    _SYM_CH = {}
    _AMP_CH = {}
    _AMP_REF = {}
    _AMP_IMB = {}
    _CAB_CH = {}
    _TREM_CH = {}
    _CLAV_CH = {}
    _DETUNE_CH = {}
    # A PART'S SPAN, for voices whose extra voices belong to the channel rather
    # than the note -- a bagpipe's drones are the only ones today. First note-on
    # to last note-off, so a drone sounds under the whole line instead of
    # restarting on every note of it. See SynthProperties.unison_spans_part.
    _SPAN_CH = {}
    for _e in notes:
        _c, _on, _off = _e[0], _e[2], _e[3]
        _s = _SPAN_CH.get(_c)
        _SPAN_CH[_c] = (_on, _off) if _s is None else (min(_s[0], _on), max(_s[1], _off))
    _SPANNED = set()          # channels whose part-voices have been emitted
    if _lyr and _CONS:
        _by_ch = {}
        for _e in notes:
            _by_ch.setdefault(_e[0], []).append(_e)
        for _ch, _rows in _lyr.items():
            _evs = sorted(_by_ch.get(_ch, []), key=lambda e: e[2])
            if not _evs: continue
            _ons = [e[2] for e in _evs]
            for _row in _rows:
                # A syllable may have a coda and NO onset -- "ex", "es", "il"
                # all begin on a vowel. Bailing out here when there is no
                # onset skipped their codas too, which is why the /ks/ of "ex"
                # stayed silent even once the spelling rules found it.
                _spec = _VOW.CONSONANTS.get(_row[2]) if len(_row) > 2 and _row[2] else None
                _cods = _row[3] if len(_row) > 3 and _row[3] else ()
                if isinstance(_cods, str): _cods = (_cods,)
                if not _spec and not _cods: continue
                _vol, _w, _ctr, _bw = _spec[:4] if _spec else (0.0, 0.02, 1000.0, 800.0)
                # A STOP IS A CLOSURE IN THE TUBE, and its burst is filtered by
                # the cavity in FRONT of that closure -- so the three classes
                # (velar compact, alveolar diffuse-rising, labial diffuse-
                # falling) are one fact about front-cavity length, not three
                # hand-set bands. It also makes "a velar burst follows its
                # vowel" disappear as a special case: the front cavity is cut
                # out of THAT vowel's own tract, so the peak runs from 2495 Hz
                # before /i/ to 614 before /u/ with no rule for it.
                _shape = _stop_shape(_row[2], _row[1]) if _spec else None
                _el = (_spec[4] if len(_spec) > 4 else 0.3) if _spec else 0.3
                _i = _bisect.bisect_left(_ons, _row[0] - 1e-3)
                if _i >= len(_evs): continue
                _e = _evs[_i]
                # THE LOCAL RHYTHMIC GRAIN: the shortest note hereabouts, which
                # is what sets how fast the words are going. Scaled by the
                # segment's own elasticity, so a fricative follows the tempo
                # and a plosive barely does.
                _lo = max(0, _i - 6); _hi = min(len(_evs), _i + 7)
                _gaps = [_evs[j+1][2] - _evs[j][2] for j in range(_lo, _hi-1)
                         if _evs[j+1][2] - _evs[j][2] > 1e-3]
                _unit = min(_gaps) if _gaps else CONSONANT_REF
                _w = _w * (_unit / CONSONANT_REF) ** _el
                # ...and it may not eat the note in front of it. A consonant
                # sits in the time before the beat; if there is less time than
                # it wants, it gets what there is.
                # A singer TAKES the time from the previous note -- closing
                # that vowel early to make room -- so the limit is the note's
                # own start, not its end. Capping at the end instead squeezed
                # every consonant in a legato line to the 20 ms floor.
                _prev_on = _evs[_i-1][2] if _i > 0 else 0.0
                _room = max(0.012, (_e[2] - _prev_on) * 0.6)
                _w = max(0.010, min(_w, _room))
                # Friction does not stop when voicing starts; it OVERLAPS it.
                # Ending the burst exactly on the onset put a seam there.
                _st = _e[2] - _w * 0.78
                _pan = _e[5][2] if isinstance(_e[5], tuple) and len(_e[5]) > 2 else 0.0
                _g = ((_e[4] / 127.0) ** 2) * CONSONANT_GAIN * _vol
                if _spec and _st >= 0.0:
                    cons_bursts.append((int(_st * SR), max(8, int(_w * SR)), _ctr, _bw, 1.0,
                                        _g * math.sqrt(max(0.0, 0.5 * (1.0 - _pan))),
                                        _g * math.sqrt(max(0.0, 0.5 * (1.0 + _pan))),
                                        _shape, _ch))
                # A CODA closes the syllable at the note's END rather than
                # opening it, and there can be TWO: "ex" is /ks/. Codas are
                # quieter than onsets -- a singer releases them, they do not
                # have to launch the note.
                _back = 0.0
                for _ck in reversed(_cods):
                    _cd = _VOW.CONSONANTS.get(_ck)
                    if not _cd: continue
                    _cv, _cw2, _cc, _cbw = _cd[:4]
                    _cel = _cd[4] if len(_cd) > 4 else 0.3
                    _cw2 *= (_unit / CONSONANT_REF) ** _cel
                    _cg = ((_e[4] / 127.0) ** 2) * CONSONANT_GAIN * _cv * 0.6
                    _cst = _e[3] - _back - _cw2 * 0.5
                    _back += _cw2 * 0.8
                    if _cst < 0.0: continue
                    cons_bursts.append((int(_cst * SR), max(8, int(_cw2 * SR)),
                                        _cc, _cbw, 1.0,
                                        _cg * math.sqrt(max(0.0, 0.5 * (1.0 - _pan))),
                                        _cg * math.sqrt(max(0.0, 0.5 * (1.0 + _pan))),
                                        _stop_shape(_ck, _row[1]), _ch))
    notes = sorted(notes, key=lambda e: (e[2], e[0], e[1]))
    for ch, note, on, off, vel, (v7, v11, pan), prog in notes:
        _MCH[0] = ch
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
        # CC1 IS HOW FAR OUT OF TUNE. 64 -- and no CC1 at all -- is the voice's
        # own range; 0 is a piano just tuned, 127 one nobody has touched.
        #
        # RESOLVED HERE, not in the per-channel block further down, which runs
        # AFTER this loop has already built every note: read there, the scale
        # was always its default and the wheel did nothing. And unlike the
        # clavinet's rockers it cannot be a pass over the finished table at all,
        # because a detune is in the partials' FREQUENCIES.
        if ch not in _DETUNE_CH:
            _c1d = [v for t, cc, v in sorted(ccs.get(ch, [])) if cc == 1]
            _DETUNE_CH[ch] = (_c1d[0] / 64.0) if _c1d else 1.0
        T.honky_detune = _DETUNE_CH[ch] if getattr(pc, 'detune_wheel', False) else 1.0
        # THE DRONES, on the same wheel and by the same rule. A piper corks a
        # drone BEFORE playing, not during -- playing with one tenor corked is
        # ordinary practice -- so this is a setup value read once, as the
        # clavinet's rockers and the amplifier's drive are, and not a control
        # moved mid-phrase. 64 is the voiced default and 0 corks them all.
        #
        # Set HERE, at the props construction site, and not in the per-channel
        # block further down: that block runs after every note is built, which
        # is how the honky-tonk's wheel came to do nothing at all.
        T.bagpipe_drone = (_DETUNE_CH[ch] if getattr(pc, 'drone_wheel', False)
                           else T.bagpipe_drone)
        props = pc(f0, pan, (vel/127.0)**2, chan_vol, _eff)   # pan = CC10 -> HRTF placement
        # A sung vowel picks its body from the PART's tessitura, not this note's
        # pitch, so a tenor stays a man across his whole range. See _VocalBody.
        if hasattr(props, '_sung_formants') and (ch in _tess or ch in _parts):
            # If the file carries its text, sing the vowel it asks for; the body
            # (tract length, singer's formant, formant tuning) is applied to that
            # vowel rather than bolted on afterwards.
            vbase = None
            rows = _lyr.get(ch)
            if rows:
                i = _bisect.bisect_right(rows, (on / float(SR) + 1e-3,)) - 1
                if i >= 0:
                    vbase = _VOW.VOWELS.get(rows[i][1])
            props.formants = props._sung_formants(_tess.get(ch, f0),
                                                  part=_parts.get(ch), base=vbase)
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
        # SLUR: the previous note on this channel ran up to this one, so the
        # exciter never stopped and there is no onset to make. Only voices with
        # an exciter that can carry declare legato_attack_s; see tonelib.
        _lg = getattr(props, 'legato_attack_s', None)
        if _lg is not None and (ch, note, _occ.get((ch, note), 0)) in legato:
            at = min(at, _lg)
        _occ[(ch, note)] = _occ.get((ch, note), 0) + 1
        rt = props.release_valve_time if props.release_valve_time is not None else props.chiff_max_valve_time
        # Pipe speech scales with wavelength: add speech_cycles periods of the
        # fundamental to the fixed floor (mirrors tonelib.speech_time -- bass
        # pipes speak slowly, trebles promptly).
        at = props.speech_time(at, f0); rt = props.speech_time(rt, f0)
        fade = max(1e-4, min(at, 0.45*dur))*SR; rel = max(1e-4, min(rt, 0.45*dur))*SR
        # ...and no longer than until this same string is plucked again, but
        # never SHORTER than a steal fade. A sampler stealing a voice does not
        # cut it, it fades it over a few milliseconds, because a cut is a step
        # and a step is a click -- the same lesson as the release jitter floor
        # in synthkernel.c. Bach's tightest repeat here leaves 1.3 ms, and five
        # notes in BWV 971 come in under 2, so the floor does real work. Where
        # it exceeds the gap the old note runs a few ms into the new one, which
        # is inaudible and is what a real damper does anyway: felt takes time.
        _nx = _next_same.get(((ch, note), on))
        if _nx is not None and _nx > off:
            rel = min(rel, max(RETRIGGER_FADE, _nx - off)*SR)
        # chiff burst width: short/capped, decoupled from the slow speech fade
        # A CONSONANT IS NOISE FOR ITS WHOLE LENGTH. The 45% cap is right for
        # a pipe, where chiff is a transient before the tone settles -- but a
        # consonant has no tone to settle into, and capping it left the back
        # 55% of every burst as a pure harmonic series on whatever base
        # frequency the band happened to need: a different pitch per consonant,
        # which is to say a beep. Ben: "sounds like R2D2".
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
        _PX[0] = getattr(props,'position_x',0.0); _PZ[0] = getattr(props,'position_z',0.0)
        # The consonant bursts are built before this loop runs, so they never
        # saw a props and never got a room -- see the reflection pass below.
        if ch not in _CONS_SRC:
            _CONS_SRC[ch] = (props, _PX[0], _PZ[0], _radius[0])
        if getattr(props, 'amp_drive', 0.0) and ch not in _AMP_CH:
            # TUNING_AMP_DRIVE overrides every voice's drive at once, which is
            # how the stage gets auditioned: the same passage clean, at the
            # edge of breakup and past it, with nothing else changed. It only
            # scales voices that HAVE an amplifier -- setting it does not put
            # one in front of a flute.
            # CC1 IS THE GAIN KNOB, for a voice that is not a rotor. Live it
            # already is (see live.py, LIVE_DRIVE_STEPS); offline it was
            # ignored, so a file could not ask for a setting it can ask for
            # live. Same mapping, so a part sounds the same either way:
            # amp_drive * LIVE_DRIVE_RANGE * cc/127, unquantised here because
            # offline has no recompute to economise on.
            #
            # ONE VALUE FOR THE PIECE, taken from the first CC1 on the channel.
            # A player sets an amplifier once and then plays it; the drive is a
            # SETTING offline, where live it is a control being moved. A file
            # with no CC1 keeps the voice's own amp_drive, which is what every
            # file in the corpus does.
            #
            # NOT for a rotor: CC1 offline is the half-moon switch below, and
            # the Hammond examples depend on it. Live resolved that by moving
            # the half-moon to the pitch wheel, which offline has no reason to
            # do since there is no wheel to move.
            _drv = float(props.amp_drive)
            if not getattr(props, 'leslie', False):
                _c1 = [v for t, cc, v in sorted(ccs.get(ch, [])) if cc == 1]
                if _c1:
                    _drv *= 4.0 * _c1[0] / 127.0
            _AMP_CH[ch] = float(os.environ.get('TUNING_AMP_DRIVE', _drv))
            # THE CHANNEL FADER IS NOT IN FRONT OF THE AMPLIFIER. chan_vol is
            # CC7*CC11 squared and it multiplies into every partial's gain, so
            # by the time tubeamp reads aM the mixer has already been applied
            # -- and turning a channel down was making the valve distort less,
            # which is not what a fader does. It is downstream: the amp is on
            # the instrument's signal path and the fader is after it.
            #
            # Scaling the REFERENCE by the same factor takes it back out. The
            # drive then depends only on how hard the strings are hit, and the
            # products still come out at the faded level because they scale
            # with the input. Measured on Riffsym, whose rhythm guitars sit at
            # CC7 87: they were reaching the valve at 0.37 of the reference,
            # so a nominal drive of 3.0 was rendering as about 1.1 -- the
            # distortion voice arriving at the overdriven setting.
            #
            # VELOCITY IS NOT TAKEN OUT, and must not be: how hard a string is
            # struck IS how hard the valve is driven. That is the whole point
            # of amp_reference. A fader is a different kind of number.
            _ref = getattr(props, 'amp_reference', None)
            _AMP_REF[ch] = (_ref * chan_vol) if _ref else None
            _AMP_IMB[ch] = getattr(props, 'amp_imbalance', None)
        if getattr(props, 'sympathetic_gain', 0.0) and ch not in _SYM_CH:
            _SYM_CH[ch] = props
        if getattr(props, 'cabinet', None) and ch not in _CAB_CH:
            # TUNING_CABINET=0 takes the speaker out, which is not a setting
            # anyone wants to play through -- it is the A/B that shows what the
            # cabinet is for, since a clipped signal without one has harmonics
            # all the way to Nyquist.
            if os.environ.get('TUNING_CABINET', '1') != '0':
                _CAB_CH[ch] = props.cabinet
        if getattr(props, 'clav_panel', False) and ch not in _CLAV_CH:
            # CC1 IS THE TONE ROCKERS. Six switches sit left of a D6's keyboard
            # and four of them are the tone section; the wheel sweeps those four
            # darkest to brightest. A file with no CC1 gets the panel at rest,
            # every rocker up, which is what CLAV_FLAT is.
            #
            # ONE VALUE FOR THE PIECE, from the channel's first CC1, the same
            # rule the amplifier's drive follows: a player sets the rockers and
            # then plays, where live it is a control being moved.
            _c1 = [v for t, cc, v in sorted(ccs.get(ch, [])) if cc == 1]
            _set = (int(round(_c1[0] / 127.0 * (len(T.CLAV_TONE) - 1)))
                    if _c1 else T.CLAV_FLAT)
            _set = int(os.environ.get('TUNING_CLAV', _set))
            if _set != T.CLAV_FLAT:
                _CLAV_CH[ch] = _set
        if getattr(props, 'tremolo_depth', 0.0) and ch not in _TREM_CH:
            # CC1 IS THE DEPTH KNOB. On a Rhodes suitcase and a Wurlitzer the
            # modulation depth is the one panel control a player moves while
            # playing, so the wheel is where it belongs -- and these voices ship
            # amp_drive 0, so the CC1-to-drive path above never fires and the
            # wheel is not being asked to do two jobs at once.
            #
            # A file with no CC1 gets no modulation, which is the panel's own
            # default position and what every file in the corpus will see.
            _c1 = [v for t, cc, v in sorted(ccs.get(ch, [])) if cc == 1]
            if getattr(props, 'tremolo_intrinsic', False):
                # AN INTRINSIC TREMOLO IS NOT A WHEEL EFFECT. GM 44 is called
                # Tremolo Strings: the stroke is the patch, so it is on at full
                # depth with no CC1 in the file, and the wheel scales it around
                # that rather than switching it on. A Rhodes is the other case
                # and keeps the behaviour above -- its panel default is off.
                _dep = float(props.tremolo_depth) * (
                    (_c1[0] / 64.0) if _c1 else 1.0)
            else:
                _dep = float(props.tremolo_depth) * (_c1[0] / 127.0 if _c1 else 0.0)
            if _dep > 0.0:
                _TREM_CH[ch] = (float(props.tremolo_hz), _dep,
                                bool(getattr(props, 'tremolo_stereo', False)),
                                float(getattr(props, 'tremolo_scatter', 0.0)))
        if getattr(props, 'leslie', False) and ch not in _LESLIE_CH:
            # CC1 IS THE HALF-MOON SWITCH: >=64 tremolo, below chorale. A
            # rotor has momentum, so this is a history of requests and not a
            # speed -- leslie.Rotor spends real seconds getting between them.
            import leslie as _LES0
            _req = [(t, _LES0.zone(v)) for t, cc, v in sorted(ccs.get(ch, []))
                    if cc == 1]
            if not _req or _req[0][0] > 0.0:
                _req.insert(0, (0.0, _LES0.TREMOLO
                                if getattr(props, 'leslie_fast', True)
                                else _LES0.CHORALE))
            _LESLIE_CH[ch] = _req
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
                _rx = props.rank_position_x(key)
                li,ri,_ld,_rd = props.hrtf_at(_rx)
                _DL[0] = _ld*SR; _DL[1] = _rd*SR; _PX[0] = _rx
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
                    # What the instrument radiates toward here: directivity at
                    # this partial's frequency, less what the air ate on the way.
                    # The head model is applied on top of it, not instead of it.
                    # An organ rank's aperture follows its own pipe, not the
                    # class: scaling makes ka = 0.105 * harmonic whatever the
                    # note, so the fundamentals go everywhere and the upperwork
                    # is aimed. Everything else uses its fixed aperture.
                    _radius[0] = (props.pipe_radius(f0*eff_ratio)
                                  if organ and hasattr(props, 'pipe_radius') else None)
                    gM = hv*gain*props.radiation_gain(hf, radius=_radius[0])
                    gL = gM*props.hrtf_gain(hf, li); gR = gM*props.hrtf_gain(hf, ri)
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
                    emit_partial(2*math.pi*hf/SR, gL, gR, gM, hf, non_m, noff, pfade, rel, chiff,
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
                        emit_partial(2*math.pi*hf/SR, gL*bg, gR*bg, gM*bg, hf, non_m+pd, noff,
                                     bfade, rel, chiff, logr, logrA, aftL, props.sustain_level,
                                     cvp, cc, crl, sjit, csc, gr, cr)
                    transverse.append((hf, hv, dbps))
                    # A DRONE IS THE PART, NOT THE NOTE: emit it once for the
                    # channel, spanning its whole range, and skip it on every
                    # later note. See SynthProperties.unison_spans_part.
                    _spans_part = getattr(props, 'unison_spans_part', False)
                    _uv = () if (_spans_part and ch in _SPANNED) \
                        else props.unison_voices(f0, m, dbps)
                    for ui, (gm, off_hz, dr, ud, uph) in enumerate(_uv):
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
                            _PX[0] = props.section_position_x(ui + 1)
                            ugL = gM*gm*props.hrtf_gain(hf, sli)
                            ugR = gM*gm*props.hrtf_gain(hf, sri)
                            _DL[0] = sld*SR; _DL[1] = srd*SR
                        _PL[0] = ui + 1
                        non_u = non_r + (min(onsets[ui+1], 0.25*dur)*SR
                                         if (onsets and ui+1 < len(onsets)) else 0.0)
                        noff_u = noff
                        if _spans_part:
                            # The channel's whole range, not this note's. Emitted
                            # only once per channel -- see the guard above.
                            non_u = _SPAN_CH[ch][0]*SR
                            noff_u = _SPAN_CH[ch][1]*SR
                        emit_partial(2*math.pi*uf/SR, ugL, ugR, gM*gm, uf, non_u, noff_u, pfade, rel, chiff,
                                     ulr, logrA, aftL, props.sustain_level, cvp, cc, crl, sjit, csc, gr, cr,
                                     2*math.pi*uph)
                    _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0    # main voice only within this harmonic
                    _PL[0] = 0
                    _PX[0] = getattr(props,'position_x',0.0)
                    if seats:
                        _DL[0] = seats[0][2]*SR; _DL[1] = seats[0][3]*SR
        # MARKED AFTER THE WHOLE NOTE, not inside the harmonic loop: the guard
        # above runs once per harmonic, so marking it there would emit the drone
        # for harmonic 1 and skip it for every other.
        if getattr(props, 'unison_spans_part', False):
            _SPANNED.add(ch)
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
                    g = coupling*va*vb*(1.0 if a==bb else 2.0)*props.radiation_gain(fph)
                    if g < floor: continue
                    dph = da+db_; lrp = math.log(T.db_ratio(dph)) if dph>0 else 0.0
                    aftp, adbp = props.aftersound(f0, dph); lrAp = math.log(T.db_ratio(adbp)) if adbp>0 else 0.0
                    emit_partial(2*math.pi*fph/SR, g, g, g, fph, non, noff, fade, rel, chiff,
                                 lrp, lrAp, aftp, props.sustain_level, 0.0, 0.0, 0.0, 0.0, csc, -1, 0)
        # THE MECHANISM LETTING GO. On a harpsichord the key coming up is not
        # only the damper arriving: the jack falls back and its tongue brushes
        # past the string it just plucked. That is a MECHANICAL event, not a
        # string one -- it happens at the same frequencies whatever note was
        # played -- so it cannot be an envelope on the note's own partials, and
        # it is not what chiff does either (chiff is jittered phase ON the
        # partials, so it wears the note's spectrum and fades out with it).
        #
        # It is emitted here as what it is: a separate short event at note-off,
        # at fixed frequencies, riding the note's gain so that a quiet note
        # clicks quietly. Voices that leave release_click_db at None -- every
        # voice but this one -- emit nothing and cost nothing.
        cdb = getattr(props, 'release_click_db', None)
        if cdb is not None and props.release_click_modes:
            cg = gain * (10.0 ** (cdb / 20.0))
            cdec = math.log(T.db_ratio(props.release_click_decay_db))
            for chz, camp in props.release_click_modes:
                if chz >= SR / 2:
                    continue
                a_ = cg * camp * props.radiation_gain(chz)
                # A floor of its own, relative to the NOTE's gain rather than an
                # absolute level, so a quiet note does not keep its mechanism
                # after its tone has gone. That is exactly what a voice whose
                # CC11 was misread as expression sounded like -- all clicks and
                # no instrument -- because the note's partials were culled and
                # the mechanism, having no floor, was not.
                if a_ < 3e-3 * gain:
                    continue
                emit_partial(2 * math.pi * chz / SR, a_ * props.hrtf_gain(chz, li),
                             a_ * props.hrtf_gain(chz, ri), a_, chz,
                             noff, noff + props.release_click_s * SR,
                             max(1e-4, 0.0005) * SR, max(1e-4, 0.002) * SR, chiff,
                             cdec, cdec, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, csc, -1, 0)
    # A CONSONANT IS SUNG BY THE SECTION, NOT BY A POINT.
    #
    # This is why the consonants sat forward of the choir. A vowel is rendered
    # once per SEAT -- section_seats() gives every singer their own position,
    # their own pair of ear delays, their own onset -- so it arrives as a body
    # of people spread across the stage. The burst was emitted once, at one
    # pan, from one place. Decorrelating its two channels helped and did not
    # fix it, because the problem was never stereo width: it was that eighteen
    # singers made the vowel and one made the consonant.
    #
    # So each burst is now emitted once per seat, with that seat's ear gains
    # and delays, its own noise, and its own small timing scatter -- because
    # singers do not release a /t/ on the same sample, which is precisely why
    # choral consonants are hard to get together. Amplitude divides by the
    # square root of the count, the seats being incoherent.
    #
    # They also get the room, for the same reason: reflections are emitted as
    # partials, and a burst is not a partial, so until now every consonant was
    # dry against voices that each carried their images. Each image is taken
    # at the BURST'S OWN centre frequency -- every term in a reflection is
    # frequency-dependent, and a consonant lives two octaves above a vowel --
    # and panned from the IMAGE's direction, not the source's, which is what
    # makes a reflection widen rather than thicken.
    _out = []
    for _bi, _b in enumerate(cons_bursts):
        _s, _n, _ctr, _bw, _amp, _gl, _gr, _shape, _bch = _b
        _src = _CONS_SRC.get(_bch)
        _fc = float(_ctr) or 3000.0
        _g = math.sqrt(_gl * _gl + _gr * _gr)
        _emit = []
        _seats = None
        if _src is not None:
            _pr = _src[0]
            try:
                _seats = _pr.section_seats()
            except Exception:
                _seats = None
        if _seats:
            _ns = len(_seats)
            _sc = _g / math.sqrt(_ns)
            for _si, (_li, _ri, _ld, _rd) in enumerate(_seats):
                # deterministic scatter, +-1 of a raised span, no RNG state
                # Deterministic, so a render repeats, but it has to be a real
                # hash: taking three windows of ONE multiply gave three views
                # of the same bits, and the seven "random" offsets came out a
                # straight line -- singers walking in evenly, which is not
                # scatter, it is a canon.
                _j = 0.0
                for _k in range(3):
                    _hv = (_bi * 0x9E3779B1) ^ (_si * 0x85EBCA6B) ^ (_k * 0xC2B2AE35)
                    _hv = (_hv ^ (_hv >> 15)) * 0x2545F491
                    _hv = (_hv ^ (_hv >> 13)) & 0xFFFFFFFF
                    _j += _hv / 4294967295.0 - 0.5
                _dj = int(CONSONANT_SCATTER * SR * (_j / 3.0) * 6.0)
                _emit.append((_s + int(_ld * SR) + _dj, _s + int(_rd * SR) + _dj,
                              _sc * _pr.hrtf_gain(_fc, _li),
                              _sc * _pr.hrtf_gain(_fc, _ri), _si))
        else:
            _emit.append((_s, _s, _gl, _gr, 0))
        if REFLECT and _src is not None:
            _pr, _px, _pz, _rad = _src
            try:
                _terms = _pr.reflection_terms(_fc, _px, _pr.radiation_distance,
                                              _pz, _rad)
            except Exception:
                _terms = []
            for _ti, (_rg, _rdelay, _image) in enumerate(_terms):
                _ix, _iy, _iz = _image
                _d = math.sqrt(_ix*_ix + _iy*_iy + _iz*_iz) or 1e-9
                _ip = max(-1.0, min(1.0, _ix / _d))
                _rs = _s + int(_rdelay * SR)
                _rgain = _g * float(_rg)
                _emit.append((_rs, _rs,
                              _rgain * math.sqrt(max(0.0, 0.5 * (1.0 - _ip))),
                              _rgain * math.sqrt(max(0.0, 0.5 * (1.0 + _ip))),
                              100 + _ti))
        # AND A STABLE ID. noisegen seeds each burst's noise from its position
        # in the list, so filtering the list for a stem renumbers every burst
        # and it comes out as DIFFERENT noise -- which is why the stems did not
        # sum back to the mix. The index into the full list is the thing that
        # does not move.
        _out.append((_n, _ctr, _bw, _shape, tuple(_emit), _bch, _bi))
    cons_bursts = _out

    # THE NOTES NOBODY HIT, AND THEY RUN BEFORE THE AMPLIFIER. A sympathetic
    # note is part of what the instrument produces, so it is part of what an
    # amplifier would be handed -- and part of what a room would hear. See
    # sympathetic.py, and note that a steelpan's coupling turned out to be a
    # mechanical kick through shared steel rather than resonance.
    if _SYM_CH:
        import sympathetic as _SYM
        _ns = _SYM.expand(A, _SYM_CH, SR, PARTIAL_COLS + ('az', 'dr'),
                          freq=FREQ)
        if _ns:
            print("  sympathetic: %d channel(s), %d partials from notes nobody hit"
                  % (len(_SYM_CH), _ns))

    # THE AMPLIFIER, AND IT RUNS FIRST. A Leslie's chain is organ -> amp ->
    # crossover -> rotors, so the valve is upstream of the rotor; here that is
    # simply which of two passes goes first, because both work on partials.
    # Distortion products emitted now are picked up by the rotor pass below and
    # given their Doppler and their level swing exactly as any other partial.
    if _AMP_CH and __import__('tubeamp').ENABLED:
        import tubeamp as _AMP
        _na = _AMP.expand(A, _AMP_CH, SR, PARTIAL_COLS + ('az', 'dr'),
                          references=_AMP_REF, imbalances=_AMP_IMB)
        if _na:
            print("  tube amp: %d channel(s), %d distortion partials"
                  % (len(_AMP_CH), _na))

    # THE SPEAKER, AFTER THE AMPLIFIER AND BEFORE THE ROOM. A cabinet creates
    # nothing -- it only fails to pass things -- but it has to see the
    # amplifier's output or it is not in the chain at all: a clipped signal has
    # harmonics to Nyquist and a real 12" throws nearly all of them away. Put
    # this before the amp pass, or on the voice class as a FormantBody, and
    # every distortion product bypasses the speaker. See cabinet.py.
    # THE CLAVINET'S TONE ROCKERS. A preamp filter of FREQUENCY, so it scales
    # the partials that exist rather than making any, and the same function
    # serves the live per-block gain. Before the speaker, because it is in the
    # instrument.
    if _CLAV_CH:
        nf = A['nf']
        for ch, setting in _CLAV_CH.items():
            sel = np.asarray(A['mch']) == ch
            if not sel.any():
                continue
            g = T.clav_tone_gain(np.asarray(nf)[sel], setting)
            for col in ('aL', 'aR', 'aM'):
                v = np.asarray(A[col]); v[sel] *= g
                A[col] = list(v) if isinstance(A[col], list) else v
            print("  clavinet: %s, %d partials through the tone section"
                  % (T.CLAV_TONE[setting][0], int(sel.sum())))

    # THE TREMOLO, and on a Rhodes it is a stereo pan rather than a level
    # swing. After the amplifier so that a valve works on the carrier and not
    # on the sidebands, before the speaker so the speaker colours them. See
    # tremolo.py, which argues both placements.
    if _TREM_CH:
        import tremolo as _TRM
        _nt = _TRM.expand(A, _TREM_CH, SR, PARTIAL_COLS + ('az', 'dr'))
        if _nt:
            _r0 = list(_TREM_CH.values())[0]
            print("  tremolo: %.1f Hz, depth %.2f%s, %d sidebands"
                  % (_r0[0], _r0[1], " (stereo pan)" if _r0[2] else "", _nt))

    if _CAB_CH:
        import cabinet as _CAB
        _nc = _CAB.expand(A, _CAB_CH, SR, PARTIAL_COLS + ('az', 'dr'))
        if _nc:
            print("  cabinet: %s, %d partials through the speaker"
                  % ("/".join(sorted(set(_CAB_CH.values()))), _nc))

    # THE ROTATING SPEAKER. Every row already knows where it went -- px/pz is
    # the listener's position for a direct partial and the IMAGE's for a
    # reflected one -- so each takes the rotor phase of its own azimuth, and
    # the room hears a different quarter of the turn than the listener does.
    # That difference is the effect; see leslie.py.
    if _LESLIE_CH:
        import leslie as _LES
        _n = _LES.expand(A, _LESLIE_CH, SR, PARTIAL_COLS + ('az', 'dr'))
        if _n:
            print("  leslie: %d channel(s), %d sideband partials, %d speed change(s)"
                  % (len(_LESLIE_CH), _n,
                     sum(len(v) - 1 for v in _LESLIE_CH.values())))

    P = len(A["om"])
    def arr(k,dt): return np.ascontiguousarray(np.array(A[k], dt))
    # Effective Q per band: direct energy over energy fed to the room. One
    # number per octave, derived from what this piece actually radiated rather
    # than guessed once for the whole orchestra.
    room_q = []
    for i, f in enumerate(ROOM_BANDS):
        d, r = _QACC[i]
        room_q.append((f, (d / r) if r > 0.0 else 1.0, d))
    prep = dict(lib=lib, P=P, N=N, nblk=nblk, total=total, sh=sh, G=G, S=S,
                cons_bursts=cons_bursts,
                room_q=room_q)
    for k,dt in (("az","f4"),("om","f8"),("p0","f8"),("aL","f4"),("aR","f4"),("aM","f4"),("mch","i4"),
                 ("px","f4"),("pz","f4"),("nf","f4"),
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
    # Friction is not a partial. The consonant bursts are generated and mixed
    # here rather than scheduled as voices -- see noisegen.py for why.
    _NG.mix(L, R, n0, prep.get('cons_bursts'), SR)
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

_LAST_PREP = {}


def render(path, tuner='hybrid440'):
    prep = prepare(path, tuner)
    _LAST_PREP.update(prep)
    t0=time.time(); L,R = synth_window(prep, 0, prep['N']); kdt=time.time()-t0
    return L,R,prep['total'],prep['P'],kdt


# ---------------------------------------------------------------- stems/objects
#
# The partial table already separates every source: each row knows which MIDI
# channel it came from, what the instrument radiates (aM) and what each ear
# receives (aL/aR, aM times a per-ear head-shadow gain). So a per-part render is
# a row selection, not a second engine, and an object render is that selection
# with the head model left off.
#
# Which you want depends on who applies the listener model:
#
#   stems    keep the head model. Stereo, and they sum back to the full mix
#            sample for sample. For mixing, and for checking one part in place.
#
#   objects  drop it. Mono, source-referenced, carrying the position the source
#            actually sits at -- what object audio (ADM BWF, Atmos) wants,
#            because there the RENDERER owns the listener. Baking our head into
#            an object would put two head models in series.

def channel_rows(prep):
    """{MIDI channel: row mask} over the partial table."""
    mch = prep['mch']
    return {int(c): (mch == c) for c in np.unique(mch)}


def source_rows(prep):
    """{(channel, player, rank): row mask}, one entry per physical source.

    Finer than channel_rows by exactly as much as the model already knows: the
    players of a section sit at their own desks (pl) and an organ's drawstops
    stand at their own places in the case (gr), so one channel is usually
    several sources.

    Grouping is by WHO is playing, not by where the sound came from. Position
    is not an identity here: position_x carries a pitch term
    (octave_position * octave_width), so every note of a part sits at a slightly
    different place, and grouping on the coordinate splits one player into one
    source per note -- 812 of them for Neptune, against an Atmos ceiling of 118.
    An object is a thing that persists and moves; the movement belongs in its
    position over time, not in its identity.
    """
    mch = prep['mch'].astype(np.int64)
    pl = prep['pl'].astype(np.int64)
    gr = prep['gr'].astype(np.int64)
    key = (mch << 40) ^ (pl << 20) ^ (gr + 1)
    out = {}
    for k in np.unique(key):
        m = key == k
        out[(int(mch[m][0]), int(pl[m][0]), int(gr[m][0]))] = m
    return out


def source_position(prep, mask):
    """Where a source sits: its partials' mean position, amplitude-weighted so
    the notes it actually projects count for more than the ones it whispers."""
    w = prep['aM'][mask].astype(np.float64)
    s = w.sum()
    if s <= 0:
        return float(prep['px'][mask].mean()), float(prep['pz'][mask].mean())
    return (float((prep['px'][mask] * w).sum() / s),
            float((prep['pz'][mask] * w).sum() / s))


def subset(prep, mask, objectify=False):
    """A prep holding only the masked rows.

    With objectify, the rows are re-pointed at what the instrument radiates:
    both ears get aM, and the interaural delay -- which is a fact about a head,
    not about a source -- is removed from both the envelope and the carrier
    phase. p0R must follow p0 for that; leaving it would keep an ITD in the
    carrier while claiming there is none, the same trap the ear-delay comment
    above describes from the other side.
    """
    out = dict(prep)
    # THE BURSTS ARE NOT PARTIALS AND SO ARE NOT MASKED BY THE ROW SELECTION.
    # dict(prep) carries the whole list into every stem, and synth_window mixes
    # whatever it is handed -- so four choir stems each got all 369 consonants
    # and their sum had them four times over. Silent in a plain render, because
    # there is only one stem; silent in a stems render too, until somebody adds
    # the stems back up, which is exactly what a per-part tract pass does.
    bursts = prep.get('cons_bursts')
    if bursts:
        chans = set(int(c) for c in np.unique(prep['mch'][mask]))
        out['cons_bursts'] = [b for b in bursts
                              if len(b) < 6 or int(b[5]) in chans]
    # By name, not by length: G and S are the registration blocks, not partial
    # columns, and selecting on len(v) == P would take them too on any file
    # whose partial count happened to equal its rank count.
    for k in PARTIAL_COLS:
        out[k] = np.ascontiguousarray(prep[k][mask])
    out['P'] = int(mask.sum())
    if objectify:
        out['aL'] = out['aR'] = np.ascontiguousarray(out['aM'])
        out['p0R'] = np.ascontiguousarray(out['p0'])
        z = np.zeros(out['P'], np.float32)
        out['delL'] = z; out['delR'] = z.copy()
    return out


def render_parts(path, tuner='hybrid440', objects=False, by='channel'):
    """Render one signal per part. Yields (key, position, L, R, partials).

    `by` is 'channel' (one per MIDI channel) or 'source' (one per distinct
    radiating point -- each desk of a section, each drawstop of a case).
    R is R for a stem and a copy of L for an object.
    """
    prep = prepare(path, tuner)
    # Same as render(): the directivity this piece measured has to reach
    # roomtail, and a stems render is no less entitled to it than a plain one.
    _LAST_PREP.update(prep)
    if by == 'source':
        groups = [(k[0], source_position(prep, m), m)
                  for k, m in sorted(source_rows(prep).items())]
    else:
        groups = [(ch, None, m) for ch, m in sorted(channel_rows(prep).items())]
    for ch, pos, mask in groups:
        sub = subset(prep, mask, objectify=objects)
        if not sub['P']:
            continue
        L, R = synth_window(sub, 0, sub['N'])
        yield ch, pos, L, R, sub['P']


def write_wav_mono(path, L):
    """One channel, at the rate it was rendered at (see write_wav)."""
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(4); w.setframerate(SR)
    w.writeframes((np.clip(L, -1, 1) * 2147483647.0).astype('<i4').tobytes()); w.close()

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
    inp,outp=sys.argv[1],sys.argv[2]; tuner=sys.argv[3] if len(sys.argv)>3 else 'hybrid440'
    # Optional 4th argument sets the pitch everything tunes to: "a=432" names the
    # frequency of A4, "c=256" the frequency of middle C. Which end you give
    # matters -- a temperament's own A-to-C ratio is not equal temperament's, so
    # c=256 lands on a different A in each one. Omit it to keep each
    # temperament's own reference. See tunelib.set_reference.
    if len(sys.argv)>4 and not sys.argv[4].startswith('--'):
        k,_,v = sys.argv[4].partition('=')
        if k.strip().lower() not in ('a','c') or not v:
            raise SystemExit("pitch reference must be a=<hz> or c=<hz>, e.g. a=432")
        midilib.set_reference(**{k.strip().lower(): float(v)})
    # blockrender.py IN.mid OUT.wav [tuner] [a=440]
    #                [--stems DIR | --objects DIR [--by-source]] [--no-reflect]
    mode = None; outdir = None
    for i, a in enumerate(sys.argv):
        if a in ('--stems', '--objects') and i + 1 < len(sys.argv):
            mode = a[2:]; outdir = sys.argv[i + 1]
    if mode:
        import os
        os.makedirs(outdir, exist_ok=True)
        base = os.path.splitext(os.path.basename(inp))[0]
        by = 'source' if '--by-source' in sys.argv else 'channel'
        t0 = time.time(); n = 0; tot = 0.0; P = 0; manifest = []
        seen = {}
        for ch, pos, L, R, p in render_parts(inp, tuner, objects=(mode == 'objects'), by=by):
            if pos is None:
                name = "%s.ch%02d" % (base, ch)
            else:
                i = seen[ch] = seen.get(ch, -1) + 1
                name = "%s.ch%02d.s%02d" % (base, ch, i)
            f = os.path.join(outdir, name + ".wav")
            if mode == 'objects': write_wav_mono(f, L)
            else: write_wav(f, L, R)
            rec = {"file": name + ".wav", "channel": ch, "partials": p}
            if pos is not None:
                rec["x_m"], rec["z_m"] = round(pos[0], 4), round(pos[1], 4)
            manifest.append(rec)
            print("  ch%-3d %s%8d partials -> %s"
                  % (ch, "" if pos is None else "x=%+6.2f z=%+5.2f " % pos, p, f))
            n += 1; P += p; tot = len(L) / float(SR)
        # Positions travel with the audio, or the objects are just files.
        import json
        # The same sidecar a plain render writes. Without it a stems render fed
        # roomtail nothing and roomtail fell back to a scalar Q: on Vivaldi's
        # Summer that meant Q=2.0 where the piece actually radiated Q=1.0, and
        # the room came out about 3 dB drier than the -3 dB target it was
        # placed for. Silent, and in exactly the quantity the placement tunes.
        _rq = _LAST_PREP.get('room_q')
        if _rq:
            with open(os.path.join(outdir, base + ".room.json"), "w") as fh:
                json.dump({"bands": [{"hz": f, "q": q, "energy": e}
                                     for f, q, e in _rq]}, fh, indent=1)
        with open(os.path.join(outdir, base + ".objects.json"), "w") as fh:
            json.dump({"source": os.path.basename(inp), "sample_rate": SR,
                       "listener_distance_m": T.SynthProperties.listener_distance,
                       "radiation_distance_m": T.SynthProperties.radiation_distance,
                       "objects": manifest}, fh, indent=1)
        dt = time.time() - t0
        print("blockrender %s: %d parts, %d partials, %.1fs audio, %.2fs = %.1fx realtime"
              % (mode, n, P, tot, dt, tot / dt if dt else 0.0))
        raise SystemExit(0)
    t0=time.time(); L,R,total,P,kdt=render(inp,tuner); dt=time.time()-t0
    write_wav(outp, L, R)
    _rq = _LAST_PREP.get('room_q')
    if _rq:
        import json
        with open(os.path.splitext(outp)[0] + '.room.json', 'w') as fh:
            json.dump({'bands': [{'hz': f, 'q': q, 'energy': e} for f, q, e in _rq]}, fh, indent=1)
    print("blockrender: %.1fs audio, %d partials, kernel %.2fs, total %.2fs = %.1fx realtime -> %s"%(total,P,kdt,dt,total/dt,outp))
