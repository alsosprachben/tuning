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
each partial at a constant frequency within a block and modulates its
amplitude, where the reference evaluates the partial per sample.

Read that as "within a block", because the exceptions now matter more than the
rule: vibrato, the tension-bend attack and a moving pitch wheel all move a
partial's frequency, and all three are integrated by the kernel rather than
approximated -- the wheel via `bend_blocks`, which costs two kernel rows per
channel and not two per partial, because a bend is a RATIO and the partial's
own frequency factors out of the accumulated phase. What is left is that a
block boundary is where a continuous change is sampled, so small
phase-sensitive differences follow from the block size.

(This paragraph said flatly "holds each partial at a CONSTANT frequency" for
longer than it was true, four lines under a warning about exactly that. See
midi.md, which was written because of it.)

WHAT CONTROLS IT READS: thirty-five CCs -- 1, 5, 6, 7, 10, 11, 38, 64-67,
71-78, 84, 91, 93, 96-101, 120, 121, 123-127 -- with RPN 0/0 to 0/5, GS's
sound NRPNs 01 xx, plus
program change, both aftertouches, the pitch wheel and SysEx (GM System On,
GM2 Scale/Octave Tuning, Master Volume, Fine and Coarse Tuning). The pedals are
here and not only in live.py. Until the RPNs arrived this list claimed GM
System On, which nothing in this file read.
CC91 is here and NOT in live.py, because a reverb send offline is a distance
from the microphone and needs no new DSP; live it would be a convolver on the
audio thread. Seeing the whole file first is this renderer's advantage and is
why the damper, sostenuto and una corda are decided at a note's onset from
events that have not happened yet. midi.md is the full surface.

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
import sys, os, time, ctypes, subprocess, wave, math, re, cmath
import numpy as np, mido
import bisect as _bisect
import mts as _MTS
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
import chorus as _CHR
import mf104 as _MFD
import gsdelay as _GSD
import gsefx as _GSX
import ctrlmatrix as _CMX

# Mirrors RAND_GRAN in synthkernel.c: the chiff phase is redrawn at this many
# times the partial's frequency per second, which at 100000 is every sample --
# a white wash. See chiff_bandwidth.
RAND_GRAN = 100000.0
# live builds its templates PLAIN of the Hammond scanner and applies the
# selector per note at the stamp (scanner.apply), so a switch moved mid-
# performance takes the next keys without a template per position
SCANNER_OFF = False
from patch_map import property_class_for_program, property_class_for_note, program_trim
from patch_map import VariationProgram, VARIATIONS, layers_of
from brass_fingering import cents_offset as brass_cents, INSTRUMENTS as BRASS_KIND
from percussion_map import (percussion_for_note, choke_group, rasp_strokes,
                            GM_PERCUSSION_CHANNEL, DrumProgram, is_drum, kit_for_program,
                            key_layers, KITS, kit_in_map)

# SR is the engine's sample rate. It used to be hardcoded here AND as six literal
# 44100s inside the kernel, so it could not actually be changed; the kernel now
# takes it as a parameter. Offline rendering stays at 44100 (the whole corpus is
# rendered there); a live front end sets it to match the audio device -- PipeWire
# on this machine runs the graph at 48000, and resampling in the path is both
# latency and a filter we did not choose.
SR = 44100
TAU = 0.015; BLK = 512
# How long after its note-off a note still counts as sounding, for deciding
# whether a channel's fader moves under it (prepare, THE CHANNEL FADER): its
# release, a pedal's tail, a ring.
FADER_TAIL = 2.0
# A channel is mt32mux-STAMPED (its CC7 a snapshot for the next note, not a
# fader) when this share of its notes has a CC7 at most STAMP_S before it.
STAMPED_SHARE = 0.9
STAMP_S = 0.005


def set_sample_rate(sr):
    """Set the engine sample rate. Call before prepare(); everything downstream
    (note-on/off sample indices, fades, the kernel's own time base) reads it."""
    global SR
    SR = int(sr)
HERE = os.path.dirname(os.path.abspath(__file__)); LIB = os.path.join(HERE, "libsynth.so")

# what reflection_terms and hrtf_at read of a voice besides their arguments
# (tonelib: reflection_terms, image_sources, surface_reflection,
# directivity_gain, off_axis_angle, air_absorption_db_per_m, hrtf_at). A new
# attribute read there must be added here, or prepare's memo goes stale:
# examples/prepcheck.py compares the table with the memo against without.
_REFL_ATTRS = ('radiation_distance', 'directivity_radius', 'directivity_floor',
               'directivity_axis_deg', 'sound_speed', 'reflection_order',
               'reflection_floor_db', 'reflection_fusion_s',
               'room_left', 'room_right', 'room_back', 'room_front', 'room_floor', 'room_ceiling',
               'air_temperature_c', 'air_pressure_kpa', 'air_humidity_pct', 'head_radius')


# A COLUMN'S STORAGE, by what reads it back before the table is final. A
# column read back -- by the sound controllers, the clavinet's tone section,
# or an effect that builds from the partials already there (sympathetic,
# mf104, tubeamp, tremolo, chorus, cabinet, leslie read levels, phases,
# frequencies, onsets, vibrato, ear delays) -- keeps the double it was
# computed as. A float32 column nothing reads back is stored as float32 from
# the start: array('f') rounds a double exactly as the final cast does. An
# int32 column is stored as int32, and array('i') REFUSES a float, so a
# column wrongly listed here fails loudly rather than rounding quietly.
# examples/prepcheck.py --against compares the table with the last commit's.
_COL_F4 = ("px", "pz", "fa", "ch", "aft", "sus", "cv", "cc", "crl", "sj", "csc", "cbw",
           "tbav", "tau", "tcut", "gb", "gt", "gc", "vdl", "rdl", "nfr")
_COL_I4 = ("mch", "br", "gr", "cr", "pl", "fx", "mk")


def _dcol(name):
    from array import array
    return array('f' if name in _COL_F4 else 'i' if name in _COL_I4 else 'd')


PREP_MEMO = True        # False: every call made afresh (examples/prepcheck.py)
PREP_MEMO_MAX = 50000   # entries before the memo is emptied (see prepare)
PREP_MEMO_STATS = [0, 0, 0]     # lookups, misses, times emptied


def _refl_state(props):
    return (type(props), id(props.SURFACE_ALPHA), id(props.SURFACE_SCATTER)) + tuple(
        getattr(props, a) for a in _REFL_ATTRS)


def ensure_lib():
    src = os.path.join(HERE, "synthkernel.c")
    # One .so per sample rate: SRATE is a compile-time constant in the kernel, so
    # that -ffast-math can fold the divisions exactly as it always did (see the
    # note above SRATE in synthkernel.c).
    return _build(src, "libsynth_%d.so" % SR, [], ["synth_voice"])


# synth_voice's source is synthkernel.c AND the fragments it includes
KERNEL_PARTS = ("synthkernel.c", "voice_main.inc", "voice_partial.inc", "voice_block.inc", "voice_moog.inc",
                "voice_cell.inc", "voice_noise.inc", "voicedesc.h")


def _build(src, name, defs, funcs):
    lib = os.path.join(HERE, name)
    newest = max(os.path.getmtime(os.path.join(HERE, f)) for f in KERNEL_PARTS)
    if (not os.path.exists(lib)) or newest > os.path.getmtime(lib):
        # built to a temporary name and moved: a live engine and a render
        # starting at once must never load a half-written library
        tmp = "%s.%d.tmp" % (lib, os.getpid())
        subprocess.check_call(["gcc","-O3","-march=native","-ffast-math","-fopenmp","-shared","-fPIC",
                               "-DSRATE=%d" % SR] + defs + [src,"-o",tmp,"-lm"])
        os.replace(tmp, lib)
    dll = ctypes.CDLL(lib)
    for f in funcs:
        _declare(dll, src, f)
    return dll


def ensure_gpu_lib():
    """The kernel built with voice_block and voice_samples (-DVOICE_BLOCK): the
    GPU renderer's block setup. A library of its own, because compiling them
    beside synth_voice changes how gcc inlines it (see synthkernel.c)."""
    src = os.path.join(HERE, "synthkernel.c")
    return _build(src, "libsynthgpu_%d.so" % SR, ["-DVOICE_BLOCK"],
                  ["synth_voice", "voice_block", "voice_samples", "voice_sizes", "voice_pack"])



def ensure_xdec_lib():
    """The kernel built with synth_voice_xdec (-DXDEC_KERNEL): synth_voice with
    its fast noise rows drawn as exponentials (synthkernel.c xdec_block), for
    the rows synth_partials sends it. A library of its own because any line of
    it inside synth_voice moved 109 of 167 corpus files (-ffast-math)."""
    src = os.path.join(HERE, "synthkernel.c")
    return _build(src, "libsynthxdec_%d.so" % SR, ["-DXDEC_KERNEL"], ["synth_voice_xdec"])


# A ROW FASTER THAN A BLOCK (synthkernel.c xdec_block): a row with a plain
# decay (no sustain, no second stage), no gate, no Moog, falling more than
# 20 dB in a block -- every strike's burst whose decay is quick, noise or
# tonal (a guiro's ridges, held up as the line and stepped at block edges).
# Such rows render through synth_voice_xdec; a table without one makes the
# one call it always made.
XDEC_NEPERS = 2.302585


def _xdec_rows(a, i0, i1):
    """The indices in [i0, i1) of rows synth_voice_xdec draws; empty: none."""
    m = (a['sus'][i0:i1] <= 0) & (a['aft'][i0:i1] <= 0) \
        & (a['logr'][i0:i1] * BLK > XDEC_NEPERS * SR) & (a['gr'][i0:i1] < 0)
    if a.get('BL') is not None:
        m &= a['br'][i0:i1] < 0
    if a.get('FT') is not None and 'fx' in a:
        m &= a['fx'][i0:i1] < 0
    return np.flatnonzero(m) + i0


def ensure_lobe_lib():
    """The kernel built with synth_voice_lobe (-DLESLIE_KERNEL): synth_voice
    with the Leslie's lobe on its rotor rows (leslie.KERNEL_LOBE), for a table
    that has one. A library of its own for the reason the GPU's is: a rotor
    test inside synth_voice moved 110 of 167 corpus files by an ULP."""
    src = os.path.join(HERE, "synthkernel.c")
    return _build(src, "libsynthlobe_%d.so" % SR, ["-DLESLIE_KERNEL"], ["synth_voice_lobe"])


# The C argument types, READ OFF THE C. Without argtypes a ctypes call does no
# checking at all: get the call site and the prototype out of step and you do
# not get a TypeError, you get a pointer read as a float and whatever memory
# lies past the end of an array. That is the worst failure mode in this file --
# silent, intermittent, and a day to find -- and adding the feature that
# prompted this (a pitch-bend row, three more arguments) is exactly when it
# would have happened.
#
# Parsed from synthkernel.c rather than transcribed, because a transcribed copy
# is one more thing that can drift from the source it describes, and the drift
# is the bug. If the parse fails for any reason the call is left unchecked,
# which is what it was before -- this must never be the thing that stops a
# render.
_CTYPE = {"float*": ctypes.POINTER(ctypes.c_float),
          "double*": ctypes.POINTER(ctypes.c_double),
          "int*": ctypes.POINTER(ctypes.c_int),
          "long*": ctypes.POINTER(ctypes.c_long),
          "float": ctypes.c_float, "double": ctypes.c_double,
          "int": ctypes.c_int, "long": ctypes.c_long}


def _declare(dll, src, func="synth_voice"):
    try:
        text = open(src).read()
        m = re.search(r"\n(void|int) %s\(" % func, text)
        i = m.start() + 1
        args = text[text.index("(", i) + 1:text.index(")", i)]
        # strip comments and line breaks, then one entry per comma
        args = re.sub(r"//[^\n]*", " ", args).replace("\n", " ")
        out = []
        for a in args.split(","):
            a = a.replace("const", "").strip()
            if not a:
                continue
            # "float* outL" and "float *outL" and "float outL" all appear
            base, name = a.rsplit(" ", 1)
            star = "*" if ("*" in base or name.startswith("*")) else ""
            # the descriptor tables (voicedesc.h) go as plain pointers
            out.append(_CTYPE.get(base.replace("*", "").strip() + star, ctypes.c_void_p))
        fn = getattr(dll, func)
        fn.argtypes = out
        fn.restype = ctypes.c_int if m.group(1) == "int" else None
    except Exception:
        pass        # unchecked, exactly as before; never fatal

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
    mid = _open_midi(path)
    ch_prog = {}; ch_progs = {}; notes = []; ccs = {}; pws = {}; on = {}; t = 0.0
    # MIDI 2.0's per-note pitch (ump.py): a Note On's own Pitch 7.9, keyed by
    # (channel, note, onset); and the timelines of Pitch 7.25, per-note bend
    # and its range. Empty for every MIDI 1.0 file.
    pn = dict(attr={}, p725={}, bend={}, range={})
    ats = {}; pts = {}       # channel pressure, and per-key pressure
    sotas = {}               # channel -> [(t, 12 cents)] from GM2 sysex
    _gsstate = {}            # channel -> a GS part's velocity sense, key range, scale (parse_gs_part_state)
    # THE RPNs, which this renderer read none of. A file that set its bend
    # range to 12 was bent over 2, and fine and coarse tuning were ignored --
    # GM Level 1 requires all three, and live.py had them the whole time. The
    # arithmetic is tonelib's, shared, so the two cannot drift apart.
    rpns = {}                # channel -> [(t, 'range'|'fine'|'coarse'|'mod', v)]
    _rsel = {}; _rfmsb = {}; _rrange = {}; _rmod = {}
    _rfine = {}; _rcoarse = {}; _rtp = {}; _rtb = {}   # current values, for CC96/97
    sndev = {}               # channel -> [(t, seq, cc, value)], CC71-78 and GS NRPN 01 xx
    _nsel = {}               # channel -> the NRPN selected, (MSB, LSB)
    master = []              # [(t, 'vol'|'fine'|'coarse', v, seq)], the device's own
    gmon = []                # [(t, seq)] GM System On: every channel back to power-on
    _pwseq = {}              # channel -> [(t, seq, pitch)], the wheel in message order
    mtsev = []               # [(t, seq, parsed)] MIDI Tuning Standard messages
    ctrl = {}  # (ch)->{cc:val} current, snapshotted at note-on
    # BANK SELECT, latched until the next program change: see tonelib's
    # resolve_patch. A channel is drums or melodic by what its last program
    # change resolved to -- channel 10 from power-on -- and the program itself
    # carries the answer (DrumProgram), snapshotted at note-on like the rest.
    _bmsb = {}; _blsb = {}; _drums = {}
    # ...and each part's MAP 0 (TONE MAP-0 NUMBER), where a file sets one: the
    # map a part with CC32 0 reads its bank and drum set in, else the standard
    _map0 = {}

    def _map_of(ch):
        return _blsb.get(ch, 0) or _map0.get(ch, DEFAULT_MAP)
    _var = {}                # the channel's variation (GS bank), from its last program change
    # THE DRUM INSTRUMENTS' OWN SETTINGS (GS): per channel, [(t, seq, key,
    # param, value)] from the drum NRPNs (18-1F rr) and the drum setup SysEx
    # (41 m p rr), key None with 'reset' where a drum set change or a reset
    # puts them back -- read at each drum note's onset in prepare. _rmap is
    # the drum MAP a rhythm part plays (0 MAP1, 1 MAP2), which the SysEx
    # addresses: channel 10 is MAP1 until "use for rhythm part" says otherwise.
    dedit = {}
    _rmap = {}
    # THE USER DRUM SETS (GS 21 dp rr: sets 65 and 66): {(set 0/1, key):
    # {param: value}} -- each key's source set and note, and its own settings
    uset = {}
    # THE INSERTION EFFECT's timeline (gsefx.parse): [(t, event)], a reset an
    # event too -- read at each note's onset in prepare
    efxev = []
    # ...and the EFX as it stands while parsing, so a controller that is one
    # of its effect controllers' sources, on a part on it, joins the timeline
    # as that source's value (gsefx 'cv'): the + and # parameters it moves
    _efxst, _efxparts = _GSX.fresh_state(), set()

    def _efx_cv(t, ch, src, v):
        if ch not in _efxparts or src not in (_efxst['ctl'].get(_GSX.CTL_SRC1), _efxst['ctl'].get(_GSX.CTL_SRC2)):
            return
        if _efxst['cv'].get(src) != v:
            _ev = ('cv', src, int(v))
            _GSX.apply(_efxst, _ev, _efxparts)
            efxev.append((t, _ev))
    # THE CONTROLLER MATRIX (ctrlmatrix: GS 40 2x, GM2 09 0s): a channel's
    # routing, made only when a message names it, and what it sets over time
    # -- the AMPLITUDE gain and the LFO1 AMPLITUDE DEPTH (a tremolo), each a
    # [(t, value)] for prepare, from the mod wheel, any CC and the channel's
    # pressure. A channel no matrix message names is untouched.
    _cmx, _cmx_last, _cat_now, _bend_now, _pat_now = {}, {}, {}, {}, {}
    cmx = dict(amp={}, tva={}, pitch={}, cutoff={}, tvf={}, rate={}, vib={})
    # THE MOD WHEEL'S VIBRATO (GS's default cell, 47 cents of LFO1 pitch) is
    # not a file's here: our bowed and blown voices carry their players' own
    # vibrato, and a Sound Canvas's on top doubled it (see tremolo_intrinsic).
    # Other sources' vibrato -- aftertouch, a CC, the bend -- is. TUNING_MOD_
    # VIBRATO=1 lets the wheel's in too.
    _modvib = os.environ.get('TUNING_MOD_VIBRATO', '0') not in ('0', 'off', '')

    def _cmx_upd(t, ch):
        _m = _cmx.get(ch)
        if _m is None:
            return
        _c = ctrl.get(ch, {})

        def _val(src):
            if src == 'mod':
                return _c.get(1, 0) / 127.0
            if src == 'cat':
                return _cat_now.get(ch, 0) / 127.0
            if src == 'bend':
                # signed: GS's bend cells act as far as the bend is pushed
                return _bend_now.get(ch, 0) / 8192.0
            if src == 'pat':
                # the channel's keys' pressure, its highest: per-note
                # destinations would want per-note rows, which no file here asks
                _kp = _pat_now.get(ch)
                return (max(_kp.values()) / 127.0) if _kp else 0.0
            if isinstance(src, tuple):
                return _c.get(src[1], 0) / 127.0
            return 0.0
        _cl = _m.cells()

        def _sum(dest, skip=()):
            return sum(d * _val(sr) for (sr, de), d in _cl.items() if de == dest and sr not in skip)
        _amp = max(0.0, 1.0 + _sum('amp'))
        _tva = max(0.0, min(1.0, _sum('lfo1_tva') + _sum('lfo2_tva')))
        # pitch: every source but the bend's own (its range: RPN 0/0, read
        # where it always was); cutoff, LFO filter depth and LFO rate as they are
        _nomod = () if _modvib else ('mod',)
        _now = dict(amp=_amp, tva=_tva, pitch=_sum('pitch', ('bend',)), cutoff=_sum('cutoff'),
                    tvf=max(0.0, _sum('lfo1_tvf') + _sum('lfo2_tvf')), rate=_sum('lfo1_rate'),
                    vib=max(0.0, _sum('lfo1_pitch', _nomod) + _sum('lfo2_pitch', _nomod)))
        _last = _cmx_last.get(ch) or dict(amp=1.0, tva=0.0, pitch=0.0, cutoff=0.0, tvf=0.0, rate=0.0, vib=0.0)
        for _k, _v in _now.items():
            if abs(_v - _last[_k]) > 1e-9:
                cmx[_k].setdefault(ch, []).append((t, _v))
        _cmx_last[ch] = _now

    def _cmx_ch(b, a):
        return (9 if b == 0 else (b - 1 if b <= 9 else b)) + (16 if a == 0x50 else 0)
    _rxbank = [True]         # Rx.BANK SELECT: GM1 On turns it off
    # MPE (M1-100-UM), as live.py plays it: the zones in force, and their
    # history for prepare. A member channel takes its manager's program and is
    # never a drum channel, whatever its number.
    _mpe = T.MpeZones(); mpe_ev = []
    def _is_drums(ch):
        if _mpe and _mpe.is_member(ch):
            return False
        return _drums.get(ch, ch % 16 == GM_PERCUSSION_CHANNEL)
    def _cur_prog(ch):
        if _mpe and _mpe.is_member(ch):
            ch = _mpe.manager_of(ch)
        p = ch_prog.get(ch, 0)
        if _is_drums(ch):
            return DrumProgram(p)
        # A VARIATION THAT EXISTS rides the program (patch_map.VariationProgram);
        # any other bank plays the capital tone, as a Sound Canvas does
        v = _var.get(ch, 0)
        return VariationProgram(p, v) if v and ((p & 0x7F), v) in VARIATIONS else p
    def cv(ch):
        # GM's power-on defaults, not 127/127/64-as-an-accident: see
        # tonelib.GM_DEFAULT_VOLUME for why volume starts at 100.
        c = ctrl.get(ch, {})
        # ...the controller matrix's amplitude, where a matrix routes one: in
        # the expression, which chan_vol squares (so its square root here)
        _ag = _cmx_last[ch]['amp'] if ch in _cmx_last else 1.0
        return (c.get(7, T.GM_DEFAULT_VOLUME)/127.0,
                c.get(11, T.GM_DEFAULT_EXPRESSION)/127.0 * (_ag ** 0.5 if _ag != 1.0 else 1.0),
                (c.get(10, T.GM_DEFAULT_PAN)-64)/63.0)
    _seq = 0     # message order, for events that share a tick -- see _pitch_stream
    # Messages the file did not send but MPE implies -- a manager's zone-wide
    # control copied to its members, the resets an MPE Configuration Message
    # causes -- are queued here and run at the same instant, through the same
    # code, straight after the message that caused them.
    _inj = []

    def _stream():
        for _m in mid:
            yield _m, False
            while _inj:
                yield _inj.pop(0), True
    for msg, _mpe_done in _stream():
        t += msg.time
        _seq += 1
        if _mpe and not _mpe_done and hasattr(msg, 'channel') and _mpe.zone_of(msg.channel):
            _mc = msg.channel
            if _mpe.is_member(_mc):
                if msg.type == 'control_change':
                    _c0 = msg.control
                    if _c0 in (126, 127):
                        if _mc == _mpe.lowest_member(_mc):
                            _inj.extend(msg.copy(channel=_m2, time=0)
                                        for _m2 in _mpe.members(_mc))
                        continue
                    if not (_c0 == 74 or _c0 in (6, 38, 96, 97, 98, 99, 100, 101,
                                                  120, 121, 123)):
                        continue            # a zone-wide control on a member (2.3.1)
                elif msg.type in ('program_change', 'polytouch'):
                    continue                # 2.3.3, 2.2.7
            elif msg.type == 'control_change':
                if msg.control in (126, 127):
                    continue
                if msg.control not in _MPE_NOT_FANNED:
                    _inj.extend(msg.copy(channel=_m2, time=0) for _m2 in _mpe.members(_mc))
        if msg.type == 'program_change':
            _dr, _pr, _var_ = T.resolve_patch(_bmsb.get(msg.channel, 0),
                                             _map_of(msg.channel), msg.program,
                                             _is_drums(msg.channel), _rxbank[0])
            if _dr and _bmsb.get(msg.channel, 0) != T.GM2_DRUM_BANK:
                # ...a drum set read in the part's map, where that map has a
                # set of its own there (percussion_map.kit_in_map)
                _pr = kit_in_map(_pr, _map_of(msg.channel))
            _drums[msg.channel] = _dr
            ch_prog[msg.channel] = _pr
            _var[msg.channel] = 0 if _dr else _var_
            if _dr and msg.channel in dedit:
                # "When the Drum Set is changed, DRUM SETUP PARAMETER values
                # will all be initialized" (VE-GS Pro MIDI Implementation)
                dedit[msg.channel].append((t, _seq, None, 'reset', 0))
            # A drum set is not a melodic program: the organ registration pass
            # reads this list, and a Power kit (16) would have registered the
            # drum channel as a Drawbar Organ.
            if not _dr:
                ch_progs.setdefault(msg.channel, []).append(_cur_prog(msg.channel))
        elif msg.type == 'control_change':
            ccs.setdefault(msg.channel, []).append((t, msg.control, msg.value))
            if 1 <= msg.control <= 95:
                _efx_cv(t, msg.channel, msg.control, msg.value)
            if msg.control == 0:
                _bmsb[msg.channel] = msg.value
            elif msg.control == 32:
                _blsb[msg.channel] = msg.value
            ctrl.setdefault(msg.channel, {})[msg.control] = msg.value
            if msg.channel in _cmx:
                _cmx_upd(t, msg.channel)
            _c, _cc, _v = msg.channel, msg.control, msg.value
            if _cc == 121:
                # RESET ALL CONTROLLERS, which only live answered. Posted as the
                # events a player resetting by hand would have sent, at this
                # instant and in this order, so every consumer below honours it
                # without knowing it exists -- the list is live's _RESET_CC.
                # Kept, as live keeps them: CC7, CC10, the program, CC5 and
                # every tuning RPN.
                _cl = ccs[_c]
                for _rc in (64, 65, 66, 67):
                    _cl.append((t, _rc, 0))
                # CC1 ONLY IF THE CHANNEL HAS SENT ONE. Offline, most CC1 readers
                # take the channel's FIRST value as a setting and "absent" is the
                # voice's default -- three drones, not none. A reset on a channel
                # that never touched the wheel would become that first value and
                # silently change the default. With a CC1 already sent, the
                # first-value readers are untouched and the one time-aware
                # reader, the Leslie half-moon, gets its reset.
                if any(_x[1] == 1 for _x in _cl):
                    _cl.append((t, 1, 0))
                _cl.append((t, 84, CC84_CANCEL))     # a pending CC84 is spent
                ctrl.setdefault(_c, {})[11] = 127
                ctrl[_c][1] = 0
                pws.setdefault(_c, []).append((t, 0))
                _pwseq.setdefault(_c, []).append((t, _seq, 0))
                ats.setdefault(_c, []).append((t, 0))   # not polytouch: live keeps it
                _rsel[_c] = (127, 127)
            if _cc in T.SOUND_CC:
                sndev.setdefault(_c, []).append((t, _seq, _cc, _v))
            if _cc in (98, 99):
                _rsel[_c] = None            # an NRPN: its data entry is not ours
                # ...unless it is one of GS's eight sound NRPNs, which are the
                # same controls as CC71-78 under an older address.
                _ns0 = _nsel.get(_c) or (127, 127)
                _nsel[_c] = (_v, _ns0[1]) if _cc == 99 else (_ns0[0], _v)
            elif _cc == 101:
                _nsel[_c] = None
                _rsel[_c] = (_v, (_rsel.get(_c) or (127, 127))[1])
            elif _cc == 100:
                _nsel[_c] = None
                _rsel[_c] = ((_rsel.get(_c) or (127, 127))[0], _v)
            elif _cc in (6, 38):
                _sel = _rsel.get(_c)
                _gs = T.GS_SOUND_NRPN.get(_nsel.get(_c)) if _sel is None else None
                if _gs is not None and _cc == 6:
                    sndev.setdefault(_c, []).append((t, _seq, _gs, _v))
                _dn = _nsel.get(_c) if _sel is None else None
                if _dn is not None and _cc == 6 and _dn[0] in GS_DRUM_NRPN:
                    # a DRUM INSTRUMENT's own: its key is the NRPN's LSB
                    _par = GS_DRUM_NRPN[_dn[0]]
                    dedit.setdefault(_c, []).append(
                        (t, _seq, _dn[1], _par, (_v - 64) if _par == 'pitch' else _v))
                if _sel == (0, 6) and _cc == 6:
                    # THE MPE CONFIGURATION MESSAGE (2.2.1): the zones, a
                    # reset on every channel whose zone changed (2.2.3), and the
                    # bend ranges, 2 on the manager and 48 on members (2.2.5).
                    _chg = _mpe.mcm(_c, _v)
                    if _chg is not None:
                        mpe_ev.append((t, dict(_mpe.channels())))
                        _inj.extend(mido.Message('control_change', channel=_x & 15,
                                                 control=121, value=0, time=0)
                                    for _x in sorted(_chg))
                        if _mpe.zone_of(_c) is not None:
                            for _x, _r in [(_c, T.MPE_MANAGER_BEND)] + \
                                    [(_m2, T.MPE_MEMBER_BEND) for _m2 in _mpe.members(_c)]:
                                _rrange[_x] = _r
                                rpns.setdefault(_x, []).append((t, 'range', _r, _seq))
                if _sel == (0, 0):
                    _rrange[_c] = T.rpn_bend_range(
                        _cc, _v, _rrange.get(_c, T.BEND_RANGE_SEMITONES))
                    rpns.setdefault(_c, []).append((t, 'range', _rrange[_c], _seq))
                    if _mpe and _mpe.is_member(_c):
                        # one range for the zone's members (2.2.5)
                        for _m2 in _mpe.members(_c):
                            if _m2 != _c:
                                _rrange[_m2] = _rrange[_c]
                                rpns.setdefault(_m2, []).append((t, 'range', _rrange[_c], _seq))
                elif _sel == (0, 1):
                    _rfmsb[_c], _fc = T.rpn_fine(_cc, _v, _rfmsb.get(_c, 64))
                    _rfine[_c] = _fc
                    rpns.setdefault(_c, []).append((t, 'fine', _fc, _seq))
                elif _sel == (0, 2):
                    _co = T.rpn_coarse(_cc, _v)
                    if _co is not None:
                        _rcoarse[_c] = _co
                        rpns.setdefault(_c, []).append((t, 'coarse', _co, _seq))
                elif _sel == (0, 5):
                    _rmod[_c] = T.rpn_mod_range(_cc, _v, _rmod.get(_c, 0.0))
                    rpns.setdefault(_c, []).append((t, 'mod', _rmod[_c], _seq))
                elif _sel in ((0, 3), (0, 4)):
                    # MTS program and bank select. Recorded under every tuner
                    # and acted on only under `gm2`, which keeps the store.
                    _tv = (T.rpn_tuning_program if _sel == (0, 3)
                           else T.rpn_tuning_bank)(_cc, _v)
                    if _tv is not None:
                        (_rtp if _sel == (0, 3) else _rtb)[_c] = _tv
                        rpns.setdefault(_c, []).append(
                            (t, 'tprog' if _sel == (0, 3) else 'tbank', _tv, _seq))
            elif _cc in (96, 97):
                # DATA INCREMENT / DECREMENT: one unit of the selected RPN's
                # finest byte (tonelib.rpn_step), posted as the same event data
                # entry would have posted, so nothing downstream can tell.
                _sel = _rsel.get(_c)
                _cur = {(0, 0): _rrange.get(_c, T.BEND_RANGE_SEMITONES),
                        (0, 1): _rfine.get(_c, 0.0),
                        (0, 2): _rcoarse.get(_c, 0.0),
                        (0, 3): _rtp.get(_c, 0), (0, 4): _rtb.get(_c, 0),
                        (0, 5): _rmod.get(_c, 0.0)}.get(_sel)
                _nv = None if _cur is None else T.rpn_step(_sel, _cur, _cc == 96)
                if _nv is not None:
                    _kind = {(0, 0): 'range', (0, 1): 'fine', (0, 2): 'coarse',
                             (0, 3): 'tprog', (0, 4): 'tbank', (0, 5): 'mod'}[_sel]
                    if _sel == (0, 0):
                        _rrange[_c] = _nv
                    elif _sel == (0, 1):
                        _rfine[_c] = _nv; _rfmsb[_c] = T.rpn_fine_msb(_nv)
                    elif _sel == (0, 2):
                        _rcoarse[_c] = _nv
                    elif _sel == (0, 3):
                        _rtp[_c] = _nv = int(_nv)
                    elif _sel == (0, 4):
                        _rtb[_c] = _nv = int(_nv)
                    else:
                        _rmod[_c] = _nv
                    rpns.setdefault(_c, []).append((t, _kind, _nv, _seq))
        elif msg.type == 'pitchwheel':
            pws.setdefault(msg.channel, []).append((t, msg.pitch))
            _bend_now[msg.channel] = msg.pitch
            if msg.channel in _cmx:
                _cmx_upd(t, msg.channel)
            _efx_cv(t, msg.channel, _GSX.SRC_BEND, (msg.pitch + 8192) >> 7)
            _pwseq.setdefault(msg.channel, []).append((t, _seq, msg.pitch))
        elif msg.type == 'sysex':
            _mx = _CMX.parse(msg.data, _cmx_ch)
            if _mx is not None:
                _cmx.setdefault(_mx[0], _CMX.Matrix()).apply(_mx[1], _mx[2])
                _cmx_upd(t, _mx[0])
            _lvl = gm_on_level(msg.data)
            if _lvl or parse_gs_reset(msg.data):
                for _mc, _mm in _cmx.items():       # the matrices back to a reset's
                    _mm.reset()
                # BANK SELECT goes back to power-on too, and Roland's text says
                # which way: "Rx.BANK SELECT is set to OFF by Turn General MIDI
                # System On, and set to ON by GS RESET". GM 2 On turns it on --
                # its whole sound set is addressed through it. Every program
                # goes to 0, as live's does; this renderer kept them.
                _rxbank[0] = _lvl != 1
                _bmsb.clear(); _blsb.clear(); _drums.clear(); ch_prog.clear(); _var.clear()
                _map0.clear()           # "When GS Reset is received ... 00: SELECTED"
                _rmap.clear()
                efxev.append((t, ('reset',)))
                _GSX.apply(_efxst, ('reset',), _efxparts)
                for _dc in dedit:
                    dedit[_dc].append((t, _seq, None, 'reset', 0))
                # BACK TO POWER-ON, which this renderer did not do at all while
                # its own docstring said it did. The controllers go (so a note
                # after it snapshots CC7 at 100 again), and every tuning the
                # file had set -- RPN, master, scale -- is reset downstream from
                # the time recorded here.
                gmon.append((t, _seq))
                ctrl.clear(); _rsel.clear(); _rfmsb.clear(); _rrange.clear()
                _cat_now.clear(); _bend_now.clear(); _pat_now.clear()
                for _mc in _cmx:
                    _cmx_upd(t, _mc)
                _nsel.clear()
                _rmod.clear(); _rfine.clear(); _rcoarse.clear()
                _rtp.clear(); _rtb.clear()
                for _c in list(sotas):
                    sotas[_c].append((t, (0.0,) * 12))
                _gsstate.clear()            # velocity sense, key range, scale: power-on
                continue
            _mst = parse_master(msg.data)
            if _mst is not None:
                master.append((t, _mst[0], _mst[1], _seq))
                continue
            _rp = parse_gs_rhythm_part(msg.data)
            if _rp is not None:
                # A DRUM PART ON ANOTHER CHANNEL (or channel 10 melodic): the
                # channel's drums state, as GM 2's bank 120 sets it. Its
                # program STAYS -- SuwaFF moves channel 12 from drum map 1 to 2
                # after its program change chose the set, and means that set
                _rc, _rm = _rp
                _drums[_rc] = bool(_rm)
                if _rm:
                    _var[_rc] = 0
                    _rmap[_rc] = _rm - 1
                continue
            _gx = _GSX.parse(msg.data)
            if _gx is not None:
                efxev.append((t, _gx))
                _GSX.apply(_efxst, _gx, _efxparts)
                continue
            _ud = parse_gs_user_drum(msg.data)
            if _ud is not None:
                uset.setdefault((_ud[0], _ud[1]), {})[_ud[2]] = _ud[3]
                continue
            _gps = parse_gs_part_state(msg.data)
            if _gps is not None:
                _gc, _gk, _gv = _gps
                _gst = _gsstate.setdefault(_gc, {})
                if _gk == 'scale':
                    # one scale per part, its notes set one at a time or together
                    _sc = _gst.setdefault('scale', [0.0] * 12)
                    _sc[_gv[0]:_gv[0] + len(_gv[1])] = _gv[1]
                    sotas.setdefault(_gc, []).append((t, tuple(_sc)))
                else:
                    _gst[_gk] = _gv
                continue
            _gp = parse_gs_part(msg.data)
            if _gp is not None:
                # A PART PARAMETER: read as the MIDI message it is, next, in order
                _inj.extend(_gp[1])
                continue
            _m0 = parse_gs_map0(msg.data)
            if _m0 is not None:
                _map0[_m0[0]] = _m0[1]
                continue
            _ds = parse_gs_drum_setup(msg.data)
            if _ds is not None:
                # A DRUM MAP'S SETTING: every channel of that port playing the map
                _dport, _dm_, _dk, _dpar, _dv = _ds
                for _dc in range(16 * _dport, 16 * _dport + 16):
                    if _is_drums(_dc) and _rmap.get(_dc, 0) == _dm_:
                        dedit.setdefault(_dc, []).append((t, _seq, _dk, _dpar, _dv))
                continue
            _mt = _MTS.parse_mts(msg.data)
            if _mt is not None:
                mtsev.append((t, _seq, _mt))
                continue
            _so_ta = parse_sota(msg.data)
            if _so_ta is not None:
                _chs, _cents = _so_ta
                # A MIDI 2.0 SysEx belongs to its group, and so do the sixteen
                # channels its bitmap names.
                _g16 = 16 * (getattr(msg, 'group', 0) or 0)
                for _c in _chs:
                    sotas.setdefault(_c + _g16, []).append((t, tuple(_cents)))
        elif msg.type == 'aftertouch':
            ats.setdefault(msg.channel, []).append((t, msg.value))
            _cat_now[msg.channel] = msg.value
            if msg.channel in _cmx:
                _cmx_upd(t, msg.channel)
            _efx_cv(t, msg.channel, _GSX.SRC_CAF, msg.value)
        elif msg.type == 'polytouch':
            pts.setdefault((msg.channel, msg.note), []).append((t, msg.value))
            _pat_now.setdefault(msg.channel, {})[msg.note] = msg.value
            if msg.channel in _cmx:
                _cmx_upd(t, msg.channel)
        elif msg.type in ('pn_pitch', 'pn_bend', 'pn_bend_range', 'pn_mgmt'):
            _k = (msg.channel, msg.note)
            if msg.type == 'pn_pitch':
                pn['p725'].setdefault(_k, []).append((t, msg.semitones))
            elif msg.type == 'pn_bend':
                pn['bend'].setdefault(_k, []).append((t, msg.value))
            elif msg.type == 'pn_bend_range':
                pn['range'].setdefault(msg.channel, []).append((t, msg.semitones))
            elif msg.reset:
                pn['p725'].setdefault(_k, []).append((t, None))
                pn['bend'].setdefault(_k, []).append((t, 0.0))
        elif msg.type == 'note_on' and msg.velocity > 0:
            if getattr(msg, 'attr_pitch', None) is not None:
                pn['attr'][(msg.channel, msg.note, t)] = msg.attr_pitch
            # THE PATCH IS SNAPSHOTTED AT NOTE-ON, like the CCs beside it. It
            # used to be read from ch_prog at render time, which holds only the
            # LAST program change on each channel -- so a file that changes
            # patch mid-piece rendered every note with whatever it happened to
            # end on. passac.mid cycles channel 0 through strings, recorder,
            # clarinet, trumpet, organ and music box, and all 2161 notes came
            # out as strings.
            _np = _cur_prog(msg.channel)
            _vel = msg.velocity
            _gst = _gsstate.get(msg.channel)
            if _gst:
                # A GS PART'S KEY RANGE (outside it the part does not sound) and
                # its VELOCITY SENSE: depth scales the velocity (64 as is),
                # offset moves it (64 none) -- Roland's "how much velocity
                # affects the volume" and "how much it is boosted"
                if not _gst.get('klo', 0) <= msg.note <= _gst.get('khi', 127):
                    continue
                if _gst.get('vsd', 64) != 64 or _gst.get('vso', 64) != 64:
                    _vel = max(1, min(127, int(round(_vel * _gst.get('vsd', 64) / 64.0
                                                     + _gst.get('vso', 64) - 64))))
            on.setdefault((msg.channel, msg.note), []).append(
                (t, _vel, cv(msg.channel), _np))
            if _mpe and _mpe.is_member(msg.channel) and not isinstance(_np, DrumProgram) \
                    and _np not in ch_progs.get(msg.channel, ()):
                ch_progs.setdefault(msg.channel, []).append(_np)
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
    for _c, _p in ch_prog.items():
        if not _is_drums(_c):
            ch_progs.setdefault(_c, []).append(_p)
    return (ch_prog, ch_progs, notes, ccs, t, _legato_ticks(mid), pws,
            (ats, pts, sotas, dict(rpns=rpns, master=master, gmon=gmon,
                                   pwseq=_pwseq, mts=mtsev, snd=sndev, pn=pn,
                                   mpe=mpe_ev, dedit=dedit, uset=uset, efx=efxev, cmx=cmx)))


# What an MPE manager's control change does NOT copy to its members: the RPN
# machinery and bank select (the manager's own), CC74 (combined per note
# instead) and the mode messages (sent to the lowest member). live.py keeps
# the same list.
_MPE_NOT_FANNED = frozenset((0, 6, 32, 38, 74, 96, 97, 98, 99, 100, 101, 126, 127))


# LIVE'S TEMPLATES CARRY NO PART DRONE: a one-note template is its own whole
# phrase, so a note-wheel drone (the pungi's) would be baked into every note,
# under live's own wheel-chosen one -- two drones (Ben: "another G drone plays
# as a hold down a key"). live marks its template files with this marker; the
# bagpipe's are corked by its own CC1 = 0 instead, as before
NO_PART_DRONES = "tuning:no-part-drones"


def _no_part_drones(path):
    """Does the file say its part drones are someone else's (live's)?"""
    try:
        mid = _open_midi(path)
        return any(m.type == 'marker' and getattr(m, 'text', '') == NO_PART_DRONES for m in mid)
    except Exception:
        return False


def _open_midi(path):
    """A path, a mido.MidiFile, or a MIDI 2.0 file (Clip File or raw UMP),
    which ump.UmpMidi presents in mido's shape -- see ump.py."""
    if hasattr(path, 'slots') or isinstance(path, PortedMidi):
        return path
    if isinstance(path, mido.MidiFile):
        # an in-memory file names its ports as a saved one does: an excerpt
        # or a test's file must not collapse port B onto port A
        return PortedMidi(path) if PortedMidi.uses_ports(path) else path
    import ump as _U
    with open(path, 'rb') as f:
        head = f.read(8)
    if _U.is_ump_file(head):
        return _U.UmpMidi.open(path)
    mid = mido.MidiFile(path)
    return PortedMidi(mid) if PortedMidi.uses_ports(mid) else mid


class _PortMsg(object):
    """A message on port B (or later): itself, its channel + 16 x port."""
    __slots__ = ("_m", "channel", "time")

    def __init__(self, m, channel, time):
        self._m, self.channel, self.time = m, channel, time

    def __getattr__(self, k):
        return getattr(self._m, k)

    def copy(self, **kw):
        ch = kw.pop("channel", self.channel)
        tm = kw.pop("time", self.time)
        return _PortMsg(self._m.copy(**kw) if kw else self._m, ch, tm)


def _gs_part_block(data):
    """True for a Roland GS DT1 message (41 dd 42 12) to a PART's block --
    40/50 1x (part settings), 2x (its controllers), 4x (its tone and EFX) --
    whose group the receiving port decides."""
    d = tuple(data)
    return (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12
            and d[4] in (0x40, 0x50) and (d[5] & 0xF0) in (0x10, 0x20, 0x40))


class PortedMidi(object):
    """A MIDI 1.0 file whose tracks name a MIDI PORT (the FF 21 meta event),
    as a two-port Sound Canvas file does: Konami's SC-88Pro data plays 32
    parts, sixteen on each port, and read as one port they collapse onto each
    other. Each channel message is presented on channel + 16 x its track's
    port -- the flat channel MIDI 2.0's groups use already (ump.py) -- so the
    renderer reads 32 channels. Shaped as UmpMidi is: iterating gives seconds,
    .tracks one merged track in ticks for the legato pass."""

    def __init__(self, mid):
        self.ticks_per_beat = mid.ticks_per_beat
        ev = []
        for k, tr in enumerate(mid.tracks):
            at, port = 0, 0
            for m in tr:
                at += m.time
                if m.type == "midi_port":
                    port = m.port
                ev.append((at, k, m, port))
        ev.sort(key=lambda e: (e[0], e[1]))     # mido.merge_tracks' order
        self._ev = ev

    @staticmethod
    def uses_ports(mid):
        return any(m.type == "midi_port" and m.port for tr in mid.tracks for m in tr)

    def _msgs(self, seconds):
        tempo, last = 500000, 0
        for at, _k, m, port in self._ev:
            dt = at - last
            last = at
            d = mido.tick2second(dt, self.ticks_per_beat, tempo) if seconds else dt
            if m.type == "set_tempo":
                tempo = m.tempo
            if hasattr(m, "channel") and not m.is_meta:
                yield _PortMsg(m, m.channel + 16 * port, d)
            elif port and m.type == "sysex" and _gs_part_block(m.data):
                # A PART'S EXCLUSIVE AT PORT B. "Exclusive data received at
                # MIDI IN B is passed to Group B Parts", and 50 00 00 is "the
                # Parts of the other Group than the MIDI IN that the data was
                # received at" (SC-88 Pro owner's manual, "Exclusive data
                # addresses") -- so at port B, 40 is group B and 50 group A.
                # Read as port A's, SENSATIO's 40 4A-4F 22 put its guitar
                # multi-effect on A11-A16 (choir, piano, strings) and left
                # the guitars B11-B16 dry. Swapped here, every reader below
                # sees the address as port A would have. The system blocks
                # (40 00-03: master, reverb/chorus, EQ, the EFX) are one set
                # here, and keep their address.
                d0 = list(m.data)
                d0[4] ^= 0x10
                yield m.copy(data=d0, time=d)
            else:
                yield m.copy(time=d)

    def __iter__(self):
        return self._msgs(True)

    @property
    def tracks(self):
        return [list(self._msgs(False))]

# ---- GM2 Scale/Octave Tuning Adjust -----------------------------------------
# Twelve cent offsets, one per pitch class, applied to a set of channels. It is
# the standard, portable way to put a TEMPERAMENT in a MIDI file, and nothing
# here spoke it -- which is why John Sankey's bwv847.mid smuggles his tuning
# through one-pitch-class-per-channel static pitch bend instead. There was no
# other way to say it.
#
#   1-byte  F0 7E <dev> 08 08 <ff> <gg> <hh> <ss x 12> F7
#           ss 0x00..0x7F  ->  -64..+63 cents, 0x40 = 0
#   2-byte  F0 7E <dev> 08 09 <ff> <gg> <hh> <ss tt x 12> F7
#           14-bit 0x0000..0x3FFF -> -100..+100 cents, 0x2000 = 0
#
# ff/gg/hh is a 3-byte channel bitmap: ff bits 0-1 are channels 14-15, gg is
# 7-13, hh is 0-6. 7F in the device byte is "all devices". The realtime form
# (7F instead of 7E) is the same payload and means "take effect now" -- which
# offline is the same thing, so both are accepted.
SOTA_NONREALTIME = 0x7E
SOTA_REALTIME = 0x7F


def _sota_channels(ff, gg, hh):
    """The 3-byte channel bitmap, as a set of 0-based channels."""
    out = set()
    for b in range(2):
        if ff & (1 << b):
            out.add(14 + b)
    for b in range(7):
        if gg & (1 << b):
            out.add(7 + b)
        if hh & (1 << b):
            out.add(b)
    return out


def in_order(evs):
    """Controller events sorted by TIME ONLY, stably -- so events that share a
    tick keep the order the file sent them.

    sorted() on the bare (t, cc, v) tuples broke ties on the VALUE: a pedal
    down and a pedal up on one tick always came out up-then-down, whatever the
    file said, so a pedal pressed on the last tick of a bar and released on
    the same one ended the bar held. `ccs` is appended in message order, and
    Python's sort is stable, so sorting on the time alone is the whole fix.
    The same bug class as GM System On's tie-break, one layer down.
    """
    return sorted(evs, key=lambda e: e[0])


# CC91 FOLLOWS THE SONG. A send was each channel's FIRST CC91, held for the
# whole piece; six of seven Sound Canvas files here move it as they go (Tokei,
# River, SENSATIO, 421 changes), the arranger setting a section's depth. A
# channel whose CC91 changes has steps: (onset samples, distance multiples),
# the value before its first change being its first, as before -- so a file
# that sends one CC91 renders as it did. Each note stands at the distance its
# onset finds (_src_dist), and the send bus weights each row by its onset.
def send_steps(ccs, sr, nominal):
    """{channel: (onsets in samples, multiples)} for the channels whose CC91
    changes; the others keep one send (the _REVERB_CH dict)."""
    out = {}
    for ch, evs in ccs.items():
        v = [(t, x) for t, cc, x in in_order(evs) if cc == 91]
        if len({x for _, x in v}) > 1:
            out[ch] = (np.array([int(round(t * sr)) for t, _ in v], np.int64),
                       np.array([x / float(nominal) for _, x in v], np.float64))
    return out


def step_at(st, n):
    """A step table's value at sample(s) n: the last change at or before it,
    and before the first, the first."""
    i = np.searchsorted(st[0], np.asarray(n), side='right') - 1
    return st[1][np.maximum(i, 0)]


def send_weights(rs, steps, mch, non):
    """Each row's reverb send: its channel's, at the row's onset where the
    channel's CC91 changes (send_steps), else the channel's one value."""
    mch = np.asarray(mch)
    g = np.ones(len(mch), np.float32)
    for c in np.unique(mch):
        m = mch == c
        st = steps.get(int(c)) if steps else None
        g[m] = step_at(st, np.asarray(non)[m]) if st is not None else (rs or {}).get(int(c), 1.0)
    return g


def send_values(rs, steps, heard):
    """Every send the channels heard stand at -- more than one, and the room
    needs a send bus of its own."""
    out = set()
    for c in heard:
        st = steps.get(int(c)) if steps else None
        out |= set(st[1].tolist()) if st is not None else {(rs or {}).get(int(c), 1.0)}
    return out


# A pending CC84 cancelled by CC121. Not a note number -- a controller value
# never exceeds 127 -- so it can ride in `ccs` in message order and be told
# apart from a real source note by the one reader that cares.
CC84_CANCEL = 128

# A valved gliss leaves the note it arrives at at least this much of itself:
# 60 ms or a fifth of the note, whichever is longer. Below that the arrival is
# not a note any more, just the last step of the run.
GLISS_ARRIVAL_S = 0.06
GLISS_ARRIVAL_FRAC = 0.2


def organ_family(cls):
    """The registered instrument a voice belongs to -- the class that defines
    its stop ranks (the tonewheel, the harmonium, the church organ, the
    harpsichord): what a channel's registration tables are kept per."""
    return next((k for k in cls.__mro__ if 'stop_ranks' in vars(k)), cls).__name__


def parse_gm_on(data):
    """True for GM System On (7E dd 09 01) or GM 2 System On (7E dd 09 03).

    Any device id: a file addresses "all devices" as 7F, but one aimed at id
    10 is not addressed to somebody else -- there is nobody else here.
    """
    return gm_on_level(data) is not None


def gm_on_level(data):
    """1 for GM System On, 2 for GM 2 System On, None for anything else."""
    d = tuple(data)
    if len(d) >= 4 and d[0] == 0x7E and d[2] == 0x09:
        return {0x01: 1, 0x03: 2}.get(d[3])
    return None


# THE STANDARD: the Sound Canvas map a part's map 0 plays (TONE MAP-0 NUMBER,
# SC-8850 owner's manual, MIDI implementation 40 4x 01) where a file does not
# set it per part -- 0 ours (patch_map.map_bank), 1 SC-55, 2 SC-88, 3 SC-88
# Pro, 4 SC-8850. `blockrender.py ... --map N`, or TUNING_MAP.
DEFAULT_MAP = int(os.environ.get('TUNING_MAP', '0') or 0)


MAP_WORDS = {'ours': 0, 'sc55': 1, 'sc-55': 1, 'sc88': 2, 'sc-88': 2, 'sc88pro': 3, 'sc-88pro': 3,
             'sc8850': 4, 'sc-8850': 4}


def map_number(s):
    """A standard as --map names it: a word of MAP_WORDS or the map's number."""
    s = str(s).strip().lower().replace(' ', '')
    n = MAP_WORDS.get(s, MAP_WORDS.get(s.replace('-', '')))
    if n is None:
        n = int(s) if s.isdigit() else -1
    if not 0 <= n <= 4:
        raise ValueError("--map: ours, sc55, sc88, sc88pro, sc8850 or 0-4, not %r" % s)
    return n


def parse_gs_map0(data):
    """(channel, map) for a part's TONE MAP-0 NUMBER, or None.

    F0 41 dd 42 12 4b 4p 01 mm cs F7 (b 0 port A, 1 port B: channel + 16; p
    the GS part, 0 part 10): the map 1-4 that map 0 means on that part."""
    d = tuple(data)
    if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12
            and d[4] in (0x40, 0x50) and d[5] >> 4 == 4 and d[6] == 0x01 and 1 <= d[7] <= 4):
        return None
    blk = d[5] & 0x0F
    return (9 if blk == 0 else (blk - 1 if blk <= 9 else blk)) + (16 if d[4] == 0x50 else 0), d[7]


def parse_gs_reset(data):
    """True for Roland's GS Reset, F0 41 dd 42 12 40 00 7F 00 41 F7.

    "A command message that resets the internal settings of a device to the GS
    initial state" (VE-GS Pro MIDI Implementation), and the one that turns bank
    select ON where GM System On turns it off. Any device id, as parse_gm_on.
    The checksum is not checked: a wrong one addressed to this device is still
    a reset somebody meant.
    """
    d = tuple(data)
    if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12):
        return False
    # ...and the SC-88's SYSTEM MODE SET, F0 41 dd 42 12 00 00 7F mm cs F7
    # (mm 0 one module, 1 two): "the SC-88 will be reset", and the file sends
    # it in GS Reset's place -- six of the seven Sound Canvas files scanned do
    return d[4:7] == (0x40, 0x00, 0x7F) and d[7] == 0x00 or d[4:7] == (0x00, 0x00, 0x7F)


# THE HAMMER-ON (hammer_legato). Chosen, by the physics' sign and not fitted:
# the finger costs the string a little (3 dB), and its onset is a fingertip's,
# not a pick's -- 6 ms at first, 12 by Ben's ear on Tokei's side guitar ("it
# works... could be even softer"), against the pick's 2.
HAMMER_LOSS_DB = 3.0
HAMMER_GAIN = 10.0 ** (-HAMMER_LOSS_DB / 20.0)
HAMMER_ATTACK_S = 0.012


# GS's DRUM INSTRUMENT NRPNs (VE-GS Pro MIDI Implementation): MSB -> what it
# sets of the instrument on key LSB. Pitch is relative (40H = 0, semitones);
# the rest absolute, replacing the instrument's preset.
GS_DRUM_NRPN = {0x18: 'pitch', 0x1A: 'level', 0x1C: 'pan', 0x1D: 'reverb',
                0x1E: 'chorus', 0x1F: 'delay'}
_GS_DRUM_SETUP = {1: 'note', 2: 'level', 3: 'group', 4: 'pan', 5: 'reverb',
                  6: 'chorus', 7: 'rxoff', 8: 'rxon', 9: 'delay'}


def parse_gs_drum_setup(data):
    """(port, map, key, param, value) for a GS DRUM SETUP parameter, or None.

    F0 41 dd 42 12 4b mp rr vv cs F7 (b 1 port A, 5 port B; m the drum map,
    0 MAP1 or 1 MAP2; p the parameter): the per-key settings the drum NRPNs
    also reach, addressed by map rather than channel. PLAY NOTE NUMBER is the
    pitch as a note number -- returned here as semitones from the key, as the
    NRPN's relative pitch is."""
    d = tuple(data)
    if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12
            and d[4] in (0x41, 0x51) and (d[5] >> 4) in (0, 1)):
        return None
    par = _GS_DRUM_SETUP.get(d[5] & 0x0F)
    if par is None:
        return None
    key, v = int(d[6]), int(d[7])
    if par == 'note':
        return (1 if d[4] == 0x51 else 0), d[5] >> 4, key, 'pitch', v - key
    return (1 if d[4] == 0x51 else 0), d[5] >> 4, key, par, v


_GS_USER_DRUM = {1: 'note', 2: 'level', 3: 'group', 4: 'pan', 5: 'reverb', 6: 'chorus',
                 7: 'rxoff', 8: 'rxon', 9: 'delay', 0xA: 'src_map', 0xB: 'src_set', 0xC: 'src_note'}
USER_DRUM_SETS = (64, 65)        # GS's user sets 65 and 66, as programs


def parse_gs_user_drum(data):
    """(set 0/1, key, param, value) for a GS USER DRUM SET parameter
    (F0 41 dd 42 12 21 dp rr vv cs F7), or None."""
    d = tuple(data)
    if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12 and d[4] == 0x21
            and (d[5] >> 4) in (0, 1)):
        return None
    par = _GS_USER_DRUM.get(d[5] & 0x0F)
    return None if par is None else (d[5] >> 4, int(d[6]), par, int(d[7]))


def user_drum(uset, prog, key):
    """For a key of user drum set `prog` (64/65): (source set, source note,
    {its own settings, as drum_edit_at's}) or None if the set leaves it unset.
    PLAY NOTE is the key's pitch as a note number, so its pitch is play - source."""
    u = uset.get((int(prog) - USER_DRUM_SETS[0], key))
    if not u or 'src_note' not in u:
        return None
    sn = u['src_note']
    own = {k: u[k] for k in ('level', 'pan', 'rxon') if k in u}
    if 'note' in u:
        own['pitch'] = u['note'] - sn
    return u.get('src_set', 0), sn, own


def drum_edit_at(edits, key, t):
    """{param: value} in force for drum key `key` at time t, from a channel's
    edit timeline (parse's dedit): the last of each since the last reset."""
    st = {}
    for et, _sq, k, par, v in edits:
        if et > t + 1e-9:
            break
        if par == 'reset':
            st = {}
        elif k == key:
            st[par] = v
    return st


# GS TONE MODIFY 1-8 (40 1x 30-37) as the CCs their NRPNs are (VE-GS Pro MIDI
# Implementation: vibrato rate, depth, TVF cutoff, resonance, attack, decay,
# release, vibrato delay)
GS_TONE_MODIFY_CC = (76, 77, 74, 71, 73, 75, 72, 78)


def parse_gs_part_state(data):
    """(channel, what, value) for a GS PART parameter that no MIDI message
    carries, or None: VELOCITY SENSE DEPTH / OFFSET (1A/1B, 'vsd'/'vso'),
    KEYBOARD RANGE LOW / HIGH (1D/1E, 'klo'/'khi') -- each a number -- and
    SCALE TUNING C..B (40-4B, 'scale': (first note, cents...), one DT1 or
    several at once). The parse loop holds them per channel and applies them
    at note-on; the scale goes to the scale/octave tuning (sotas)."""
    d = tuple(data)
    if not (len(d) >= 9 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12
            and d[4] in (0x40, 0x50) and d[5] >> 4 == 1):
        return None
    blk = d[5] & 0x0F
    ch = (9 if blk == 0 else (blk - 1 if blk <= 9 else blk)) + (16 if d[4] == 0x50 else 0)
    a, body = d[6], d[7:-1]                 # the values, without the checksum
    kind = {0x1A: 'vsd', 0x1B: 'vso', 0x1D: 'klo', 0x1E: 'khi'}.get(a)
    if kind is not None and body:
        return ch, kind, int(body[0])
    if 0x40 <= a <= 0x4B and body:
        return ch, 'scale', (a - 0x40, tuple(float(x) - 64.0 for x in body[:0x4C - a]))
    return None


def parse_gs_part(data):
    """(channel, [mido messages]) for a GS PART parameter that has a MIDI
    message of its own, or None: the part's level, pan, reverb and chorus
    sends, tone, mono/poly and key shift are what CC7, CC10, CC91, CC93, CC0 +
    program change, CC126/127 and RPN 0/2 set -- so they are read as those,
    through the same code, and nothing new decides what they mean.

    F0 41 dd 42 12 4b 1p aa vv [ww] cs F7, b 0 port A / 1 port B (address 40 /
    50), p the GS part (0 is part 10). Port B's channels are 16-31, carried
    as PortedMidi carries them."""
    d = tuple(data)
    if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12
            and d[4] in (0x40, 0x50) and d[5] >> 4 in (1, 2, 4)):
        return None
    blk = d[5] & 0x0F
    ch = (9 if blk == 0 else (blk - 1 if blk <= 9 else blk)) + (16 if d[4] == 0x50 else 0)
    a, v = d[6], d[7]
    C = lambda cc, val: ('control_change', dict(control=cc, value=max(0, min(127, val))))
    if d[5] >> 4 == 4:
        # TONE MAP NUMBER (40 4x 00, "= CC#32 : Bank number LSB", SC-8850
        # owner's manual): 0 SELECTED -- the part's map 0 -- or a map, 1-4.
        # The rest of the 4x block (the EFX, EQ, outputs) is read elsewhere
        if a != 0x00 or v > 4:
            return None
        msgs = [C(32, v)]
    elif d[5] >> 4 == 2:
        # THE CONTROLLERS' DESTINATIONS (40 2x): the two our voices have as
        # messages. BEND PITCH CONTROL is the bend range (RPN 0/0); MOD LFO1
        # PITCH DEPTH, 0-600 cents, the mod wheel's vibrato (RPN 0/5, GM 2's
        # modulation depth range). The rest move a Sound Canvas's own TVF,
        # TVA and LFOs, which these voices are not built from.
        if a == 0x10:
            msgs = [C(101, 0), C(100, 0), C(6, max(0, min(24, v - 0x40))), C(38, 0),
                    C(101, 127), C(100, 127)]
        elif a == 0x04:
            _ct = v * 600.0 / 127.0
            msgs = [C(101, 0), C(100, 5), C(6, int(_ct // 100)),
                    C(38, int(round((_ct % 100.0) * 128.0 / 100.0))), C(101, 127), C(100, 127)]
        else:
            return None
    elif a == 0x00 and len(d) >= 9:                     # TONE NUMBER: CC00, then the program
        msgs = [C(0, v), ('program_change', dict(program=d[8]))]
    elif a == 0x13:                                     # MONO/POLY
        msgs = [C(126, 1) if v == 0 else C(127, 0)]
    elif a == 0x16:                                     # PITCH KEY SHIFT, 28-58 about 40
        msgs = [C(101, 0), C(100, 2), C(6, 64 + max(-24, min(24, v - 0x40))), C(101, 127), C(100, 127)]
    elif a == 0x19:                                     # PART LEVEL
        msgs = [C(7, v)]
    elif a == 0x1C:                                     # PART PANPOT (0 random: centre)
        msgs = [C(10, v or 64)]
    elif a == 0x21:                                     # CHORUS SEND LEVEL
        msgs = [C(93, v)]
    elif a == 0x22:                                     # REVERB SEND LEVEL
        msgs = [C(91, v)]
    elif a == 0x2C:                                     # DELAY SEND LEVEL (the SC-88's CC94)
        msgs = [C(94, v)]
    elif a == 0x2A and len(d) >= 10:                    # PITCH FINE TUNE (= RPN 1), MSB LSB
        msgs = [C(101, 0), C(100, 1), C(6, v), C(38, d[8]), C(101, 127), C(100, 127)]
    elif 0x30 <= a <= 0x37:
        # TONE MODIFY 1-8 (=NRPN 8, 9, 20H, 21H, 63H, 64H, 66H, 0AH): the
        # sound controllers the NRPNs are read as (tonelib.GS_SOUND_NRPN)
        msgs = [C(GS_TONE_MODIFY_CC[a - 0x30], v)]
    else:
        return None
    out = []
    for typ, kw in msgs:
        m = mido.Message(typ, channel=ch & 15, time=0, **kw)
        out.append(_PortMsg(m, ch, 0) if ch >= 16 else m)
    return ch, out


def parse_gs_rhythm_part(data):
    """(channel, mode) for GS's USE FOR RHYTHM PART, or None.

    F0 41 dd 42 12 4b 1p 15 mm cs F7: part p of block b (40 port A, 50 port B
    -- channel + 16) a drum part (mm 1 or 2, the SC-88's two drum maps) or a
    melodic one (0). The GS part numbering: p 0 is part 10, 1-9 parts 1-9,
    A-F parts 11-16 -- each on its own channel by default. Files put a kit on
    channel 11, 12, or 9 this way (Falcom, Konami); channel 10 can be made
    melodic.
    """
    d = tuple(data)
    if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12
            and d[4] in (0x40, 0x50) and d[5] >> 4 == 1 and d[6] == 0x15):
        return None
    blk = d[5] & 0x0F
    ch = 9 if blk == 0 else (blk - 1 if blk <= 9 else blk)
    return ch + (16 if d[4] == 0x50 else 0), int(d[7])


def parse_master(data):
    """('vol', gain) / ('fine', cents) / ('coarse', semitones), or None.

    Universal Realtime Device Control, F0 7F dd 04 xx ll mm F7:
      01  Master Volume          14-bit, the CC7 law (tonelib.master_volume_gain)
      03  Master Fine Tuning     14-bit, +/-100 cents about 2000H
      04  Master Coarse Tuning   MSB only, semitones about 40H

    Roland's VE-GS Pro receives only the first of these, and says so, so fine
    and coarse follow the MIDI definition rather than a reference device.
    Anything else returns None and is ignored silently, like every other
    message for a machine this is not.
    """
    d = tuple(data)
    # ROLAND'S OWN, the GS system parameters (F0 41 dd 42 12 40 00 aa .. F7):
    #   40 00 00  MASTER TUNE   four nibbles, 0018-07E8 about 0400: -100.0 ..
    #                           +100.0 cents in tenths
    #   40 00 04  MASTER VOLUME 0-127 (127 at power-on), the universal law
    #   40 00 05  MASTER KEY-SHIFT  28-58 about 40: semitones
    # Sensation (Konami's SC-88Pro data) fades out on 111 of the volume
    if len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12 and d[4:6] == (0x40, 0x00):
        if d[6] == 0x04:
            return ('vol', T.master_volume_gain(d[7] << 7 | d[7]))
        if d[6] == 0x05:
            return ('coarse', float(max(0x28, min(0x58, d[7])) - 0x40))
        if d[6] == 0x00 and len(d) >= 11:
            nib = (d[7] & 15) << 12 | (d[8] & 15) << 8 | (d[9] & 15) << 4 | (d[10] & 15)
            return ('fine', (max(0x18, min(0x7E8, nib)) - 0x400) / 10.0)
        return None
    if len(d) < 6 or d[0] != 0x7F or d[2] != 0x04:
        return None
    ll, mm = d[4], d[5]
    if d[3] == 0x01:
        return ('vol', T.master_volume_gain(mm << 7 | ll))
    if d[3] == 0x03:
        return ('fine', ((mm << 7 | ll) - 8192) / 8192.0 * 100.0)
    if d[3] == 0x04:
        return ('coarse', float(mm - 64))
    return None


def master_message(kind, value, device=0x7F):
    """The bytes for one master message, BETWEEN F0 and F7 -- for tests and
    examples, so nothing writes these by hand and gets the order wrong."""
    if kind == 'vol':
        v = int(round((max(0.0, min(1.0, value)) ** 0.5) * 16383))
        return [0x7F, device, 0x04, 0x01, v & 0x7F, v >> 7]
    if kind == 'fine':
        v = int(round(value / 100.0 * 8192.0)) + 8192
        v = max(0, min(16383, v))
        return [0x7F, device, 0x04, 0x03, v & 0x7F, v >> 7]
    if kind == 'coarse':
        return [0x7F, device, 0x04, 0x04, 0x00, int(value) + 64]
    raise ValueError(kind)


def parse_sota(data):
    """(channels, [12 cents]) from a sysex payload, or None if it is not one.

    `data` is mido's view: the bytes BETWEEN F0 and F7, so it starts at the
    manufacturer/universal id. Anything that is not a Scale/Octave Tuning
    Adjust returns None and must be ignored silently -- a Roland GS or Yamaha
    XG header in a file is a message for a different machine, not a malformed
    one.
    """
    d = tuple(data)
    if len(d) < 7 or d[0] not in (SOTA_NONREALTIME, SOTA_REALTIME):
        return None
    if d[2] != 0x08 or d[3] not in (0x08, 0x09):
        return None
    chans = _sota_channels(d[4], d[5], d[6])
    body = d[7:]
    if d[3] == 0x08:
        if len(body) < 12:
            return None
        cents = [float(b) - 64.0 for b in body[:12]]
    else:
        if len(body) < 24:
            return None
        cents = [((body[2 * i] << 7 | body[2 * i + 1]) - 8192) / 8192.0 * 100.0
                 for i in range(12)]
    return chans, cents


def sota_message(cents, channels=range(16), two_byte=True, realtime=False):
    """A mido sysex carrying twelve cent offsets. The inverse of parse_sota.

    This is the half with a payoff: the renderer's own tuners are finer than
    twelve cents-per-pitch-class, so reading this is a convenience, but WRITING
    it lets a temperament travel to any GM2 instrument. See
    examples/tuning_sysex.py.
    """
    ff = gg = hh = 0
    for c in channels:
        if 14 <= c <= 15:
            ff |= 1 << (c - 14)
        elif 7 <= c <= 13:
            gg |= 1 << (c - 7)
        elif 0 <= c <= 6:
            hh |= 1 << c
    out = [SOTA_REALTIME if realtime else SOTA_NONREALTIME, 0x7F, 0x08,
           0x09 if two_byte else 0x08, ff, gg, hh]
    for c in cents[:12]:
        if two_byte:
            v = int(round(max(-100.0, min(100.0, c)) / 100.0 * 8192.0)) + 8192
            v = max(0, min(0x3FFF, v))
            out += [(v >> 7) & 0x7F, v & 0x7F]
        else:
            out.append(max(0, min(127, int(round(c)) + 64)))
    return out


# THE RENDER ENDS WHEN THE MUSIC DOES, NOT WHEN THE FILE DOES. It used to
# stop one second after the last MIDI event, whatever was still sounding: a
# crash on the final beat was cut 14 dB down at 1.25 s, and the room tail,
# added after, rang on past the cut (Ben: "crashes at the end of a recording
# seem to be stopped short, then the room tail hangs"). Every partial's
# envelope is known in closed form (voice_partial.inc's AMP), so the render
# runs on to the last sample any partial is still above RING_FLOOR -- an
# absolute level, -100 dB on the output scale, so the streaming renderer,
# which never sees the whole table at once, reaches the same length. A
# one-shot's note is a fixed 8 s; this ends it where it has actually died.
RING_FLOOR = 1e-5
RING_MAX = 30.0              # seconds past the file's end, at most


def ring_last(r):
    """The last sample any of these partials sounds above RING_FLOOR: rows as
    a dict of columns (numpy arrays or array.array). 0 if none does."""
    a = np.maximum(np.abs(np.asarray(r['aL'], np.float64)), np.abs(np.asarray(r['aR'], np.float64)))
    if not len(a):
        return 0
    sl = np.asarray(r['sus'], np.float64)
    af = np.asarray(r['aft'], np.float64)
    out = np.zeros(len(a))
    with np.errstate(divide='ignore', invalid='ignore'):
        t = np.zeros(len(a))
        for c, lr in (((1.0 - sl) * (1.0 - af) * a, np.asarray(r['logr'], np.float64)),
                      ((1.0 - sl) * af * a, np.asarray(r['logrA'], np.float64))):
            loud = c > RING_FLOOR
            tt = np.where(lr > 0.0, np.log(np.where(loud, c, 1.0) / RING_FLOOR) / np.where(lr > 0.0, lr, 1.0), np.inf)
            t = np.maximum(t, np.where(loud, tt, 0.0))
        # a sustain above the floor holds until the release
        t = np.where(sl * a > RING_FLOOR, np.inf, t)
    non = np.asarray(r['non'], np.float64)
    stop = np.asarray(r['noff'], np.float64) + np.asarray(r['re'], np.float64)
    out = np.minimum(stop, non + t * SR)
    out = np.where(a > RING_FLOOR, out, 0.0)
    out += np.maximum(np.asarray(r['delL'], np.float64), np.asarray(r['delR'], np.float64))
    return int(np.ceil(out.max()))


def bend_blocks(events, nblk):
    """Per-block (mean ratio, cumulative extra phase) for one channel's bend.

    THE BEND IS A RATIO, so the extra phase a partial of angular frequency w
    accrues over block k is w*(r_k - 1)*BLK -- and w factors out. The cumulative
    term is therefore PARTIAL-INDEPENDENT, which is the whole reason a channel
    needs two rows rather than two per partial, and the reason the kernel can
    stay stateless.

    NOT onepole_blocks, which is the other per-block control in this file. Its
    TAU is a model of a swell shutter's and a fader's mechanical inertia. A
    pitch wheel is a sprung lever and MIDI pitch bend is a zero-order hold
    between messages -- and A-Team.mid, the only real bend in the corpus,
    writes one message every 11.4 ms against a block of 11.6. Smoothing that
    would round off the only gesture there is.

    r is the block's exact MEAN of the step function the file wrote, and C is
    the running sum of those same means -- computed FROM C rather than beside
    it, so C[b+1] == C[b] + (r[b]-1)*BLK holds by construction and not by care.
    That identity is what makes the phase continuous across a step in the
    wheel: a bend is a chirp and not a click only because of it. Same argument
    as the vibrato's block-mean frequency in synthkernel.c.

    THE STATIC PART IS NOT IN HERE. A bend that never moves is folded into f0
    instead (see the tuning/gesture split in prepare), and that is a numerical
    requirement, not a tidiness one: C grows without bound while a bend is
    held, and a -11.7 cent offset over a ten-minute piece accumulates some
    180,000 samples of phase. In float32 the rounding there lands as a phase
    step per block -- an audible buzz. Here C only ever carries excursions.
    """
    ev = sorted(events)
    edges = np.arange(nblk + 1, dtype=np.float64) * BLK / SR
    # I(t) = integral of (r-1) dt, in SECONDS, over the step function
    ts = np.array([0.0] + [t for t, _ in ev], np.float64)
    rs = np.array([1.0] + [r for _, r in ev], np.float64)
    # cumulative integral at each event time
    seg = np.diff(ts, append=max(edges[-1], ts[-1]) + 1.0)
    acc = np.concatenate(([0.0], np.cumsum((rs - 1.0) * seg)))
    i = np.searchsorted(ts, edges, side='right') - 1
    I = acc[i] + (rs[i] - 1.0) * (edges - ts[i])
    C = I * SR                                  # samples of extra phase
    r = 1.0 + np.diff(C) / float(BLK)
    return r.astype(np.float32), C[:nblk].astype(np.float64)


def onepole_blocks(events, nblk, default):
    bc = (np.arange(nblk) + 0.5) * BLK / SR
    out = np.empty(nblk, np.float32); segs = [(0.0, default)] + list(events); v = default
    for k, (t0, target) in enumerate(segs):
        t1 = segs[k + 1][0] if k + 1 < len(segs) else 1e18
        m = (bc >= t0) & (bc < t1); out[m] = target + (v - target) * np.exp(-(bc[m] - t0) / TAU)
        if t1 < 1e17: v = target + (v - target) * np.exp(-(t1 - t0) / TAU)
    return out

def onepole_edges(events, nblk, default):
    """onepole_blocks at the nblk+1 block EDGES rather than the centres: a
    bend row's level (BL), which the kernel ramps across each block. The same
    fader inertia (TAU), so a CC7 step is a 15 ms glide and not a click."""
    te = np.arange(nblk + 1) * BLK / SR
    out = np.empty(nblk + 1, np.float32); segs = [(0.0, default)] + list(events); v = default
    for k, (t0, target) in enumerate(segs):
        t1 = segs[k + 1][0] if k + 1 < len(segs) else 1e18
        m = (te >= t0) & (te < t1); out[m] = target + (v - target) * np.exp(-(te[m] - t0) / TAU)
        if t1 < 1e17: v = target + (v - target) * np.exp(-(t1 - t0) / TAU)
    return out

# How long a voice takes to get out of the way when its own pitch is struck
# again. Not a cut: a cut is a step and a step is a click. Samplers call this
# stealing and give it a few milliseconds for exactly this reason.
RETRIGGER_FADE = 0.004
# the controller matrix's tremolo rate (GS LFO1, GM2's LFO): the rate a
# tone's own LFO runs at isn't in the file, so a GM vibrato's
TREMOLO_MATRIX_HZ = 5.5
EASTERN = None          # the secondary tuning's spec (ragas.py); eastern= on the command line
LAST_DRONES = []        # see prepare(): the drone notes it last inserted

# GM's default reverb send. It is also the value that means "the distance this
# room was placed for", so a file that never sends CC91 is unchanged.
GM_DEFAULT_REVERB = 40


def registration_blocks(ch, prop, ccs, nblk, amp=None):
    ranks = prop.stop_ranks; order = getattr(prop, 'crescendo_order', [r[0] for r in ranks])
    # 14-bit stop word: CC11 (low 7 bits 0..6) | CC43 (high bits 7..13) -- lets a
    # Mixtur and other stops past bit 6 be drawn. CC43=0 -> the old 7-bit behaviour.
    # WHERE THE STOP WORD LIVES. CC11/CC43 on the pipe organ and the harpsichord,
    # where CC7 is the swell shutter. A voice can put it elsewhere -- the
    # harmonium's is CC43/CC44, CC11 being its bellows -- and then CC7 and CC11
    # stay the channel's volume and expression, as on any other voice.
    # SEVEN BITS A CONTROLLER, as many controllers as the voice names: the
    # church organ's is CC11 | CC43<<7 | CC44<<14 | CC45<<21, 28 stops (its
    # recorded Pitea ranks past bit 13). A file that sends only CC11/CC43 draws
    # what it always drew: the higher bytes start at the default's.
    wccs = tuple(getattr(prop, 'stop_word_ccs', (11, 43)))
    ev = in_order(ccs.get(ch, [])); ds = getattr(prop,'default_stops',1); cres = 0.0; vol = 1.0
    wbytes = [(ds >> (7 * i)) & 0x7F for i in range(len(wccs))]
    swells = wccs[0] == 11
    rank_ev = {r[0]: [] for r in ranks}; swell_ev = []
    def emit(t):
        mask = 0
        for i, b in enumerate(wbytes):
            mask |= b << (7 * i)
        nd = int(cres*len(order)+1e-9); drawn = set(order[:nd])
        for i, r in enumerate(ranks):
            k = r[0]; rank_ev[k].append((t, 1.0 if ((mask>>i)&1 or k in drawn) else 0.0))
        swell_ev.append((t, vol))
    emit(0.0)
    for t, cc, val in ev:
        if cc in wccs: wbytes[wccs.index(cc)] = val
        elif cc==4: cres=val/127.0
        elif cc==7 and swells: vol=val/127.0
        else: continue
        emit(t)
    gate = {r[0]: onepole_blocks(rank_ev[r[0]][1:], nblk, rank_ev[r[0]][0][1]) for r in ranks}
    # ...and a controller matrix's AMPLITUDE (ctrlmatrix), [(t, gain)], on
    # every rank's gate: the swell is a shutter's position, capped open, so a
    # gain there did nothing to an organ already open. Not on rank_ev, whose
    # targets also say when a rank is drawn
    if amp:
        ac = onepole_blocks(list(amp), nblk, 1.0)
        gate = {k: v * ac for k, v in gate.items()}
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
                "tbav","tau","tcut","gb","gt","gc","vd","vr","vp","vdl","delL","delR",
                "gr","cr","br","p0R","pl","fx","mk","rdl","fmw","fmp","fmpR","nfr")

# LIVE'S MOOG TEMPLATES ARE KNOB-NEUTRAL (moog.weights): every harmonic of every
# oscillator at unit weight and phase 0, so the slab can apply whatever the
# panel says -- and move it under a held note -- without a template rebuild.
# live.py sets this while it builds a template; a file render never does.
MOOG_NEUTRAL = False


# THE STRING, ONE SOURCE OF TRUTH. A partial's frequency and decays, and a
# unison string's, as the note loop emits them -- and as the free-string
# register (register.py) builds the strings that were not struck. Shared, not
# copied, so a struck partial and the same string ringing sympathetically
# cannot disagree by so much as a rounding: the register's response to a
# tuning is only as true as its strings are the strings that are played.
def string_partial(props, f0, ratio, m, B):
    """Partial m of a string at f0 (a rank's footage `ratio`), stretched by its
    inharmonicity B: (h, Hz), or None past the voice's last mode."""
    mr = props.mode_ratio(m)
    if mr <= 0.0:
        return None
    h = ratio*mr; stretch = (1.0+0.5*(h*h-1.0)*B) if B>0 else 1.0; hf = f0*h*stretch
    return h, hf


def partial_decay(rp, f0, m):
    """Partial m's decay: (dB/s, its log rate, the aftersound's share, the
    aftersound's log rate) -- the kernel's logr / aft / logrA."""
    dbps = rp.harmonic_decay(m); logr = math.log(T.db_ratio(dbps)) if dbps>0 else 0.0
    # aftersound() is asked with the NOTE's frequency (a register law); a voice
    # whose remainder depends on the partial's own answers aftersound_partial
    _ap = getattr(rp, 'aftersound_partial', None)
    aftL, adbps = _ap(f0, m, dbps) if _ap is not None else rp.aftersound(f0, dbps)
    logrA = math.log(T.db_ratio(adbps)) if adbps>0 else 0.0
    return dbps, logr, aftL, logrA


# A drum machine's sweep carries its cutoff as -cut/TBEND_CUT_SCALE
# (synthkernel.c); register.cut_time reads it back.
TBEND_CUT_SCALE = 1048576.0

ONE_SHOT_FLOOR_DB = 80.0
ONE_SHOT_MIN_S, ONE_SHOT_MAX_S = 8.0, 60.0


def one_shot_ring(rp, f0):
    """How long a melodic one-shot (a bar, a bell: note-off means nothing to
    it) is held: until its last partial is ONE_SHOT_FLOOR_DB under the note's
    loudest -- each partial from its own level, through either stage of its
    decay -- between 8 and 60 s. It had been a flat 8 s, which cut a
    glockenspiel ringing at 1.9 dB/s off at -15 dB (Ben: "its decay goes to
    zero too early ... should probably make it 80"). BY LEVEL, not the slowest
    partial: a pedal hi-hat's first modes sit 30 dB under its top and keep a
    -34 dB aftersound, and timed alone they held a chick for a minute. Never
    shorter than the 8 s it was; a partial that does not decay keeps that.
    A drum kit keeps the flat 8 s (see the caller)."""
    hv = []
    for m in range(1, min(int(getattr(rp, 'max_harmonic', 8) or 8), 512) + 1):
        try:
            v = rp.harmonic_volume(m)
        except (IndexError, ValueError, ZeroDivisionError):
            break
        if v and v > 0.0:
            hv.append((m, v))
    if not hv:
        return ONE_SHOT_MIN_S
    top = max(v for _m, v in hv)
    t = 0.0
    for m, v in hv:
        room = ONE_SHOT_FLOOR_DB + 20.0 * math.log10(v / top)    # dB above the floor
        if room <= 0.0:
            continue
        dbps, _lr, aft, lrA = partial_decay(rp, f0, m)
        if dbps > 0:
            t = max(t, room / dbps)
        adbps = lrA * 20.0 / math.log(10.0)
        if aft > 0 and adbps > 0 and room + 20.0 * math.log10(aft) > 0.0:
            t = max(t, (room + 20.0 * math.log10(aft)) / adbps)
    return min(max(t, ONE_SHOT_MIN_S), ONE_SHOT_MAX_S)


def unison_partial(hf, off_hz, dr, ud):
    """A unison string's partial from the main string's: (Hz, its log rate)."""
    uf = hf*(1.0+dr) + off_hz
    ulr = math.log(T.db_ratio(ud)) if ud>0 else 0.0
    return uf, ulr


def _strike_rows(A, r0, r1, cols, grs=None):
    """A strike's rows for the register, {column: array}: on a voice with
    choirs, only the ranks drawn at its key-down (their gate rows, `grs`) --
    an undrawn rank's partials are emitted gated shut and pluck nothing."""
    rows = {k: np.array(A[k][r0:r1]) for k in cols}
    if grs is not None:
        keep = np.isin(rows['gr'], grs)
        rows = {k: v[keep] for k, v in rows.items()}
    return rows


# THE GS REVERB, as a Sound Canvas file sets it (40 01 3x): its MACRO picks
# one of our physical rooms -- the module has one reverb, as a render has one
# room -- and its LEVEL and TIME scale the tail roomtail draws from that room.
# MATCHED BY WHAT IT IS FOR, NOT BY ITS NAME ("more semantically matching than
# literally matching", Ben), the rooms stepping small to large as Roland's do:
# Room 1-3 the studio (0.33 s), the chamber (0.8) and a larger chamber (~1.1);
# Hall 1 our hall, a modern mid-size concert hall (1.3-2.1 s); Hall 2, Roland's
# "deeper" hall, the grand one (Musikverein-scale, 2.0 s mid, 2.6 in the bass).
# Not the chapel, which rings longer than our hall and would put a "room" past
# Hall 1; not the church, wetter than any Roland hall. Plate and the two
# delays are DEVICES (tonelib: the studio's walls, roomtail the device): a
# plate reverb (EMT 140), and an echo, plain or panning L-R.
GS_REVERB_ROOM = {0: 'studio', 1: 'chamber', 2: 'large_chamber', 3: 'hall', 4: 'grand_hall',
                  5: 'plate', 6: 'delay', 7: 'pan_delay'}
_GS_REVERB_PARAM = {0x30: 'reverb_macro', 0x33: 'reverb_level', 0x34: 'reverb_time',
                    0x35: 'reverb_delay_fb'}
# ...the delays' REV DELAY FB, each macro's own (SC-8850 owner's manual, "About
# Reverb Type"): how many repeats, 0-127; only Delay and Panning Delay read it
GS_REVERB_DELAY_FB = {6: 40, 7: 32}
# ...each macro's own REV TIME (SC-8850 owner's manual, "About Reverb Type"): a
# file's time is measured from it -- Hall 2's where it set none, as a reset leaves
GS_REVERB_TIME = {0: 80, 1: 56, 2: 64, 3: 72, 4: 64, 5: 88, 6: 32, 7: 64}


def parse_gs_reverb(data):
    """(param, value) for a GS reverb macro / level / time message, or None."""
    d = tuple(data)
    if (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12
            and d[4:6] == (0x40, 0x01) and d[6] in _GS_REVERB_PARAM):
        return _GS_REVERB_PARAM[d[6]], int(d[7])
    return None


def gs_reverb(path):
    """{param: value} the file's GS reverb is set to by its first note: the
    song's setup. A reset puts it back to the module's (none)."""
    return gs_setup(path)[0]


_GSD_PLACE = {}


def gsd_place(side, f):
    """Where the GS delay's output `side` ('c', 'l', 'r') reaches the ears at
    frequency f: (gL, gR, dL, dR samples) -- the head model's, for a source
    at the field's middle or side, as a pan of 0 or +-1 places one. A side
    may be a pan (-1..1) itself: a voice between the outputs (a Hexa
    Chorus's), at the angle the pan law puts it (tonelib.stage_angle)."""
    k = (side, int(f))
    v = _GSD_PLACE.get(k)
    if v is None:
        if len(_GSD_PLACE) > 200000:
            _GSD_PLACE.clear()
        if not _GSD_PLACE:
            _GSD_PLACE['_p'] = T.StoppedPipeProperties(261.6, 0, 1, 1)
        q = _GSD_PLACE['_p']
        _x = (_GSD.OUTPUT_X[side] if isinstance(side, str)
              # ...or an angle itself, degrees (the 3D types: past the speakers)
              else q.listener_distance * math.tan(math.radians(max(-80.0, min(80.0, side[1]))))
              if isinstance(side, tuple)
              else q.listener_distance * math.tan(T.stage_angle(float(side))))
        li, ri, ld, rd = q.hrtf_at(_x, 0.0, q.listener_distance)
        v = _GSD_PLACE[k] = (q.hrtf_gain(f, li), q.hrtf_gain(f, ri), ld * SR, rd * SR)
    return v


def parse_gs_eq(data):
    """('eq', param, value) for the GS EQ (40 02 0p), ('eq_part', channel, on)
    for a part's EQ switch (4b 4p 20), or None."""
    d = tuple(data)
    if not (len(d) >= 8 and d[0] == 0x41 and d[2] == 0x42 and d[3] == 0x12):
        return None
    if d[4:6] == (0x40, 0x02) and d[6] <= 3:
        return 'eq', int(d[6]), int(d[7])
    if d[4] in (0x40, 0x50) and d[5] >> 4 == 4 and d[6] == 0x20:
        blk = d[5] & 0x0F
        ch = (9 if blk == 0 else (blk - 1 if blk <= 9 else blk)) + (16 if d[4] == 0x50 else 0)
        return 'eq_part', ch, bool(d[7])
    return None


def gs_setup(path):
    """The file's GS setup by its first note -- (reverb {param: value}, EQ
    {0-3: value}, {channel: EQ on/off}, delay {param: value}, GS?, chorus
    {param: value}) -- a reset
    putting all back. GS? is whether the file speaks GS at all (a GS reset,
    the SC-88's mode set, or a GS parameter): CC94 is the GS delay's send
    only there -- General MIDI 1 calls it celeste depth."""
    rv, eq, sw, dl, gs, ch = {}, {}, {}, {}, False, {}
    for m in _open_midi(path):
        if m.type == 'note_on' and getattr(m, 'velocity', 0):
            break
        if m.type == 'sysex':
            _d = tuple(m.data)
            if len(_d) >= 4 and _d[0] == 0x41 and _d[2] == 0x42 and _d[3] == 0x12:
                gs = True
            if parse_gs_reset(m.data):
                rv, eq, sw, dl, ch = {}, {}, {}, {}, {}
                continue
            if len(_d) >= 8 and _d[4:6] == (0x40, 0x01) and _d[6] in _CHR.GS_PARAM:
                ch[_CHR.GS_PARAM[_d[6]]] = int(_d[7])
                if _d[6] == 0x38:             # a macro sets them all
                    ch = {'macro': int(_d[7])}
                continue
            if len(_d) >= 8 and _d[4:6] == (0x40, 0x01) and _d[6] in _GSD.PARAM:
                dl[_GSD.PARAM[_d[6]]] = int(_d[7])
                if _d[6] == 0x50:             # a macro sets all ten: what came before is gone
                    dl = {'macro': int(_d[7])}
                continue
            r = parse_gs_reverb(m.data)
            if r is not None:
                if r[0] == 'reverb_macro':      # a macro sets all: what came before is gone
                    rv = {}
                rv[r[0]] = r[1]
                continue
            e = parse_gs_eq(m.data)
            if e is not None:
                if e[0] == 'eq':
                    eq[e[1]] = e[2]
                else:
                    sw[e[1]] = e[2]
    return rv, eq, sw, dl, gs, ch


def gs_eq_gain(f, eq):
    """THE SC-88's EQ at frequency f: a low and a high shelf, first order --
    the low at 200 or 400 Hz, the high at 3 or 6 kHz, each -12..+12 dB about
    40H (VE-GS Pro MIDI Implementation 40 02 0x). Linear amplitude."""
    lo_f = 400.0 if eq.get(0, 0) else 200.0
    hi_f = 6000.0 if eq.get(2, 0) else 3000.0
    lo_g = max(-12, min(12, eq.get(1, 0x40) - 0x40))
    hi_g = max(-12, min(12, eq.get(3, 0x40) - 0x40))
    x = (f / lo_f) ** 2
    y = (f / hi_f) ** 2
    return 10.0 ** ((lo_g / (1.0 + x) + hi_g * y / (1.0 + y)) / 20.0)


_GS_ROOM = {}            # the last prepare's room and GS reverb level/time, for the sidecar
_GS_EQ = {}              # the file's GS EQ while it prepares: {'eq': {0-3: v}, 'off': {channels}}
_GS_DLY = {}             # ...and its GS delay: {'dev': gsdelay.device} for a GS file
_GS_CHO = {}             # ...and its GS chorus: {'dev': chorus.gs_device} for a GS file
_GS_FILE = [False]       # ...and whether it speaks GS at all (patch_map.GS_TRIM_DB)



def prepare(path, tuner='hybrid440', sink=None):
    """_prepare, in the room the file's GS reverb macro chose -- where nobody
    chose one (TUNING_ROOM) -- and the room put back after; the file's reverb
    level and time ride _LAST_PREP to the room sidecar, for roomtail."""
    fx, eq, eqsw, dly, gs, cho = gs_setup(path)
    _GS_FILE[0] = bool(gs)
    # ...and its GS chorus, the device (chorus.gs_device): Chorus 3 as a reset
    # leaves it, then the file's
    _GS_CHO.clear()
    if gs and os.environ.get('TUNING_GS_CHORUS', '1') not in ('0', 'off', ''):
        _GS_CHO['dev'] = _CHR.gs_device(cho)
    # THE GS DELAY, for a GS file: Delay 1 as a reset leaves it, then the file's
    _GS_DLY.clear()
    if gs and os.environ.get('TUNING_GS_DELAY', '1') not in ('0', 'off', ''):
        _GS_DLY['dev'] = _GSD.device(dly)
    if os.environ.get('TUNING_ROOM'):
        fx = {}
    room = GS_REVERB_ROOM.get(fx.get('reverb_macro'))
    # the EQ, for _prepare's partials: off where flat, so nothing moves
    _GS_EQ.clear()
    if any(eq.get(k, 0x40) != 0x40 for k in (1, 3)):
        _GS_EQ.update(eq=eq, off={c for c, on in eqsw.items() if not on})
    prev = T.ROOM_NAME[0]
    if room is not None and room != prev:
        T.set_room(room)
    try:
        out = _prepare(path, tuner, sink)
    finally:
        if T.ROOM_NAME[0] != prev:
            T.set_room(prev)
    # (its own record: render() rebuilds _LAST_PREP from what prepare returns,
    # and a streamed render from the stream)
    _GS_ROOM.clear()
    _GS_ROOM.update(room_name=room or prev, tail_gain=fx.get('reverb_level', 64) / 64.0,
                    tail_time=2.0 ** ((fx['reverb_time'] - GS_REVERB_TIME.get(fx.get('reverb_macro', 4), 64))
                                      / 64.0) if 'reverb_time' in fx else 1.0)
    if fx.get('reverb_macro') in GS_REVERB_DELAY_FB:
        _GS_ROOM['delay_fb'] = fx.get('reverb_delay_fb', GS_REVERB_DELAY_FB[fx['reverb_macro']])
    return out


def _prepare(path, tuner='hybrid440', sink=None):
    """Parse + tune + build the full partial table (the one-time cost). Returns a
    dict of contiguous arrays ready for synth_window(); reused by render() (one
    full window) and play.py (streamed windows)."""
    lib = ensure_lib(); lib.synth_voice.restype = None
    import random; random.seed(0)   # per-note pitch/timing jitter, deterministic (as the reference seeds)
    T.RND_STREAM.seed(0)            # ...and the [RND] drum strikes' (tonelib.RandomStrike)
    FREQ = tuning_table(tuner)
    # A SECONDARY TUNING for the Eastern instruments (ragas.py): the classes that
    # declare tuning_family = 'indian' play this table, the rest the render's.
    # Sa sits at the primary tuner's own pitch for its key unless the spec
    # names one, so Sa coincides with the Western instruments. None = off.
    FREQ_E = None
    _east = EASTERN or os.environ.get('TUNING_EASTERN') or None
    if _east:
        import ragas
        _sys_e, _raga_e, _sa_key, _sa_hz = ragas.parse(_east)
        FREQ_E = ragas.table(_east, sa_hz=FREQ.get(ragas.sa_note(_sa_key)))
        T.raga_sa_note = ragas.sa_note(_sa_key)
        T.raga_spec = _east
    elif str(tuner).lower().startswith('raga:'):
        # ...or the render's own tuner IS a raga's: Sa is then its Sa
        import ragas
        T.raga_sa_note = ragas.sa_note(ragas.parse(tuner)[2])
        T.raga_spec = tuner
    else:
        T.raga_sa_note = None
        T.raga_spec = None
    ch_prog, ch_progs, notes, ccs, total, legato, pws, (ats, pts, sotas, _sys) = parse(path)
    _DEDIT = _sys.get('dedit') or {}
    _EFXEV = (_sys.get('efx') or []) if os.environ.get('TUNING_GS_EFX', '1') not in ('0', 'off', '') else []
    # THE CONTROLLER MATRIX's timelines (parse: ctrlmatrix) -- amplitude, and
    # LFO1 amplitude depth -- per channel
    _CMXEV = _sys.get('cmx') or dict(amp={}, tva={}, pitch={}, cutoff={}, tvf={}, rate={}, vib={})

    def _cmx_at(_k, _c, _t, _d=0.0):
        """The controller matrix's value _k on channel _c in force at _t."""
        _v = _d
        for _et, _ev in _CMXEV[_k].get(_c, ()):
            if _et > _t + 1e-9:
                break
            _v = _ev
        return _v
    _EFXN = [None]          # this note's insertion-effect chain (gsefx.chain), or None
    _EFX_CH = {}            # channel -> its first EFX chain: what is set once (amp, cabinet, flanger)
    # ...and the parts on a type with a bus of its own (efxbus), each over the
    # whole file -- found from the timeline up front, not at a part's first
    # effect note, for a part may come to it later in the song
    _BUS_CH = {}
    if _EFXEV and not MOOG_NEUTRAL:
        for _bc in sorted({ev[1] for _, ev in _EFXEV if ev[0] == 'part'}):
            _bs = _GSX.bus_setup(_EFXEV, _bc, SR)
            if _bs is not None:
                _BUS_CH[_bc] = _bs
    _USET = _sys.get('uset') or {}
    rpns, master, gmon = _sys['rpns'], _sys['master'], _sys['gmon']
    _pwseq = _sys['pwseq']

    # ---------------------------------------------- THE `gm2` TUNER'S STORE
    #
    # Under `gm2`, and only under it, the FILE owns the tuning: its MTS dumps
    # and single-note changes fill an mts.TuningStore, and RPN 0/4 and 0/3 pick
    # a bank and program per channel. Replayed in message order -- the
    # tie-break the RPNs taught -- into a timeline of (time, table) per
    # channel, and each note reads the table in force at its ONSET through
    # _F(ch, t). Under every other tuner _F is simply FREQ, so the note loop
    # below does not branch on the tuner at all.
    #
    # THE SPEC SAYS SOUNDING NOTES MOVE, for two of these: a tuning program or
    # bank select ("This change takes effect immediately") and a real-time
    # single-note change. Here each note keeps the table in force at its
    # onset, so a change that lands mid-note reaches it only from its next
    # onset -- moving a sounding partial is a gesture, and live does it where
    # this does not. Counted and reported, not hidden. Dumps and non-real-time
    # changes are setup messages and do not count: the spec has them ignored
    # by notes already sounding, which is exactly what this does.
    _MTS_TL = {}
    if str(tuner).lower() == 'gm2':
        _store = _MTS.TuningStore(warn=lambda m: print("  " + m))
        _tev = [(_t, _q, 'mts', None, _m) for _t, _q, _m in _sys['mts']]
        for _c, _evs in rpns.items():
            _tev += [(_t, _q, _k, _c, _v) for _t, _k, _v, _q in _evs
                     if _k in ('tprog', 'tbank')]
        _tev += [(_t, _q, 'gmon', None, None) for _t, _q in gmon]
        _tev.sort(key=lambda e: (e[0], e[1]))
        _cur = {}
        # Every channel a note is on, and at least the first sixteen: a MIDI
        # 2.0 file can address sixteen groups of them.
        _mts_chs = sorted(set(range(16)) | {n[0] for n in notes})

        def _snap(_t):
            for _c in _mts_chs:
                _tab = _store.table_for(_c)
                if _cur.get(_c) is not _tab:
                    _cur[_c] = _tab
                    _MTS_TL.setdefault(_c, []).append(
                        (_t, {_k: float(_tab[_k]) for _k in range(128)}))
        _snap(0.0)
        for _t, _q, _k, _c, _v in _tev:
            if _k == 'mts':
                _store.load(_v)
            elif _k == 'tprog':
                _store.select(_c, program=_v)
            elif _k == 'tbank':
                _store.select(_c, bank=_v)
            elif _k == 'gmon':
                _store.reset_selections()
            _snap(_t)
        _late = 0
        for _t, _q, _m in _sys['mts']:
            if _m[0] == 'single' and _m[4]:
                _late += sum(1 for _n in notes if _n[2] < _t < _n[3])
        for _c, _evs in rpns.items():
            for _t, _k, _v, _q in _evs:
                if _k in ('tprog', 'tbank'):
                    _late += sum(1 for _n in notes
                                 if _n[0] == _c and _n[2] < _t < _n[3])
        if _late:
            print("  gm2: %d notes were sounding when a tuning change that "
                  "should move them arrived; here they keep their tuning until "
                  "their next onset (live moves them)" % _late)

    # ------------------------------------------- CC71-78, IN FORCE AT AN ONSET
    # A timeline per channel rather than a snapshot per note, so the notes this
    # renderer makes for itself -- a mono handoff, a gliss rung -- read the same
    # state as the notes the file wrote. GM System On puts every control back
    # to 64; CC121 does not touch them, as live does not.
    _SND_TL = {}
    for _c, _evs in _sys['snd'].items():
        _ev = [(_t, _q, _cc, _v) for _t, _q, _cc, _v in _evs]
        _ev += [(_t, _q, None, None) for _t, _q in gmon]
        _ev.sort(key=lambda e: (e[0], e[1]))
        _SND_TL[_c] = _ev

    def _snd_d(_c, _t):
        """{control name: d} in force at _t, only the ones that are not 64."""
        _st = {}
        for _et, _q, _cc, _v in _SND_TL.get(_c, ()):
            if _et > _t + 1e-9:
                break
            if _cc is None:
                _st = {}
            else:
                _st[T.SOUND_CC[_cc]] = T.sound_offset(_v)
        # ...and the controller matrix's, at this onset (ctrlmatrix): its CUTOFF
        # as brightness (GS's TVF NRPN spans the same 9600 cents in 64 steps),
        # its LFO1 rate as the voice's own vibrato rate (x 2^d). (Its LFO1 pitch
        # depth is a gesture on a sounding note: the pitch stream's, below.)
        if _c in _CMXEV['cutoff']:
            _st['brightness'] = max(-1.0, min(1.0, _st.get('brightness', 0.0) + _cmx_at('cutoff', _c, _t) / 9600.0))
        if _c in _CMXEV['rate']:
            _st['vib_rate'] = _st.get('vib_rate', 0.0) + math.log2(max(0.1, 1.0 + _cmx_at('rate', _c, _t) / 5.5))
        return {_k: _d for _k, _d in _st.items() if _d}

    def _F(_c, _t):
        """This channel's 128-key table at time _t: FREQ unless under gm2."""
        _tl = _MTS_TL.get(_c)
        if not _tl:
            return FREQ
        _i = _bisect.bisect_right([_x[0] for _x in _tl], _t + 1e-9) - 1
        return _tl[max(0, _i)][1]

    def _F_SYM(c, t):
        """The table a channel's SYMPATHETIC strings are tuned in: _F's, or
        under a secondary tuning the raga's for an Indian instrument (FREQ_E)."""
        if FREQ_E is not None and getattr(_SYM_CH.get(c), 'tuning_family', None) == 'indian':
            return FREQ_E
        return _F(c, t)

    # ------------------------------------------- CHANNEL MODE, CC123 to CC127
    #
    # ALL NOTES OFF, which this renderer did not read -- and Roland's text
    # makes four more messages carry it: OMNI OFF (124) and OMNI ON (125) are
    # "the same processing ... as when All Note Off is received", and MONO
    # (126) and POLY (127) are All Sounds Off AND All Notes Off before they
    # change the mode. So all five lift every key held on the channel, and a
    # held damper then does what it would do to any lifted key.
    for _c, _evs in ccs.items():
        _aoff = sorted(_t for _t, _cc, _v in _evs if _cc in (123, 124, 125, 126, 127))
        if not _aoff:
            continue
        _nn = []
        for _n in notes:
            if _n[0] == _c:
                _i = _bisect.bisect_right(_aoff, _n[2])
                if _i < len(_aoff) and _aoff[_i] < _n[3]:
                    _n = (_n[0], _n[1], _n[2], _aoff[_i]) + tuple(_n[4:])
            _nn.append(_n)
        notes = _nn

    # MONO MODE, which is what makes portamento's source note a fact rather
    # than a convention. In poly mode "which note does this glide from" has no
    # answer when a chord is sounding -- Roland gives none, and CC84 exists
    # because there is none. In mono there is only ever one note.
    #
    # Roland sets the channel to Mode 4, M = 1, "regardless of the value of
    # mono number": one voice. What it does not specify is what happens when
    # the key on top is released while another is still held. Every monophonic
    # instrument answers the same way -- it goes back to the key still down,
    # last-pressed first -- and that is what a trill with one finger held
    # needs, so that is what this does. Stated as a convention, not as Roland.
    #
    # The handoff is a SLUR: the new note takes the voice's legato attack, and
    # the old one stops as it starts rather than ringing out on its own
    # release or under the damper. One voice cannot be in two places.
    _MONO_SLUR = set()      # (ch, note, on) that arrive by slur
    _MONO_CUT = set()       # (ch, note, on) that are cut off by the next
    _mono_notes = []
    _in_mono = set()
    for _c, _evs in ccs.items():
        _gm = [_t for _t, _q in gmon]
        _mode = sorted([(_t, _cc == 126) for _t, _cc, _v in _evs if _cc in (126, 127)]
                       + [(_t, False) for _t in _gm], key=lambda e: e[0])
        if not any(_m for _t, _m in _mode):
            continue
        _spans = []; _st = None
        for _t, _m in _mode:
            if _m and _st is None:
                _st = _t
            elif not _m and _st is not None:
                _spans.append((_st, _t)); _st = None
        if _st is not None:
            _spans.append((_st, total + 1.0))

        def _mono_at(_t, _spans=_spans):
            return any(_a <= _t < _b for _a, _b in _spans)

        _mine = [_n for _n in notes if _n[0] == _c and _mono_at(_n[2])]
        if not _mine:
            continue
        _in_mono.update(id(_n) for _n in _mine)
        # Releases before presses at the same instant: a key lifted as the next
        # goes down is not an overlap, so it is not a slur.
        _ev = sorted([(_n[2], 1, _n) for _n in _mine]
                     + [(_n[3], 0, _n) for _n in _mine],
                     key=lambda e: (e[0], e[1]))
        _stack = []            # held keys, in the order they went down
        _cur = None            # (note tuple it came from, start, slur)

        def _emit(_src, _start, _end, _slur, _cut):
            if _end - _start <= 1e-9:
                return
            _nt = (_c, _src[1], _start, _end) + tuple(_src[4:])
            _mono_notes.append(_nt)
            if _slur:
                _MONO_SLUR.add((_c, _src[1], _start))
            if _cut:
                _MONO_CUT.add((_c, _src[1], _start))

        for _t, _kind, _n in _ev:
            if _kind == 1:
                if _cur is not None:
                    _emit(_cur[0], _cur[1], _t, _cur[2], True)
                _stack = [_x for _x in _stack if _x[1] != _n[1]] + [_n]
                _cur = (_n, _t, _cur is not None)
            else:
                _top = _cur is not None and _cur[0][1] == _n[1]
                _stack = [_x for _x in _stack if _x[1] != _n[1]]
                if not _top:
                    continue            # already replaced: nothing sounds for it
                if _stack:
                    _emit(_cur[0], _cur[1], _t, _cur[2], True)
                    _cur = (_stack[-1], _t, True)   # back to the key still down
                else:
                    _emit(_cur[0], _cur[1], _t, _cur[2], False)
                    _cur = None
    if _mono_notes:
        notes = [_n for _n in notes if id(_n) not in _in_mono] + _mono_notes


    # THE SAME SPLIT THE PITCH WHEEL GETS, and for the same reason: a table set
    # before the channel's first note and never changed is a TEMPERAMENT, and a
    # fixed factor on f0 reproduces it exactly. Real files send it once in the
    # header. One that changed mid-note would be a gesture, which this does not
    # model -- the last table in force at the channel's first note is used and
    # the change is reported rather than silently interpolated.
    _OTUN = {}
    for _c, _ev in sotas.items():
        # ON TIME ALONE, and stably. sorted() on the bare tuples broke ties on
        # the table itself, so two tables sent on the same tick came out in
        # order of their cents rather than the order they were sent -- which
        # mattered the moment GM System On started posting a zero table.
        _ev = sorted(_ev, key=lambda e: e[0])
        _f = min((_n[2] for _n in notes if _n[0] == _c), default=None)
        if _f is None:
            continue
        _tab = next((_t for _s, _t in reversed(_ev) if _s <= _f + 1e-6),
                    _ev[0][1])
        if any(abs(_x) > 1e-9 for _x in _tab):
            _OTUN[_c] = _tab
        # Only a change AFTER the first note is a change mid-piece. A header
        # that sets a table and then resets it on the same tick has changed
        # its mind before anyone played, which is nothing to report.
        if any(_s > _f + 1e-6 and _t != _tab for _s, _t in _ev):
            print("  scale/octave tuning changes mid-piece on channel %d; "
                  "the table in force at its first note is used" % _c)

    def _pressure_of(ch, note, on, off):
        """This note's pressure, 0..1: the time-weighted MEAN over its span.

        NOT A NOTE-ON SNAPSHOT, which is what CC7/CC11/CC10 get from cv() and
        is wrong here for a reason that is in the name. Pressure is applied
        AFTER the key is already down -- channel aftertouch almost always
        arrives mid-note and polytouch always does -- so a value read at
        note-on is the PREVIOUS note's.

        Collapsing a gesture to one number per note is the honest limit of the
        file path, and it is the same limit CC7 already sits behind: a swell
        WITHIN a held note is not rendered offline. The mean is the collapse
        that preserves the note's energy.
        """
        ev = pts.get((ch, note)) or ats.get(ch)
        if not ev or off <= on:
            return 0.0
        ev = sorted(ev)
        acc = 0.0; v = 0.0; t0 = on
        for t1, val in ev:
            if t1 >= off:
                break
            if t1 > t0:
                acc += v * (t1 - t0); t0 = t1
            elif t1 <= on:
                pass
            v = val / 127.0
            if t1 <= on:
                t0 = on
        acc += v * (off - t0)
        return max(0.0, min(1.0, acc / (off - on)))
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
    Grows=[]; Srows=[]; grow_of={}; crow_of={}; rankev_of={}; sh=(0.06,1.6,3.5,1500.0); _laws=[]
    # KEYED BY (channel, organ): a channel can change program from one
    # registered instrument to another (a tonewheel, then a harmonium), and
    # each has its own ranks, stop word and swell -- organ_family. A channel
    # with one organ is built exactly as it was.
    for ch, _plist in ch_progs.items():
        for prog in dict.fromkeys(_plist):
            pc = property_class_for_program(prog)
            if not getattr(pc, 'registerable', False):
                continue
            _orgk = (ch, organ_family(pc))
            if _orgk in rankev_of:
                continue
            pr = pc(261.6,0,1,1); g,s,rev = registration_blocks(ch, pr, ccs, nblk, _CMXEV['amp'].get(ch))
            rankev_of[_orgk]=rev
            crow_of[_orgk]=len(Srows); Srows.append(s)
            for r in pr.stop_ranks: k=r[0]; grow_of[(_orgk,k)]=len(Grows); Grows.append(g[k])
            if tuple(getattr(pr, 'stop_word_ccs', (11, 43)))[0] == 11:   # only what swells shapes the swell
                _laws.append((crow_of[_orgk], (pr.swell_floor, pr.swell_gain_power,
                                             pr.swell_hf_max, pr.swell_hf_ref_hz)))
    # ONE SWELL LAW PER RENDER, BUT EVERY ORGAN'S OWN LEVEL. The kernel applies
    # one law (sh) to every swell row, and it used to be whichever organ was
    # processed LAST -- so with a Hammond and a church organ in one file each
    # got the other's box: the Hammond, whose swell is fixed open (floor 1.0),
    # took the flue's 0.06 floor, and a rock organ asked for -3 dB by CC7 came
    # out +16 (examples/qkbattle_mix.py). Now the law is a real box's -- the
    # first organ that has one -- and every other organ's row is re-mapped so
    # that law gives the LEVEL its own law would:
    #     L = f_i + (1 - f_i) s^p_i,   s' = ((L - f_g) / (1 - f_g))^(1/p_g)
    # A single-organ render keeps its own law and its rows untouched.
    if _laws:
        sh = next((lw for _r, lw in _laws if lw[0] < 1.0), _laws[-1][1])
        fg, pg = sh[0], sh[1]
        for _r, (fi, pi, _hm, _hr) in _laws:
            if (fi, pi) == (fg, pg):
                continue
            _s = np.asarray(Srows[_r], np.float64)
            _L = fi + (1.0 - fi) * np.clip(_s, 0.0, 1.0) ** pi
            if fg < 1.0:
                Srows[_r] = np.clip((_L - fg) / (1.0 - fg), 0.0, 1.0) ** (1.0 / pg)
            else:
                Srows[_r] = np.ones_like(_s)      # a law with no range: open
    # THE CHEST'S WIND (wind.py): one pressure per organ channel -- a division
    # stands on its own chest -- moved by its wander and its sag under the
    # pipes speaking (TUNING_WIND) and by the Tremulant when drawn (a stop, on
    # whatever TUNING_WIND says). Every rank answers it by its family: the
    # pitch rides a bend row per (channel, family), the level that row's BL.
    # Built whole here, before any note, so a stream is the table by
    # construction. A channel with neither gets no rows, and renders as it did.
    _WROWS = {}              # channel -> {(a, b): (ratio per block, level at block edges)}
    wrow_key = {}            # (channel, rank) -> (a, b)
    for ch, _plist in ch_progs.items():
        prog = next((q for q in dict.fromkeys(_plist)
                     if getattr(property_class_for_program(q), 'registerable', False)), None)
        if prog is None:
            continue
        pc = property_class_for_program(prog)
        if getattr(pc, 'wind_skirt_db', None) is None or not getattr(pc, 'wind_pitch_exp', 0.0):
            continue                            # not a pipe organ
        _wk = (ch, organ_family(pc))
        _tr = rankev_of[_wk].get('tremulant', ())
        _trem_on = any(tg >= 0.5 for _t, tg in _tr) and pc.tremulant_depth > 0.0
        _wsc = wind_scale_for(pc)
        if not (_wsc or _trem_on):
            continue
        import wind as _WND
        _bt = (np.arange(nblk) + 0.5) * BLK / SR
        _trem = np.zeros(nblk)
        for _t, tg in _tr:                      # the stop's draw, a step per block
            _trem[_bt >= _t] = tg
        _dem = np.zeros(nblk + 1)
        _ranks = [r for r in pc.stop_ranks if r[1] is not None]
        for _n in notes:
            if _n[0] != ch or property_class_for_program(_n[6]) is not pc:
                continue
            _f = 440.0 * 2.0 ** ((_n[1] - 69) / 12.0)
            _b0 = min(nblk, int(_n[2] * SR / BLK)); _b1 = min(nblk, int(_n[3] * SR / BLK) + 1)
            if _b1 <= _b0:
                continue
            for r in _ranks:
                _rat = r[1] if isinstance(r[1], (list, tuple)) else [r[1]]
                _w = sum(_WND.pipe_draw(_f * q) for q in _rat)
                _dem[_b0:_b1] += _w * Grows[grow_of[(_wk, r[0])]][_b0:_b1]
        _wd = _WND.Wind(pc, BLK / SR, seed=ch, scale=_wsc, wander_scale=(1.0 if _wsc else 0.0))
        _p = _wd.blocks(_dem[:nblk], _trem)
        _WROWS[ch] = {}
        for r in _ranks:
            _wc = T.rank_wind_class(pc, r)
            _ab = (float(_wc.wind_pitch_exp), float(_wc.wind_level_exp))
            wrow_key[(ch, r[0])] = _ab
            if _ab not in _WROWS[ch]:
                _WROWS[ch][_ab] = _WND.pitch_level(_p, *_ab)
        if _VERBOSE_WIND:
            print("  wind ch%d: pressure %.4f..%.4f, peak draw %.1f units%s"
                  % (ch, _p.min(), _p.max(), _dem.max(), ", tremulant" if _trem_on else ""))
    # THE PLAYER'S BREATH (tonelib.SynthProperties.breath_wobble_db): on a
    # channel a played pipe sounds on, the tone's level, the breath noise's
    # level and the pitch -- each slow noise (one pole at its corner, unit
    # variance from the first edge). The levels ride BEND ROWS' levels (BL,
    # below), given at block EDGES and ramped across each block: as gate rows,
    # held a block, every 11.6 ms step on a loud fundamental was a click and
    # the breath crackled (kurtosis 21 against the recordings' 4). Seeded by
    # the channel, built whole here: a stream is the table by construction.
    _BREATH = {}             # ch -> (tone level at edges, noise level at edges, pitch ratio a block)
    for ch, _plist in ch_progs.items():
        if any(k[0] == ch for k in crow_of):
            continue
        pc = next((c for c in (property_class_for_program(q) for q in dict.fromkeys(_plist))
                   if getattr(c, 'breath_wobble_db', 0.0) > 0.0
                   or getattr(c, 'breath_noise_wobble_db', 0.0) > 0.0
                   or getattr(c, 'breath_pitch_cents', 0.0) > 0.0), None)
        if pc is None:
            continue
        _rng = np.random.default_rng(9173 + ch)

        def _wander(fc):
            a = math.exp(-2.0 * math.pi * fc * BLK / SR)
            b = math.sqrt(1.0 - a * a)
            z = _rng.standard_normal(nblk + 1)
            y = np.empty(nblk + 1)
            y[0] = z[0]
            for i in range(1, nblk + 1):
                y[i] = a * y[i - 1] + b * z[i]
            return y
        _tz = _wander(pc.breath_wobble_hz)
        _sh = float(pc.breath_noise_wobble_share)
        _nz = _sh * _tz + math.sqrt(max(0.0, 1.0 - _sh * _sh)) * _wander(pc.breath_noise_wobble_hz)
        _ps = float(pc.breath_pitch_share)
        _pz = _ps * _tz + math.sqrt(max(0.0, 1.0 - _ps * _ps)) * _wander(pc.breath_pitch_hz)
        _pzb = 0.5 * (_pz[:-1] + _pz[1:])                 # a block's pitch: its edges' mean
        _BREATH[ch] = (10.0 ** (pc.breath_wobble_db * _tz / 20.0),
                       10.0 ** (pc.breath_noise_wobble_db * _nz / 20.0),
                       2.0 ** (pc.breath_pitch_cents * _pzb / 1200.0))
    G = np.ascontiguousarray(np.array(Grows if Grows else [[1.0]],np.float32))
    S = np.ascontiguousarray(np.array(Srows if Srows else [[1.0]],np.float32))

    # ---- PITCH BEND: A TUNING IS NOT A GESTURE ----------------------------
    # The wheel carries two entirely different things and they need different
    # machinery, so they are separated here rather than downstream.
    #
    # A bend SET BEFORE THE CHANNEL'S FIRST NOTE AND NEVER MOVED is a TUNING.
    # John Sankey's bwv847.mid and bwv974.mid are the reason this matters: they
    # put one pitch class on each channel and one static bend on each, which is
    # a temperament written in twelve numbers -- C +0.0 cents, C# -9.8, D -7.7,
    # D# -5.9, E -9.8, F -2.0, F# -11.7, G -3.8, G# -7.8, A -11.7, A# -3.9,
    # B -7.8. The renderer threw it away. A tuning goes into f0 with the other
    # fixed pitch offsets, costs nothing, is EXACT, and is honoured by every
    # voice -- including the harpsichord those files are written for, which
    # could not bend a note if it wanted to.
    #
    # A bend that MOVES WHILE THE CHANNEL IS SOUNDING is a GESTURE, and only a
    # voice that can physically be bent gets one. (A-Team.mid is the corpus's
    # only example: 0 to +200 cents in 57 ms on a guitar.)
    #
    # The classifier is not a heuristic and has no threshold: if the wheel
    # never moves while anything is sounding, a fixed offset reproduces it
    # EXACTLY, and there is nothing left to approximate.
    _BTUN = {}          # channel -> fixed ratio, folded into f0
    _BGEST = {}         # channel -> [(t, residual ratio)], only where it moves
    _first_on = {}
    for _n in notes:
        if _n[0] not in _first_on or _n[2] < _first_on[_n[0]]:
            _first_on[_n[0]] = _n[2]
    # ONE RATIO PER CHANNEL, FROM FIVE INPUTS: the wheel over its range (RPN 0),
    # the channel's coarse and fine tuning (RPN 2, 1), and the device's master
    # coarse and fine tuning (Universal Realtime 04 04, 04 03). The split below
    # then runs on the PRODUCT, so a coarse tune set in the header is a
    # temperament exactly as a static wheel is, and an RPN 0 change while the
    # wheel is off centre moves the pitch -- which is the entire point of RPN 0.
    # tonelib.channel_pitch_ratio is the same function live.py's _repitch uses.
    #
    # IN THE ORDER THE FILE SENT THEM, not by a rule about which kind of
    # message usually comes first. Most of these land on the same tick -- a
    # file's header is all tick zero -- and the first draft broke those ties by
    # putting GM System On first, on the theory that that is where files put
    # it. A file that tunes and THEN resets was left tuned. Message order is
    # the only tie-break that is not a guess.
    def _pitch_stream(_c, with_master=True):
        _ev = [(_t, _q, 'wheel', _p) for _t, _q, _p in _pwseq.get(_c, ())]
        _ev += [(_t, _q, _k, _v) for _t, _k, _v, _q in rpns.get(_c, ())
                if _k in ('range', 'fine', 'coarse')]
        if with_master:
            _ev += [(_t, _q, 'm' + _k, _v) for _t, _k, _v, _q in master
                    if _k in ('fine', 'coarse')]
        _ev += [(_t, _q, 'gmon', None) for _t, _q in gmon]
        _ev.sort(key=lambda e: (e[0], e[1]))
        st = {}
        out = []
        for _t, _o, _k, _v in _ev:
            if _k == 'gmon':
                st = {}
            else:
                st[_k] = _v
            out.append((_t, T.channel_pitch_ratio(
                st.get('range', T.BEND_RANGE_SEMITONES), st.get('wheel', 0),
                st.get('coarse', 0.0), st.get('fine', 0.0),
                st.get('mcoarse', 0.0), st.get('mfine', 0.0))))
        return out

    # MPE: a MEMBER channel is not a tuning and a gesture -- every note on it
    # brings its own bend -- so its pitch is decided per note below (_MPE_AT),
    # and the channel split is for everything else.
    _mpe_ev = _sys.get('mpe') or []

    def _zone_at(_c, _t):
        _z = None
        for _t0, _chs in _mpe_ev:
            if _t0 <= _t + 1e-9:
                _z = _chs
            else:
                break
        return (_z or {}).get(_c)

    def _manager(_c, _t):
        _z = _zone_at(_c, _t)
        return None if _z is None else 16 * _z[0] + (0 if _z[1] == 'lower' else 15)
    _mpe_member = {}
    if _mpe_ev:
        for _n in notes:
            _m = _manager(_n[0], _n[2])
            if _m is not None and _m != _n[0]:
                _mpe_member[(_n[0], _n[1], _n[2])] = _m
    _mchans = {k[0] for k in _mpe_member}
    # A MEEND IS THE NOTE'S, NOT THE CHANNEL'S (tonelib.meend_cents): a channel
    # whose notes lock their bend to the tuning's swaras (bend_detents) has its
    # wheel read per note below (_MEEND_AT), and is left out of the channel's
    # tuning/gesture split here so the bend is not applied twice
    _MEEND_CH = set()
    for _n in notes:
        if (_n[0] in _pwseq and not isinstance(_n[6], DrumProgram)
                and getattr(property_class_for_note(_n[6], _n[1]), 'bend_detents', False)):
            _MEEND_CH.add(_n[0])
    _pchans = (set(pws) | set(rpns) | (set(_first_on) if master else set()) | set(_CMXEV['pitch'])
               | set(_CMXEV['vib'])) - _mchans - _MEEND_CH
    _bdt2 = BLK / float(SR)
    for _c in _pchans:
        _ev = _pitch_stream(_c)
        if _c in _CMXEV['pitch'] or _c in _CMXEV['vib']:
            # ...times the controller matrix's PITCH (ctrlmatrix: a source other
            # than the bend into pitch, in semitones), each change a ratio
            # event; and its VIBRATO (LFO1 pitch depth from aftertouch, a CC, the
            # bend: a gesture on a note already sounding) as a sine on the same
            # stream, a point a block wherever its depth is up -- the bend
            # row's phase runs on across blocks, so its steps do not click
            _mev = [(_t, 2.0 ** (_s / 12.0)) for _t, _s in _CMXEV['pitch'].get(_c, ())]
            if _c in _CMXEV['vib']:
                _vev = _CMXEV['vib'][_c]
                _pv = 0.0
                _vi = 0
                _psemi = 0.0
                _pit = _CMXEV['pitch'].get(_c, ())
                _pj = 0
                _was = False
                for _kb in range(nblk):
                    _tb = (_kb + 0.5) * _bdt2
                    while _vi < len(_vev) and _vev[_vi][0] <= _tb:
                        _pv = _vev[_vi][1]; _vi += 1
                    while _pj < len(_pit) and _pit[_pj][0] <= _tb:
                        _psemi = _pit[_pj][1]; _pj += 1
                    if _pv <= 0.0:
                        if _was:                # back to the plain pitch as it stops
                            _mev.append((_kb * _bdt2, 2.0 ** (_psemi / 12.0)))
                        _was = False
                        continue
                    _was = True
                    _hz = max(0.5, TREMOLO_MATRIX_HZ + _cmx_at('rate', _c, _tb))
                    _mev.append((_kb * _bdt2, 2.0 ** ((_psemi * 100.0 + _pv * math.sin(2.0 * math.pi * _hz * _tb)) / 1200.0)))
                _mev.sort()
            _merged, _rb, _rm = [], 1.0, 1.0
            for _t, _k, _r in sorted([(_t, 0, _r) for _t, _r in (_ev or ())] + [(_t, 1, _r) for _t, _r in _mev]):
                if _k == 0:
                    _rb = _r
                else:
                    _rm = _r
                _merged.append((_t, _rb * _rm))
            _ev = _merged
        _f = _first_on.get(_c)
        if _f is None or not _ev:
            continue                            # tuning a silent channel
        # THE VALUE IN FORCE AT THE FIRST NOTE, which is the LAST event at or
        # before it. This used to take the FIRST such event: a file that set
        # the wheel twice before playing was tuned by the setting it had
        # already changed its mind about.
        _pre = [_r for _t, _r in _ev if _t <= _f + 1e-6]
        _tun = _pre[-1] if _pre else 1.0
        # Only what happens once the channel is sounding can be a gesture;
        # anything earlier is folded into the tuning above.
        _res = [(_t, _r / _tun) for _t, _r in _ev if _t > _f + 1e-6]
        if abs(_tun - 1.0) > 1e-12:
            _BTUN[_c] = _tun
        if any(abs(_r - 1.0) > 1e-9 for _, _r in _res):
            _BGEST[_c] = _res
    BRrows=[]; BCrows=[]; brow_of={}
    # THE MEEND, per note: the wheel's pull, from this note, mapped through the
    # tuning's swaras above it (tonelib.meend_detents/meend_cents) -- the
    # secondary tuning's raga when one is set, else every key of the table the
    # note is tuned in -- over the file's RPN 0 range, or the class's own when
    # it sets none. (ratio at Note On, its own row), as _MPE_AT.
    _MEEND_AT = {}
    if _MEEND_CH:
        import ragas as _RG
        for _n in notes:
            _c, _nt, _on, _off = _n[0], _n[1], _n[2], _n[3]
            if _c not in _MEEND_CH or isinstance(_n[6], DrumProgram):
                continue
            _pcm = property_class_for_note(_n[6], _nt)
            if not getattr(_pcm, 'bend_detents', False):
                continue
            _ind = getattr(_pcm, 'tuning_family', None) == 'indian'
            _tab = FREQ_E if (FREQ_E is not None and _ind) else _F(_c, _on)
            _sa = (T.raga_sa_note if (T.raga_sa_note is not None and (_ind or FREQ_E is None))
                   else int(getattr(_pcm, 'sympathetic_tonic', 60)))
            if _sa not in _tab or _nt not in _tab:
                continue
            if T.raga_spec and (_ind or FREQ_E is None):
                _sy, _rg, _, _ = _RG.parse(T.raga_spec)
                _sw = [_cv for _, _cv in _RG.swaras(_sy, _rg)]
            else:
                _sw = [1200.0 * math.log2(_tab[_sa + _k] / _tab[_sa]) for _k in range(12)]
            _nc = 1200.0 * math.log2(_tab[_nt] / _tab[_sa])
            _rng = [(_t, _v) for _t, _k, _v, _q in rpns.get(_c, ()) if _k == 'range']
            _rst = ([_v for _t, _v in _rng if _t <= _on + 1e-9] or [None])[-1]
            if _rst is None:
                _rst = float(getattr(_pcm, 'bend_range_semitones', T.BEND_RANGE_SEMITONES))
            _det = T.meend_detents(_nc, _sw, 100.0 * _rst)
            _st = float(getattr(_pcm, 'meend_strength', 0.6))

            def _ratio(_w):
                return 2.0 ** (T.meend_cents(100.0 * _rst * _w / 8192.0, _det, _st) / 1200.0)
            _wseq = sorted((_t, _p) for _t, _q, _p in _pwseq.get(_c, ()))
            _w0 = ([_p for _t, _p in _wseq if _t <= _on + 1e-9] or [0])[-1]
            _r0 = _ratio(_w0)
            _mv = [(_t, _ratio(_p) / _r0) for _t, _p in _wseq if _on + 1e-9 < _t <= _off]
            _row = -1
            if any(abs(_r - 1.0) > 1e-9 for _, _r in _mv):
                _r, _cc = bend_blocks(_mv, nblk)
                _row = len(BRrows); BRrows.append(_r); BCrows.append(_cc)
            _MEEND_AT[(_c, _nt, _on)] = (_r0, _row)
    for _c, _ev in _BGEST.items():
        _r, _cc = bend_blocks(_ev, nblk)
        brow_of[_c] = len(BRrows); BRrows.append(_r); BCrows.append(_cc)
    # THE BREATH'S ROWS (above): per channel, a bend row carrying the pitch
    # (times the channel's gesture, if it has one; the phase summed exactly as
    # bend_blocks sums it) with the TONE'S level as its BL, and an unbent row
    # with the BREATH NOISE'S level. Only a note of a breathing class takes them.
    bbrow_of = {}; _BLrows = {}
    for _c, (_tl, _nl, _rt) in _BREATH.items():
        _r = _rt.astype(np.float32)
        if _c in brow_of:
            _r = (BRrows[brow_of[_c]].astype(np.float64) * _r).astype(np.float32)
        _cc = np.concatenate(([0.0], np.cumsum((_r.astype(np.float64) - 1.0) * BLK)))[:nblk]
        _i = len(BRrows); BRrows.append(_r); BCrows.append(_cc)
        _BLrows[_i] = _tl.astype(np.float32)
        _j = len(BRrows); BRrows.append(np.ones(nblk, np.float32)); BCrows.append(np.zeros(nblk))
        _BLrows[_j] = _nl.astype(np.float32)
        bbrow_of[_c] = (_i, _j)
    # the wind's rows (above): a bend row per (channel, family), its phase the
    # running sum of its ratio exactly as bend_blocks makes it, and its level
    wrow_of = {}
    for _c, _fams in _WROWS.items():
        for _ab, (_r, _lv) in _fams.items():
            _r = _r.astype(np.float32)          # the ratio the kernel reads, summed as it is
            _cc = np.concatenate(([0.0], np.cumsum((_r.astype(np.float64) - 1.0) * BLK)))[:nblk]
            _i = len(BRrows); BRrows.append(_r); BCrows.append(_cc)
            _BLrows[_i] = _lv.astype(np.float32)
            for (_c2, _k), _ab2 in wrow_key.items():
                if _c2 == _c and _ab2 == _ab:
                    wrow_of[(_c, _k)] = _i
    # MPE, PER NOTE: the member's bend plus the manager's, in semitones -- a
    # product of ratios (M1-100-UM Appendix C). The value in force at Note On
    # goes into that note's f0; what moves afterwards is the note's own row:
    # its member's bend until its Note Off and no longer (2.2.6), its
    # manager's for as long as it sounds (A.4.1). (ratio at onset, row).
    _MPE_AT = {}
    if _mpe_member:
        def _val(_st, _tt, _d=1.0):
            _v = _d
            for _t0, _r in _st:
                if _t0 <= _tt + 1e-9:
                    _v = _r
                else:
                    break
            return _v
        _sm = {}
        for (ch, note, on), mgr in _mpe_member.items():
            if ch not in _sm:
                _sm[ch] = _pitch_stream(ch)
            if ('m', mgr) not in _sm:
                _sm[('m', mgr)] = _pitch_stream(mgr, with_master=False)
        _offs = {(n[0], n[1], n[2]): (n[3], n[6]) for n in notes if (n[0], n[1], n[2]) in _mpe_member}
        for (ch, note, on), mgr in _mpe_member.items():
            off, prog = _offs[(ch, note, on)]
            ms, gs = _sm[ch], _sm[('m', mgr)]
            r0 = _val(ms, on) * _val(gs, on)
            row = -1
            bendable = (not isinstance(prog, DrumProgram)
                        and getattr(property_class_for_note(prog, note), 'pitch_bendable', True))
            moves = sorted({_t for _t, _ in ms if on + 1e-9 < _t <= off}
                           | {_t for _t, _ in gs if _t > on + 1e-9})
            if bendable and moves:
                ev = [(_t, _val(ms, min(_t, off)) * _val(gs, _t) / r0) for _t in moves]
                if any(abs(_r - 1.0) > 1e-9 for _, _r in ev):
                    _r, _cc = bend_blocks(ev, nblk)
                    row = len(BRrows); BRrows.append(_r); BCrows.append(_cc)
            _MPE_AT[(ch, note, on)] = (r0, row)
    # MIDI 2.0 PER-NOTE PITCH, per note: (absolute semitones at onset or None,
    # the per-note bend ratio at onset, and a bend row of its own when the
    # pitch moves while it sounds). The row is the channel's gesture times the
    # note's own movement, so the kernel is unchanged: one row per note.
    _PN_AT = {}
    _pnd = _sys.get('pn') or {}
    if any(_pnd.get(k) for k in ('attr', 'p725', 'bend')):
        def _step(evs, tt, default):
            v = default
            for _t, _v in evs:
                if _t <= tt + 1e-9:
                    v = _v
                else:
                    break
            return v
        for (ch, note, on, off, vel, _cvv, prog) in notes:
            if isinstance(prog, DrumProgram):
                continue
            _k = (ch, note)
            _attr = _pnd['attr'].get((ch, note, on))
            _p7 = _pnd['p725'].get(_k, [])
            _bd = _pnd['bend'].get(_k, [])
            _rg = _pnd['range'].get(ch, [])
            if _attr is None and not _p7 and not _bd:
                continue
            _tuned = _F(ch, on)[note] * (2.0 ** (_OTUN[ch][note % 12] / 1200.0)
                                         if _OTUN.get(ch) else 1.0)

            def _abs(tt):
                p = _attr if _attr is not None else _step(_p7, tt, None)
                return None if p is None else p

            def _hz(tt):
                p = _abs(tt)
                return 440.0 * 2.0 ** ((p - 69.0) / 12.0) if p is not None else _tuned

            def _pb(tt):
                b = _step(_bd, tt, 0.0)
                return 2.0 ** (b * _step(_rg, tt, T.PN_BEND_RANGE) / 12.0) if b else 1.0
            p0, b0 = _abs(on), _pb(on)
            moves = sorted({_t for _t, _ in (([] if _attr is not None else _p7) + _bd + _rg)
                            if on + 1e-9 < _t <= off})
            row = -1
            if moves:
                bendable = getattr(property_class_for_note(prog, note), 'pitch_bendable', True)
                chev = _BGEST.get(ch, []) if bendable else []
                ref = _hz(on) * b0
                times = sorted({_t for _t, _ in chev} | set(moves))
                ev = [(_t, _step(chev, _t, 1.0) * (_hz(_t) * _pb(_t) / ref)) for _t in times]
                _r, _cc = bend_blocks(ev, nblk)
                row = len(BRrows); BRrows.append(_r); BCrows.append(_cc)
            _PN_AT[(ch, note, on)] = (p0, b0, row)
    # THE SIREN'S ROTOR (siren.py; tonelib siren_rotor): a siren's pitch is its
    # disc's speed, and its speed has inertia -- wound up by its drive, coasting
    # without it. Each siren note gets its rotor integrated a block at a time
    # into a ROW of its own (the mean speed a block, the phase summed from it
    # as bend_blocks sums it, the level at each block edge), carried key to
    # key: a press while the disc still coasts starts from the speed it has.
    # The fire siren's drive is its motor, full while held (its GS length the
    # least); the Helmholtz siren's is its AIR -- velocity, channel and poly
    # aftertouch, CC2, the most of them -- and its level the air's, against
    # the velocity's own gain. Its upper disc rides a second row, the first's
    # turned by the crank (CC1): the same ratio, its phase ahead by the
    # chest's angle, and its ratio moved while the wheel moves, as the crank
    # moved it. (ch, note, on) -> (rows, end).
    _SIREN_AT = {}
    _sir_keys = {}
    for (_c, _nt, _on, _of, _v, _cvv, _pg) in notes:
        if (_c, _nt, _on) in _mpe_member:
            continue
        if is_drum(_pg):
            _dd = percussion_for_note(_nt, kit_for_program(int(_pg)))
            _spc = _dd[1] if _dd else None
        else:
            _spc = property_class_for_note(_pg, _nt)
        _kind = getattr(_spc, 'siren_rotor', None)
        if _kind:
            _sir_keys.setdefault((_c, _nt, _kind), []).append((_on, _of, _v, _spc))
    if _sir_keys:
        import siren as _SIR
        _bdt = BLK / float(SR)

        def _stepv(_ev, _tt, _d=0):
            _x = _d
            for _t0, _val in _ev:
                if _t0 <= _tt + 1e-9:
                    _x = _val
                else:
                    break
            return _x
        for (_c, _nt, _kind), _ns in _sir_keys.items():
            _ns.sort()
            _rot = _SIR.Rotor(_kind)
            _tprev = None
            _at = sorted(ats.get(_c, []))
            _pt = sorted(pts.get((_c, _nt), []))
            _c2 = sorted((_t, _val) for _t, _cc, _val in ccs.get(_c, []) if _cc == 2)
            _c1 = sorted((_t, _val) for _t, _cc, _val in ccs.get(_c, []) if _cc == 1)
            for _i, (_on, _of, _v, _spc) in enumerate(_ns):
                if _tprev is not None and _on > _tprev:
                    _rot.coast(_on - _tprev)
                _drive_end = _of
                if getattr(_spc, 'held_texture', False) and getattr(_spc, 'gate_time', None):
                    _drive_end = max(_of, _on + _spc.gate_time)
                _cap = _ns[_i + 1][0] if _i + 1 < len(_ns) else float('inf')
                _pv = _v / 127.0
                _b0 = int(_on * SR // BLK)
                _r = []; _lv = []
                _k = _b0
                _end = None
                while True:
                    _tb = _k * _bdt
                    if _tb >= _cap or _k >= nblk:
                        _end = min(_cap, nblk * _bdt)
                        break
                    _tm = _tb + 0.5 * _bdt
                    if _tm < _drive_end:
                        if _kind == 'fire':
                            _p = 1.0
                        else:
                            _p = max(_pv, _stepv(_at, _tm) / 127.0, _stepv(_pt, _tm) / 127.0,
                                     _stepv(_c2, _tm) / 127.0)
                    else:
                        _p = 0.0
                    _rr, _l0, _l1 = _rot.block(_p, _bdt)
                    _r.append(_rr); _lv.append(_l0)
                    _k += 1
                    if _tb >= _drive_end:
                        if _kind == 'fire':
                            if _l1 <= 10.0 ** (-_SIR.FLOOR_DB / 20.0):
                                _end = _k * _bdt
                                break
                        elif _rot.air <= 1e-3 * max(_pv, 1e-3):
                            _end = _k * _bdt
                            break
                _lv.append(_rot.level())
                _tprev = min(_end, _cap)
                # ...AND HELD AT ITS LAST past its end, for its release: a row
                # back at 1 there sounded the tail at full level and the key's
                # nominal pitch
                _ra = np.ones(nblk, np.float32)
                _n = min(len(_r), nblk - _b0)
                _ra[_b0:_b0 + _n] = _r[:_n]
                if _n:
                    _ra[_b0 + _n:] = _r[_n - 1]
                _la = np.ones(nblk + 1, np.float32)
                _lvn = np.asarray(_lv[:_n + 1], np.float64)
                if _kind != 'fire':
                    _lvn = _lvn / math.sqrt(max(_pv, 1e-3))   # the velocity's gain is the onset's level
                _la[_b0:_b0 + len(_lvn)] = _lvn
                _la[_b0 + len(_lvn):] = _lvn[-1]
                _cc = np.concatenate(([0.0], np.cumsum((_ra.astype(np.float64) - 1.0) * BLK)))[:nblk]
                _lo = len(BRrows); BRrows.append(_ra); BCrows.append(_cc)
                _BLrows[_lo] = _la
                _rows = (_lo,)
                if getattr(_spc, 'siren_upper', None):
                    # the crank: the upper chest's angle as samples of phase at
                    # each block's start, from the wheel; 0 outside the note
                    _frev = _F(_c, _on)[_nt] / 12.0
                    _dl = np.zeros(nblk + 1, np.float64)
                    for _j in range(_b0, min(_b0 + _n + 1, nblk + 1)):
                        _dl[_j] = _SIR.crank_samples(_SIR.crank_angle(_stepv(_c1, _j * _bdt)),
                                                     _frev, SR)
                    _ru = (_ra.astype(np.float64) + np.diff(_dl) / BLK).astype(np.float32)
                    # the lower disc's phase plus the chest's angle, exactly --
                    # summed from _ru instead, a note in the render's first
                    # block lost its starting angle (no block before it to
                    # carry the step)
                    _cu = _cc + _dl[:nblk]
                    _up = len(BRrows); BRrows.append(_ru); BCrows.append(_cu)
                    _BLrows[_up] = _la.copy()
                    _rows = (_lo, _up)
                _SIREN_AT[(_c, _nt, _on)] = (_rows, _tprev)
    # THE HAMMOND SCANNER (scanner.py; tonelib `scanner`, 'V1'..'C3'): its
    # vibrato is a moving delay -- one row per channel, BC the delay as phase,
    # on the synchronous motor's clock from the render's start, so every note
    # rides the same sweep. Its partials go onto it after the notes are built
    # (scanner.expand, below: vibrato moves them, chorus adds a copy).
    _SCAN_CH = {}
    for (_c, _nt, _on, _of, _v, _cvv, _pg) in notes:
        if SCANNER_OFF or _c in _SCAN_CH or is_drum(_pg):
            continue
        _spc = property_class_for_note(_pg, _nt)
        if not (getattr(_spc, 'scanner_switch', False) or getattr(_spc, 'scanner', None)):
            continue
        import scanner as _SCN
        # the selector's position: the channel's first CC94, else the voice's own
        _c94 = [_val for _t, _cc, _val in in_order(ccs.get(_c, [])) if _cc == _SCN.SWITCH_CC]
        _sset = _SCN.setting_of(_spc, _c94[0] if _c94 else None)
        if _sset:
            _dep, _cho = _sset
            _rws = []
            for _r, _cc in _SCN.rows(nblk, BLK, SR, _dep, _cho):      # a row per band
                _rws.append(len(BRrows)); BRrows.append(_r); BCrows.append(_cc)
            _SCAN_CH[_c] = (tuple(_rws), _dep, _cho)
    # THE CHANNEL FADER, MID-NOTE. A note took CC7 x CC11 (squared) once, at
    # its onset, so a swell or a fade written over a held note did nothing
    # here -- while live, a fader in someone's hand, moved the notes already
    # sounding (Ben, the Prophet's Song's sea: "needs to fade out"). Now a
    # channel whose CC7 or CC11 MOVES while one of its notes sounds (its
    # release with it, FADER_TAIL) carries the level as a row: its notes are
    # emitted at unity and every row they ride takes the level as BL -- the
    # channel's bend and breath rows, its notes' own MPE and per-note rows,
    # and for everything else a level-only row (emit_partial). A channel
    # that only sets its level between notes is untouched, folded in at
    # onset as it always was, so its render is the same to the bit.
    # Not an organ whose CC11 is its stop word and CC7 its swell: those
    # have their own rows (registration_blocks). Keyed as _MCH is: an MPE
    # member's note by its zone's manager.
    _LROW = {}
    _org = {}

    def _plain(_pg, _nt):
        if isinstance(_pg, DrumProgram):
            return True
        _k = (_pg, getattr(_pg, 'variation', 0), getattr(_pg, 'layer', None), _nt)
        if _k not in _org:
            _pc = property_class_for_note(_pg, _nt)
            _org[_k] = not (getattr(_pc, 'registerable', False)
                            and tuple(getattr(_pc, 'stop_word_ccs', (11, 43)))[0] == 11)
        return _org[_k]
    _spans = {}
    for (_c, _nt, _on, _of, _v, _cvv, _pg) in notes:
        if _plain(_pg, _nt):
            _spans.setdefault(_mpe_member.get((_c, _nt, _on), _c), []).append((_on, _of + FADER_TAIL))
    # ...BUT NOT A STAMPED CHANNEL. mt32mux carries several parts on one
    # channel by putting each part's CC7 (and CC11) a tick before EVERY note
    # it plays, for the note to snapshot at its onset -- so another part's
    # note still sounding sees the stamp as a fader move, and would be
    # rescaled by a level that is not its own. A channel where nearly every
    # note (STAMPED_SHARE) has a CC7 within STAMP_S before it is stamped,
    # and keeps the onset rule the stamps were written for. No ordinary
    # file sends a volume before every note.
    _ons = {}
    for (_c, _nt, _on, _of, _v, _cvv, _pg) in notes:
        _ons.setdefault(_mpe_member.get((_c, _nt, _on), _c), []).append(_on)
    for _c in list(_spans):
        _t7 = np.array(sorted(_t for _t, _cc, _val in ccs.get(_c, []) if _cc == 7))
        _o = np.array(sorted(_ons.get(_c, [])))
        if len(_t7) and len(_o):
            _k = np.searchsorted(_t7, _o + 1e-9, side='right') - 1
            _hit = (_k >= 0) & ((_o - _t7[np.maximum(_k, 0)]) <= STAMP_S)
            if _hit.mean() >= STAMPED_SHARE:
                del _spans[_c]
    for _c, _sp in _spans.items():
        _v7, _v11, _fev = T.GM_DEFAULT_VOLUME, T.GM_DEFAULT_EXPRESSION, []
        _lv = ((_v7 / 127.0) * (_v11 / 127.0)) ** 2
        # ...and the controller matrix's AMPLITUDE (ctrlmatrix), a gain moved
        # by the mod wheel, a CC or the pressure -- after the CC at its instant,
        # whose change it follows. A channel with none: the CCs, in their order
        _ag = 1.0
        _evs = [(_t, 0, _i, _cc, _val) for _i, (_t, _cc, _val) in enumerate(in_order(ccs.get(_c, [])))]
        _evs += [(_t, 1, _i, 'amp', _gv) for _i, (_t, _gv) in enumerate(_CMXEV['amp'].get(_c, ()))]
        for _t, _k, _i, _cc, _val in (sorted(_evs) if len(_evs) and _c in _CMXEV['amp'] else _evs):
            if _cc == 'amp':
                _ag = _val
            elif _cc == 7:
                _v7 = _val
            elif _cc == 11:
                _v11 = _val
            elif _cc == 121:
                _v11 = 127                      # reset: expression back up, volume kept
            else:
                continue
            _g = ((_v7 / 127.0) * (_v11 / 127.0)) ** 2
            if _ag != 1.0:
                _g = _g * _ag
            if _g != _lv and any(_a < _t < _b for _a, _b in _sp):
                _LROW[_c] = None
            _fev.append((_t, _g))
            _lv = _g
        if _c not in _LROW:
            continue
        _L = onepole_edges(_fev, nblk, ((T.GM_DEFAULT_VOLUME / 127.0) * (T.GM_DEFAULT_EXPRESSION / 127.0)) ** 2)
        _own = [brow_of.get(_c)] + list(bbrow_of.get(_c, ()))
        _own += [_r for (_ch, _nt, _on), (_r0, _r) in _MPE_AT.items() if _mpe_member.get((_ch, _nt, _on)) == _c]
        _own += [_x[2] for (_ch, _nt, _on), _x in _PN_AT.items() if _mpe_member.get((_ch, _nt, _on), _ch) == _c]
        _own += [_rw for (_ch, _nt, _on), (_rws, _e) in _SIREN_AT.items() if _ch == _c for _rw in _rws]
        if _c in _SCAN_CH:
            _own.extend(_SCAN_CH[_c][0])
        for _r in set(_own):
            if _r is not None and _r >= 0:
                _BLrows[_r] = (_BLrows[_r] * _L) if _r in _BLrows else _L.copy()
        _i = len(BRrows); BRrows.append(np.ones(nblk, np.float32)); BCrows.append(np.zeros(nblk))
        _BLrows[_i] = _L
        _LROW[_c] = _i
    # A NOTE RIDES ONE BEND ROW, so a note with a row of its own -- MIDI 2.0
    # per-note pitch, MPE, a meend, the channel's gesture or the player's
    # breath -- on an organ chest rides their PRODUCT: its own ratio and level
    # times its family's wind row's. The rank loop used to put it on the wind
    # row alone, and the note's own pitch was lost the day the shared wind
    # came on by default (live's Clip File test). (base row, wind row) -> row.
    wcombo = {}
    if wrow_of:
        _wch = {}
        for (_c, _k), _w in wrow_of.items():
            _wch.setdefault(_c, set()).add(_w)
        _bases = {}
        for _c, _r in brow_of.items():
            _bases.setdefault(_c, set()).add(_r)
        for _c, _rs in bbrow_of.items():
            _bases.setdefault(_c, set()).add(_rs[0])
        for (_c, _nt, _on), _x in _PN_AT.items():
            _bases.setdefault(_c, set()).add(_x[2])
        for (_c, _nt, _on), _x in _MPE_AT.items():
            _bases.setdefault(_c, set()).add(_x[1])
        for (_c, _nt, _on), _x in _MEEND_AT.items():
            _bases.setdefault(_c, set()).add(_x[1])
        for _c, _ws in _wch.items():
            for _b in _bases.get(_c, ()):
                if _b is None or _b < 0:
                    continue
                for _w in _ws:
                    _r = (BRrows[_b].astype(np.float64) * BRrows[_w].astype(np.float64)).astype(np.float32)
                    _cc = np.concatenate(([0.0], np.cumsum((_r.astype(np.float64) - 1.0) * BLK)))[:nblk]
                    _i = len(BRrows); BRrows.append(_r); BCrows.append(_cc)
                    if _b in _BLrows or _w in _BLrows:
                        _one = np.ones(nblk + 1, np.float32)
                        _BLrows[_i] = _BLrows.get(_b, _one) * _BLrows.get(_w, _one)
                    wcombo[(_b, _w)] = _i
    # THE MATRIX'S TREMOLO (ctrlmatrix: LFO1 AMPLITUDE DEPTH, moved by the mod
    # wheel, a CC or the pressure): the channel's sidebands (tremolo.expand)
    # at the peak depth, each riding a row of its own -- its parent's ratio
    # and level times depth(t) / peak, the faders' glide -- so a held note's
    # tremolo swells with the wheel. A row for each row its notes can ride:
    # the channel's bend, breath and fader rows, and none (-1).
    _CMX_TREM = {}
    for _c, _tv in _CMXEV['tva'].items():
        _pk = max(_v for _t, _v in _tv)
        if _pk <= 0.0:
            continue
        _cur = onepole_edges([(_t, _v / _pk) for _t, _v in _tv], nblk, 0.0)
        _map = {}
        _wpar = [_v for (_wc, _wk), _v in wrow_of.items() if _wc == _c]      # a pipe organ's wind rows
        for _par in set([brow_of.get(_c), _LROW.get(_c), -1] + list(bbrow_of.get(_c, ())) + _wpar):
            if _par is None:
                continue
            _r = (BRrows[_par] if _par >= 0 else np.ones(nblk, np.float32)).astype(np.float32)
            _cc = (BCrows[_par] if _par >= 0 else np.zeros(nblk))
            _i = len(BRrows); BRrows.append(_r); BCrows.append(_cc)
            _BLrows[_i] = ((_BLrows[_par] if _par in _BLrows else 1.0) * _cur).astype(np.float32)
            _map[_par] = _i
        _CMX_TREM[_c] = (_pk, _map)
    # AN ALIASING SWEEP (tonelib `alias_sweep`: (start Hz, end Hz, seconds,
    # sample rate, harmonics)): a sawtooth swept up through a sampler with no
    # filter -- each harmonic FOLDED about its Nyquist (|k f - m fs|), so each
    # moves on its own path, falling while the note rises once it is past the
    # fold. A row a harmonic, its ratio to where it sat at the onset (the
    # class's mode_ratios are those). (ch, note, on) -> its rows, by harmonic.
    _ALIAS_AT = {}
    for (_c, _nt, _on, _of, _v, _cvv, _pg) in notes:
        if is_drum(_pg):
            _dd = percussion_for_note(_nt, kit_for_program(int(_pg)))
            _apc = _dd[1] if _dd else None
        else:
            _apc = property_class_for_note(_pg, _nt)
        _asw = getattr(_apc, 'alias_sweep', None)
        if not _asw:
            continue
        _af0, _af1, _aT, _afs, _anh = _asw
        _ab0 = int(_on * SR) // BLK
        _atb = (np.arange(nblk) - _ab0 + 0.5) * BLK / float(SR)
        _af = _af0 * (_af1 / _af0) ** np.clip(_atb / _aT, 0.0, 1.0)
        _rws = []
        for _ak in range(1, int(_anh) + 1):
            _nom = T.alias_fold(_ak * _af0, _afs)
            if _nom < 20.0:
                _rws.append(-1)
                continue
            _fk = np.mod(_ak * _af, _afs)
            _fk = np.where(_fk > _afs / 2.0, _afs - _fk, _fk)
            _r = np.where(_atb > 0.0, _fk / _nom, 1.0).astype(np.float32)
            _cc = np.concatenate(([0.0], np.cumsum((_r.astype(np.float64) - 1.0) * BLK)))[:nblk]
            _rws.append(len(BRrows)); BRrows.append(_r); BCrows.append(_cc)
        _ALIAS_AT[(_c, _nt, _on)] = _rws
    BR = np.ascontiguousarray(np.array(BRrows if BRrows else [[1.0]], np.float32))
    BC = np.ascontiguousarray(np.array(BCrows if BCrows else [[0.0]], np.float64))
    BL = None
    if _BLrows:
        BL = np.ones((len(BRrows), nblk + 1), np.float32)
        for _i, _lv in _BLrows.items():
            BL[_i] = _lv
    # partial table
    # THE COLUMNS AS DOUBLES, not lists: a list holds a pointer and a float
    # object a partial (32 bytes), array('d') the 8-byte double itself, and
    # Valkyries' 16M partials ran a 7 GB machine out of memory. A double is
    # what the list's float WAS, so the table converts to the same bits (and an
    # int, a sample index or a row, fits one exactly).
    # STREAMED (sink given): each note's rows go to sink(A, i0, i1) the moment
    # they are final -- when the next note flushes its sound controllers --
    # and the columns can let go of rows behind them (streamrender.PrefixCol,
    # indexed by global row as these are). See streamrender.
    if sink is not None:
        import streamrender as _SR
        _dcol_ = lambda k: _SR.PrefixCol(_dcol(k).typecode)         # noqa: E731
    else:
        _dcol_ = _dcol
    _S0 = [None]             # the note being emitted: its first row (streamed only)
    cols = {k:_dcol_(k) for k in ("az","dr","om","p0","aL","aR","aM","mch","px","pz","nf","non","noff","fa","re","ch","logr","logrA","aft","sus","cv","cc","crl","sj","csc","cbw","tbav","tau","tcut","gb","gt","gc","vd","vr","vp","vdl","delL","delR","gr","cr","br","p0R","pl","fx","mk","rdl","fmw","fmp","fmpR","nfr")}
    A = cols  # alias
    _BR = [-1]               # per-note bend row, -1 = this note does not bend
    _TB = [0.0, 0.28, 1.8]   # per-note [tension_bend*attack_volume, settle_time, settle_cutoff]
    _GL = [0.0, 0.05, 0.0]   # per-note portamento [g = ftgt/fsrc - 1, tau, cutoff]
    _VB = [0.0, 5.5, 0.0]    # per-VOICE vibrato [depth fraction, rate Hz, phase rad]
    _VDL = [0.0]             # per-note vibrato delay, seconds (CC78); 0 = none
    _PJ = [1.0]              # per-note pitch-jitter frequency scale (1 + pitch_jitter), times a whole transposition
    _NYQ_OM = 0.98 * math.pi  # 0.49 SR: a transposed note's rows were placed under 0.45 SR before its scale
    _XPON = [False]           # this note is transposed whole: only then is the guard on (other
                              # voices emit rows above it, as they always have)
    _DL = [0.0, 0.0]         # per-note per-ear HRTF envelope delay in samples (ITD)
    _PL = [0]                # which player of a section this partial belongs to
    _FX = [-1]               # the Moog filter row of this note (moog.py), -1 = none
    _MK = [0]                # a Moog partial's oscillator * 4096 + harmonic, 0 = none
    _NOREFL = [False]        # emit no room images for this partial (noise: see below)
    _LATE = [False]     # rows of a late copy (bloom): dr 0.75 direct, 0.25 an image -- see sympathetic.expand
    _RING = []          # [(first, end)] of each note's ring rows: off the wheel (live reads them too)
    _GRAIN_ROWS = []    # [(first, end)] of each note's grains: live keeps their own onsets
    _NOTE_ROW0 = []     # (first row, a stroke?) of each note in turn: stroke_rows, below
    _RINGF = [False]    # emitting ring rows: dr 0.9 direct, 0.1 an image -- see sympathetic.expand
    # A ROOM IMAGE'S EXTRA PATH, in samples: how much later than its direct
    # sound it starts and stops. Already in its `non`/`noff` here; recorded on
    # its own because live re-times every onset at stamp (a section's scatter
    # is drawn afresh per press) and has to know which part of an offset is
    # scatter to redraw and which is the room's, to keep.
    _RD = [0.0]
    # 1 -> 2 FM: OSC 1's angular frequency and the phase its fundamental partial
    # carries (moog.fm_coeffs), set while an FM'd OSC 2 is emitted. Each partial
    # gets OSC 1's phase anchor for its OWN onset and ear delays -- an image's
    # for an image -- exactly as OSC 1's partial there is anchored.
    _FMW = [0.0]; _FMPH = [0.0]
    _MOOG_FT, _MOOG_KN, _MOOG_KROW = [], [], {}   # per-note rows, per-channel knobs
    # ...a knob row that MOVES (moog: KN, one entry a grid point): {row: [(grid,
    # knob row), ...]} -- a channel whose cutoff or resonance the file turns
    # while notes sound (a GS TVF NRPN sweep, CC74/71, the controller matrix's
    # cutoff), every Moog note on it reading the channel's knobs as they are
    _MOOG_KVAR = {}
    _KMOVES = {}

    def _kn_moves(_c):
        """True for a channel whose cutoff or resonance changes after it is
        first set: its Moog notes read a timeline (_MOOG_KVAR). A channel set
        once, or never, keeps its notes' constant rows."""
        if _c not in _KMOVES:
            _ts = {round(_et, 6) for _et, _q, _cc, _v in _SND_TL.get(_c, ()) if _cc in (71, 74)}
            _ts |= {round(_et, 6) for _et, _v in _CMXEV['cutoff'].get(_c, ())}
            _KMOVES[_c] = len(_ts) > 1
        return _KMOVES[_c]
    _MOOG_MPI, _MOOG_MPC, _MOOG_MPR = [], [], []   # per-note pitch rows (moog.pitch_rows)
    _MOOG_MKI, _MOOG_MPK, _MOOG_MPKN = [], [], [0]  # per-note shape rows (moog.shape_rows)
    _MF104 = []         # (first row, end row, settings): notes through the MF-104M (mf104.py)
    _GSDN = []          # (first row, end row, device, send): notes into the GS delay (gsdelay.py)
    _GSD_OPEN = [None]  # this note's (first row, send), closed where the next begins
    _PAR_OPEN = [None]  # a parallel type's note: (first row, part, its chain) -- copied to branch B where it closes
    _CC94 = {}          # channel -> [(t, value)] of CC94, the GS delay send, in order

    def _gsd_send(c, t):
        """The channel's DELAY SEND (CC94) in force at t, 0-1."""
        if c not in _CC94:
            _CC94[c] = [(et, v) for et, cc, v in in_order(ccs.get(c, [])) if cc == 94]
        v = 0
        for et, cv in _CC94[c]:
            if et > t + 1e-9:
                break
            v = cv
        return v / 127.0
    _CBW = [RAND_GRAN, 0.0]  # wash bandwidth: [fraction of partial f, absolute Hz]
    # Reflections cost about 7x the partials, since every one of them is
    # audible and nothing prunes. Worth it for a render you will listen to,
    # not for a batch. --no-reflect on the command line, or TUNING_REFLECT=0.
    REFLECT = (os.environ.get('TUNING_REFLECT', '1') not in ('0', 'off', '')
               and '--no-reflect' not in sys.argv)
    _MCH = [0]               # MIDI channel of the note being emitted (stem/object export)
    _LV = [-1]               # its channel's fader row, if the fader moves under it (THE CHANNEL FADER)
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
    # THE EARLY REFLECTIONS, REMEMBERED. reflection_terms (and hrtf_at at each
    # image) is a pure function of the partial's frequency, where its source
    # stands, and the values below -- the voice's directivity, the room, the
    # air -- and the same pitch from the same desk asks it the same question
    # every time the note sounds. Keyed by those VALUES, not by the voice
    # object: every note has an object of its own, so an object key never hits
    # (and holds them all alive), and an id() key hits a dead note's recycled
    # id -- which is how a first version of this got 0.2% of Mars's levels
    # wrong. Kept for this render only, where the room cannot change.
    _REFL = {}
    # How much power the sources actually put INTO the room, per octave, which
    # is what the diffuse tail is excited by. Accumulated on the direct partials
    # only: a reflection is that same power heard again, not more of it.
    ROOM_BANDS = (63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0)
    _QACC = [[0.0, 0.0] for _ in ROOM_BANDS]   # [sum a^2, sum a^2/Q] per band
    # PLAYED BACKWARDS (tonelib.ReverseCymbalProperties): (the note's onset,
    # its arrival), in samples, while such a note emits; None otherwise.
    _REV = [None]
    REV_FLOOR = math.log(1e5)    # a reversed decay starts 100 dB under its arrival

    def _reverse_partial(om, ampL, ampR, ampM, nomf, non, fa, ch, logr, logrA, aft, sus, cv, cc,
                         crl, sj, csc, gr, cr, ph0):
        """One partial of the forward note, emitted TIME-REVERSED: what a tape
        of it played backwards is. Each decay is a growth at its own rate, so
        the longest-lived modes rise first and the brief ones -- the bright
        upper modes, the stick's strike -- surge in at the end; a partial that
        started d after the forward onset ends d before the arrival. Each of
        the two decays (the kernel's logr and its aftersound, logrA) is its own
        row, begun where it is REV_FLOOR under its end (or at the note's
        onset, faded in), so no growth is ever more than 100 dB. The attack's
        chiff, a hump of wash just after the strike, becomes a swell of noise
        (a noise row, the wash's width) just before the arrival."""
        n0, arr = _REV[0]
        end = arr - (non - n0)
        if end <= n0:
            return
        _REV[0] = None                             # its own rows are forward rows
        try:
            _reverse_rows(n0, end, om, ampL, ampR, ampM, nomf, fa, ch, logr, logrA, aft, sus, cv, cc,
                          crl, sj, csc, gr, cr, ph0)
        finally:
            _REV[0] = (n0, arr)

    def _reverse_rows(n0, end, om, ampL, ampR, ampM, nomf, fa, ch, logr, logrA, aft, sus, cv, cc,
                      crl, sj, csc, gr, cr, ph0):
        _out = max(fa, 0.001 * SR)                 # the forward fade-in, now the cut-off
        _out = min(_out, 0.5 * (end - n0))
        # ...AND THE PHASE MIRRORED: cos(w t + ph0) backwards is cos(w t' - ph0),
        # so each row reaches -ph0 at its end, where the forward one began at
        # ph0. The modes that set out together at the strike arrive together:
        # turned through whatever phase their spans gave them, the crash's
        # arrival summed incoherently, 4-5 dB short of the strike it mirrors.
        def _ph(start):
            return -ph0 - om * _PJ[0] * (end - start)
        for w, lr in (((1.0 - sus) * (1.0 - aft), logr), ((1.0 - sus) * aft, logrA), (sus, 0.0)):
            if w <= 0.0:
                continue
            span = REV_FLOOR / lr * SR if lr > 0.0 else end - n0
            start = max(n0, end - span)
            g = w * math.exp(-lr * (end - start) / SR)
            fin = 0.01 * SR if start <= n0 else 0.001 * SR
            # the forward fade-in, reversed, is a fade-out ENDING at the arrival.
            # ITS WASH WITH IT: the chiff's sustained floor (sj x cv, the
            # partial's own jittered copy) rides the partial's level, so it
            # swells as the partial does -- a hat or a cymbal is mostly that
            # wash (sj x cv ~115 x the modes on the closed hat), and without it
            # a reversed hat was its quiet modes and a 2 ms click. The row's own
            # attack hump is made a sample wide and its release hump dropped:
            # the hump is the arrival's, below
            # ...its fade-out no longer than the row itself, so it ENDS at the
            # arrival: a slow forward fade-in (the jazz crash's, 0.36 s) on a
            # row begun 29 ms before it went on growing past it, ~e^144 -- NaN
            _o = min(_out, max(1.0, end - start))
            emit_partial(om, ampL * g, ampR * g, ampM * g, nomf, start, max(start + 1.0, end - _o),
                         fin, _o, 1.0, -lr, 0.0, 0.0, 0.0, cv, cc, 0.0, sj, csc, gr, cr, _ph(start))
        jp = cv * csc * 0.25                       # the hump's peak, r(1-r) at r = 1/2
        if jp > 0.0 and ch > 0.0:
            _cbw = (_CBW[0], _CBW[1])
            _CBW[0], _CBW[1] = -max(abs(_cbw[0]), 1e-3), 0.0
            _nr = _NOREFL[0]
            _NOREFL[0] = True
            start = max(n0, end - ch)
            pk = end - ch / 3.0                    # the forward hump peaks a third in
            g = jp * (1.0 - sus) * (1.0 - aft) * math.exp(-logr * (ch / 3.0) / SR)
            emit_partial(om, ampL * g, ampR * g, ampM * g, nomf, start, max(start + 1.0, pk),
                         max(1.0, pk - start), max(1.0, end - pk), ch, 0.0, 0.0, 0.0, 1.0, 0.0,
                         cc, crl, 0.0, csc, gr, cr, _ph(start))
            _CBW[0], _CBW[1] = _cbw
            _NOREFL[0] = _nr

    def emit_partial(om, ampL, ampR, ampM, nomf, non, noff, fa, re, ch, logr, logrA, aft, sus, cv, cc, crl, sj, csc, gr, cr, ph0=0.0,
                     _place=None):
        # _place is (delL, delR, px, pz) for an image source; None means the
        # direct sound, which also emits the images.
        if _REV[0] is not None and _place is None:
            _reverse_partial(om, ampL, ampR, ampM, nomf, non, fa, ch, logr, logrA, aft, sus, cv, cc,
                             crl, sj, csc, gr, cr, ph0)
            return
        om = om * _PJ[0]
        if _XPON[0] and om >= _NYQ_OM:
            return          # a transposition (_XP) carried it past Nyquist
        dl, dr, px, pz = _place if _place else (_DL[0], _DL[1], _PX[0], _PZ[0])
        _am0 = ampM
        if _place is None:
            _AZ[0] = math.atan2(px, max(props.radiation_distance, 1e-6))
            # FURTHER AWAY, THE SAME BALANCE: a channel's distance multiple
            # (_src_dist -- CC91, or the voice's own) moves the source out
            # along its own ray, so the reflections below follow it and the
            # direct path crosses the extra air -- its top end, a few dB at 8-16
            # kHz over ten metres. Its LEVEL stays as the mix wrote it: that is
            # the normalisation that makes the send a distance, not a fader
            # (roomtail sets the tail by the same multiple).
            _dm = _src_dist(_MCH[0], props)
            if _dm != 1.0:
                _r0 = math.sqrt(px * px + props.radiation_distance ** 2 + pz * pz)
                _ga = 10.0 ** (-props.air_absorption_db_per_m(nomf) * (_dm - 1.0) * _r0 / 20.0)
                # ...AND THE PART AS LOUD AS IT WAS. Further out the direct
                # weakens against its own images, so holding the direct alone
                # left a part sent to 127 1.5-3 dB louder (measured over an
                # octave: flute, piano, strings). The direct and its early
                # images are held to the energy they had at the voice's own
                # distance: the ratio between them moves, which is the cue
                if REFLECT and not _NOREFL[0]:
                    _ga *= _refl_norm(nomf, px, pz, _dm)
                ampL *= _ga; ampR *= _ga; ampM *= _ga
            # THE FILE'S GS EQ, on the parts that have it on (gs_eq_gain):
            # the partial at its frequency, its reflections with it
            if _GS_EQ and _MCH[0] not in _GS_EQ['off']:
                _ge = gs_eq_gain(nomf, _GS_EQ['eq'])
                ampL *= _ge; ampR *= _ge; ampM *= _ge
            # THE INSERTION EFFECT's compressor (gsefx), before its OD: its
            # sustain the decay slowed (logr, logrA), its makeup a gain. Its
            # EQ is after the OD and the amp: the speaker pass (_EFXEQ_CH)
            _ex = _EFXN[0]
            if _ex is not None:
                if _ex['comp'] is not None:
                    logr = logr * _ex['comp'][0]
                    logrA = logrA * _ex['comp'][0]
                    ampL *= _ex['comp'][1]; ampR *= _ex['comp'][1]; ampM *= _ex['comp'][1]
                    # ...and its attack: the onset risen over it (gsefx.CMP_ATTACK_MS)
                    if _ex['comp'][2] > 0.0:
                        fa = max(fa, _ex['comp'][2] * SR)
            # A HAMMER-ON / PULL-OFF (hammer_legato): no pick -- the string
            # rings on from the note that was picked, so each partial starts
            # where its own decay (the compressor's, if any) has got to since
            # that pick (the kernel's two-stage law: logr, then the
            # aftersound's logrA), less what the fretting finger costs
            # (HAMMER_LOSS_DB)
            if _HAM[0] > 0.0:
                _hg = (((1.0 - aft) * math.exp(-logr * _HAM[0]) + aft * math.exp(-logrA * _HAM[0]))
                       * HAMMER_GAIN)
                ampL *= _hg; ampR *= _hg; ampM *= _hg
        # THE EAR DELAY MOVES THE CARRIER, NOT JUST THE ENVELOPE. A path length
        # delays the whole signal; delaying only the envelope leaves both ears
        # with identical carrier phase, so a held note has no interaural time
        # difference at all -- and below ~500 Hz, where the head casts no shadow
        # (0.01 dB at C2), ITD is the ONLY cue there is. Measured on a C2 string
        # chord, sustain-only peak IACC: 0.9978 as a point source, 0.9926 with
        # the players seated but the carrier shared, 0.8382 with both. The seats
        # supply the positions; this is what turns a position into an arrival.
        # p0 = -om*(non + d) + ph0, i.e. exactly "this partial, delayed by d".
        #
        # THE SAME PLATE STRUCK AGAIN (fold_restrike: a gong). The new strike
        # does not erase the old ring, it adds to it -- and both are the same
        # modes, at the same frequencies, each decaying at its own one rate
        # (no aftersound: a single exponential). So from the re-strike on the
        # old mode IS its value then, decaying on the new note's clock, and the
        # two sum as phasors into one row: exact, and a roll costs one strike's
        # rows however long it runs. The old strike's direct rows (and its
        # bloom's, once risen) end at the re-strike, fading over the new
        # attack; the new strike's direct rows take them in. Reflections are
        # made from the direct row below, so they fold with it.
        if _place is None and _FOLDIN[0] and not _LATE[0] and aft == 0.0 and sus == 0.0:
            _old = _FOLDIN[0].pop(round(nomf, 3), None)
            if _old:
                _pl, _pr = -om * (non + dl) + ph0, -om * (non + dr) + ph0
                _zl, _zr, _zm = (ampL * cmath.exp(1j * _pl), ampR * cmath.exp(1j * _pr),
                                 ampM * cmath.exp(1j * _pl))
                for _oL, _oR, _oM, _q0, _q0R, _n1, _lr in _old:
                    _g = math.exp(-_lr * (non - _n1) / SR)
                    _zl += _oL * _g * cmath.exp(1j * _q0)
                    _zr += _oR * _g * cmath.exp(1j * _q0R)
                    _zm += _oM * _g * cmath.exp(1j * _q0)
                ampL, ampR, ampM = abs(_zl), abs(_zr), abs(_zm)
                ph0 = cmath.phase(_zl) + om * (non + dl)
        # (taking in the strike before FIRST, then leaving the sum to the next:
        # in a roll each strike carries all the ones before it)
        if _place is None and _FOLD[0] is not None:
            _n2, _xf, _st = _FOLD[0]
            if aft == 0.0 and sus == 0.0 and non + fa <= _n2 < noff:
                _st.setdefault(round(nomf, 3), []).append(
                    (ampL, ampR, ampM, -om * (non + dl) + ph0, -om * (non + dr) + ph0, non, logr))
                noff = _n2
                re = _xf
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
        # ...and a LATE COPY's (the bloom) 0.75 and 0.25: still direct and an
        # image either side of 0.5, as every reader tests, but marked, so the
        # sympathetic pass does not take its late arrivals for new strikes
        A["dr"].append((0.75 if _LATE[0] else 0.9 if _RINGF[0] else 1.0) if _place is None
                       else (0.25 if _LATE[0] else 0.1 if _RINGF[0] else 0.0))
        A["nf"].append(nomf); A["non"].append(non); A["noff"].append(noff); A["fa"].append(fa); A["re"].append(re); A["ch"].append(ch)
        A["logr"].append(logr); A["logrA"].append(logrA); A["aft"].append(aft); A["sus"].append(sus)
        A["cv"].append(cv); A["cc"].append(cc); A["crl"].append(crl); A["sj"].append(sj); A["csc"].append(csc)
        # index is t*f*gran, so gran IS the fractional width; an absolute
        # width in Hz is that same number divided by where the partial sits.
        A["cbw"].append(_CBW[1]/max(1e-6,nomf) if _CBW[1] > 0.0 else _CBW[0])
        A["tbav"].append(_TB[0]); A["tau"].append(_TB[1]); A["tcut"].append(_TB[2])
        # THE GLIDE IS PER NOTE, NOT PER PARTIAL, but it is stamped per partial
        # because that is where the kernel reads it -- and because _TB beside it
        # is NOT per note: mode lock overrides it per partial, which is exactly
        # why portamento could not borrow those three slots and has its own.
        A["gb"].append(_GL[0]); A["gt"].append(_GL[1]); A["gc"].append(_GL[2])
        # CC77 moves the depth -- adding up to 30 cents where a voice has none,
        # taking a voice's own toward zero downward -- and CC76 the rate.
        _vd0 = _VB[0]
        if _SV[0] > 0.0:
            _vd0 = _vd0 + _SV[0] * (2.0 ** (T.SOUND_VIB_DEPTH_CENTS / 1200.0) - 1.0)
        elif _SV[0] < 0.0:
            _vd0 = _vd0 * (1.0 + _SV[0])
        A["vd"].append(_vd0); A["vr"].append(_VB[1] * _SV[1]); A["vp"].append(_VB[2])
        A["vdl"].append(_VDL[0])
        A["delL"].append(dl); A["delR"].append(dr)
        A["gr"].append(gr); A["cr"].append(cr); A["br"].append(_BR[0] if (_BR[0] >= 0 or _LV[0] < 0) else _LV[0]); A["pl"].append(_PL[0])
        A["fx"].append(_FX[0]); A["mk"].append(_MK[0]); A["rdl"].append(_RD[0])
        A["fmw"].append(_FMW[0])
        # the onset's fraction of a sample, which the table's whole-sample
        # `non` drops and the phase anchor above keeps: live needs it to move a
        # partial's frequency without moving its phase (a room image's onset
        # is hardly ever a whole sample)
        A["nfr"].append(non - math.floor(non))
        A["fmp"].append(-_FMW[0] * (non + dl) + _FMPH[0] if _FMW[0] else 0.0)
        A["fmpR"].append(-_FMW[0] * (non + dr) + _FMPH[0] if _FMW[0] else 0.0)
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
            e = _am0 * _am0             # the power it feeds the room, before the air
            _QACC[bi][0] += e
            _QACC[bi][1] += e / max(q, 1e-6)
        if _place is not None or not REFLECT or _NOREFL[0]:
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
        _dm = _src_dist(_MCH[0], props)
        _rk = (nomf, px, pz, _radius[0], _dm) + _refl_state(props)
        _terms = _REFL.get(_rk) if PREP_MEMO else None
        PREP_MEMO_STATS[0] += 1
        if _terms is None:
            PREP_MEMO_STATS[1] += 1
            # BOUNDED: Valkyries (16M partials) ran a 7 GB machine into swap
            # with the memo unbounded, and prepared slower than without it.
            # Emptying it changes no result, only what is asked again.
            if len(_REFL) >= PREP_MEMO_MAX:
                _REFL.clear()
                PREP_MEMO_STATS[2] += 1
            # THE SOURCE MOVED OUT ALONG ITS RAY by the distance multiple: the
            # same direction (so the same width and pan), the images from where
            # it now stands -- gains and delays still relative to its direct sound
            #
            # AND EACH IMAGE'S EAR DELAYS ON THE DIRECT SOUND'S BASELINE. The
            # direct sound's come from the head model's stage image at
            # listener_distance; an image's hrtf_at counts its whole path from
            # the origin, and rdelay already carries the path it adds -- so the
            # image arrived (path - stage)/c late: 9.1 ms after the direct on a
            # piano's floor bounce whose geometry says 2.1. Each image keeps its
            # interaural difference and loses the path counted twice.
            _sx, _sy, _sz = px * _dm, props.radiation_distance * _dm, pz * _dm
            _stage = math.sqrt(px * px + props.listener_distance ** 2 + pz * pz)
            _terms = []
            for rg, rdelay, image in props.reflection_terms(nomf, _sx, _sy, _sz, _radius[0]):
                _rli, _rri, _rld, _rrd = props.hrtf_at(image[0], image[2], image[1])
                _sh = (math.sqrt(image[0] ** 2 + image[1] ** 2 + image[2] ** 2) - _stage) / props.sound_speed
                _terms.append((rg, rdelay, image, (_rli, _rri, _rld - _sh, _rrd - _sh)))
            if PREP_MEMO:
                _REFL[_rk] = _terms
        for rg, rdelay, image, (rli, rri, rld, rrd) in _terms:
            ix, iy, iz = image
            _AZ[0] = math.atan2(ix, max(iy, 1e-6))
            gm = ampM * rg
            # as the table will store it: onsets are kept as whole samples
            _RD[0] = float(int(non + rdelay*SR) - int(non))
            emit_partial(om/_PJ[0], gm*props.hrtf_gain(nomf, rli),
                         gm*props.hrtf_gain(nomf, rri), gm, nomf,
                         non + rdelay*SR, noff + rdelay*SR, fa, re, ch,
                         logr, logrA, aft, sus, cv, cc, crl, sj, csc, gr, cr, ph0,
                         _place=(rld*SR, rrd*SR, ix, iz))
        _RD[0] = 0.0
        _AZ[0] = _direct_az
    # SCRAPED instruments expand into their individual ridge impacts before
    # anything else looks at the note list, so the choke and the envelopes all
    # see the real strokes.
    expanded = []
    inner_ridge = set()          # ridges after the first, which must not choke each other
    stroke_pitch = {}            # (note, t) -> frequency scale, for swept instruments
    stroke_tilt = {}             # (note, t) -> a throat's tilt dB, for a voice's pulses
    stroke_mouth = {}            # (note, t) -> a throat's formant scale: the mouth's opening
    stroke_morph = {}            # (note, t) -> a throat's vowel moving: toward its DRUM_MODES_B
    _sfx_strokes_of = {}         # (program, note) -> (kit, key) whose strokes a melodic SFX plays
    _stroked = set()             # (ch, note, t) of every stroke: live keeps their own onsets
    for ev in notes:
        ch, note, on, off, vel, rest, pg = ev
        # A KEY THAT ALSO STRIKES ANOTHER'S SOUND (percussion_map.KIT_LAYER):
        # the metronome bell's tick is the click key's, at the bell's velocity
        if is_drum(pg):
            for _ln in key_layers(note, kit_for_program(int(pg))):
                expanded.append((ch, _ln, on, off, vel, rest, pg))
        # A LAYERED VARIATION (patch_map.LAYERED: GS's Orchestra): one event a
        # layer, each its own program and transposition, before anything else
        # sees the note
        _lys = None if is_drum(pg) else layers_of(pg)
        if _lys:
            # ...each within its velocity range (a "Velo" variation switches
            # voice with how hard the key is struck)
            for _lp, _st, _vlo, _vhi in _lys:
                if 0 <= note + _st <= 127 and _vlo <= vel <= _vhi:
                    expanded.append((ch, note + _st, on, off, vel, rest, _lp))
            continue
        strokes = rasp_strokes(note, on, off, kit=kit_for_program(int(pg))) if is_drum(pg) else None
        # ...AND A KIT KEY PLAYED FROM THE KEYBOARD (patch_map.melodic_sfx: a GS
        # SFX variation) keeps its strokes: the dog's bark, the gallop's hooves,
        # the machine gun's train, the laugh's syllables, the bubbles' run --
        # its class names the key whose table they are
        if strokes is None and not is_drum(pg):
            # keyed by the variation and layer as well: a VariationProgram is
            # equal to its plain program, so 126.1's laugh and 126.0's applause
            # shared one entry, whichever came first
            _skk = (pg, getattr(pg, 'variation', 0), getattr(pg, 'layer', None), note)
            _sk = _sfx_strokes_of.get(_skk, 0)
            if _sk == 0:
                _sk = _sfx_strokes_of[_skk] = getattr(
                    property_class_for_note(pg, note), 'sfx_strokes_of', None)
            if _sk:
                # ...the note's own key in that kit where it names none (the
                # Morse keyboard: every key its character)
                strokes = rasp_strokes(note if _sk[1] is None else _sk[1], on, off, kit=_sk[0])
        if strokes is None:
            expanded.append(ev); continue
        for k, st in enumerate(strokes):
            t0, t1, lvl = st[0], st[1], st[2]
            # A swept instrument gives each stroke its own PITCH -- a bell tree's
            # rod crosses graduated bars. Carried alongside the note list the way
            # inner_ridge is, so the event tuple keeps its shape.
            if len(st) > 3 and st[3] != 1.0:
                stroke_pitch[(note, t0)] = st[3]
            if len(st) > 4:
                stroke_tilt[(note, t0)] = st[4]
            if len(st) > 5:
                stroke_mouth[(note, t0)] = st[5]
            if len(st) > 6:
                stroke_morph[(note, t0)] = st[6]
            expanded.append((ch, note, t0, t1, max(1, int(vel * lvl)), rest, pg))
            _stroked.add((ch, note, t0))
            if k: inner_ridge.add((note, t0))
    notes = expanded

    # EXCLUSIVE CLASSES: a closed hi-hat stroke damps a ringing open one. Applied
    # here, on the note list, because it is a fact about the instrument rather
    # than about the envelope -- the open hat simply stops.
    #
    # PER CHANNEL: a hi-hat is one object in ONE kit. Keyed on the note alone,
    # a second drum channel (GM 2's CC0 = 120) would close the first one's hat.
    drum_ons = {}
    kit_on = {}                 # each drum note's set: its exclusive classes are the set's
    for ch, note, on, off, vel, _, _pg in notes:
        if is_drum(_pg) and choke_group(note, kit_for_program(int(_pg))) is not None:
            kit_on[(ch, note)] = kit_for_program(int(_pg))
            # A ridge WITHIN a scrape is not a new stroke: the gourd goes on
            # ringing as the stick moves to the next ridge, so only the start of
            # a scrape damps what came before it.
            if (note, on) in inner_ridge: continue
            drum_ons.setdefault((ch, note), []).append(on)
    choke_at = {}
    for (ch, note), ons in drum_ons.items():
        grp = choke_group(note, kit_on.get((ch, note), 0))
        later = sorted(t for (c2, n2), ts in drum_ons.items()
                       if c2 == ch and n2 in grp for t in ts)
        choke_at[(ch, note)] = later

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
    # THE DAMPER PEDAL. CC64 >= 64 lifts the dampers off every string, so a key
    # released while it is down goes on ringing until the pedal comes up. That
    # is a note-LENGTH fact, which is why it is resolved here rather than in
    # parse(): _next_same below and _PHRASE_CH further down are both computed
    # from the file's own note-offs, and they mean different things -- a phrase
    # is when a piper lets the bag down, not when a pianist lifts a foot.
    #
    # ccs already carries every (t, control, value), so this costs no parsing.
    _PED_CH = {}          # channel -> [(down_sec, up_sec)], sorted and disjoint
    for _c, _evs in ccs.items():
        _segs = []; _dn = None
        for _t, _cc, _v in in_order(_evs):
            if _cc != 64:
                continue
            # 64 is the switch point GM specifies, and half-pedalling is real:
            # ondine.mid writes 0/24/40/56/72/88/104/127. Anything under 64 is
            # the damper on the string.
            if _v >= 64 and _dn is None:
                _dn = _t
            elif _v < 64 and _dn is not None:
                _segs.append((_dn, _t)); _dn = None
        if _dn is not None:
            _segs.append((_dn, total))      # held down to the end of the file
        if _segs:
            _PED_CH[_c] = _segs

    # ALL SOUND OFF stops a channel dead, pedal or no pedal -- what a panic
    # button sends. Collected the same way as the damper, and applied after it
    # in the note loop so it overrides a held pedal.
    _SOFF_CH = {}
    for _c, _evs in ccs.items():
        # 126 and 127 too: Roland's MONO and POLY are "the same processing ...
        # as when All Sounds Off and All Notes Off is received".
        _ts = sorted(_t for _t, _cc, _v in _evs if _cc in (120, 126, 127))
        if _ts:
            _SOFF_CH[_c] = _ts

    # SOSTENUTO holds only the keys already down when the pedal went down, and
    # lets everything played after it damp normally. That asymmetry is the
    # whole instrument and nothing else here expresses it: _next_same answers
    # "when is this key struck again", _PHRASE_CH answers "is the channel
    # active", and neither answers "what was sounding at this instant".
    #
    # Keyed on the note INSTANCE, (channel, note, onset), because being caught
    # by the pedal is a fact about one press of one key -- and read from the
    # RAW note-off, before the damper below can extend it.
    _SOST_HELD = {}
    for _c, _evs in ccs.items():
        _segs = []; _dn = None
        for _t, _cc, _v in in_order(_evs):
            if _cc != 66:
                continue
            if _v >= 64 and _dn is None:
                _dn = _t
            elif _v < 64 and _dn is not None:
                _segs.append((_dn, _t)); _dn = None
        if _dn is not None:
            _segs.append((_dn, total))
        for _d0, _u0 in _segs:
            for _e in notes:
                if _e[0] == _c and _e[2] <= _d0 < _e[3]:
                    _SOST_HELD[(_e[0], _e[1], _e[2])] = max(
                        _u0, _SOST_HELD.get((_e[0], _e[1], _e[2]), 0.0))

    # CC67, the soft pedal: same switch, same half-pedal collapse.
    _SOFT_CH = {}
    for _c, _evs in ccs.items():
        _segs = []; _dn = None
        for _t, _cc, _v in in_order(_evs):
            if _cc != 67:
                continue
            if _v >= 64 and _dn is None:
                _dn = _t
            elif _v < 64 and _dn is not None:
                _segs.append((_dn, _t)); _dn = None
        if _dn is not None:
            _segs.append((_dn, total))
        if _segs:
            _SOFT_CH[_c] = _segs

    def _soft_at(_c, _t):
        """Was the una corda shift in at this note's ONSET?

        At the onset and not across the note, because the shift decides which
        strings the HAMMER reaches. Once a note is struck, moving the pedal
        cannot un-strike a string -- which is why this is a build-time fact
        and not a gain.
        """
        for _d0, _u0 in _SOFT_CH.get(_c, ()):
            if _d0 <= _t < _u0:
                return True
        return False

    # ------------------------------------------------- PORTAMENTO (CC5/65/84)
    #
    # THREE CONTROLLERS THAT ARE NOT THREE SETTINGS OF ONE THING. CC65 is a
    # switch, CC5 is a speed, and CC84 is neither: its data byte is a source
    # NOTE NUMBER, it fires once, and it works with the switch off. Roland's
    # VE-GS Pro MIDI Implementation is the primary source for all three -- the
    # SC-55 manual is a scan with no text layer (see sources.md) and this one
    # is the same GS control set with the text intact.
    #
    # CC5 IS A RATE, NOT A TIME, and that is Roland's own word: "This adjusts
    # the rate of pitch change when Portamento is ON or when using the
    # Portamento Control. A value of 0 results in the fastest change." So a
    # wide interval takes proportionally longer than a narrow one, which is
    # also what a hand does. What Roland does NOT publish is the curve from
    # the 0-127 value to an actual speed; that is chosen here and written down
    # in midi.md, the same position tension_settle_time is in.
    _PORTA_ON = {}      # channel -> [(down_sec, up_sec)], the CC65 segments
    for _c, _evs in ccs.items():
        _segs = []; _dn = None
        for _t, _cc, _v in in_order(_evs):
            if _cc != 65:
                continue
            # 64 again, the same switch point the three pedals collapse at.
            if _v >= 64 and _dn is None:
                _dn = _t
            elif _v < 64 and _dn is not None:
                _segs.append((_dn, _t)); _dn = None
        if _dn is not None:
            _segs.append((_dn, total))
        if _segs:
            _PORTA_ON[_c] = _segs

    _PORTA_T = {}       # channel -> sorted [(t, CC5 value)]
    _PORTA_CTL = {}     # channel -> sorted [(t, source note number)]
    for _c, _evs in ccs.items():
        _t5 = [(_t, _v) for _t, _cc, _v in in_order(_evs) if _cc == 5]
        if _t5:
            _PORTA_T[_c] = _t5
        _t84 = [(_t, _v) for _t, _cc, _v in in_order(_evs) if _cc == 84]
        if _t84:
            _PORTA_CTL[_c] = _t84

    def _porta_on_at(_c, _t):
        """Was CC65 up at this instant? Roland: 0-63 OFF, 64-127 ON."""
        for _d0, _u0 in _PORTA_ON.get(_c, ()):
            if _d0 <= _t < _u0:
                return True
        return False

    def _porta_cc5_at(_c, _t):
        """The CC5 in force at _t. Roland's initial value is 0 -- fastest."""
        _ev = _PORTA_T.get(_c)
        if not _ev:
            return 0
        _i = _bisect.bisect_right(_ev, (_t, 128)) - 1
        return _ev[_i][1] if _i >= 0 else 0

    # WHERE EACH NOTE GLIDES FROM, decided once for the whole file because
    # offline it can be. Keyed on the note INSTANCE, (channel, note, onset),
    # for the same reason sostenuto is: being glided into is a fact about one
    # press of one key.
    #
    # CC84 WINS OVER CC65 AND IS CONSUMED. Roland's Example 2 sends it with
    # nothing sounding at all and still glides, so it is not "reuse the voice
    # that is playing" -- it is "the next note starts from here", and it fires
    # once. The most recent CC84 before a note-on applies to that note-on and
    # to no other.
    _GLIDE_SRC = {}
    _prev_on = {}       # channel -> (onset, pitch) of the last note started
    _ctl_used = {}      # channel -> index of the last CC84 already spent
    for _e in sorted(notes, key=lambda e: (e[2], e[0], e[1])):
        _c, _n, _on = _e[0], _e[1], _e[2]
        _src = None
        _ctl = _PORTA_CTL.get(_c)
        if _ctl:
            _i = _bisect.bisect_right(_ctl, (_on, 128)) - 1
            if _i >= 0 and _i != _ctl_used.get(_c, -1):
                _pv = _prev_on.get(_c)
                # ...only if it arrived AFTER the previous note-on, or it is a
                # message about a note that has already been and gone.
                if _pv is None or _ctl[_i][0] >= _pv[0]:
                    _ctl_used[_c] = _i
                    if _ctl[_i][1] != CC84_CANCEL:
                        _src = _ctl[_i][1]
        if _src is None and _porta_on_at(_c, _on):
            _pv = _prev_on.get(_c)
            # A STRICTLY EARLIER ONSET, so a chord does not glide from itself.
            # Which note of a chord a glide starts from is undefined in poly
            # mode -- Roland does not say, and CC84 exists because it does not.
            # The last one to start is the convention, and it is a convention.
            if _pv is not None and _pv[0] < _on:
                _src = _pv[1]
        if _src is not None and _src != _n:
            _GLIDE_SRC[(_c, _n, _on)] = _src
        _pv = _prev_on.get(_c)
        if _pv is None or _on >= _pv[0]:
            _prev_on[_c] = (_on, _n)

    # ---------------------------------- A VALVED GLISS WALKS THE HARMONICS
    #
    # A trumpet does not slide. Ben, who plays these: brass players gliss by
    # moving "cleanly from one fingering to another, and blow through the
    # harmonics", or by half-valving to break the alignment and smear between
    # them. So the reachable pitches are a LATTICE -- a partial over whatever
    # length the valves have added -- and a gliss is a RUN through it, not a
    # sweep across it. sources.md carries the physical account.
    #
    # THE RENDERER THEREFORE EMITS REAL NOTES, which is not a workaround: the
    # model says a run of pitches is what is happening, so a run of pitches is
    # what gets built. Each step goes through the same note loop as everything
    # else, which means each one picks up the FINGERED pitch for free --
    # brass_fingering puts every semitone a few cents off equal temperament,
    # differently, and that wobble is a good part of what makes the gesture
    # recognisable rather than merely continuous.
    #
    # AND THE RUN IS EVEN, not exponential. The reciprocal settle the other
    # mechanisms use is a hand DECELERATING into a target, which is what a
    # slide or a finger does; ripping through seven fingerings is a sequence of
    # discrete actions at a steady rate, and an exponential would also never
    # reach the last step.
    _gliss_clean = 0    # glisses too short to play, reported below
    _GLISS = {}         # (ch, note, on) -> (level scale, smear 0..1)
    _GLISS_DROP = set() # the notes the run replaces
    _GLISS_STEPS = []
    for _e in notes:
        _k3 = (_e[0], _e[1], _e[2])
        _gs = _GLIDE_SRC.get(_k3)
        if _gs is None:
            continue
        _pcv = property_class_for_note(_e[6], _e[1])
        if getattr(_pcv, 'glide_mechanism', None) != 'valve':
            continue
        _step = 1 if _e[1] > _gs else -1
        _path = list(range(_gs, _e[1], _step))       # src .. one short of target
        if len(_path) < 2 or _e[3] - _e[2] <= 0.0:
            continue                                 # a tone or less: the lip has it
        # One journey time, from the same speed law every other mechanism uses,
        # so CC5 means one thing across the bank -- and it KEEPS meaning it
        # unless the note physically cannot hold the run. The cap used to be
        # half the note, which squeezed a slow gliss on any note shorter than
        # twice its run, so CC5 meant different speeds at different note
        # lengths. Now the run keeps CC5's time and gives way only to leave the
        # arrival a real hold: max(60 ms, 20%) of the note, the least that
        # still sounds like landing somewhere.
        _cc5 = _porta_cc5_at(_e[0], _e[2])
        _Fe = _F(_e[0], _e[2])
        _T = T.glide_tau(_cc5, _Fe[_e[1]], _Fe[_gs], 'slide') * T.PORTA_SETTLE_TAUS
        _dur = _e[3] - _e[2]
        _T = min(_T, _dur - max(GLISS_ARRIVAL_S, GLISS_ARRIVAL_FRAC * _dur))
        _dt = _T / float(len(_path)) if _T > 0.0 else 0.0
        if _dt < 0.012:
            # Faster than a valve moves: played clean. COUNTED, which it was
            # not -- a gliss that disappeared left nothing to say it had.
            _gliss_clean += 1
            continue
        # SMEAR RIDES ON THE SAME KNOB, which is Ben's suggestion: "maybe the
        # speed controller can control how straight or slurred the glissando is
        # across the harmonics". A quick gliss is a RIP and the steps are the
        # sound of it; a slow one is held, and a player holding a staircase
        # half-valves instead. So the smear opens with CC5, and with it the
        # level comes DOWN -- half-valving breaks the harmonic alignment and
        # loses support, and that dip is the audible tell. Without it a smear
        # is just a portamento with extra steps.
        _sm = min(1.0, max(0.0, _cc5 / 127.0))
        for _i, _p in enumerate(_path):
            _t0 = _e[2] + _i * _dt
            # Quietest in the middle, where the alignment is worst, and back up
            # at both ends where a real fingering is being held.
            _mid = 1.0 - abs((_i + 0.5) / len(_path) * 2.0 - 1.0)
            _lv = 1.0 - 0.45 * _sm * _mid
            _GLISS[(_e[0], _p, _t0)] = (_lv, _sm,
                                        _path[_i - 1] if _i else None, _dt)
            _GLISS_STEPS.append(
                (_e[0], _p, _t0, _t0 + _dt * 1.35, _e[4], _e[5], _e[6]))
        # The note proper begins where the run arrives. Its own onset is where
        # the gliss STARTED, which is what the file asked for: a rip into a
        # note is part of the note, not something played before it.
        _GLISS[(_e[0], _e[1], _e[2] + _T)] = (1.0, _sm, _path[-1], _dt)
        _GLISS_STEPS.append(
            (_e[0], _e[1], _e[2] + _T, _e[3], _e[4], _e[5], _e[6]))
        _GLIDE_SRC.pop(_k3, None)       # the lattice replaces the smooth glide
        _GLISS_DROP.add(_k3)
    # A FALL IS A GLISS DOWN (tonelib fall_cents: GS 61.16 "Brass Fall"), so it
    # walks the lattice as one does -- not a smooth sweep, which a valved
    # instrument cannot make past the lip's tone (Ben). The note holds
    # fall_at_s, then runs down a semitone a step over fall_s, each step a real
    # note on its fingered pitch, the level fading fall_fade_db across the run,
    # half-valved (smear fall_smear) as a fall usually is; the run ends it. A
    # key let go before the fall begins releases as any note does.
    for _e in list(notes):
        _k3 = (_e[0], _e[1], _e[2])
        if _k3 in _GLISS_DROP or is_drum(_e[6]):
            continue
        _pcf = property_class_for_note(_e[6], _e[1])
        _fc = getattr(_pcf, 'fall_cents', 0.0) or 0.0
        if not _fc:
            continue
        _tf = _e[2] + float(_pcf.fall_at_s)
        if _e[3] <= _tf:
            continue
        _ns = max(2, int(round(_fc / 100.0)))
        _dt = float(_pcf.fall_s) / _ns
        _sm = float(getattr(_pcf, 'fall_smear', 0.6))
        _GLISS_DROP.add(_k3)
        _GLISS_STEPS.append((_e[0], _e[1], _e[2], _tf, _e[4], _e[5], _e[6]))
        for _i in range(_ns):
            _p = _e[1] - 1 - _i
            if _p < 0:
                break
            _t0 = _tf + _i * _dt
            _GLISS[(_e[0], _p, _t0)] = (10.0 ** (-float(_pcf.fall_fade_db) * (_i + 1) / _ns / 20.0), _sm,
                                        _e[1] - _i, _dt)
            _GLISS_STEPS.append((_e[0], _p, _t0, _t0 + _dt * 1.35, _e[4], _e[5], _e[6]))
    if _gliss_clean:
        print("  %d valved glissandi were too short to run and played clean "
              "(a step would have been under 12 ms)" % _gliss_clean)
    if _GLISS_STEPS:
        notes = [_n for _n in notes
                 if (_n[0], _n[1], _n[2]) not in _GLISS_DROP] + _GLISS_STEPS

    def _sound_off(_c, _t):
        """The first All Sound Off on this channel strictly AFTER _t.

        Strictly, not "at or after". A sound-off on the same tick as a note-on
        is in the file's header nearly every time it happens -- CC126 and
        CC127 carry one, and they are set before the first note -- and "at or
        after" let it kill the note it preceded, four milliseconds in. It was
        the same for a bare CC120; nobody sends one of those in a header, so it
        never showed until mono mode did.
        """
        _ts = _SOFF_CH.get(_c)
        if not _ts:
            return None
        _i = _bisect.bisect_right(_ts, _t)
        return _ts[_i] if _i < len(_ts) else None

    def _damper_falls(_c, _t):
        """When the damper actually lands for a key released at _t."""
        _segs = _PED_CH.get(_c)
        if not _segs:
            return _t
        _i = _bisect.bisect_right(_segs, (_t, 1e18)) - 1
        if _i >= 0 and _segs[_i][0] <= _t < _segs[_i][1]:
            return _segs[_i][1]
        return _t

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
    _FILTER_CH = {}     # channel -> its moving filter (efxfilter.Channel)
    _SYM_CH = {}
    # THE FREE-STRING REGISTER: channel -> its class's strike list and setup,
    # and the strike whose rows are being emitted (closed at the next note)
    _REG_CH = {}
    _REG_OPEN = [None]
    _AMP_CH = {}
    _AMP_REF = {}
    _AMP_LV0 = {}       # the EFX level in a part's reference when it was taken (1 if none)
    _AMP_IMB = {}
    _CAB_CH = {}
    _EFXEQ_CH = {}      # a part's insertion-effect EQ, after its valve: {ch: eq}
    _TREM_CH = {}
    # ...the controller matrix's (above): a GM vibrato's rate, its rows' map
    for _c, (_pk, _map) in _CMX_TREM.items():
        # ...at the LFO1 rate in force where its depth peaks (a sideband's
        # offset is fixed for the note: a rate that moved mid-note would move
        # it, which nothing here does)
        _tpk = max(_CMXEV['tva'][_c], key=lambda e: e[1])[0]
        _TREM_CH[_c] = (max(0.5, TREMOLO_MATRIX_HZ + _cmx_at('rate', _c, _tpk)), _pk, False, 0.0, None, _map)
    # The harmonium's Tremolo stop: channel -> (rate, depth, stereo), and the
    # row spans of the notes that sounded with it drawn. Per NOTE, because it
    # is a stop and not a panel knob -- tremolo.expand takes the row mask.
    _HTREM_CH = {}; _HT_ROWS = []; _HT_PEND = [None]
    _CHORUS_CH = {}     # channel -> (CC93 send 0..1, cents tuple)
    _REVERB_CH = {}     # channel -> CC91 send as a DISTANCE MULTIPLE
    _C91D = {}          # channel -> its first CC91 as that multiple, or None
    # ...and the channels whose CC91 moves, by onset (send_steps)
    _REVERB_STEPS = send_steps(ccs, SR, GM_DEFAULT_REVERB)
    _ON_NOW = [0.0]     # the onset, seconds, of the note being emitted

    _RNORM = {}

    def _refl_norm(f, px, pz, d):
        """sqrt(E(1) / E(d)), E = 1 + the images' energy against the direct,
        for the current voice at frequency f moved out by d (_src_dist)."""
        k = (round(f, 1), px, pz, _radius[0], d) + _refl_state(props)
        g = _RNORM.get(k)
        if g is None:
            r = props.radiation_distance
            e = [1.0 + sum(rg * rg for rg, _, _ in props.reflection_terms(f, px * m, r * m, pz * m, _radius[0]))
                 for m in (1.0, d)]
            if len(_RNORM) >= PREP_MEMO_MAX:
                _RNORM.clear()
            g = _RNORM[k] = math.sqrt(e[0] / e[1])
        return g

    def _src_dist(ch, pr):
        """The source's distance as a multiple of its voice's own: the channel's
        first CC91 against GM's default 40, else the voice's reverb_distance,
        else 1 -- the number the send bus weights the room by (_REVERB_CH),
        so the reflections and the tail stand at one distance."""
        if ch not in _C91D:
            _c = [v for t, cc, v in in_order(ccs.get(ch, [])) if cc == 91]
            _C91D[ch] = (_c[0] / float(GM_DEFAULT_REVERB)) if _c else None
        d = _C91D[ch]
        if ch in _REVERB_STEPS:          # its CC91 at this note's onset (send_steps)
            d = float(step_at(_REVERB_STEPS[ch], int(round(_ON_NOW[0] * SR))))
        if d is None:
            d = getattr(pr, 'reverb_distance', None)
        return 1.0 if d is None else max(0.1, float(d))
    _CLAV_CH = {}
    _DETUNE_CH = {}
    _DRONE_CH = {}          # how many drones, per channel: see below
    # A PART'S SPAN, for voices whose extra voices belong to the channel rather
    # than the note -- a bagpipe's drones are the only ones today. First note-on
    # to last note-off, so a drone sounds under the whole line instead of
    # restarting on every note of it. See SynthProperties.unison_spans_part.
    # PHRASES, not the channel's whole lifetime. This spanned first note-on to
    # last note-off, so a bagpipe part with sixteen bars of tacet in the middle
    # droned straight through them. A piper does not stop for a two-bar rest and
    # does not keep the bag up through a whole section off, so the drones follow
    # the PLAYED PHRASES: notes are grouped, and a gap longer than the voice's
    # part_break_s starts a new one.
    #
    # Seconds and not bars, because the decision being modelled is when a player
    # lets the bag down, and that is a real-time judgement.
    _PHRASE_CH = {}
    _by_ch = {}
    for _e in notes:
        _by_ch.setdefault(_e[0], []).append((_e[2], _e[3]))
    for _c, _ns in _by_ch.items():
        _gap = 2.0
        for _p in {_e[6] for _e in notes if _e[0] == _c}:
            _gap = getattr(property_class_for_program(_p), 'part_break_s', _gap)
        _ph = []
        for _on, _off in sorted(_ns):
            if _ph and _on - _ph[-1][1] <= _gap:
                _ph[-1] = (_ph[-1][0], max(_ph[-1][1], _off))
            else:
                _ph.append((_on, _off))
        _PHRASE_CH[_c] = _ph
    _SPANNED = set()          # (channel, phrase index) already emitted
    # THE DRONES ARE NOTES OF THE PART, each its own voice (tonelib
    # BagpipeDroneProperties): under every phrase a bagpipe channel plays, the
    # drones its CC1 leaves uncorked (the first CC1, read once, as below), from
    # the phrase's first note-on to its last note-off, at the velocity of its
    # first note (which sets the strike-in). Each is keyed to its class here:
    # the two tenors share a note, so the second starts a microsecond later.
    _DRONE_PC = {}
    _dnew = []
    for _c, _ph in _PHRASE_CH.items():
        _bpc = None
        for _p in {_e[6] for _e in notes if _e[0] == _c}:
            if getattr(property_class_for_program(_p), 'drone_classes', None):
                _bpc = property_class_for_program(_p)
        # ...OR A VARIATION'S (the pungi, 111.8: the program's class is the
        # shanai's), where the program's own has none
        # (one look a program: a melodic variation's class is the same at
        # every key)
        if _bpc is None:
            for _p, _k in {_e[6]: _e[1] for _e in notes if _e[0] == _c}.items():
                if not is_drum(_p):
                    _vc = property_class_for_note(_p, _k)
                    if getattr(_vc, 'drone_classes', None):
                        _bpc = _vc
                        break
        if _bpc is None or is_drum(next(_e[6] for _e in notes if _e[0] == _c)):
            continue
        _c1 = [v for t, cc, v in in_order(ccs.get(_c, [])) if cc == 1]
        if getattr(_bpc, 'drone_note_wheel', False):
            if _no_part_drones(path):
                continue          # live's template: live sounds the drone itself
            # THE WHEEL CHOOSES THE DRONE'S NOTE (a pungi): even steps over its
            # choices, its default with no CC1 -- one drone, never corked
            _chs = _bpc.drone_note_choices
            _dsel = (_chs[min(len(_chs) - 1, int(_c1[0]) * len(_chs) // 128)] if _c1
                     else int(_bpc.drone_note_default))
            _dlist = [(_dsel, _bpc.drone_classes[0][1])]
        else:
            # the wheel corks them, in even steps over the drones the class has
            _nd = (int(round(_c1[0] / 127.0 * len(_bpc.drone_classes))) if _c1
                   else len(_bpc.drone_classes))
            _dlist = list(_bpc.drone_classes[:_nd])
        for _a, _b in _ph:
            _first = min((_e for _e in notes if _e[0] == _c and _a <= _e[2] <= _b),
                         key=lambda _e: _e[2])
            for _i, (_dn, _dcls) in enumerate(_dlist):
                _don = _a + 1e-6 * _i
                _dnew.append((_c, _dn, _don, _b, _first[4], _first[5], _first[6]))
                _DRONE_PC[(_c, _dn, _don)] = _dcls
    # THE TAISHOGOTO'S STRUCK DRONE (its last stop, tonelib.TaishoKotoProperties:
    # the channel's first CC1 in even shares of the wheel, read once):
    # the open G2 under every stroke of the channel, re-struck by the next --
    # one string, so each ends where the next begins, the last left to ring --
    # drone_strike_db under the stroke (velocity on the square law)
    _TD_CH = {}

    def _drone_stop(_c, _pc):
        if _c not in _TD_CH:
            _c1t = [v for t, cc, v in in_order(ccs.get(_c, [])) if cc == 1]
            _TD_CH[_c] = (min(len(_pc.drone_stops) - 1, int(_c1t[0] * len(_pc.drone_stops) / 128))
                          if _c1t else int(_pc.drone_stop_default))
        return _TD_CH[_c]
    for _c in _by_ch:
        _cn = sorted((_e for _e in notes if _e[0] == _c and not is_drum(_e[6])
                      and getattr(property_class_for_note(_e[6], _e[1]), 'drone_stops', None)),
                     key=lambda _e: _e[2])
        if not _cn:
            continue
        _tpc = property_class_for_note(_cn[0][6], _cn[0][1])
        if _drone_stop(_c, _tpc) < len(_tpc.drone_stops) - 1:
            continue
        _dcls = getattr(T, _tpc.drone_strike_class)
        _dv = 10 ** (_tpc.drone_strike_db / 40.0)
        _starts = sorted({_e[2] for _e in _cn})
        for _e in _cn:
            _nx = [t for t in _starts if t > _e[2]]
            if _e[2] in [_d[2] - 1e-6 for _d in _dnew if _d[0] == _c]:
                continue                  # a chord: one drone stroke
            _doff = min(_nx[0] if _nx else _e[2] + _tpc.drone_strike_ring_s,
                        _e[2] + _tpc.drone_strike_ring_s)
            _don = _e[2] + 1e-6
            _dnew.append((_c, _tpc.drone_strike_note, _don, _doff,
                          max(1, int(round(_e[4] * _dv))), _e[5], _e[6]))
            _DRONE_PC[(_c, _tpc.drone_strike_note, _don)] = _dcls
    notes = notes + _dnew
    # what the last prepare() sounded as drones: (channel, note, on, off, class
    # name), for the selftests to read
    global LAST_DRONES
    LAST_DRONES = sorted((_d[0], _d[1], _d[2], _d[3], _DRONE_PC[(_d[0], _d[1], _d[2])].__name__)
                         for _d in _dnew)

    def _phrase_of(_c, _on):
        """Which phrase a note falls in, and that phrase's span."""
        for _i, (_a, _b) in enumerate(_PHRASE_CH.get(_c, ())):
            if _a <= _on <= _b:
                return _i, (_a, _b)
        return 0, (_on, _on)
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
    # A SLUR ENDS THE NOTE IT LEAVES. The slurred note's attack is the voice's
    # legato one (slur_attack, below); the note it follows must stop as the new
    # one sounds, not ring its whole release under it -- on a chanter the
    # finger moves and the old pitch is gone, and an 80 ms release under every
    # change sounds as a release and a fresh attack (Ben, of Scotland the
    # Brave). The notes a slurred note FOLLOWS on its channel (sounding up to
    # its onset, or ending within the file's legato tolerance before it), for
    # a voice that says so (SynthProperties.slur_cuts_release).
    _SLUR_OUT = set()
    _socc = {}
    _sl_on = {}
    for _e in notes:
        _k = _socc.get((_e[0], _e[1]), 0); _socc[(_e[0], _e[1])] = _k + 1
        if (_e[0], _e[1], _k) in legato:
            _sl_on.setdefault(_e[0], []).append(_e[2])
    if _sl_on:
        import bisect as _bis
        for _v in _sl_on.values():
            _v.sort()
        for _e in notes:
            _v = _sl_on.get(_e[0])
            if not _v:
                continue
            _q = _bis.bisect_right(_v, _e[2])       # the first slurred onset after this one
            if _q < len(_v) and _e[3] >= _v[_q] - 0.02:
                _SLUR_OUT.add((_e[0], _e[1], _e[2]))

    def _snd_finish(_p):
        """Brightness, resonance and decay on the partials one note made.

        Applied to the note's FINISHED rows -- the slice of the table it
        emitted -- with the same tonelib.sound_shape live applies to its slots,
        so the renderers agree by construction. The gain is power-normalised
        over the note: both are colour, not level.
        """
        if _p is None:
            return
        _i0, _pc, _sd = _p
        _i1 = len(A['om'])
        if _i1 <= _i0:
            return
        _s75 = _sd.get('decay')
        if _s75:
            _k = 1.0 / T.sound_time_scale(_s75)
            for _j in range(_i0, _i1):
                A['logr'][_j] *= _k
                A['logrA'][_j] *= _k
        _d74, _d71 = _sd.get('brightness', 0.0), _sd.get('resonance', 0.0)
        if _d74 or _d71:
            _nf = np.asarray(A['nf'][_i0:_i1], dtype=np.float64)
            _g = T.sound_shape(_pc, _nf, _d74, _d71)
            _g = T.normalise_power(np.asarray(A['aM'][_i0:_i1]), _g)
            for _o, _j in enumerate(range(_i0, _i1)):
                A['aL'][_j] *= float(_g[_o]); A['aR'][_j] *= float(_g[_o])
                A['aM'][_j] *= float(_g[_o])

    _SND_PEND = [None]
    _SV = [0.0, 1.0]         # per-note CC77 depth offset d, CC76 rate scale

    def _push_finish(_p):
        """THE BELLOWS' PUSH (tonelib.bellows_push_gain): a note from silence,
        on a voice whose wind is a player's arm, swells over its first tenth of
        a second and eases back -- the reed driven harder, louder and (low
        down) brighter. A transient COPY of the note's finished rows, the
        direct sound and its images, at the same frequency and phase so it adds
        to the note coherently: rising over bellows_push_rise_s, dying at
        bellows_push_dbs to nothing, each partial scaled by
        tonelib.bellows_push_weight. Its rows are recorded (_PUSH_ROWS) so live
        drops them from a legato note."""
        if _p is None:
            return
        _i0, _pc0, _f00, _dt, _sfa = _p
        _i1 = len(A['om'])
        if _i1 <= _i0:
            return
        # A RANK THAT SPEAKS AS ITSELF (_PUSH_SEG) overshoots as itself: its
        # class's push, its harmonics counted from its own pitch
        _segs = [(_i0, _pc0, _f00)] + [g for g in _PUSH_SEG if g[0] >= _i0]
        _keys = list(A.keys())
        _r0 = _i1
        _si = 0
        for _j in range(_i0, _i1):
            while _si + 1 < len(_segs) and _segs[_si + 1][0] <= _j:
                _si += 1
            _pc, _f0 = _segs[_si][1], _segs[_si][2]
            if not getattr(_pc, 'bellows_push_gain', 0.0):
                continue
            _fa = float(_pc.bellows_push_rise_s) * SR
            _w = T.bellows_push_weight(_pc, float(A['nf'][_j]) / max(_f0, 1e-9), _f0)
            # A SLURRED NOTE TAKES THE PUSH OVER where it stands (_dt after it
            # began), rising with the note's own legato attack: the swell is
            # the bellows', not the note's, and it does not stop at a slur
            _env = T.bellows_push_env(_pc, _dt, _w) if _dt > 0.0 else 1.0
            if _w * _env <= 1e-4:
                continue
            for _k in _keys:
                A[_k].append(A[_k][_j])
            A['aL'][-1] *= _w * _env; A['aR'][-1] *= _w * _env; A['aM'][-1] *= _w * _env
            A['fa'][-1] = _fa if _dt <= 0.0 else _sfa
            A['logr'][-1] = T.bellows_push_rate(_pc, _w) * math.log(10.0) / 20.0
            A['logrA'][-1] = 0.0; A['aft'][-1] = 0.0; A['sus'][-1] = 0.0
        if len(A['om']) > _r0:
            _PUSH_ROWS.append((_r0, len(A['om'])))

    _PUSH_PEND = [None]
    _PUSH_SEG = []          # (first row, speech class, pitch) per rank that speaks as itself
    _PUSH_ROWS = []
    # THE KEY-UP'S OWN ROWS (release_click_*): an event AT note-off, so live
    # leaves them out of the note's stamp and stamps them at the key-up
    _REL_ROWS = []
    _REL_JACKS = []         # (first, end, rank, jack offset s): the click rows of each jack
    _PUSH_T0 = {}           # channel -> when its bellows' push began (a note from silence)
    _HAM_T0 = {}            # channel -> when its string was last PICKED (hammer_legato)
    _FOLD = [None]          # (re-strike sample, crossfade, store) if this note's plate is struck again
    _FOLDIN = [None]        # {mode Hz: [old rows]} the strike before left this one to take in
    _FOLD_STORE = {}        # (ch, note) -> (re-strike time s, store)
    _FOLD_ON = os.environ.get('TUNING_FOLD', '1') not in ('0', 'off', '')
    _HAM = [0.0]            # this note's seconds since that pick, if a hammer-on; else 0
    _LFLIP = []             # rows on the Leslie rotor their pitch would not pick (the crossover's copies)

    def _mvol():
        """MASTER VOLUME, the device's own fader: every channel, after
        everything. A GM System On puts it back to full. Kept as (sample,
        gain) steps and ramped where it is applied, in synth_window."""
        _mv = [(_t, _q, _v) for _t, _k, _v, _q in master if _k == 'vol']
        _mv += [(_t, _q, 1.0) for _t, _q in gmon]
        _mv.sort(key=lambda e: (e[0], e[1]))
        mv = [(int(round(_t * SR)), float(_g)) for _t, _q, _g in _mv]
        if mv and all(abs(_g - 1.0) < 1e-12 for _, _g in mv):
            mv = []                     # a file that only ever says "full"
        return mv

    def _moog_tables():
        """THE MOOG'S ROWS (moog.py), as far as they have been built. None when
        the file has no Moog note, and the kernel then never reads fx -- every
        other file renders as it did."""
        FT = (np.ascontiguousarray(np.array(_MOOG_FT, np.float32).reshape(-1))
              if _MOOG_FT else None)
        KN = (np.ascontiguousarray(np.array(_MOOG_KN, np.float32).reshape(-1))
              if _MOOG_KN else None)
        knk, kb0 = 1, 0
        if _MOOG_KVAR:
            # MOVING ROWS: every row gets knk entries, grid kb0 on (the kernel
            # clamps outside them), from the first change to the last; a
            # constant row the same entry throughout
            _chg = [_g for _tl in _MOOG_KVAR.values() for _g, _r in _tl[1:]]
            kb0 = max(0, min(_chg) - 1)
            knk = max(_chg) - kb0 + 1
            _kn = np.repeat(np.array(_MOOG_KN, np.float32)[:, None, :], knk, axis=1)
            for _row, _tl in _MOOG_KVAR.items():
                _cur = _tl[0][1]
                for _g, _r in _tl:
                    if _g <= kb0:
                        _cur = _r
                _kn[_row, :, :] = _cur
                for _g, _r in _tl:
                    if _g > kb0:
                        _kn[_row, _g - kb0:, :] = _r
            KN = np.ascontiguousarray(_kn.reshape(-1))
        _mpon = any(int(r[12]) & 1 for r in _MOOG_FT) if _MOOG_FT else False
        MPI = np.ascontiguousarray(np.array(_MOOG_MPI, np.int32).reshape(-1)) if _mpon else None
        MPC = np.ascontiguousarray(np.array(_MOOG_MPC or [0.0], np.float64)) if _mpon else None
        MPR = np.ascontiguousarray(np.array(_MOOG_MPR or [1.0], np.float32)) if _mpon else None
        _mkon = any(int(r[12]) & 14 for r in _MOOG_FT) if _MOOG_FT else False
        MKI = np.ascontiguousarray(np.array(_MOOG_MKI, np.int32).reshape(-1)) if _mkon else None
        MPK = np.ascontiguousarray(np.concatenate(_MOOG_MPK).astype(np.float32)) if _mkon else None
        return dict(FT=FT, KN=KN, knk=knk, kb0=kb0, MPI=MPI, MPC=MPC, MPR=MPR, MKI=MKI, MPK=MPK)

    def _cons_expand(_bi, _b):
        """One burst as its EMISSIONS (see below): a seat each, the room's
        images, a stable id. Shared by the whole-file path and the stream,
        which expands each as soon as its channel has a source -- the
        stream used to mix the raw bursts, and crashed on them."""
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
                _dmb = _src_dist(_MCH[0], _pr)
                _terms = _pr.reflection_terms(_fc, _px * _dmb, _pr.radiation_distance * _dmb,
                                              _pz * _dmb, _rad)
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
        return (_n, _ctr, _bw, _shape, tuple(_emit), _bch, _bi)

    if sink is not None and hasattr(sink, 'begin'):
        # what a streamed render needs besides the rows: the kernel's whole-file
        # rows and side tables, the bursts, the fader, and the per-channel
        # settings the effects read (live dicts: filled as channels first sound)
        sink.begin(dict(mod=sys.modules[__name__], room_bands=ROOM_BANDS,
                        lib=lib, N=N, nblk=nblk, total=total, sh=sh, G=G, S=S, BR=BR, BC=BC, BL=BL,
                        cons_bursts=cons_bursts, cons_expand=_cons_expand, cons_src=_CONS_SRC,
                        mvol=_mvol, moog_tables=_moog_tables,
                        reverb=_REVERB_CH, reverb_steps=_REVERB_STEPS, qacc=_QACC, F=_F_SYM, ht_rows=_HT_ROWS,
                        amp_ref=_AMP_REF, amp_imb=_AMP_IMB,
                        moog_ft=_MOOG_FT, moog_mpi=_MOOG_MPI, moog_mki=_MOOG_MKI,
                        effects=dict(sympathetic=_SYM_CH, mf104=_MF104, gsdelay=_GSDN, tubeamp=_AMP_CH,
                                     clavinet=_CLAV_CH, htremolo=_HTREM_CH, tremolo=_TREM_CH,
                                     chorus=_CHORUS_CH, cabinet=_CAB_CH, efxeq=_EFXEQ_CH,
                                     leslie=_LESLIE_CH,
                                     filter=_FILTER_CH,
                                     bus=_BUS_CH,
                                     scanner=_SCAN_CH,
                                     register=_REG_CH, register_scale=REGISTER_SCALE,
                                     register_strings=(string_partial, partial_decay,
                                                       unison_partial))))
    def _par_close(gsw):
        """A PARALLEL TYPE's note closes (gsefx.PARALLEL_TYPES): its rows are
        branch A's, at A's pan; a copy of them, at branch B's level and pan,
        goes on the part's virtual channel (+ gsefx.VIRT), whose own stages
        were set at the part's first note -- B's delay over the copy, or the
        GS delay the note was sent to, as the note's own rows are."""
        po = _PAR_OPEN[0]; _PAR_OPEN[0] = None
        if po is None:
            return
        r0, pch, ca = po
        r1 = len(A['om'])
        if r1 <= r0:
            return
        cb, vch = ca['par']['B'], pch + _GSX.VIRT
        fb = (cb['level'] * (cb.get('od_gain') or 1.0)) / max(ca['level'] * (ca.get('od_gain') or 1.0), 1e-12)
        la, ra = _GSX.pan_gains(ca['par']['pan'])
        lb, rb = _GSX.pan_gains(ca['par']['panB'])
        from array import array as _arr
        for k, col in A.items():
            if len(col) != r1:
                continue
            tc = col.typecode if hasattr(col, 'typecode') else col.a.typecode
            seg = np.frombuffer(_arr(tc, col[r0:r1]).tobytes(), dtype=np.dtype(tc)).copy()
            if k == 'mch':
                seg[:] = vch
            elif k in ('aL', 'aR', 'aM'):
                seg = (seg * (fb * {'aL': lb, 'aR': rb}.get(k, 1.0))).astype(seg.dtype)
            col.extend(_arr(tc, seg.tobytes()))
        if la != 1.0 or ra != 1.0:              # A's own pan, on its rows
            for k, gg in (('aL', la), ('aR', ra)):
                col = A[k]
                for i in range(r0, r1):
                    col[i] = col[i] * gg
        if cb.get('dly'):
            _GSDN.append((r1, len(A['om']), cb['dly'], 1.0))
        elif gsw is not None and not ca.get('dly'):
            _GSDN.append((r1, len(A['om']), gsw[2], gsw[1]))
        # ...and what the voice itself does per part, B's as A's
        for _d in (_CLAV_CH, _HTREM_CH, _TREM_CH):
            if pch in _d and vch not in _d:
                _d[vch] = _d[pch]

    for ch, note, on, off, vel, (v7, v11, pan), prog in notes:
        _ON_NOW[0] = on
        _pna = None              # MIDI 2.0 per-note pitch: set where f0 is decided
        _mmgr = None             # MPE: this note's manager channel, if it is on a member
        _snd_finish(_SND_PEND[0]); _SND_PEND[0] = None
        _push_finish(_PUSH_PEND[0]); _PUSH_PEND[0] = None; del _PUSH_SEG[:]
        # the previous strike's rows end where this note's begin -- its own
        # rows (_pre), and after them any parallel type's branch B copy of them
        _pre = len(A['om'])
        _gsw = _GSD_OPEN[0]
        if _GSD_OPEN[0] is not None:
            if _pre > _GSD_OPEN[0][0]:
                _GSDN.append((_GSD_OPEN[0][0], _pre, _GSD_OPEN[0][2], _GSD_OPEN[0][1]))
            _GSD_OPEN[0] = None
        _par_close(_gsw)
        _row0 = len(A['om'])
        _NOTE_ROW0.append((_row0, (ch, note, on) in _stroked))
        if _REG_OPEN[0] is not None:
            _REG_OPEN[0]['rows'] = (_REG_OPEN[0]['rows'][0], _pre); _REG_OPEN[0] = None
        _raw_off = off           # when the KEY came up, before any pedal held it
        if _HT_PEND[0] is not None:
            _HT_ROWS.append((_HT_PEND[0], _pre)); _HT_PEND[0] = None
        if sink is not None:            # the last note's rows are final
            if _S0[0] is not None:
                # ...and every note to come starts at or after this one
                sink(A, _S0[0], len(A['om']), int(on * SR))
            _S0[0] = len(A['om'])
        _SV[0], _SV[1] = 0.0, 1.0; _VDL[0] = 0.0
        _MCH[0] = ch
        _LV[0] = -1
        choked = None
        if (ch, note) in choke_at:
            choked = next((t for t in choke_at[(ch, note)] if t > on + 1e-4), None)
        # PERCUSSION (GM channel 10). The note number selects a drum, not a
        # pitch: it takes a fixed base frequency and its own property class, and
        # the tuner never sees it. Without this the whole kit was routed through
        # property_class_for_program and played as PITCHED notes -- a Steinway
        # sounding drum note-numbers -- which is what a GM game cue exposed.
        # The reference (midilib) has always done this; only the block engine
        # did not, so the two disagreed on any file with a drum track.
        # THE DRUM SET is the program, when the note began on a drum channel.
        # A USER DRUM SET's key is another set's key (user_drum): its sound
        # from there, its own settings as the key's preset, the file's drum
        # NRPN / setup edits over them (pitch adding, the rest replacing)
        _ud = (user_drum(_USET, prog, note)
               if (is_drum(prog) and int(prog) in USER_DRUM_SETS and _USET) else None)
        if _ud is not None:
            drum = percussion_for_note(_ud[1], kit_for_program(int(_ud[0])))
        else:
            drum = (percussion_for_note(note, kit_for_program(int(prog)))
                    if is_drum(prog) else None)
        if is_drum(prog) and drum is None:
            continue                      # unmapped drum: the reference drops it
        _dst = drum_edit_at(_DEDIT[ch], note, on) if (drum is not None and ch in _DEDIT) else {}
        if _ud is not None:
            _own = dict(_ud[2])
            for _k, _v in _dst.items():
                _own[_k] = _own.get('pitch', 0) + _v if _k == 'pitch' else _v
            _dst = _own
        if _dst.get('rxon', 1) == 0:
            continue                      # the kit told not to receive this key
        # INTO THE GS DELAY: the part's send at the onset, a drum key's own
        # multiplying it (its 0-127 a share of the part's, preset taken as all)
        # THE INSERTION EFFECT, where this part is assigned to it and its type
        # is built (gsefx.chain): what it is at this note's onset
        _EFXN[0] = None
        if _EFXEV and not MOOG_NEUTRAL and _GSX.assigned(_EFXEV, ch, on):
            _EFXN[0] = _GSX.chain(_GSX.state_at(_EFXEV, on))
        elif drum is None and not MOOG_NEUTRAL:
            # ...or THE TONE'S OWN (insertion_efx: the SC-8850's EP Phase, its
            # Delayed Lead), where the file assigns the part none: (type, its
            # parameters over the type's), as the module's own tone would
            _tefx = getattr(_DRONE_PC.get((ch, note, on)) or property_class_for_note(prog, note),
                            'insertion_efx', None)
            if _tefx is not None:
                _EFXN[0] = _GSX.chain(_GSX.tone_state(*_tefx))
                _EFX_CH[('tone', ch)] = True
        # the part's first chain, the file's or the tone's, is the channel's
        if _EFXN[0] is not None and ch not in _EFX_CH:
            _EFX_CH[ch] = _EFXN[0]
            # ITS SENDS ARE THE PART'S NOW: the reverb's distance, here
            # before the channel's is read from CC91
            _rv = _EFXN[0]['sends'].get(_GSX.SEND_REV, 40)
            _C91D[ch] = max(0.0, _rv) / float(GM_DEFAULT_REVERB)
            _REVERB_CH.setdefault(ch, _C91D[ch])
            _REVERB_STEPS.pop(ch, None)    # the effect's send, not CC91's
        if _GS_DLY and not MOOG_NEUTRAL:
            if _EFXN[0] is not None:
                _gs_s = _EFXN[0]['sends'].get(_GSX.SEND_DLY, 0) / 127.0
            else:
                _gs_s = _gsd_send(ch, on) * (_dst.get('delay', 127) / 127.0 if drum is not None else 1.0)
            if _gs_s > 0.0:
                _GSD_OPEN[0] = (_row0, _gs_s, _GS_DLY['dev'])
        if _EFXN[0] is not None and _EFXN[0].get('dly'):
            # a guitar multi's own delay (its Dly stage), in the GS delay's place
            _GSD_OPEN[0] = (_row0, 1.0, _EFXN[0]['dly'])
        if _EFXN[0] is not None and _EFXN[0].get('par'):
            _PAR_OPEN[0] = (_row0, ch, _EFXN[0])     # its branch B made where the note closes
        _seat = 0.0                # a seat inside the instrument (below); none
        if drum is not None:
            FREQ_N = FREQ          # a drum's pitch is its own, not a tuning's
            _, pc, f0, dpan = drum
            # THE FILE'S OWN SETTING OF THIS DRUM (GS drum NRPN / drum setup):
            # its pitch in semitones, its pan in place of the kit's (0 random,
            # the same at every render), its level against the preset -- ours
            # taken as Roland's typical 100, the value no preset table gives
            if 'pitch' in _dst:
                f0 *= 2.0 ** (_dst['pitch'] / 12.0)
            if 'pan' in _dst:
                if _dst['pan'] == 0:
                    _hv = (ch * 0x9E3779B1) ^ (note * 0x85EBCA6B) ^ (int(on * 1000) * 0xC2B2AE35)
                    _hv = ((_hv ^ (_hv >> 15)) * 0x2545F491) & 0xFFFFFFFF
                    dpan = 2.0 * (_hv / 4294967295.0) - 1.0
                else:
                    dpan = (_dst['pan'] - 64) / 63.0
            f0 *= stroke_pitch.get((note, on), 1.0)   # bell tree: this bar, not the lowest
            _tilt = stroke_tilt.get((note, on))       # a voice's pulse: its tilt, below
            # ...and a key's written pitch that picks a RATE, as the program's
            # note does (sounding_octaves, below): the SFX set's helicopter had
            # run its rotor at 261.6 Hz, four octaves fast -- a buzz
            _so = getattr(pc, 'sounding_octaves', 0.0)
            if _so:
                f0 *= 2.0 ** _so
            organ = False; _orgk = None; chan_vol = (v7*v11)**2
            if 'level' in _dst:
                chan_vol *= (_dst['level'] / 100.0) ** 2
            # THE KIT'S SEAT (or the key's own pan) is where the piece sits in
            # the kit; the part's pan turns the kit (tonelib.stage_angle) --
            # GS's relative part pan on an absolute key pan, as Roland has it
            _seat = dpan
        else:
            pc = _DRONE_PC.get((ch, note, on)) or property_class_for_note(prog, note)
            # A WIDE VOICE (key_pan_spread: GS's "w" tones) spreads its keys
            # across the stereo field, low left and high right, about the
            # channel's pan: the spread at 30 semitones from middle C
            _kps = getattr(pc, 'key_pan_spread', 0.0)
            if _kps:
                _seat = _kps * (note - 60) / 30.0   # within the instrument: a seat
            organ = getattr(pc,'registerable',False)
            _orgk = (ch, organ_family(pc)) if organ else None   # its registration tables' key
            # An organ's CC7 is its swell shutter and its CC11 half the stop
            # word, so its channel gain is 1 and the swell row does the rest; a
            # voice whose stop word lives elsewhere (the harmonium) keeps the
            # volume and expression every other voice has.
            chan_vol = (1.0 if organ and tuple(getattr(pc, 'stop_word_ccs', (11, 43)))[0] == 11
                        else (v7*v11)**2)
            FREQ_N = _F(ch, on)
            if FREQ_E is not None and getattr(pc, 'tuning_family', None) == 'indian':
                FREQ_N = FREQ_E         # the secondary tuning: see FREQ_E above
            # MIDI 2.0 PER-NOTE PITCH is absolute and outranks the tuner, MTS
            # and the channel's scale/octave table (M2-104 7.4.15); static bend
            # and channel tuning still offset it, below. See _PN_AT.
            _pna = _PN_AT.get((ch, note, on))
            f0 = (440.0 * 2.0 ** ((_pna[0] - 69.0) / 12.0)
                  if _pna and _pna[0] is not None else FREQ_N[note])
            if _pna:
                f0 *= _pna[1]
            _mpa = _MPE_AT.get((ch, note, on))
            if _mpa:
                f0 *= _mpa[0]           # this note's own MPE bend at Note On
            _mea = _MEEND_AT.get((ch, note, on))
            if _mea:
                f0 *= _mea[0]           # this note's meend at Note On
            # A WRITTEN NOTE IS NOT ALWAYS A PITCH. A helicopter's note chooses
            # a blade passing rate, which is four octaves under where it is
            # written; see SynthProperties.sounding_octaves. Applied HERE,
            # because everything downstream -- the partial frequencies, the
            # stretch, the bore -- is built from f0, and a class that scaled its
            # own frequency instead changed none of them.
            _so = getattr(pc, 'sounding_octaves', 0.0)
            if _so:
                f0 *= 2.0 ** _so
            # A STATIC PITCH BEND IS A TUNING, and it belongs here with the
            # other fixed pitch offsets -- for the reason stated two hundred
            # lines above this one: everything downstream is built from f0.
            # Every voice honours it, a harpsichord included, because a wheel
            # that never moves while anything sounds is a temperament and not
            # a gesture. See the tuning/gesture split in prepare.
            _bt = _BTUN.get(ch)
            if _bt:
                f0 *= _bt
            # ...AND THE CHANNEL'S OWN TEMPERAMENT, if a GM2 Scale/Octave
            # Tuning sysex set one. A sibling of the static bend above: both
            # say "this channel is tuned differently", and both are exact as a
            # fixed factor on f0. MULTIPLICATIVE, so it composes with the
            # instrument's own scale below rather than replacing it -- a
            # retuned channel retunes a chanter too, and the drones follow.
            _ot = _OTUN.get(ch)
            if _ot and not (_pna and _pna[0] is not None):
                f0 *= 2.0 ** (_ot[note % 12] / 1200.0)
            # AN INSTRUMENT WITH HOLES HAS ITS OWN SCALE, and it is not the
            # render's temperament. A chanter is cut once for one tonic and
            # every note of it is tuned to beat cleanly against a fixed drone,
            # which is just intonation and not twelve equal semitones. The
            # TONIC still comes from the temperament -- so the pipe plays with
            # whatever else is in the file -- and only the intervals inside the
            # instrument are its own. See SynthProperties.scale_cents; same
            # mechanism as the brass intonation immediately below, which takes
            # a trumpet's pitch from its valve combination.
            _sc = getattr(pc, 'scale_cents', None)
            _st = getattr(pc, 'scale_tonic_note', None)
            if _sc and _st is not None and _st in FREQ_N:
                _tonic = (FREQ_N[_st] * (2.0 ** _so if _so else 1.0) * (_bt or 1.0)
                          * (2.0 ** (_ot[_st % 12] / 1200.0) if _ot else 1.0))
                _deg = _sc.get(note - _st)
                if _deg is not None:
                    f0 = _tonic * 2.0 ** (_deg / 1200.0)
                # ...AND THE DRONES ARE TUNED TO IT, by ear, before playing.
                # They were absolute Hz, which is right at A=440 and a hundred
                # cents out at `hybrid`'s A=415 -- against the one note they
                # exist to reinforce.
                T.bagpipe_tonic_hz = _tonic
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
        # AFTERTOUCH IS EFFORT, and it arrives in the same units, so the two
        # renderers agree by ALGEBRA rather than by calibration. Live scales
        # each partial by (f/f0)^(press_tilt*p) with press_tilt = effort_tilt *
        # PRESS_DB / 6.0206 (see live._press_tilt); tonelib does
        # attack_dampening -= effort_tilt*effort/6.0206, which is the same
        # expression with effort = PRESS_DB*p. Setting it makes them identical,
        # not merely similar.
        #
        # Added AFTER the velocity clamp on purpose: +/-12 dB is a statement
        # about what a MIDI velocity can be taken to mean, and a player leaning
        # on a key is a separate and explicit request.
        _press = _pressure_of(ch, note, on, off)
        _mmgr = _mpe_member.get((ch, note, on))
        if _mmgr is not None:
            # AN MPE ZONE IS ONE INSTRUMENT. Its notes sit on member channels
            # only so each can bend alone; everything that belongs to the
            # INSTRUMENT -- its amplifier and cabinet, its chorus, its stem --
            # is the zone's. Tagged with the member, every note of an MPE
            # guitar went through an amplifier of its own, and two strings that
            # should intermodulate in one valve stage distorted apart (Ben).
            _MCH[0] = _mmgr
            # MPE: the louder of the note's own and its manager's (Appendix D)
            _press = T.mpe_pressure(_press, _pressure_of(_mmgr, -1, on, off))
        if _press:
            _eff += T.PRESS_DB * _press
        # CC1 IS HOW FAR OUT OF TUNE. 64 -- and no CC1 at all -- is the voice's
        # own range; 0 is a piano just tuned, 127 one nobody has touched.
        #
        # RESOLVED HERE, not in the per-channel block further down, which runs
        # AFTER this loop has already built every note: read there, the scale
        # was always its default and the wheel did nothing. And unlike the
        # clavinet's rockers it cannot be a pass over the finished table at all,
        # because a detune is in the partials' FREQUENCIES.
        if ch not in _DETUNE_CH:
            _c1d = [v for t, cc, v in in_order(ccs.get(ch, [])) if cc == 1]
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
        # THE DRONES, and CC1 says HOW MANY -- not how loud. A piper does not
        # turn a drone down, they cork it, so this is a count over the set the
        # instrument has, read ONCE from the channel as the clavinet's rockers
        # and the amplifier's drive are. See tonelib.bagpipe_drones for why the
        # order is (tenor, tenor, bass) and why absence means all three.
        #
        # BUILT HERE, INLINE, exactly as the detune wheel above is. It was first
        # written in the per-channel block far below -- which runs AFTER every
        # note is built, so the wheel did nothing and every CC1 value gave three
        # drones. That is precisely how the honky-tonk's wheel came to be inert,
        # recorded in sources.md, and it was reintroduced within the hour.
        if getattr(pc, 'drone_wheel', False):
            if ch not in _DRONE_CH:
                _c1d2 = [v for t, cc, v in in_order(ccs.get(ch, [])) if cc == 1]
                _DRONE_CH[ch] = (int(round(_c1d2[0] / 127.0 * 3.0)) if _c1d2
                                 # drone_RATIOS, the class's tuple: drone_hz
                                 # became a property (it follows the chanter's
                                 # tuning), and on the CLASS a property is not
                                 # a sequence -- so from 8a86e4a until this
                                 # line, every bagpipe file that never sent a
                                 # CC1 crashed the file renderer. Nothing sent
                                 # one without CC1; the CC121 check did.
                                 else len(getattr(pc, 'drone_ratios', ())))
            T.bagpipe_drones = _DRONE_CH[ch]
        T.soft_pedal_down = _soft_at(ch, on)
        # ...and on a channel whose fader moves under its notes, the note is
        # at unity and the fader is its row (THE CHANNEL FADER, above)
        if not (organ and tuple(getattr(pc, 'stop_word_ccs', (11, 43)))[0] == 11):
            _lk = _mpe_member.get((ch, note, on), ch)
            if _lk in _LROW:
                chan_vol = 1.0
                _LV[0] = _LROW[_lk]
        # THE BANK'S BALANCE (patch_map.PROGRAM_TRIM_DB): the program's own
        # level against GeneralUser GS's, on the channel volume
        chan_vol *= program_trim(prog, drum is not None, gs=_GS_FILE[0])
        # A SOUND TRANSPOSED WHOLE (tonelib transposed_from_hz: the SFX set
        # played from the keyboard, patch_map.melodic_sfx): built at the pitch
        # it was fitted at, and every frequency it emits -- harmonics, the
        # noise table's bands, the grains, all in Hz -- moved by the key's
        # interval, as a sample transposes. Its times stay its own.
        _XP = 1.0
        _xf = getattr(pc, 'transposed_from_hz', None)
        if drum is None and _xf:
            _XP, f0 = f0 / _xf, _xf
            # ...each stroke of it its own pitch and tilt, as on the kit
            f0 *= stroke_pitch.get((note, on), 1.0)
            _tilt = stroke_tilt.get((note, on))
        _EFG = 1.0
        if _EFXN[0] is not None:
            chan_vol *= _EFXN[0]['level']      # the insertion effect's output level, this note's
            # ITS OD STAGE'S GAIN, in front of the valve: into the note's
            # level, and NOT into the valve's reference below (which takes a
            # fader back out) -- so it drives the valve harder and comes out
            # louder, saturating at the valve's ceiling, as a pedal does
            _EFG = _EFXN[0].get('od_gain') or 1.0
            chan_vol *= _EFG
        props = pc(f0, pan, (vel/127.0)**2, chan_vol, _eff)   # pan = CC10: a turn (tonelib.stage_angle)
        if _seat:
            # a seat inside the instrument, at the angle its pan names
            props.seat_x = props.listener_distance * math.tan(T.stage_angle(_seat))
            props.place()
        if _EFXN[0] is not None and _EFXN[0].get('pos3d'):
            # THE PART PLACED IN 3D (gsefx: 3D Manual, 3D Auto): its angle the
            # type's, past the speakers and behind, turning at 3D Auto's speed --
            # each note where its onset finds it
            _az, _turn = _EFXN[0]['pos3d']
            props.pan_angle = math.radians(((_az + 360.0 * _turn * on + 180.0) % 360.0) - 180.0)
            props.place()
        if (drum is not None or _xf) and _tilt is not None:
            # a voice's pulse, darker or brighter as its syllable goes on
            # (percussion_map._voiced; tonelib.SfxThroatProperties)
            props.stroke_tilt_db = _tilt
        if drum is not None or _xf:
            # ...and its MOUTH, opening and closing: its formants moved
            # (tonelib.SfxThroatProperties.stroke_formant_scale)
            _mouth = stroke_mouth.get((note, on))
            if _mouth is not None:
                props.stroke_formant_scale = _mouth
            # ...and its VOWEL moving (stroke_formant_morph)
            _morph = stroke_morph.get((note, on))
            if _morph is not None:
                props.stroke_formant_morph = _morph
        if _press:
            # ...and the LEVEL half of it. `gain` is read lazily inside
            # harmonic_volume, long after construction, so this needs no change
            # to a constructor signature that subclasses override.
            props.gain *= T.db_amplitude(T.PRESS_DB * _press)
        # HALF-VALVING LOSES SUPPORT, and the dip is the whole tell. Deepest in
        # the middle of the run where the harmonic alignment is worst, back up
        # at either end where a real fingering is being held. A smear without
        # it is just a portamento wearing a staircase.
        _gl = _GLISS.get((ch, note, on))
        if _gl is not None and _gl[0] != 1.0:
            props.gain *= _gl[0]
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
        # how long the key was held, before a one-shot's extension: a shaken
        # noise (tonelib.ShakenNoiseProperties) shakes for a share of it
        _held = off - on
        # A one-shot voice (cymbal, struck drum) ignores note-off and rings out
        # on its own decay; the reference skips release() for these.
        if getattr(pc, 'one_shot', False):
            # ...unless it is GATED, when it stops where the gate closes,
            # whatever the key did: see tonelib.GatedSnareProperties.
            _gate = getattr(pc, 'gate_time', None)
            # A KIT keeps the flat hold: a ride's 1240 partials held to -80 dB
            # (32 s) a hit, on eighths, would fill live's slab
            off = ((max(off, on + _gate) if getattr(pc, 'held_texture', False) else on + _gate)
                   if _gate else max(off, on + (ONE_SHOT_MIN_S if drum is not None
                                                else one_shot_ring(props, f0))))
        # A MELLOTRON'S TAPE RUNS OUT (tonelib.MellotronMixin, tape_length_s):
        # a key held past its strip's length falls silent there
        _tape = getattr(pc, 'tape_length_s', None)
        if _tape and not getattr(pc, 'one_shot', False):
            off = min(off, on + _tape)
        # A SIREN sounds while its rotor does (_SIREN_AT): the fire siren's
        # coast, the Helmholtz siren's air running out
        _sir = _SIREN_AT.get((ch, note, on))
        if _sir is not None:
            off = max(on + 1e-3, _sir[1])
        # THE PEDAL, between the two of them on purpose. After the one-shot
        # extension, because a cymbal has no damper to lift and must not be
        # pedalled; before the choke override below, so a closed hi-hat still
        # stops an open one whatever the foot is doing; and before dur = off-on
        # a few lines down, so the longer note also gets the larger release,
        # fade and chiff caps that follow from it.
        #
        # Nothing in the kernel changes: the two-stage decay is measured from
        # note-on and is never reset at note-off, so a later noff simply lets
        # the string's own decay run on under a lifted damper. Which is what
        # actually happens.
        _nx = _next_same.get(((ch, note), on))
        _mcut = (ch, note, on) in _MONO_CUT
        if (not getattr(pc, 'one_shot', False) and getattr(pc, 'damper_pedal', True)
                and not _mcut):
            _rel = _damper_falls(ch, off)
            if _rel > off:
                # ...AND NO LONGER THAN UNTIL THIS SAME STRING IS STRUCK AGAIN.
                # Replaying a key drops the damper back onto that string
                # whatever the pedal is doing -- there is only one string, and
                # two copies of it do not sum, they BEAT. Measured on
                # ondine.mid, 2658 of 4579 pedalled notes would otherwise run
                # past their own next onset, so this is the common case and not
                # an edge.
                #
                # The RETRIGGER_FADE margin is load-bearing. Clamp to exactly
                # _nx and the guard below (`if _nx > off`) goes false, the
                # release is never clipped, and the tail runs straight through
                # the re-strike -- the same bug wearing a different hat. One
                # steal-fade of margin keeps that guard true, so the existing
                # clip fires and the tail lands exactly on the new attack.
                if _nx is not None:
                    _rel = min(_rel, max(off, _nx - RETRIGGER_FADE))
                off = _rel
        # ...AND THE SOSTENUTO PEDAL, which caught this note only if its key
        # was already down when the pedal went down. Same clamp as the damper:
        # a string re-struck is a string re-damped whatever any pedal is doing.
        _sh = _SOST_HELD.get((ch, note, on))
        if _sh is not None and _sh > off and getattr(pc, 'damper_pedal', True) \
                and not getattr(pc, 'one_shot', False) and not _mcut:
            if _nx is not None:
                _sh = min(_sh, max(off, _nx - RETRIGGER_FADE))
            off = max(off, _sh)
        # ALL SOUND OFF overrides both of them, and the note's own length: it
        # is the one message that means "stop now" rather than "let go".
        _sf = _sound_off(ch, on)
        if _sf is not None and _sf < off:
            off = max(on + RETRIGGER_FADE, _sf)
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
        # A STRIKE-IN SET BY THE HAND: a voice whose onset is how fast something
        # comes up to pressure (a bagpipe drone: the bag) takes it from the
        # velocity, soft to hard (SynthProperties.strike_in_s)
        _si = getattr(props, 'strike_in_s', None)
        if _si:
            at = _si[0] + (_si[1] - _si[0]) * min(1.0, max(0.0, vel / 127.0))
        # SLUR: the previous note on this channel ran up to this one, so the
        # exciter never stopped and there is no onset to make. Only voices with
        # an exciter that can carry declare legato_attack_s; see tonelib.
        # The arithmetic is tonelib's (slur_attack), shared with live, which
        # applies the same slur after stamping a template.
        _slurred = (ch, note, _occ.get((ch, note), 0)) in legato
        if _slurred:
            at = T.slur_attack(at, props)
        # A GUITAR'S LEGATO IS THE FRETTING HAND (hammer_legato: Roland's ":"
        # guitars). A note over the one before is hammered or pulled, not
        # picked: a softer onset, and the string's energy carried on from the
        # last pick (emit_partial); a picked note starts the chain again
        # THE SAME PLATE STRUCK AGAIN (fold_restrike; emit_partial): this
        # strike takes in what the one before left it, and leaves its own to
        # the next strike of the key, if there is one
        _FOLD[0] = _FOLDIN[0] = None
        if _FOLD_ON and getattr(props, 'fold_restrike', False):
            _fs = _FOLD_STORE.pop((ch, note), None)
            if _fs is not None and abs(_fs[0] - on) < 1e-6:
                _FOLDIN[0] = _fs[1]
            _nx2 = _next_same.get(((ch, note), on))
            if _nx2 is not None:
                _st2 = {}
                _FOLD[0] = (int(_nx2 * SR), max(32.0, (props.attack_time or 0.004) * SR), _st2)
                _FOLD_STORE[(ch, note)] = (_nx2, _st2)
        _HAM[0] = 0.0
        if getattr(props, 'hammer_legato', False):
            if (ch, note, _occ.get((ch, note), 0)) in legato and ch in _HAM_T0:
                _HAM[0] = max(0.0, on - _HAM_T0[ch])
                at = max(at, HAMMER_ATTACK_S)
            else:
                _HAM_T0[ch] = on
        # A GLISS STEP IS NOT RETONGUED. The lips keep buzzing through the whole
        # run -- that is what "blow through the harmonics" means -- so every
        # step takes the legato attack whether or not _legato_ticks saw it.
        # It could not have: these notes did not exist when the file was parsed.
        if (ch, note, on) in _GLISS or (ch, note, on) in _MONO_SLUR:
            at = T.slur_attack(at, props)
            _slurred = True
        # ...AND A NOTE FROM SILENCE IS A PUSH OF THE BELLOWS (_push_finish); a
        # slurred one is not -- the bellows is already moving
        if getattr(props, 'bellows_push_gain', 0.0) and getattr(props, 'bellows_push_every_note', False):
            # A PIPE'S SPEECH, not a bellows: every pipe that speaks overshoots
            _PUSH_PEND[0] = (_row0, props, f0, 0.0, 0.0)
        elif getattr(props, 'bellows_push_gain', 0.0):
            if ((ch, note, _occ.get((ch, note), 0)) not in legato
                    and (ch, note, on) not in _GLISS and (ch, note, on) not in _MONO_SLUR):
                _PUSH_T0[ch] = on
                _PUSH_PEND[0] = (_row0, props, f0, 0.0, 0.0)
            elif ch in _PUSH_T0:
                # ...and carried over a slur, where it has got to
                _PUSH_PEND[0] = (_row0, props, f0, on - _PUSH_T0[ch], at * SR)
        _occ[(ch, note)] = _occ.get((ch, note), 0) + 1
        rt = props.release_valve_time if props.release_valve_time is not None else props.chiff_max_valve_time
        # Pipe speech scales with wavelength: add speech_cycles periods of the
        # fundamental to the fixed floor (mirrors tonelib.speech_time -- bass
        # pipes speak slowly, trebles promptly).
        at = props.speech_time(at, f0); rt = props.speech_time(rt, f0)
        # CC71-78: WHAT THIS INSTRUMENT HAS, AND WHAT THE CHANNEL ASKS. Only the
        # controls sound_controls_of grants reach the note; the rest are refused
        # here, silently, as a bend is on a piano.
        _sctl = T.sound_controls_of(pc)
        _sdd = _snd_d(ch, on)
        # ...AND THE VOICE'S OWN STARTING POINT (sound_bias: a GS "d"ark or
        # bright variation), the channel's offsets on top of it
        _sbias = getattr(pc, 'sound_bias', None)
        if _sbias:
            _sdd = dict(_sdd)
            for _bk, _bv in _sbias.items():
                _sdd[_bk] = _sdd.get(_bk, 0.0) + _bv
        if _mmgr is not None:
            # MPE: CC74 per note, the manager's a bias on it (Appendix D)
            _mb = _snd_d(_mmgr, on).get('brightness', 0.0)
            if _mb:
                _sdd = dict(_sdd)
                _sdd['brightness'] = T.mpe_timbre(_sdd.get('brightness', 0.0), _mb)
        _sd = {_k: _d for _k, _d in _sdd.items() if _k in _sctl} if _sctl else {}
        if _sd:
            if 'attack' in _sd:
                at *= T.sound_time_scale(_sd['attack'])
            if 'release' in _sd:
                rt *= T.sound_time_scale(_sd['release'])
            if 'vib_depth' in _sd:
                _SV[0] = _sd['vib_depth']
            if 'vib_rate' in _sd:
                _SV[1] = T.sound_vib_rate(_sd['vib_rate'])
            if 'vib_delay' in _sd:
                _VDL[0] = T.sound_vib_delay(_sd['vib_delay'])
            _SND_PEND[0] = (len(A['om']), pc, _sd)
        # The ATTACK's share of the note is a property, because a reverse cymbal
        # needs almost all of it; see SynthProperties.attack_fraction_max. So is
        # the RELEASE's (release_fraction_max): 0.45 for a damper or a bow, and
        # none for a voice whose release is its own length, whatever the note
        # (a plucked string's ring after the finger lifts, GS's per-tone
        # release). It had been a flat 0.45 "because nothing wants more", and
        # an eighth-note koto was cut dead.
        _afm = getattr(props, 'attack_fraction_max', 0.45)
        _rfm = getattr(props, 'release_fraction_max', 0.45)
        fade = max(1e-4, min(at, _afm*dur))*SR
        rel = max(1e-4, rt if _rfm is None else min(rt, _rfm*dur))*SR
        if (ch, note, on) in _SLUR_OUT and getattr(props, 'slur_cuts_release', False):
            rel = min(rel, max(RETRIGGER_FADE, getattr(props, 'legato_attack_s', 0.0) or 0.0) * SR)
        # ...and no longer than until this same string is plucked again, but
        # never SHORTER than a steal fade. A sampler stealing a voice does not
        # cut it, it fades it over a few milliseconds, because a cut is a step
        # and a step is a click -- the same lesson as the release jitter floor
        # in synthkernel.c. Bach's tightest repeat here leaves 1.3 ms, and five
        # notes in BWV 971 come in under 2, so the floor does real work. Where
        # it exceeds the gap the old note runs a few ms into the new one, which
        # is inaudible and is what a real damper does anyway: felt takes time.
        # _nx was looked up above, before the pedal could move `off`.
        if _nx is not None and _nx > off:
            rel = min(rel, max(RETRIGGER_FADE, _nx - off)*SR)
        # ONE VOICE CANNOT BE IN TWO PLACES. A mono note cut by the next one
        # hands its voice straight over: the release is the steal-fade and not
        # the instrument's own, which would leave the old pitch sounding under
        # the new one for as long as the instrument rings.
        if _mcut:
            rel = min(rel, RETRIGGER_FADE * SR)
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
        # a reversed note's partials are emitted backwards, ending at its note-off (_reverse_partial)
        _REV[0] = (non, noff) if getattr(props, 'played_backwards', False) else None
        _PJ[0] = (1.0 + getattr(props,'pitch_jitter',0.0)) * _XP
        _XPON[0] = _XP != 1.0
        # ...AND WHETHER THIS NOTE CAN BE BENT AT ALL. Per NOTE and not per
        # channel, because a channel can change program mid-piece (passac.mid
        # cycles six of them), so each note is judged by its own class.
        _BR[0] = (brow_of.get(ch, -1)
                  if getattr(pc, 'pitch_bendable', True) else -1)
        if ch in bbrow_of and (props.breath_pitch_cents > 0.0 or props.breath_wobble_db > 0.0):
            _BR[0] = bbrow_of[ch][0]    # the player's breath: the tone's level and pitch
        if _pna and _pna[2] >= 0:
            _BR[0] = _pna[2]            # its own row: per-note pitch that moves
        _mpa = _MPE_AT.get((ch, note, on))
        if _mpa is not None:
            _BR[0] = _mpa[1]            # MPE: the note's own row, or none
        _mea = _MEEND_AT.get((ch, note, on))
        if _mea is not None:
            _BR[0] = _mea[1]            # the meend: the note's own row, or none
        if _sir is not None:
            _BR[0] = _sir[0][0]         # the siren's rotor (its lower disc's, a rank's below)
        _als = _ALIAS_AT.get((ch, note, on))
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
        if _MCH[0] not in _CONS_SRC:
            _CONS_SRC[_MCH[0]] = (props, _PX[0], _PZ[0], _radius[0])
        if getattr(props, 'plunger', False) and _MCH[0] not in _FILTER_CH:
            # A PLUNGER (efxfilter.plunger): the channel's moving filter, the
            # player's hand on the channel's aftertouch -- the part's, as an
            # insertion effect's wah is
            _FILTER_CH[_MCH[0]] = __import__('efxfilter').plunger(ats.get(ch, ()))
        if getattr(props, 'amp_drive', 0.0) and _MCH[0] not in _AMP_CH:
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
            # do: there IS a wheel offline now (bend_blocks integrates a moving
            # one), but a half-moon is read as an EDGE and what makes the flick
            # work is the SPRING RETURN, which a written bend has no reason to
            # have.
            _drv = float(props.amp_drive)
            if not getattr(props, 'leslie', False):
                _c1 = [v for t, cc, v in in_order(ccs.get(_MCH[0], [])) if cc == 1]
                if _c1:
                    _drv *= 4.0 * _c1[0] / 127.0
            _AMP_CH[_MCH[0]] = float(os.environ.get('TUNING_AMP_DRIVE', _drv))
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
            _AMP_REF[_MCH[0]] = (_ref * chan_vol / _EFG) if _ref else None
            _AMP_LV0[_MCH[0]] = _EFXN[0]['level'] if _EFXN[0] is not None else 1.0
            _AMP_IMB[_MCH[0]] = getattr(props, 'amp_imbalance', None)
        # THE INSERTION EFFECT's AMP, SPEAKER AND FLANGER, set once for the
        # part at its first note through it: its OD stage a gain in front of
        # the voice's own valve (two stages in series: their gains multiply,
        # through the note's level above) -- a voice with no valve given one
        # at its edge, its reference the Strat's; its cabinet; its chorus or
        # flanger in the CC93 chorus's place, its mix followed note by note
        if _EFXN[0] is not None and _EFX_CH.get(_MCH[0]) is _EFXN[0] and not _EFX_CH.get(('done', _MCH[0])):
            _EFX_CH[('done', _MCH[0])] = True
            _ex = _EFXN[0]
            if _ex['od_gain'] is not None and _MCH[0] not in _AMP_CH:
                _AMP_CH[_MCH[0]] = _GSX.PEDAL_AMP_DRIVE
                _ref = getattr(props, 'amp_reference', None) or 0.2289
                _AMP_REF[_MCH[0]] = _ref * chan_vol / _EFG
                _AMP_LV0[_MCH[0]] = _ex['level']
            if _AMP_REF.get(_MCH[0]) and not isinstance(_AMP_REF[_MCH[0]], tuple):
                # ITS LEVEL IS AFTER THE VALVE: the reference follows the
                # file's level timeline (tubeamp.segment), so the level's
                # automation is a level and the OD's gain alone is drive
                _st = sorted({0.0} | {float(t) for t, e in _EFXEV})
                _AMP_REF[_MCH[0]] = ('steps', _AMP_REF[_MCH[0]] / max(_AMP_LV0.get(_MCH[0], 1.0), 1e-12),
                                     [t * SR for t in _st],
                                     [((_GSX.chain(_GSX.state_at(_EFXEV, t)) or _ex)['level'])
                                      for t in _st])
            if _ex['eq'] is not None:
                _EFXEQ_CH[_MCH[0]] = _ex['eq']
            if _ex['cabinet'] and _MCH[0] not in _CAB_CH and os.environ.get('TUNING_CABINET', '1') != '0':
                _CAB_CH[_MCH[0]] = _ex['cabinet']
            if _ex['cf'] is not None:
                # its wet share as the file sets it -- or, the tone's own effect
                # (no event assigns it), the chain's own (gsefx.chain_share)
                _CHORUS_CH[_MCH[0]] = (0.0, _ex['cf'][0], 'gs',
                                       _GSX.chain_share(_ex) if _EFX_CH.get(('tone', _MCH[0]))
                                       else _GSX.mix_share(_EFXEV, _MCH[0], SR))
            if _ex.get('rotary') and _MCH[0] not in _LESLIE_CH:
                # a Rotary: the part through our Leslie, its rotors as the type
                # sets them and its speed as the file switches it
                _rs_ = _GSX.rotary_setup(_EFXEV, _MCH[0])
                if _rs_ is not None:
                    _LESLIE_CH[_MCH[0]] = _rs_
            if _ex.get('filter') and _MCH[0] not in _FILTER_CH:
                # a moving filter (a Phaser, a wah, a Step Flanger, a Humanizer):
                # its control over the file, from the effect's timeline
                _fc_ = _GSX.filter_setup(_EFXEV, _MCH[0],
                                         [(_n[2], _n[3], _n[4]) for _n in notes if _n[0] == _MCH[0]])
                if _fc_ is not None:
                    _FILTER_CH[_MCH[0]] = _fc_
            if _ex.get('trem') and _MCH[0] not in _TREM_CH:
                # a Tremolo Chorus's tremolo: the tremolo pass's (rate, depth, stereo)
                _TREM_CH[_MCH[0]] = tuple(_ex['trem'])
            if _ex.get('par'):
                # BRANCH B's part (gsefx.PARALLEL_TYPES), on the virtual channel:
                # the voice's own valve and speaker as A's, B's OD, chorus or
                # flanger, Leslie, moving filter -- and A's reverb send
                _vc, _eb = _MCH[0] + _GSX.VIRT, _ex['par']['B']
                _cv0 = chan_vol / max(_ex['level'] * _EFG, 1e-12)      # the part's level before the effect
                _ref = getattr(props, 'amp_reference', None)
                if getattr(props, 'amp_drive', 0.0) and _MCH[0] in _AMP_CH:
                    _AMP_CH[_vc] = _AMP_CH[_MCH[0]]                    # the voice's own valve, as A's
                    _AMP_IMB[_vc] = getattr(props, 'amp_imbalance', None)
                elif _eb['od_gain'] is not None:
                    _AMP_CH[_vc] = _GSX.PEDAL_AMP_DRIVE
                    _ref = _ref or 0.2289
                if _vc in _AMP_CH and _ref:
                    _st = sorted({0.0} | {float(t) for t, e in _EFXEV})
                    _AMP_REF[_vc] = ('steps', _ref * _cv0, [t * SR for t in _st],
                                     [((_GSX.at(_EFXEV, _vc, t) or _eb)['level']) for t in _st])
                    _AMP_LV0[_vc] = _eb['level']
                if _eb['cabinet'] and os.environ.get('TUNING_CABINET', '1') != '0':
                    _CAB_CH[_vc] = _eb['cabinet']
                elif getattr(props, 'cabinet', None) and os.environ.get('TUNING_CABINET', '1') != '0':
                    _CAB_CH[_vc] = props.cabinet
                if _eb['cf'] is not None:
                    _CHORUS_CH[_vc] = (0.0, _eb['cf'][0], 'gs', _GSX.mix_share(_EFXEV, _vc, SR))
                if _eb.get('rotary'):
                    _rs_ = _GSX.rotary_setup(_EFXEV, _vc)
                    if _rs_ is not None:
                        _LESLIE_CH[_vc] = _rs_
                if _eb.get('filter'):
                    _fc_ = _GSX.filter_setup(_EFXEV, _vc,
                                             [(_n[2], _n[3], _n[4]) for _n in notes if _n[0] == _MCH[0]])
                    if _fc_ is not None:
                        _FILTER_CH[_vc] = _fc_
                if _MCH[0] in _REVERB_CH:
                    _REVERB_CH[_vc] = _REVERB_CH[_MCH[0]]
        if getattr(props, 'sympathetic_gain', 0.0) and _MCH[0] not in _SYM_CH:
            _SYM_CH[_MCH[0]] = props
        if REGISTER and (getattr(props, 'register_gain', 0.0)
                         or getattr(props, 'register_knock_gain', 0.0)):
            if _MCH[0] not in _REG_CH:
                # ITS STRINGS ARE BUILT HERE, at its first note, for both the
                # whole table and the stream: whatever tonelib's per-note state
                # is now (the soft pedal, honky_detune) is the instrument's at
                # its first strike in either -- not "when the register ran".
                import register as _REG
                # (a voice with no damper pedal -- the harpsichord -- frees
                # nothing at CC64, as its notes ignore it)
                _REG_CH[_MCH[0]] = dict(pc=type(props), props=props, pan=pan, chan_vol=chan_vol,
                                        table=FREQ_N, strikes=[],
                                        pedal=(_PED_CH.get(ch, []) if getattr(props, 'damper_pedal', True)
                                               else []),
                                        strings=_REG.Strings(type(props), FREQ_N, pan, chan_vol, SR,
                                                             (string_partial, partial_decay,
                                                              unison_partial)))
            _sost = _SOST_HELD.get((ch, note, on))
            _REG_OPEN[0] = dict(key=note, on=on, rows=(_row0, None), av=props.attack_volume,
                                held=max(_raw_off, _sost) if _sost is not None else _raw_off)
            # THE CHOIRS IT PLUCKS (tonelib string_choirs): the ranks drawn at
            # the key-down, each on its choir's string. Only their rows drive
            # the bridge -- an undrawn rank's are emitted gated shut -- and the
            # key's other choirs are free while it is down.
            _chs = getattr(props, 'string_choirs', None)
            if _chs and organ and _orgk in rankev_of:
                _ci = {c[0]: i for i, c in enumerate(_chs)}
                _drawn = [r[0] for r in props.stop_ranks
                          if next((v for t, v in reversed(rankev_of[_orgk][r[0]]) if t <= on), 0.0) >= 0.5]
                _REG_OPEN[0]['plucked'] = sorted({_ci[props.rank_choirs.get(k, k)] for k in _drawn})
                _REG_OPEN[0]['gr'] = [grow_of[(_orgk, k)] for k in _drawn]
                # ...and each drawn rank's choir, by its gate row: which bridge
                # its partials drive the free strings through
                _REG_OPEN[0]['grc'] = {grow_of[(_orgk, k)]: _ci[props.rank_choirs.get(k, k)] for k in _drawn}
            _REG_CH[_MCH[0]]['strikes'].append(_REG_OPEN[0])
        if getattr(props, 'cabinet', None) and _MCH[0] not in _CAB_CH:
            # TUNING_CABINET=0 takes the speaker out, which is not a setting
            # anyone wants to play through -- it is the A/B that shows what the
            # cabinet is for, since a clipped signal without one has harmonics
            # all the way to Nyquist.
            if os.environ.get('TUNING_CABINET', '1') != '0':
                _CAB_CH[_MCH[0]] = props.cabinet
        if getattr(props, 'clav_panel', False) and _MCH[0] not in _CLAV_CH:
            # CC1 IS THE TONE ROCKERS. Six switches sit left of a D6's keyboard
            # and four of them are the tone section; the wheel sweeps those four
            # darkest to brightest. A file with no CC1 gets the panel at rest,
            # every rocker up, which is what CLAV_FLAT is.
            #
            # ONE VALUE FOR THE PIECE, from the channel's first CC1, the same
            # rule the amplifier's drive follows: a player sets the rockers and
            # then plays, where live it is a control being moved.
            _c1 = [v for t, cc, v in in_order(ccs.get(_MCH[0], [])) if cc == 1]
            _set = (int(round(_c1[0] / 127.0 * (len(T.CLAV_TONE) - 1)))
                    if _c1 else T.CLAV_FLAT)
            _set = int(os.environ.get('TUNING_CLAV', _set))
            if _set != T.CLAV_FLAT:
                _CLAV_CH[_MCH[0]] = _set
        if getattr(props, 'tremolo_depth', 0.0) and _MCH[0] not in _TREM_CH:
            # CC1 IS THE DEPTH KNOB. On a Rhodes suitcase and a Wurlitzer the
            # modulation depth is the one panel control a player moves while
            # playing, so the wheel is where it belongs -- and these voices ship
            # amp_drive 0, so the CC1-to-drive path above never fires and the
            # wheel is not being asked to do two jobs at once.
            #
            # A file with no CC1 gets no modulation, which is the panel's own
            # default position and what every file in the corpus will see.
            _c1 = [v for t, cc, v in in_order(ccs.get(_MCH[0], [])) if cc == 1]
            if getattr(props, 'tremolo_intrinsic', False):
                # AN INTRINSIC TREMOLO IS NOT A WHEEL EFFECT. GM 44 is called
                # Tremolo Strings: the stroke is the patch, so it is on at full
                # depth whatever CC1 says. Roland's SC-55 "Tremolo Str" is a
                # recording of a section bowing tremolo (its manual's instrument
                # table, p.66: one partial, no variation) -- the stroke is in
                # the sample and nothing turns it -- and its wheel is the pitch
                # vibrato every GS tone's is. So CC1 here is what it is on the
                # other bowed strings (the vibrato, a gesture: live's, not a
                # file's), and what live's panel says. It had scaled the depth
                # around full, which thinned a file's tremolo wherever it asked
                # for vibrato. A Rhodes is the other case and keeps the
                # behaviour below -- its panel default is off.
                _dep = float(props.tremolo_depth)
            else:
                _dep = float(props.tremolo_depth) * (_c1[0] / 127.0 if _c1 else 0.0)
            if _dep > 0.0:
                _TREM_CH[_MCH[0]] = (float(props.tremolo_hz), _dep,
                                bool(getattr(props, 'tremolo_stereo', False)),
                                float(getattr(props, 'tremolo_scatter', 0.0)))
        # CC93 CHORUS. The send is the CHANNEL's; the offsets are the VOICE's,
        # because on a string machine or a synth pad the chorus is part of what
        # the instrument is and its comb is already declared. Anything else
        # gets a plain pair, which is a chorus pedal in front of it.
        #
        # Read once per channel, like the other effect settings here: a send
        # that moved mid-note would have to scale the copies' gain per block,
        # and nothing in this file does that to a partial already written.
        # CC91 REVERB SEND IS A DISTANCE. This renderer has no wet/dry knob and
        # never did: roomtail sets the reverberant field against the direct
        # sound at the SOURCE DISTANCE, through the room constant
        # (roomtail.decay_and_level). T60 does not contain r at all; only the
        # ratio does, and it goes as r squared.
        #
        # So the send is how many times the nominal distance this channel
        # stands at, and GM's default of 40 IS that nominal distance -- a file
        # that never sends CC91 renders exactly as it did. 0 puts the source on
        # the microphone and 127 puts it 3.2 times out, which on the hall
        # preset is 11.8 m, past the 6-7.8 m where the room overtakes the
        # direct sound.
        #
        # Because the IR's SHAPE does not depend on r and only its amplitude
        # does, a whole channel's contribution to the tail is one scalar --
        # which is a textbook send bus, arrived at from the room equation
        # rather than bolted onto it.
        if _MCH[0] not in _REVERB_CH:
            _c91 = [v for t, cc, v in in_order(ccs.get(_MCH[0], [])) if cc == 91]
            if _c91:
                _REVERB_CH[_MCH[0]] = _c91[0] / float(GM_DEFAULT_REVERB)
            elif getattr(props, 'reverb_distance', None) is not None:
                # A VOICE'S OWN DISTANCE, where the file says none: the
                # gunshot stands back (tonelib.GunshotProperties). A CC91 on
                # the channel overrides it, as a desk's send would.
                _REVERB_CH[_MCH[0]] = float(props.reverb_distance)
        if _MCH[0] not in _CHORUS_CH:
            _c93t = [(t, v) for t, cc, v in in_order(ccs.get(_MCH[0], [])) if cc == 93]
            _c93 = [v for _, v in _c93t]
            if _c93 and len(set(_c93)) > 1 and max(_c93) > 0 and _GS_CHO and not MOOG_NEUTRAL:
                # ...AND ITS CC93 FOLLOWS THE SONG, as CC91 does (send_steps):
                # the share each row's onset finds, through the chorus pass's
                # own per-row share (chorus.expand's fourth)
                def _cshare(v, _l=_GS_CHO['dev']['level']):
                    _ca = v / 127.0 * _l
                    return _ca * _ca / (1.0 + _ca * _ca)
                _st = (np.array([int(round(t * SR)) for t, _ in _c93t], np.int64),
                       np.array([_cshare(v) for v in _c93], np.float64))
                _CHORUS_CH[_MCH[0]] = (float(_st[1][0]), _GS_CHO['dev'], 'gs',
                                       lambda non, _st=_st: step_at(_st, non))
            elif _c93:
                if _c93[0] > 0 and _GS_CHO and not MOOG_NEUTRAL:
                    # A SOUND CANVAS FILE'S CHORUS is its device (chorus.gs_copies).
                    # The device ADDS its output, at send x level, to the dry;
                    # here the share is that same power taken out of the dry
                    # (a^2 / (1 + a^2)), the level held as CC93's is
                    _ca = _c93[0] / 127.0 * _GS_CHO['dev']['level']
                    _CHORUS_CH[_MCH[0]] = (_ca * _ca / (1.0 + _ca * _ca), _GS_CHO['dev'], 'gs')
                elif _c93[0] > 0:
                    _CHORUS_CH[_MCH[0]] = (_c93[0] / 127.0, _CHR.offsets_for(props))
            elif getattr(props, 'chorus_send', None):
                # A VOICE THAT IS ITS INSTRUMENT THROUGH A CHORUS PEDAL (GS's
                # Chorus Gt): the pedal on by default, as the file's CC93 would
                # set it -- and a CC93 the file does send overrides it, 0 for off
                _CHORUS_CH[_MCH[0]] = (float(props.chorus_send), _CHR.offsets_for(props))
            elif getattr(props, 'detuned_pair', None):
                # a DETUNED voice's own pair (chorus._pair): GS's Detuned EP
                # and Organ; a CC93 on the channel is a chorus instead
                _CHORUS_CH[_MCH[0]] = (1.0, tuple(props.detuned_pair), 'pair')
        if getattr(props, 'leslie', False) and _MCH[0] not in _LESLIE_CH:
            # CC1 IS THE HALF-MOON SWITCH: >=64 tremolo, below chorale. A
            # rotor has momentum, so this is a history of requests and not a
            # speed -- leslie.Rotor spends real seconds getting between them.
            import leslie as _LES0
            _req = [(t, _LES0.zone(v)) for t, cc, v in in_order(ccs.get(_MCH[0], []))
                    if cc == 1]
            if not _req or _req[0][0] > 0.0:
                _req.insert(0, (0.0, _LES0.TREMOLO
                                if getattr(props, 'leslie_fast', True)
                                else _LES0.CHORALE))
            _LESLIE_CH[_MCH[0]] = _req
        seats = props.section_seats() if hasattr(props,'section_seats') else None
        if seats:
            li, ri, _sd0, _sd1 = seats[0]
            _DL[0] = _sd0*SR; _DL[1] = _sd1*SR
        cv = props.chiff_volume; cc = props.chiff_cycle
        crl = getattr(props,'chiff_release',1.0) or 0.0; sjit = props.sustain_jitter; csc = f0/440.0
        sjit_n = sjit; _pjit = getattr(props, 'jitter_by_partial', False)
        _CBW[0] = getattr(props,'chiff_bandwidth',None) or RAND_GRAN
        _CBW[1] = getattr(props,'chiff_bandwidth_hz',None) or 0.0
        _TB[0] = getattr(props,'tension_bend',0.0) * props.tension_stroke()
        # ...NOT ON A SLUR where the voice says so (tonelib tension_bend_slurs:
        # a hichiriki's enbai lips up only the note a phrase starts on)
        if _slurred and not getattr(props, 'tension_bend_slurs', True):
            _TB[0] = 0.0
        _TB[1] = getattr(props,'tension_settle_time',0.28) or 0.28
        _TB[2] = getattr(props,'tension_settle_cutoff',1.8)
        # A DRUM MACHINE'S SWEEP (tonelib tension_log): the same start, 1 +
        # bend, but falling evenly in PITCH, as an exponential control voltage
        # does; the kernel takes it as the start's ln-ratio and a NEGATIVE
        # cutoff, scaled down (synthkernel.c tbend_log: the linear lines read
        # it first, as a time, and must find it all but zero)
        if getattr(props, 'tension_log', False) and _TB[0] > -1.0:
            _TB[0] = math.log1p(_TB[0])
            _TB[2] = -abs(_TB[2]) / TBEND_CUT_SCALE
        _TBN = (_TB[0], _TB[1], _TB[2])   # note-level bend, restored per partial

        # ------------------------------------------------ THE GLIDE, per note
        #
        # A SEPARATE SLOT FROM _TB, and the two lines above are why: mode lock
        # overwrites the tension-bend triple PER PARTIAL a few lines down, and
        # mode lock is carried by brass and strings -- exactly the voices that
        # glide. Portamento cannot borrow those three floats because the voices
        # that need them are the voices already using them.
        #
        # THE RATIO CANCELS EVERYTHING THE CHANNEL DID. Source and target are
        # the same channel, so the static bend, the octave transposition and
        # the GM2 scale table are the same multiplier on both and divide out:
        # the tuning table's own ratio is the whole answer, and it is exact.
        _GL[0] = 0.0
        # THE SMEAR IS THE SAME GLIDE TERM, one step at a time: each rung of the
        # run arrives FROM the one below rather than starting on its own pitch.
        # It has to be that way round and not "leans toward the next", because
        # the kernel's curve always ENDS on the pitch the note was built at --
        # a glide here is something a note arrives from, never something it
        # departs toward.
        #
        # At CC5 = 0 tau collapses and every step is clean; opening it stretches
        # each arrival until a step is still moving when the next begins, and a
        # staircase with no flat left on it is a half-valve.
        if _gl is not None and _gl[1] > 0.0 and _gl[2] is not None:
            _stau = _gl[3] * _gl[1] * 0.75
            if _stau > 2e-3 and FREQ_N[_gl[2]] > 0.0:
                _GL[0] = T.glide_g(FREQ_N[note], FREQ_N[_gl[2]])
                _GL[1] = _stau
                _GL[2] = _stau * T.PORTA_SETTLE_TAUS
        _gsrc = _GLIDE_SRC.get((ch, note, on))
        _gmech = getattr(pc, 'glide_mechanism', None)
        if (_GL[0] == 0.0 and _gsrc is not None and _gmech
                and 0 <= _gsrc < len(FREQ_N) and FREQ_N[_gsrc] > 0.0):
            # CAN THE MECHANISM REACH? A hand and a slide have a compass and a
            # circuit does not, and a valved gliss does not reach at all -- it
            # crosses harmonics, which is a different thing and is handled by
            # the lattice rather than by this test.
            _reach = getattr(pc, 'glide_reach_semitones', None)
            if _reach is None or abs(note - _gsrc) <= _reach + 1e-9:
                _gg = T.glide_g(FREQ_N[note], FREQ_N[_gsrc])
                _gtau = T.glide_tau(_porta_cc5_at(ch, on),
                                    FREQ_N[note], FREQ_N[_gsrc], _gmech)
                _GL[0] = _gg
                _GL[1] = _gtau
                _GL[2] = _gtau * T.PORTA_SETTLE_TAUS
        # No _GLN beside _TBN: nothing overwrites the glide per partial, because
        # a glide is a fact about the NOTE. Mode lock is a fact about a partial,
        # which is the whole reason these are two triples and not one.
        # A pipe's passive modes start sharp and are pulled into lock by the drive
        # (mirrors tonelib: mode_lock_offset_for / mode_lock_time). It reuses the
        # kernel's per-partial pitch-bend slot -- a voice never needs both, since
        # tension bend is a struck string and mode lock is a driven air column.
        mls = getattr(props,'mode_lock_spread',0.0)
        stops = props.stop_ranks if organ else [("_",1.0,1.0)]
        # THE HARMONIUM'S EFFECT STOPS, each read at NOTE-ON -- the moment CC11
        # is read for loudness -- from the gate events the stop word made. See
        # tonelib above harmonium_expression_gain for all three.
        _hx = None; _hperc = False
        if organ and 'expression' in rankev_of[_orgk]:
            _st = lambda k: T.stop_drawn_at(rankev_of[_orgk].get(k, ()), on)
            if _st('expression'):
                _hx = v11
            _hperc = _st('percussion')
            if _st('tremolo') and getattr(props, 'stop_tremolo_depth', 0.0) > 0.0:
                _HTREM_CH[ch] = (float(props.stop_tremolo_hz),
                                 float(props.stop_tremolo_depth), False)
                _HT_PEND[0] = len(A['om'])
        transverse = []   # (freq, raw gain, decay dbps) of the main partials, for phantom pairing
        if getattr(props, 'moog', False):
            # A MOOG IS NOT A RANK. Its oscillators are its own partial sets,
            # every one tagged with this note's filter row, which carries the
            # contours the kernel evaluates in place of the envelope above --
            # so the envelope columns are neutral (a 1-sample fade, no decay)
            # and the release column only has to cover the release. The rows
            # it is emitted with are the same ones every voice uses: radiation,
            # the head, the room's images.
            import moog as _MG
            # GM's sound controllers are this instrument's knobs (moog.apply_gm),
            # both layers' alike
            _sd = _SND_PEND[0][2] if _SND_PEND[0] else None
            # A LAYERED VOICE (moog.layers_of) is two Messengers on one channel:
            # the whole note again for each panel, each with its own rows, the
            # two summed. A live template stays ONE knob-neutral set, which
            # live stamps once per layer (live.py, Slab.stamp's layer).
            for _lay in (('a',) if MOOG_NEUTRAL else _MG.layers_of(props)):
                _pan = _MG.apply_gm(_MG.panel_of(props, layer=_lay), _sd)
                _knr = tuple(_MG.kn_row(_pan))
                _kkey = (ch, _knr)
                if not MOOG_NEUTRAL and _mmgr is None and _kn_moves(ch):
                    # THE CHANNEL'S KNOBS OVER TIME: one row for every note of
                    # this voice on it, its knobs as the channel's sound
                    # controllers stand at each change (the note's own filter
                    # of them, as at its onset: what the class grants, its bias)
                    _kkey = (ch, 'moves', pc.__name__, _lay)
                    if _kkey not in _MOOG_KROW:
                        _kbase = _MG.panel_of(props, layer=_lay)

                        def _kn_at(_t):
                            _d = _snd_d(ch, _t)
                            if _sbias:
                                _d = dict(_d)
                                for _bk, _bv in _sbias.items():
                                    _d[_bk] = _d.get(_bk, 0.0) + _bv
                            _d = {_k: _v for _k, _v in _d.items() if _k in _sctl} if _sctl else {}
                            return tuple(_MG.kn_row(_MG.apply_gm(_kbase, _d)))
                        _kts = sorted({_et for _et, _q, _cc, _v in _SND_TL.get(ch, ())}
                                      | {_et for _et, _v in _CMXEV['cutoff'].get(ch, ())})
                        _MOOG_KROW[_kkey] = len(_MOOG_KN); _MOOG_KN.append(list(_kn_at(0.0)))
                        _MOOG_KVAR[_MOOG_KROW[_kkey]] = [(0, _kn_at(0.0))] + [
                            (int(_et * SR) // _MG.MG, _kn_at(_et)) for _et in _kts]
                if _kkey not in _MOOG_KROW:
                    _MOOG_KROW[_kkey] = len(_MOOG_KN); _MOOG_KN.append(list(_knr))
                # A VALVE AFTER THE LADDER (the charang) hears the filter at its
                # sustain: baked into the partials here, before tubeamp.expand
                # runs on them, and taken back out by the kernel (FT slot 11).
                _pre = bool(getattr(props, 'amp_drive', 0.0))
                _body = getattr(props, 'moog_body', None)       # formants, after it
                _FX[0] = len(_MOOG_FT)
                # THE MOD SECTION'S PITCH: the note's rows, if anything moves OSC 2
                _mpp = _MG.pitch_params(_pan)
                if _mpp is not None:
                    _mj0, _mc, _mr = _MG.pitch_rows(_mpp, float(non), float(noff), float(noff) + _MG.release_span(_pan) * SR + 4096.0,
                                                    SR, _MG.MG)
                    _MOOG_MPI.append([len(_MOOG_MPC), _mj0, len(_mc)])
                    _MOOG_MPC.extend(_mc.tolist()); _MOOG_MPR.extend(_mr.tolist())
                else:
                    _MOOG_MPI.append([0, 0, 1])
                # ...AND ITS SHAPE ROWS, if a shape moves (moog.shape_rows)
                _msf = _MG.shape_flags(_pan)
                if _msf:
                    _mj0, _mn, _mst, _moff, _mdat = _MG.shape_rows(
                        _MG.shape_params(_pan), float(non), float(noff),
                        float(noff) + _MG.release_span(_pan) * SR + 4096.0, SR, _MG.MG)
                    _MOOG_MKI.append([_MOOG_MPKN[0], _mj0, _mn, _mst] + _moff)
                    _MOOG_MPK.append(_mdat); _MOOG_MPKN[0] += len(_mdat)
                else:
                    _MOOG_MKI.append([0, 0, 1, 0, -1, -1, -1])
                _MOOG_FT.append(_MG.ft_row(_pan, f0, _MOOG_KROW[_kkey], _pre,
                                           (_MG.FT_PITCH if _mpp is not None else 0) | _msf))
                _mre = max(1.0, _MG.release_span(_pan) * SR)
                vb = props.voice_vibrato(f0, 0)
                _VB[0], _VB[1], _VB[2] = vb if vb else (0.0, 5.5, 0.0)
                _PL[0] = 0
                if MOOG_NEUTRAL:
                    # every harmonic, unit weight, phase 0, at its NOMINAL frequency
                    # (OSC 1 and 2 on the key, the SUB an octave under), over
                    # Nyquist included: the slab weighs them, and zeroes those the
                    # panel's octave and tuning put out of range.
                    _mparts = [(_o, _k, _fn * _k, 1.0, 0.0)
                               for _o, _fn, _n in ((_MG.OSC1, f0, _MG.OSC_HARMONICS),
                                                   (_MG.OSC2, f0, _MG.OSC_HARMONICS),
                                                   (_MG.SUB, f0 * 0.5, _MG.SUB_HARMONICS))
                               for _k in range(1, _n + 1)]
                    _mparts += [(_MG.NOISE, _k + 1, float(_MG.NOISE_HZ[_k]), 1.0, 0.0)
                                for _k in range(len(_MG.NOISE_HZ))]
                    _mparts.append((_MG.SELF, 1, f0, 1.0, 0.0))    # at the key; the slab moves it
                else:
                    _mparts = _MG.partials(_pan, f0, min(_MG.FMAX_HZ, SR / 2.0))
                _cbw = (_CBW[0], _CBW[1])
                # THE MF-104M after it, if the panel has the pedal on: this note's
                # rows, room images and all, are what its repeats are copied from
                _mf0 = len(A['om'])
                _fmi = _MG.fm_index(_pan)
                _fm1 = (2 * math.pi * f0 * _MG.osc_ratio(_pan, _MG.OSC1) / SR) if _fmi else 0.0
                _fmph = cmath.phase(_MG.osc_spectrum(_pan['osc1_wave'], 1)[0]) if _fmi else 0.0
                # THE UNISON (moog.unison: a supersaw's seven saws), each voice its
                # own detune, phase, drift and place; noise and the ladder's own
                # sine sound once, the centre voice's
                _uvs = None if MOOG_NEUTRAL else _MG.unison(getattr(props, 'moog_unison', None), f0)
                _umid = min(range(len(_uvs)), key=lambda i: abs(_uvs[i][0] - 1.0)) if _uvs else 0
                _vb0 = (_VB[0], _VB[1], _VB[2])
                for _osc, _k, _hf, _amp, _ph, _ur, _ug, _ul, _urr, _udr in (
                        (_o, _k0, _h, _a, _p0 + (2.0 * math.pi * _uv[2] * _k0
                                                 if _o in (_MG.OSC1, _MG.OSC2, _MG.SUB) else 0.0),
                         _uv[0], _uv[1], _uv[3], _uv[4], _uv[5])
                        for _o, _k0, _h, _a, _p0 in _mparts
                        for _ui, _uv in enumerate(_uvs or ((1.0, 1.0, 0.0, 1.0, 1.0, None),))
                        if not (_ui != _umid and _o in (_MG.NOISE, _MG.SELF))):
                    if _uvs:
                        # ...the voice's drift in the vibrato slot (the note's
                        # own vibrato where the voice has none)
                        _VB[0], _VB[1], _VB[2] = _udr if _udr else _vb0
                    _MK[0] = _osc * 4096 + _k
                    _FMW[0], _FMPH[0] = (_fm1, _fmph) if _osc == _MG.OSC2 else (0.0, 0.0)
                    # a noise band: its wash bandwidth, NEGATIVE, is what makes the
                    # kernel draw it as noise rather than as a tone (moog.NOISE)
                    _nz = _osc == _MG.NOISE
                    _CBW[0], _CBW[1] = (-_MG.NOISE_BW, 0.0) if _nz else _cbw
                    # NOISE GETS NO IMAGES. A reflection of noise is more noise,
                    # uncorrelated with the first -- nothing an ear can place --
                    # and the images doubled the dearest partials there are (a
                    # hash and a sine per sample). The tail still hears it.
                    _NOREFL[0] = _nz
                    # THE HEAD, THE RADIATION AND THE BODY AT THE KEY'S HARMONIC: where
                    # live's knob-neutral template reads them (moog.weights), so the two
                    # agree for a transposed oscillator too -- a fourth up was 8e-3
                    # apart. The pitch, and the ladder before a valve, are the true one.
                    _hn = (f0 * _k if _osc in (_MG.OSC1, _MG.OSC2) else f0 * 0.5 * _k if _osc == _MG.SUB
                           else f0 if _osc == _MG.SELF else _hf)
                    _gM = props.gain * _amp * props.radiation_gain(_hn)
                    if _body is not None:
                        _gM *= float(_body(_hn))
                    if _pre and not MOOG_NEUTRAL and _osc != _MG.SELF:
                        _gM *= float(_MG.sustain_gain(_pan, f0, _hf))
                    emit_partial(2 * math.pi * _hf * _ur / SR, _gM * _ug * _ul * props.hrtf_gain(_hn, li),
                                 _gM * _ug * _urr * props.hrtf_gain(_hn, ri), _gM * _ug, _hn, non, noff, 1.0, _mre,
                                 chiff, 0.0, 0.0, 0.0, 1.0,
                                 0.0 if _nz else cv * props.chiff_harmonic_gain(_k),
                                 cc, crl, sjit, csc, -1, 0, ph0=_ph)
                _CBW[0], _CBW[1] = _cbw
                # ...but not into a LIVE template (MOOG_NEUTRAL): live stamps its
                # own repeats, and a template carrying the file's would be echoed twice
                _mfst = None if MOOG_NEUTRAL else _MFD.settings(_pan)
                if _mfst is not None:
                    _MF104.append((_mf0, len(A['om']), _mfst))
                _NOREFL[0] = False
                _FMW[0] = _FMPH[0] = 0.0
                _MK[0] = 0
                _FX[0] = -1
                _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            _SND_PEND[0] = None      # its CC74/71 moved the ladder, not sound_shape
            stops = ()
        if getattr(props, 'strike_noise_db', ()):
            # THE HAMMER'S STRIKE (tonelib.GrandPianoProperties.strike_noise_db):
            # the felt's impact, the key bottoming, the board knocked -- a thump
            # under the note and noise between its partials, dying in tens of
            # ms. Without it a piano's attack is its partials alone, which is a
            # pluck (Ben). Noise rows a third octave apart, one to a band, their
            # level (Hz, dB re the note's gain) shifted by strike_noise_slope dB
            # an octave from A4, falling strike_noise_dbs; no room images, as
            # any noise. Emitted beside the note's partials, not instead.
            _cbw = (_CBW[0], _CBW[1])
            _CBW[0], _CBW[1] = -0.25, 0.0
            _NOREFL[0] = True
            _PL[0] = 0
            _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            _slr = math.log(10.0) / 20.0 * props.strike_noise_dbs
            # dB an octave from A4: strike_noise_octave_db where a class names
            # it (the harpsichord's pluck), else strike_noise_slope -- which on
            # SynthProperties also scales the CHIFF by attack_volume, a second
            # meaning a new voice need not inherit
            # ...read within strike_noise_span_hz where a class names one: a
            # slope fitted over a recorded compass is not extrapolated past it
            _sspan = getattr(props, 'strike_noise_span_hz', None)
            _sf0 = min(max(f0, _sspan[0]), _sspan[1]) if _sspan else f0
            _reg = getattr(props, 'strike_noise_octave_db', props.strike_noise_slope) \
                * math.log2(max(_sf0, 1.0) / 440.0)
            _sfade = max(1.0, props.strike_noise_fade_s * SR)
            # ...and its length a class may lengthen (strike_noise_len_s): a
            # slower strike than the grand's is still heard at 0.25 s
            _slen = (getattr(props, 'strike_noise_len_s', None) or 0.25) * SR
            # ...and a GATE closes it with the note (gate_time: a gated snare, a
            # drum machine's pad), as an amplifier closing cuts all it passes:
            # the Electronic toms' strike had rung on at -40 to -50 dB past it
            if getattr(props, 'gate_time', None) and getattr(props, 'one_shot', False):
                _slen = min(_slen, max(1.0, noff - non))
            # ONE ROW A BAND, and gone by 0.25 s (62 dB down at its 250 dB/s):
            # two a band, held 0.5 s, took live's ten-note chord past its block
            # budget (99th percentile 2.71 ms of 2.67)
            # A FLAM (strike_flam > 1: an ensemble clap): that many strikes,
            # each at its own offset within strike_flam_s and its own level
            # within strike_flam_db under the loudest -- several hands not quite
            # together. Drawn from the note itself, so a render repeats.
            _bursts = [(0.0, 0.0)]
            _nfl = int(getattr(props, 'strike_flam', 0) or 0)
            # ...OR A CROWD (strike_flam_rate: bursts a second through the
            # whole held note -- an audience's claps), each at its own instant
            # and level within strike_flam_db
            _frate = getattr(props, 'strike_flam_rate', 0.0) or 0.0
            _fspan = props.strike_flam_s
            if _frate > 0.0:
                _fspan = max(0.0, (noff - non) / SR)
                _nfl = max(2, int(round(_frate * _fspan)))
            _fbal = None
            _fpk = None
            if _frate > 0.0 and getattr(props, 'strike_flam_record', False):
                # A RECORD'S CLICKS (tonelib.PhonoNoiseProperties): ONE timeline,
                # drawn second by second of the piece from a seed of that
                # second, so every note of the voice sounding at once meets the
                # same clicks at the same instants -- a speck in the groove is
                # one event under the stylus -- and each click its own place in
                # the BALANCE, the same for all of them: a note's left ear takes
                # cos theta, its right sin theta (power kept). Its levels the
                # draw's, not renormalised a note, so two parts agree.
                _a0, _a1 = non / SR, noff / SR
                _bursts, _fbal = [], []
                for _ct, _cl, _cb in _record_clicks(props, _a1):
                    if _a0 <= _ct < _a1:
                        _bursts.append((_ct - _a0, _cl)); _fbal.append(_cb)
                if not _bursts:
                    _bursts, _fbal = [(0.0, -200.0)], [0.25 * math.pi]
            elif getattr(props, 'strike_flam_times', None):
                # ...OR A MACHINE'S (strike_flam_times: (s, dB) a burst): a
                # drum machine's clap is one sample, its bursts where its
                # envelope generator put them, the same on every note
                _bursts = [(float(_fb[0]), float(_fb[1])) for _fb in props.strike_flam_times]
                # ...each in its own place in the balance, where it says (a
                # stereo clap: tonelib.RfxStereoClapProperties)
                if all(len(_fb) > 2 for _fb in props.strike_flam_times):
                    _fbal = [float(_fb[2]) for _fb in props.strike_flam_times]
            elif getattr(props, 'strike_flam_people', None):
                # ...OR A FEW PEOPLE (strike_flam_people: (n, lowest and
                # highest claps a second, jitter, dB spread)): each clapping
                # at their own steady rate, from their own place in the
                # balance and at their own distance (level) -- coming in
                # raggedly within 0.2 s and each stopping at their own time in
                # the note's last third. Ben: "12 individuals in different
                # positions, clapping at different rates", where claps
                # scattered at a crowd's rate had read too frequent and too
                # broad. Drawn from the note, so a render repeats.
                _pn, _plo, _phi, _pjit, _pdb = props.strike_flam_people
                _prng = random.Random(int(round(on * 1e6)) * 137 + note * 11 + ch)
                _pspan = max(0.0, (noff - non) / SR)
                # ...AND EACH PERSON'S HANDS (strike_flam_people_peak: lowest
                # and highest Hz, dB, Q): the air cupped between their palms
                # ringing at its own pitch on every clap (Repp 1987; single
                # claps measured: Q 7-12 at 1.2-2 kHz, 20-34 dB over the
                # clap's median) -- one colour for all had sounded as rain
                _ppk = getattr(props, 'strike_flam_people_peak', None)
                _bursts, _fbal, _fpk = [], [], []
                for _p in range(int(_pn)):
                    _per = 1.0 / _prng.uniform(_plo, _phi)
                    _plvl = -_prng.uniform(0.0, _pdb)
                    _pang = _prng.uniform(0.08, 0.92) * 0.5 * math.pi
                    _phz = _ppk[0] * (_ppk[1] / _ppk[0]) ** _prng.random() if _ppk else None
                    _pt = _prng.uniform(0.0, 0.2)
                    _pend = _pspan * _prng.uniform(0.67, 1.0)
                    while _pt < _pend:
                        _bursts.append((_pt, _plvl + _prng.gauss(0.0, 1.0)))
                        _fbal.append(_pang)
                        _fpk.append(_phz)
                        _pt += _per * max(0.5, _prng.gauss(1.0, _pjit))
                if _bursts:
                    _t0 = min(b[0] for b in _bursts); _l0 = max(b[1] for b in _bursts)
                    _bursts = [(t - _t0, l - _l0) for t, l in _bursts]
                else:
                    _bursts, _fbal, _fpk = [(0.0, 0.0)], [0.25 * math.pi], [None]
            elif _nfl > 1:
                _frng = random.Random(int(round(on * 1e6)) * 131 + note * 7 + ch)
                _fexp = getattr(props, 'strike_flam_exp_db', 0.0) or 0.0
                if _fexp:
                    # ...ITS LEVELS EXPONENTIAL in dB under the loudest (a reed's
                    # crackle: each dB down ~1.6x as many), held within
                    # strike_flam_db
                    _bursts = [(_frng.uniform(0.0, _fspan),
                                -min(_frng.expovariate(1.0 / _fexp), props.strike_flam_db))
                               for _ in range(_nfl)]
                else:
                    _bursts = [(_frng.uniform(0.0, _fspan), -_frng.uniform(0.0, props.strike_flam_db))
                               for _ in range(_nfl)]
                _t0 = min(b[0] for b in _bursts); _l0 = max(b[1] for b in _bursts)
                # ...the first at the onset (a crowd's first clap is the cue);
                # a reed's crackle (strike_flam_exp_db) keeps its draw's times,
                # not a click on every note's start
                if _fexp:
                    _t0 = 0.0
                _bursts = [(t - _t0, l - _l0) for t, l in _bursts]
            # ...AND A LATE ONE (strike_noise_at: a surdo's hand), its table
            # moved strike_noise_cal_db
            _sat = (getattr(props, 'strike_noise_at', 0.0) or 0.0) * SR
            _scal = getattr(props, 'strike_noise_cal_db', 0.0) or 0.0
            # ...AND A SLOWER TAIL under it (strike_noise_tail: dB re the
            # strike, its own dB/s): the table again, quieter and longer -- a
            # music box's pin snaps off the tooth and is gone in 5 ms, while
            # the comb's own buzz under it lasts tens
            _bal = [(1.0, 1.0)] * len(_bursts) if _fbal is None else \
                [(math.sqrt(2.0) * math.cos(_c), math.sqrt(2.0) * math.sin(_c)) for _c in _fbal]
            _pks = _fpk if _fpk is not None else [None] * len(_bursts)
            _bursts = [(b, d, _slr, g, k) for (b, d), g, k in zip(_bursts, _bal, _pks)]
            _stail = getattr(props, 'strike_noise_tail', None)
            if _stail:
                _bursts += [(b, d + _stail[0], math.log(10.0) / 20.0 * _stail[1], g, k) for b, d, _, g, k in _bursts]
            for _boff, _bdb, _slr, (_bgl, _bgr), _bpk in _bursts:
                _bon = non + _sat + _boff * SR
                for _hf, _db in props.strike_noise_db:
                    if _hf >= 0.45 * SR:
                        continue
                    _gM = props.gain * 10.0 ** ((_db + _reg + _bdb + _scal) / 20.0)
                    emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li) * _bgl,
                                 _gM * props.hrtf_gain(_hf, ri) * _bgr, _gM, _hf, _bon, _bon + _slen,
                                 _sfade, 0.01 * SR, chiff, _slr, 0.0, 0.0, 0.0, 0.0, cc, crl, 0.0, csc, -1, 0)
                if _bpk:
                    # ...the air between the palms RINGING: a decaying sine at
                    # the person's pitch, _ppk[2] dB over the clap's colour
                    # there, dying as its Q says (27.3 dB/s a hertz of width)
                    _tab = props.strike_noise_db
                    _cdb = float(np.interp(math.log(_bpk), [math.log(_r[0]) for _r in _tab],
                                           [_r[1] for _r in _tab]))
                    _gM = props.gain * 10.0 ** ((_cdb + _ppk[2] + _reg + _bdb + _scal) / 20.0)
                    _plr = math.log(10.0) / 20.0 * 27.29 * _bpk / _ppk[3]
                    emit_partial(2 * math.pi * _bpk / SR, _gM * props.hrtf_gain(_bpk, li) * _bgl,
                                 _gM * props.hrtf_gain(_bpk, ri) * _bgr, _gM, _bpk, _bon, _bon + _slen,
                                 _sfade, 0.01 * SR, chiff, _plr, 0.0, 0.0, 0.0, 0.0, cc, crl, 0.0, csc, -1, 0)
            # ...AND MORE STRUCK THINGS THAN ONE (strike_noise_layers: (table,
            # rise s, dB/s, length s) each): an orchestra hit's bass drum, which
            # BLOOMS -- its boom peaks 50-100 ms in -- and its cymbal, which
            # rings on above the rest. One table has one rise and one fall; a
            # drum and a cymbal do not share them.
            for _ltab, _lrise, _ldbs, _llen in getattr(props, 'strike_noise_layers', ()):
                _lslr = math.log(10.0) / 20.0 * _ldbs
                # ...closed by a gate with the note, as the strike is
                if getattr(props, 'gate_time', None) and getattr(props, 'one_shot', False):
                    _llen = min(_llen, max(1.0, noff - non) / SR)
                for _hf, _db in _ltab:
                    if _hf >= 0.45 * SR:
                        continue
                    _gM = props.gain * 10.0 ** ((_db + _reg) / 20.0)
                    emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li),
                                 _gM * props.hrtf_gain(_hf, ri), _gM, _hf, non, non + _llen * SR,
                                 max(1.0, _lrise * SR), 0.01 * SR, chiff, _lslr, 0.0, 0.0, 0.0, 0.0,
                                 cc, crl, 0.0, csc, -1, 0)
            _CBW[0], _CBW[1] = _cbw
            _NOREFL[0] = False
        if getattr(props, 'struck_layer', None):
            # A STRUCK, PITCHED LAYER (tonelib.SynthProperties.struck_layer):
            # another instrument struck with the note -- an orchestra hit's
            # TIMPANI on its root -- as that instrument's own modes (a kettle's
            # 1 : 1.488 : 1.963 ..., its measured levels), tuned to the note
            # moved by octaves into the drum's range, with its own rise and
            # fall. A rank cannot do it: a rank's partials sit on the
            # harmonic series whatever class lends them their levels.
            _scls, _sdb, _srise, _sdbs = props.struck_layer
            _lo, _hi = getattr(props, 'struck_layer_range', (73.42, 146.83))
            _ft = f0
            while _ft >= _hi:
                _ft *= 0.5
            while _ft < _lo:
                _ft *= 2.0
            _sp = T.rank_spectrum(_scls)(_ft, pan, 1.0, chan_vol)
            _nm = len(getattr(_sp, 'mode_ratios', None) or ()) or 8
            _hv = [_sp.harmonic_volume(_m) for _m in range(1, _nm + 1)]
            _hmax = max(_hv) if _hv and max(_hv) > 0.0 else 1.0
            _sslr = math.log(10.0) / 20.0 * _sdbs
            _srng = random.Random(int(round(on * 1e6)) * 149 + note * 13 + ch)
            for _m, _h in enumerate(_hv, 1):
                _hf = _ft * _sp.mode_ratio(_m)
                if _h <= 0.0 or _hf >= 0.45 * SR:
                    continue
                _gM = props.gain * 10.0 ** (_sdb / 20.0) * _h / _hmax
                emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li),
                             _gM * props.hrtf_gain(_hf, ri), _gM, _hf, non, non + 1.5 * SR,
                             max(1.0, _srise * SR), rel, 0.0, _sslr, 0.0, 0.0, 0.0, 0.0,
                             cc, crl, 0.0, csc, -1, 0, ph0=_srng.random() * 2.0 * math.pi)
        if getattr(props, 'ring_db', ()):
            # THE OTHER TINES (tonelib.SynthProperties.ring_db): fixed
            # frequencies, the instrument's own, rung through the bridge by
            # every pluck -- sines, each dying at its own rate. A row on one of
            # this note's own modes is the plucked tine itself: skipped. No
            # damper lifts them: they ring 4 s (76 dB at the slowest, 19 dB/s).
            _own = [f0 * r for r in (props.mode_ratios or (1.0, 2.0))] + [2.0 * f0]
            _PL[0] = 0
            _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            # their phases from the note, not the render's seeded stream, which
            # every later note's jitter draws from
            _rrng = random.Random(int(round(on * 1e6)) * 137 + note * 11 + ch)
            # ...AND OFF THE WHEEL: another string, a tine, a drumhead does not
            # move when the played string is bent (no bend row; the fader's
            # still) -- the banjo's G3 string was following a semitone's bend
            _r0, _bkeep = len(A['om']), _BR[0]
            _BR[0] = -1
            _RINGF[0] = True
            for _hf, _db, _dps in props.ring_db:
                # ...TUNED AS THE NOTES ARE: a row is the nearest key and its
                # offset from 12-TET at A440 (none for the koto's strings, the
                # measured tines' own for the kalimba), so the other strings
                # sit in the tuning the music is played in -- the key's
                # frequency in the table in force at this note's onset
                _rk = int(round(69.0 + 12.0 * math.log2(_hf / 440.0)))
                if _rk in FREQ_N:
                    _hf = FREQ_N[_rk] * _hf / (440.0 * 2.0 ** ((_rk - 69.0) / 12.0))
                if _hf >= 0.45 * SR or any(abs(_hf / _q - 1.0) < props.ring_skip for _q in _own):
                    continue
                _gM = props.gain * 10.0 ** (_db / 20.0)
                emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li),
                             _gM * props.hrtf_gain(_hf, ri), _gM, _hf, non, max(noff, non + 4.0 * SR),
                             fade, rel, chiff, math.log(10.0) / 20.0 * _dps, 0.0, 0.0, 0.0, 0.0,
                             cc, crl, 0.0, csc, -1, 0, ph0=_rrng.random() * 2.0 * math.pi)
            _BR[0] = _bkeep
            _RINGF[0] = False
            if len(A['om']) > _r0:
                _RING.append((_r0, len(A['om'])))
        if getattr(props, 'touch_leak_db', None) is not None and (props.harmonic_touch or 1) > 1:
            # A TOUCHED STRING'S OTHER MODES (tonelib.SynthProperties.touch_leak_db):
            # the modes the finger kills sound for a moment first, at k/n of
            # the note -- between its harmonics, not on them -- each as the
            # string would have it untouched, dying at touch_leak_dbs. Their
            # phases from the note, as the ring rows' are.
            _n = props.harmonic_touch
            _fs = f0 / _n
            _Bs = (props.inharmonicity_coefficient_for_frequency(_fs)
                   if props.inharmonicity_dynamic else props.inharmonicity_coefficient)
            _PL[0] = 0
            _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            _lrng = random.Random(int(round(on * 1e6)) * 149 + note * 17 + ch)
            _llr = math.log(10.0) / 20.0 * props.touch_leak_dbs
            for _k, _a in props.touch_leak_modes():
                _hf = _fs * _k * (1.0 + 0.5 * (_k * _k - 1.0) * _Bs if _Bs > 0 else 1.0)
                if _hf >= 0.45 * SR:
                    continue
                _gM = _a * props.radiation_gain(_hf)
                emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li),
                             _gM * props.hrtf_gain(_hf, ri), _gM, _hf, non, max(noff, non + 0.5 * SR),
                             fade, rel, chiff, _llr, 0.0, 0.0, 0.0, 0.0,
                             cc, crl, 0.0, csc, -1, 0, ph0=_lrng.random() * 2.0 * math.pi)
        if getattr(props, 'breath_noise_db', ()):
            # THE BREATH (tonelib.SynthProperties.breath_noise_db): the jet's
            # own noise, held for the note -- the strike's rows, but sustained
            # and released with the note. Its colour is its own table (a
            # recorder's peaks near 1.3 kHz whatever the note), not skirts on
            # the partials, which put it where the partials are.
            _cbw = (_CBW[0], _CBW[1])
            _CBW[0], _CBW[1] = -0.25, 0.0
            _NOREFL[0] = True
            _PL[0] = 0
            _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            _bfade = max(1.0, props.breath_noise_fade_s * SR)
            # ...and on a SLUR the player never stopped blowing: where the voice
            # says so (breath_noise_slur), the breath takes the legato attack,
            # not its swell from silence
            if _slurred and getattr(props, 'breath_noise_slur', False):
                _bfade = max(1.0, T.slur_attack(props.breath_noise_fade_s, props) * SR)
            # ...wavering on its own gate row (breath_noise_wobble_db), if the
            # channel has one
            _bkeep = _BR[0]
            if ch in bbrow_of and props.breath_noise_wobble_db > 0.0:
                _BR[0] = bbrow_of[ch][1]
            # EACH BAND breath_noise_rows ROWS, spread across it: one noise row
            # keeps its level as it turns, smoother than noise (an ocean drum's
            # hiss read kurtosis 2.5 on one, the takes 3.0); a few summed are not
            _k = int(getattr(props, 'breath_noise_rows', 1))
            for _hf, _db in [(_bf * 2.0 ** ((_j - 0.5 * (_k - 1)) / (3.0 * _k)), _bd - 10.0 * math.log10(_k))
                             for _bf, _bd in props.breath_noise_at(f0) for _j in range(_k)]:
                if _hf >= 0.45 * SR:
                    continue
                _gM = props.gain * 10.0 ** (_db / 20.0)
                emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li),
                             _gM * props.hrtf_gain(_hf, ri), _gM, _hf, non, noff,
                             _bfade, rel, chiff, 0.0, 0.0, 0.0, 1.0, 0.0, cc, crl, 0.0, csc, -1, 0)
            _BR[0] = _bkeep
            _CBW[0], _CBW[1] = _cbw
            _NOREFL[0] = False
        if getattr(props, 'grains', ()):
            # GRAINS (tonelib.SynthProperties.grains): sparse damped sines at
            # Poisson instants through the held note -- an ocean drum's beads
            # landing on the head (the drips) and on each other (the ticks).
            # Drawn from the note, so a render repeats; on the breath noise's
            # swell (the beads run as the frame tilts); no room images.
            _cbw = (_CBW[0], _CBW[1])
            _CBW[0], _CBW[1] = 0.0, 0.0
            _NOREFL[0] = True
            _PL[0] = 0
            _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            _bkeep = _BR[0]
            if ch in bbrow_of and props.breath_noise_wobble_db > 0.0:
                _BR[0] = bbrow_of[ch][1]
            _grng = random.Random(int(round(on * 1e6)) * 139 + note * 13 + ch)
            _glkeep = (_GL[0], _GL[1], _GL[2])
            _gr0 = len(A['om'])
            for _row in props.grains:
                _lo, _hi, _rate, _db, _dsc, _dps = _row[:6]
                # ...and a GLIDE where the row carries one (a bubble's ring
                # rising as it nears the surface): it starts at _rise times its
                # pitch and settles onto it in _gtau -- the note glide's own
                # term, each grain its own. Six-field rows (the ocean drum's
                # beads) emit exactly as before.
                if len(_row) > 6:
                    _rise, _gtau = _row[6], _row[7]
                    _GL[0], _GL[1], _GL[2] = 1.0 / _rise - 1.0, _gtau, _gtau * T.PORTA_SETTLE_TAUS
                # ...ON A CLOCK where the rate is NEGATIVE: one every -1/rate s from
                # the onset, each 7% rms off it (a machine gun's cyclic rate,
                # 4.9 ms on its 69). Poisson rows draw as before
                _per = -1.0 / _rate if _rate < 0.0 else 0.0
                _t = non if _per else non + _grng.expovariate(_rate) * SR
                _glr = math.log(10.0) / 20.0 * _dps
                # ...and a CLUSTER where the row carries a ninth field: that many
                # sines at one instant, each its own pitch across the band, at
                # 1/sqrt(n) -- with random phases a broadband CLICK, as a drop's
                # impact is (a rain drop reads +6 to +11 dB over its hiss in every
                # octave from 500 Hz to 16 kHz). One a grain otherwise, as before.
                _ncl = int(_row[8]) if len(_row) > 8 else 1
                _gcl = 1.0 / math.sqrt(_ncl)
                while _t < noff:
                    if _ncl == 1:
                        # the draws in their old order: pitch, then level
                        _hf = _lo * (_hi / _lo) ** _grng.random()
                        _gM0 = props.gain * 10.0 ** ((_db - _grng.uniform(0.0, _dsc)) / 20.0)
                    else:
                        _gM0 = props.gain * 10.0 ** ((_db - _grng.uniform(0.0, _dsc)) / 20.0) * _gcl
                    for _k in range(_ncl):
                        if _ncl > 1:
                            _hf = _lo * (_hi / _lo) ** _grng.random()
                        _gM = _gM0
                        if _hf < 0.45 * SR:
                            emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li),
                                         _gM * props.hrtf_gain(_hf, ri), _gM, _hf, _t, _t + 0.1 * SR,
                                         8.0, 0.005 * SR, chiff, _glr, 0.0, 0.0, 0.0, 0.0, cc, crl, 0.0, csc,
                                         -1, 0, ph0=_grng.random() * 2.0 * math.pi)
                    _t += (max(0.2 * _per, _grng.gauss(_per, 0.07 * _per)) if _per
                           else _grng.expovariate(_rate)) * SR
                _GL[0], _GL[1], _GL[2] = _glkeep
            _GRAIN_ROWS.append((_gr0, len(A['om'])))
            _BR[0] = _bkeep
            _CBW[0], _CBW[1] = _cbw
            _NOREFL[0] = False
        if getattr(props, 'shake_noise', False):
            # A SHAKE AS SHAPED NOISE (tonelib.ShakenNoiseProperties): its
            # spectrum as noise bands (a negative wash bandwidth, the kernel's
            # noise row), each band twice -- the shake, swelling in over rise_s
            # and held for shake_frac of the note, then the settle, falling
            # settle_db over settle_s. The settle fades in over the shake's
            # last _xf while the shake fades out over the first half of it, so
            # the two (uncorrelated: their onsets seed them) meet at no more
            # than +1 dB rather than dipping 3. No room images, as any noise.
            _shk = max(props.shake_min_s, _held * props.shake_frac)
            _xf = min(props.shake_xfade_s, 0.5 * _shk)
            _rise = max(1e-4, min(props.rise_s, _shk - _xf)) * SR
            _slr = math.log(10.0) / 20.0 * props.settle_db / props.settle_s
            _sgain = math.exp(_slr * _xf)       # the settle's own fall over its fade, given back
            _son = non + (_shk - _xf) * SR
            _cbw = (_CBW[0], _CBW[1])
            _CBW[0], _CBW[1] = -props.noise_rel, 0.0
            _NOREFL[0] = True
            _PL[0] = 0
            _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            # EACH BAND SEVERAL ROWS, spread across it: a noise row turns its
            # phase but keeps its level, so one a band is smoother than noise
            # (kurtosis 2.5 where the takes read 3.0); a few summed are not
            _k = int(props.noise_rows)
            _rows = [(_bf * 2.0 ** ((_j - 0.5 * (_k - 1)) / (3.0 * _k)), _db - 10.0 * math.log10(_k))
                     for _bf, _db in props.noise_bands for _j in range(_k)]
            for _hf, _db in _rows:
                if _hf >= 0.45 * SR:
                    continue
                _gM = props.gain * 10.0 ** (_db / 20.0) * props.radiation_gain(_hf)
                _gl, _gr = props.hrtf_gain(_hf, li), props.hrtf_gain(_hf, ri)
                _om = 2 * math.pi * _hf / SR
                emit_partial(_om, _gM * _gl, _gM * _gr, _gM, _hf, non, non + (_shk - 0.5 * _xf) * SR,
                             _rise, _xf * SR, chiff, 0.0, 0.0, 0.0, 1.0, 0.0, cc, crl, 0.0, csc, -1, 0)
                _g2 = _gM * _sgain
                emit_partial(_om, _g2 * _gl, _g2 * _gr, _g2, _hf, _son,
                             _son + (_xf + 4.0 * props.settle_s) * SR, _xf * SR, 0.02 * SR, chiff,
                             _slr, 0.0, 0.0, 0.0, 0.0, cc, crl, 0.0, csc, -1, 0)
            _CBW[0], _CBW[1] = _cbw
            _NOREFL[0] = False
            stops = ()
        if getattr(props, 'noise_events', ()):
            # TIMED NOISE BANDS (tonelib.SfxHeartbeatProperties' blood flow):
            # each (Hz, dB, start s, end s) a noise band sounding over its own
            # span of the note, ramped in and out over noise_event_ramp_s --
            # a spectrum whose top follows a curve, built from the bands it
            # reaches. Beside the class's partials, not in place of them. As
            # the shake's rows: several a band, no room images.
            _cbw = (_CBW[0], _CBW[1])
            _CBW[0], _CBW[1] = -props.noise_rel, 0.0
            _NOREFL[0] = True
            _PL[0] = 0
            _vbk = (_VB[0], _VB[1], _VB[2])
            _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            _k = int(props.noise_rows)
            _rmp = props.noise_event_ramp_s * SR
            for _bf, _db, _t0, _t1 in props.noise_events:
                for _j in range(_k):
                    _hf = _bf * 2.0 ** ((_j - 0.5 * (_k - 1)) / (3.0 * _k))
                    if _hf >= 0.45 * SR:
                        continue
                    _gM = props.gain * 10.0 ** ((_db - 10.0 * math.log10(_k)) / 20.0) * props.radiation_gain(_hf)
                    _gl, _gr = props.hrtf_gain(_hf, li), props.hrtf_gain(_hf, ri)
                    emit_partial(2 * math.pi * _hf / SR, _gM * _gl, _gM * _gr, _gM, _hf, non + _t0 * SR,
                                 non + _t1 * SR, _rmp, _rmp, chiff, 0.0, 0.0, 0.0, 1.0, 0.0, cc, crl, 0.0,
                                 csc, -1, 0)
            _CBW[0], _CBW[1] = _cbw
            _VB[0], _VB[1], _VB[2] = _vbk
            _NOREFL[0] = False
        if getattr(props, 'pulse', False):
            # A PRESSURE PULSE (the gunshot's N-wave, tonelib.pulse_series): a
            # waveform written as one period of a Fourier series, every
            # partial under ONE gate. The kernel evaluates a gate at block
            # edges and ramps between them, so the gate is opened a full two
            # blocks before the pulse and shut a block after it, and the
            # period is long enough that the next pulse falls after it has
            # shut. Where it ramps, the series sums to zero -- so the ramps
            # multiply nothing, and the pulse is the waveform exactly. The
            # onset is moved earlier by the lead, so the pulse lands on the
            # note (live: the lead is two of its own short blocks, 5 ms).
            _T = props.pulse_length(f0)
            _lead = 2.0 * BLK
            _rel = 0.002 * SR
            _gate = _lead + _T * SR + BLK
            _per = (_gate + _rel + BLK + 0.002 * SR) / SR
            _pnon = max(0.0, non - _lead)
            # ...AND A NOTE INSIDE THE FIRST TWO BLOCKS keeps its time: the
            # gate cannot open before the render does, so the pulse sits
            # NON into the series rather than a full lead -- where it had
            # landed up to two blocks late (23 ms at the file's 512, 5 ms at
            # live's 128) behind its own blast. Its first block's ramp then
            # touches the pulse; a later note is as before
            _t0 = _lead if non >= _lead else non
            _PL[0] = 0
            _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0
            for _hf, _amp, _ph in T.pulse_series(_T, _t0 / SR, _per, props.pulse_fmax,
                                                 props.pulse_taper):
                _gM = props.gain * _amp * props.radiation_gain(_hf)
                emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li),
                             _gM * props.hrtf_gain(_hf, ri), _gM, _hf, _pnon, _pnon + _gate,
                             1.0, _rel, chiff, 0.0, 0.0, 0.0, 1.0, 0.0,
                             cc, crl, 0.0, csc, -1, 0, ph0=_ph)
            stops = ()
        _bnote = _BR[0]          # the note's own row, which a chest row multiplies
        for key, ratio, gain, *rest in stops:
            # A stop with no pipes (the harmonium's Expression, Percussion,
            # Tremolo) has a gate and no partials; a rank with a key range (its
            # split registers) has none outside it.
            if ratio is None:
                continue
            if len(rest) > 3 and rest[3] is not None and not (rest[3][0] <= note <= rest[3][1]):
                continue
            # A RANK THAT IS NOTHING UNTIL DRAWN (rank_only_when_drawn: the
            # tonewheel's percussion taps): on a channel that never draws it,
            # not emitted at all -- gated shut, its rows still moved the voice
            # around them (GM 18 by -28 dB through its driven amplifier)
            if (rest and rest[0] is not None and getattr(rest[0], 'rank_only_when_drawn', False)
                    and not any(v >= 0.5 for _t, v in rankev_of[_orgk].get(key, ()))):
                continue
            spec_cls = rest[0] if rest else None   # cross-family stop: borrow this voice's spectrum only
            # the chest's wind (wind.py): this rank's family's row on its channel
            if organ and (ch, key) in wrow_of:
                _w = wrow_of[(ch, key)]
                _BR[0] = wcombo.get((_bnote, _w), _w) if _bnote >= 0 else _w
            # a siren's row of holes turns with its own disc (_SIREN_AT)
            if _sir is not None and len(_sir[0]) > 1:
                _BR[0] = _sir[0][1] if key in getattr(props, 'siren_upper', ()) else _sir[0][0]
            dyn = rest[1] if len(rest) > 1 else False   # force flue-dynamic inharmonicity (hybrid-lock)
            # "BORROW THIS VOICE'S SPECTRUM ONLY" -- and the line under that
            # comment handed the borrowed class a velocity as well, so it also
            # borrowed its TOUCH. A church organ's Gedackt is written as a
            # StoppedPipeProperties, which sits above OrganProperties in the
            # chain and therefore takes SynthProperties' touch-sensitive
            # default: measured, one rank of a patch whose own class says
            # velocity does nothing scaled by (vel/127)^2 while the other seven
            # did not. 33 partials of 491, exactly the odd harmonics of the
            # fundamental, which is what a stopped pipe has.
            #
            # A rank is part of the instrument that draws it. Whose wind chest
            # a pipe stands on is the parent's question, not the spectrum's.
            # This also moves the bagpipe's trumpet rank and the synth lead's
            # flute, both borrowed into voices with no touch of their own.
            _rank_av = ((vel/127.0)**2 if (getattr(props, 'touch_sensitive', True) or not T.FIXED_TOUCH)
                        else 1.0)
            spv = T.rank_spectrum(spec_cls)(f0, pan, _rank_av, chan_vol) if spec_cls else None
            # A CHOIR AT ANOTHER FOOTAGE IS ITS OWN STRING (tonelib string_choirs):
            # the harpsichord's 4' is a string at twice the key's pitch, its
            # spectrum and decay that string's -- not the 8''s read at 2m, which
            # rang it as long as the 8' and coloured it by the key's register.
            # register.Strings builds the same string (tonelib.own_string).
            _ownstr = None
            if (spv is None and getattr(props, 'string_choirs', None)
                    and not isinstance(ratio, (list, tuple)) and ratio != 1.0):
                _ownstr = spv = T.own_string(props, f0 * ratio, pan, _rank_av, chan_vol)
            hv_fn = spv.harmonic_volume if spv else props.harmonic_volume
            # A RANK'S REGISTER IS ITS OWN PITCH: a voice with measured series by
            # register (mode_gains_low) takes the table at the rank's sounding
            # pitch, not the key's -- the shape only, its level as the class sets
            # it (the church organ's 4' over a low key is a middle-register pipe)
            # -- and so does a borrowed spectrum with tables of its own (the
            # console's Gedakt and reeds, measured on Pitea's)
            _tsrc = spv or props
            if (organ and (getattr(_tsrc, 'mode_gains_low', None) is not None
                           or getattr(_tsrc, 'mode_gains_points', None))
                    and not isinstance(ratio, (list, tuple)) and ratio != 1.0):
                _mgn, _mgr = _tsrc.mode_gains_here(), _tsrc.mode_gains_at(f0 * ratio)
                hv_fn = (lambda m, _b=_tsrc.harmonic_volume, _n=_mgn, _r=_mgr:
                         _b(m) * (_r[m - 1] / _n[m - 1]) if m - 1 < len(_n) and _n[m - 1] > 0 else 0.0)
            # ...UNLESS THE BORROWED CLASS IS ITSELF AN ORGAN PIPE, when the rank
            # IS that pipe: its ceiling (where its upperwork breaks back), its
            # decay, its chiff -- a reed has none -- and its sustain are its own,
            # not the host's. The pipe reeds on the church organ's console
            # (tonelib, bits 8-11) need exactly this: borrowing only the
            # spectrum put them 5 dB hot (the flue's zero decay against the
            # reed's own), chiffed, and broken back at the flue's 2100 Hz rather
            # than their 1600 -- 4-8 dB off in the upper octaves. A class opts in
            # with rank_is_pipe (the pipe reed does); NOT "is an OrganProperties",
            # which the brass also is by descent -- the flute (a stopped pipe),
            # the trumpet (brass) and the harpsichord's ranks render as they did.
            # A rank may also NAME its pipe (the sixth element): the console's
            # trumpet is a brass SPECTRUM on a reed PIPE, which is what it was
            # when it stood in the reed organ, whose pipe was its host.
            pipe_cls = rest[2] if len(rest) > 2 else None
            if pipe_cls is not None:
                rp = T.rank_spectrum(pipe_cls)(f0, pan, _rank_av, chan_vol)
            elif spv is not None and (getattr(spv, 'rank_is_pipe', False) or _ownstr is not None):
                rp = spv
            else:
                rp = props
            # EACH PIPE SPEAKS AS ITSELF (props.rank_speech_own_pitch, the church
            # organ): its speech, harmonic order and overshoot are its own
            # class's -- the pipe reed's, or a borrowed spectrum's that says
            # rank_speech (the Gedakt) -- and timed by its OWN pitch, so a 4'
            # over a key speaks as the 4' pipe it is. Otherwise the host's,
            # by the key, as before.
            _own = organ and getattr(props, 'rank_speech_own_pitch', False)
            _sc = (rp if rp is not props else
                   spv if (_own and spv is not None and getattr(spv, 'rank_speech', False)) else props)
            _f0s = (f0 * (min(ratio) if isinstance(ratio, (list, tuple)) else ratio)
                    if _own and ratio else f0)
            if _own:
                _PUSH_SEG.append((len(A['om']), _sc, _f0s))
            # ...and its CHIFF, the edge's spit: the pipe's own, where it is a
            # pipe of its own (a Gedakt's is not a principal's)
            _cp = _sc if _sc is not props else rp
            cv_r = _cp.chiff_volume if _cp is not props else cv
            cc_r = _cp.chiff_cycle if _cp is not props else cc
            # Its speech too: the attack, release and chiff times were set per
            # NOTE from the host's pipe, so the rank's are the host's scaled by
            # its own speech against the host's -- which keeps whatever the note
            # already folded in (a slur, CC73, the caps).
            if _sc is not props or _f0s != f0:
                def _speech(pp, ff):
                    a = pp.attack_time if pp.attack_time is not None else pp.chiff_max_valve_time
                    r = pp.release_valve_time if pp.release_valve_time is not None else pp.chiff_max_valve_time
                    return pp.speech_time(a, ff), pp.speech_time(r, ff)
                _ha, _hr = _speech(props, f0); _ra, _rr = _speech(_sc, _f0s)
                fade_r = fade * (_ra / _ha) if _ha > 0 else fade
                rel_r = rel * (_rr / _hr) if _hr > 0 else rel
                _hc = props.chiff_time(f0, _ha)
                chiff_r = chiff * (_sc.chiff_time(_f0s, _ra) / _hc) if _hc > 0 else chiff
            else:
                fade_r, rel_r, chiff_r = fade, rel, chiff
            if _hperc and key in getattr(props, 'percussion_ranks', ()):
                # The hammer: min(attack, hammer), as a slur is min(attack, legato).
                fade_r = min(fade_r, max(1e-4, min(props.percussion_attack_s, _afm*dur))*SR)
            rank_B = (spv or props).inharmonicity_coefficient_for_frequency(f0) if dyn else B
            gr = grow_of[(_orgk,key)] if organ else -1; cr = crow_of[_orgk] if organ else 0
            # A drawn stop speaks (phase + attack fade start) at its draw time, not
            # the note onset -- a fresh pipe, matching the reference. Non-organ voices
            # always speak at note onset.
            if organ:
                sp = rank_speak_sec(rankev_of[_orgk][key], on, getattr(props,'attack_jitter',0.0))
                # A STOP DRAWN AFTER THE KEY LIFTED DOES NOT SPEAK on it: the
                # pallet is shut, as live stamps a drawn rank on the keys still
                # down and no others. Its gate opened on the note's release tail
                # (Ben, BuxWV 161: "registration changes bled a tiny fraction of
                # a second into the releases")
                # The DRAW is compared, not the speech: the attack jitter would
                # otherwise push a short note's rank past its own key-up, and a
                # rank drawn at the onset always speaks.
                _dr = rank_speak_sec(rankev_of[_orgk][key], on, 0.0)
                if _dr is not None and _dr > on and _dr >= _raw_off:
                    continue
                # ...nor one pushed in before the key-up and drawn again in the
                # release: what it had ends at the key-up. Only a rank that
                # spoke: one never drawn for the note is gated silent already,
                # and its release is left exactly as it was.
                if _dr is not None:
                    _drawn_off = 0.0
                    for _t, _tg in rankev_of[_orgk][key]:
                        if _t <= _raw_off: _drawn_off = _tg
                        else: break
                    if _drawn_off < 0.5:
                        rel_r = 1.0
                # ...and a Hammond's drawbar speaks when ITS contact closes
                # (tonelib.contact_offset_s): the key click
                if sp is not None:
                    sp += T.contact_offset_s(props, key, note)
                non_r = sp*SR if sp is not None else non
                # ...AND IT BOUNCES: a burst of noise at that contact, its own
                # drawbar's (its gate row, so a stop pushed in silences it and
                # live stamps it with the rank) -- the click's broadband part
                # (tonelib.TonewheelProperties.contact_noise_db)
                if sp is not None and getattr(props, 'contact_noise_db', ()):
                    _cbw = (_CBW[0], _CBW[1])
                    _CBW[0], _CBW[1] = -0.25, 0.0
                    _NOREFL[0] = True
                    _pl_keep = _PL[0]
                    _PL[0] = 0
                    _clr = math.log(10.0) / 20.0 * props.contact_noise_dbs
                    _cgr = grow_of[(_orgk, key)] if organ else -1
                    # dB re THIS DRAWBAR's own fundamental, as the stop sets it
                    _cref = hv_fn(1) * gain
                    for _hf, _db in props.contact_noise_db:
                        if _hf >= 0.45 * SR:
                            continue
                        _gM = _cref * 10.0 ** (_db / 20.0)
                        emit_partial(2 * math.pi * _hf / SR, _gM * props.hrtf_gain(_hf, li),
                                     _gM * props.hrtf_gain(_hf, ri), _gM, _hf, non_r, non_r + 0.1 * SR,
                                     1.0, 0.002 * SR, 0.0, _clr, 0.0, 0.0, 0.0, 0.0, cc, crl, 0.0, csc,
                                     _cgr, crow_of[_orgk] if organ else 0)
                    _CBW[0], _CBW[1] = _cbw
                    _NOREFL[0] = False
                    _PL[0] = _pl_keep
            else:
                non_r = non
            # Place this drawstop at its case position (shared across a compound rank).
            if organ and getattr(props,'spiral_spatial',False):
                _rx = props.rank_position_x(key)
                li,ri,_ld,_rd = props.hrtf_at(_rx)
                _DL[0] = _ld*SR; _DL[1] = _rd*SR; _PX[0] = _rx
            ceiling = getattr(rp,'pipe_ceiling_hz',None); bmode = getattr(rp,'pipe_break_mode','fold')
            # Compound rank (Mixtur): ratio is a LIST of footages; else a scalar. Each
            # sub-footage breaks back on the note's grid past the ceiling (mirrors
            # tonelib._build_registered_partials); only upperwork (>=2) breaks.
            # A HAMMOND'S LEAKAGE (tonelib.TonewheelProperties.drawbar_leak_db):
            # a drawn drawbar's closed contact carries the other wheel
            # positions faintly -- sines at the other drawbars' frequencies,
            # under this one's fundamental, on its own gate and envelope (so a
            # stop pushed in takes its leak with it, and live stamps it with
            # the rank)
            # ...THE DRAWBARS' CONTACTS ONLY: a rank with a class of its own
            # (the percussion taps, tonelib.TonewheelPercussionProperties) is
            # not on a drawbar's busbar -- it neither leaks nor is leaked
            _lk = getattr(props, 'drawbar_leak_db', None)
            if organ and _lk is not None and not isinstance(ratio, (list, tuple)) and spv is None:
                _lrng = random.Random(int(round(on * 1e6)) * 157 + note * 23 + ch + 7 * len(key))
                _lref = hv_fn(1) * gain * 10.0 ** (_lk / 20.0)
                _pl_keep = _PL[0]
                _PL[0] = 0
                for _ok, _orat, *_or in stops:
                    if _orat is None or isinstance(_orat, (list, tuple)) or _ok == key:
                        continue
                    if len(_or) > 1 and _or[1] is not None:
                        continue
                    _lf = f0 * _orat
                    if _lf >= 0.45 * SR:
                        continue
                    _lg = _lref * props.radiation_gain(_lf, radius=_radius[0])
                    emit_partial(2*math.pi*_lf/SR, _lg*props.hrtf_gain(_lf, li), _lg*props.hrtf_gain(_lf, ri),
                                 _lg, _lf, non_r, noff, fade_r, rel_r, 0.0, 0.0, 0.0, 0.0,
                                 props.sustain_level, 0.0, cc, crl, 0.0, csc, gr, cr,
                                 ph0=2.0 * math.pi * _lrng.random())
                _PL[0] = _pl_keep
            _subs, _comp = ((T.mixture_ratios(props, key, ratio, f0)) if isinstance(ratio, (list, tuple))
                            else ([ratio], False))
            for sub in _subs:
                eff_ratio = sub
                # ...EACH MIXTURE PIPE ITS OWN REGISTER: the measured tables at
                # the pipe's pitch, as a single rank's are
                hv_sub = hv_fn
                if (organ and isinstance(ratio, (list, tuple)) and getattr(_tsrc, 'mode_gains_points', None)
                        and sub != 1.0):
                    _mgn, _mgr = _tsrc.mode_gains_here(), _tsrc.mode_gains_at(f0 * sub)
                    hv_sub = (lambda m, _b=_tsrc.harmonic_volume, _n=_mgn, _r=_mgr:
                              _b(m) * (_r[m - 1] / _n[m - 1]) if m - 1 < len(_n) and _n[m - 1] > 0 else 0.0)
                # only a MIXTURE breaks back (tonelib, the same): a single
                # upperwork stop runs the full compass; a composed one is
                # broken back by its composition (tonelib.mixture_ratios)
                if (ceiling and not _comp and isinstance(ratio, (list, tuple)) and sub >= 2.0
                        and f0*sub > ceiling):
                    if bmode == 'truncate': continue
                    while f0*eff_ratio > ceiling and eff_ratio >= 2.0: eff_ratio *= 0.5
                # ...AND A RANK THE TUNER LEFT A LITTLE OUT (tonelib.rank_detune_cents):
                # each key's own few cents, so its pair with the foundation beats
                _rdt = T.rank_detune_cents(props, key, note)
                if _rdt:
                    eff_ratio *= 2.0 ** (_rdt / 1200.0)
                _pps = getattr(props, 'partial_phase_spread', 0.0)
                _prng = random.Random(int(round(on * 1e6)) * 151 + note * 19 + ch) if _pps > 0.0 else None
                _ushare = getattr(props, 'unison_shares_phase', False)
                # ...AND ON A CLASS WITH CHOIRS, ITS CHOIR'S OWN WIRE (tonelib.
                # choir_stiffness, choir_partial_hz): the same string register.
                # Strings builds, so a free choir and a drawn one are one string
                _cho = T.choir_of(props, key)
                _cB = rank_B * T.choir_stiffness(props, _cho, note) if _cho else rank_B
                for m in range(1, props.max_harmonic+1):
                    _hh = string_partial(props, f0, eff_ratio, m, _cB)
                    if _hh is None: break
                    h, hf = _hh
                    if _cho:
                        hf += T.choir_partial_hz(props, _cho, note, m)
                    if hf > SR/2: break
                    hv = hv_sub(m)
                    if hv == 0.0: continue
                    # ...an aliasing sweep's harmonic on its own folded row
                    if _als is not None:
                        _BR[0] = _als[m - 1] if m - 1 < len(_als) else -1
                    # each partial's own jitter where the voice says so (a snare's
                    # wires are noise, its head is not); else the note's
                    sjit = rp.partial_jitter(m) if _pjit else sjit_n
                    # PER-PARTIAL ARRIVAL. A struck plate's middle spectrum
                    # arrives hundreds of ms after the strike (see
                    # SynthProperties.bloom_delay_for). This DELAYS the partial --
                    # its fade and its decay together -- rather than stretching
                    # its fade, which would leave it decaying while it faded in.
                    pdelay = props.bloom_delay_for(hf)*SR
                    pfade = fade_r
                    # A PIPE'S UPPER HARMONICS SPEAK FIRST (SynthProperties.
                    # speech_harmonic_exp): harmonic m builds in m^-exp of the
                    # speech, the fundamental slowest -- the jet catches the
                    # upper modes before the pipe settles on its note
                    _she = getattr(_sc, 'speech_harmonic_exp', 0.0)
                    # ...the exponent moving with the register (tonelib.
                    # speech_harmonic_exp_per_octave): a bandoneon's bass
                    # blooms, its treble barely
                    _sho = getattr(_sc, 'speech_harmonic_exp_per_octave', 0.0)
                    if _sho:
                        # ...and never past together: a reed's upper harmonics
                        # do not lead its note, so above where the bloom runs
                        # out they all speak at once
                        _she = min(0.0, _she + _sho * math.log2(max(_f0s, 1.0) / 415.0))
                    if _she and m > 1:
                        # ...counted up to speech_harmonic_cap: a reed's whole
                        # upper spectrum waits on its swing together
                        _shc = getattr(_sc, 'speech_harmonic_cap', None)
                        pfade = max(1.0, fade_r * (min(m, _shc) if _shc else m) ** (-_she))
                    # ...AND ITS RELEASE IS ITS OWN, band by band (tonelib.
                    # release_band_scale): as the wind falls a pipe may let its
                    # fundamental go and ring on in an upper band -- the release's
                    # squeak, Pitea's, on some pipes and not others
                    prel = rel_r * T.release_band_scale(_sc, key, note, m) if _own else rel_r
                    dbps, logr, aftL, logrA = partial_decay(rp, f0, m)
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
                    if _hx is not None:
                        gM *= float(T.harmonium_expression_gain(h, _hx))
                    gL = gM*props.hrtf_gain(hf, li); gR = gM*props.hrtf_gain(hf, ri)
                    cvp = cv_r * _cp.chiff_harmonic_gain(h)   # roll chiff off the upper harmonics
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
                    # A MODE'S OWN PHASE (SynthProperties.mode_phase): where the
                    # waveform puts it -- the electric pianos' harmonics at the
                    # phases their pickup gives them, so the wave has its real
                    # shape (flat against the slot's maximum, not peaky), and a
                    # layer whose term is negative half a turn round, so layers
                    # at one pitch sum to a signed envelope
                    _mph = getattr(rp, 'mode_phase', None)
                    if _mph is not None:
                        mph += _mph(m)
                    if _prng is not None:
                        # each partial its own phase (SynthProperties.partial_phase_spread)
                        mph += 2.0 * math.pi * _pps * _prng.random()
                    _mph_course = mph
                    # ...and how hard this stroke caught it (SynthProperties.stroke_scatter)
                    if getattr(rp, 'stroke_scatter', False):
                        _ssd = rp.stroke_scatter_db(m)
                        if _ssd > 0.0:
                            _sk = 10.0 ** (random.gauss(0.0, _ssd) / 20.0)
                            gL *= _sk; gR *= _sk; gM *= _sk
                    # THE QUILL CATCHES BEFORE IT LETS GO (tonelib.HarpsiBase.
                    # pre_pluck_s): the string already moving, quietly, while the
                    # plectrum pushes it; the pluck proper at the slip, a snap,
                    # its phase continuing the catch's
                    if hasattr(rp, 'pre_pluck_s') and m <= rp.pre_pluck_partials:
                        _tp = rp.pre_pluck_s(f0) * SR
                        _gp = 10.0 ** (rp.pre_pluck_db / 20.0)
                        emit_partial(2*math.pi*hf/SR, gL*_gp, gR*_gp, gM*_gp, hf, non_m, non_m + _tp,
                                     _tp, rp.pre_pluck_snap_s*SR, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                     cc_r, crl, sjit, csc, gr, cr, ph0=mph)
                        mph += 2*math.pi*hf/SR * _tp
                        non_m += _tp
                        pfade = min(pfade, rp.pre_pluck_snap_s*SR)
                    elif hasattr(rp, 'pre_pluck_s'):
                        # the partials past the catch's: they start at the slip too
                        _tp = rp.pre_pluck_s(f0) * SR
                        mph += 2*math.pi*hf/SR * _tp
                        non_m += _tp
                        pfade = min(pfade, rp.pre_pluck_snap_s*SR)
                    emit_partial(2*math.pi*hf/SR, gL, gR, gM, hf, non_m, noff, pfade, prel, chiff_r,
                                 logr, logrA, aftL, rp.sustain_level, cvp, cc_r, crl, sjit, csc,
                                 gr, cr, ph0=mph)
                    # THE WIND'S SKIRT on this partial (see WIND): a noise band
                    # at its frequency, its envelope and damper, no chiff of its
                    # own, no room images (the tail still hears it)
                    # WHOSE wind: the rank's own pipe if it has one (a reed, a
                    # trumpet on its reed pipe), else the spectrum it borrows if
                    # that is a pipe's (the flute 8 is a stopped pipe), else the host's
                    _wsrc = rp if rp is not props else (
                        spv if (spv is not None and getattr(spv, 'wind_skirt_db', None) is not None)
                        else rp)
                    # ...or a PLAYED pipe's, always (wind_skirt_always: a recorder's
                    # harmonics flutter whatever TUNING_WIND says), rising with
                    # the harmonic number (wind_skirt_harmonic_db)
                    _walw = getattr(_wsrc, 'wind_skirt_always', False)
                    _wsk = getattr(_wsrc, 'wind_skirt_db', None) if ((WIND and organ) or _walw) else None
                    if _wsk is not None and m <= WIND_PARTIALS:
                        _wg = 10.0 ** ((_wsk + _wsrc.wind_skirt_harmonic_db * math.log2(m)) / 20.0) \
                            * (1.0 if _walw else WIND_SCALE)
                        _cbw_keep = (_CBW[0], _CBW[1])
                        # its width: the wider of a floor in Hz (wind_skirt_hz) and a
                        # fraction of the partial's own frequency (wind_skirt_rel: a
                        # resonance of constant Q is wider the higher it is)
                        _wrel = getattr(_wsrc, 'wind_skirt_rel', None) or 0.0
                        _CBW[0], _CBW[1] = -max(float(_wsrc.wind_skirt_hz) / hf, float(_wrel)), 0.0
                        _NOREFL[0] = True
                        emit_partial(2*math.pi*hf/SR, gL*_wg, gR*_wg, gM*_wg, hf, non_m, noff, pfade,
                                     prel, chiff_r, logr, logrA, aftL, rp.sustain_level, 0.0, cc_r,
                                     crl, 0.0, csc, gr, cr)
                        # THE ATTACK'S RUSH (wind_attack_db): a reed's tongue
                        # beats before its resonator has hold of it, and the wind
                        # rushes past -- a burst of noise at the onset, louder
                        # than the sustained skirt, wider, and dying away on its
                        # own: a decay with no sustain, so it ends where it should
                        # however long the key is held, live as in a file.
                        _wad = getattr(_wsrc, 'wind_attack_db', None) if WIND_ATTACK else None
                        if _wad is not None:
                            # ...falling up the keyboard (wind_attack_slope, dB an
                            # octave above middle C), as Pitea's does
                            _wad = float(_wad) - float(_wsrc.wind_attack_slope) * math.log2(f0 / 261.6)
                            _ag = _wg * 10.0 ** (_wad / 20.0)
                            _CBW[0] = -max(float(_wsrc.wind_skirt_hz) / hf,
                                           float(_wsrc.wind_attack_rel))
                            _alr = math.log(T.db_ratio(float(_wsrc.wind_attack_dbps)))
                            emit_partial(2*math.pi*hf/SR, gL*_ag, gR*_ag, gM*_ag, hf, non_m, noff,
                                         float(_wsrc.wind_attack_fade_s) * SR, rel_r, chiff_r,
                                         _alr, 0.0, 0.0, 0.0, 0.0, cc_r, crl, 0.0, csc, gr, cr)
                        _CBW[0], _CBW[1] = _cbw_keep
                        _NOREFL[0] = False
                    # THE LATE ARRIVAL. A second copy of this partial, quieter
                    # and starting pdelay later: the cascade adds energy to the
                    # middle of the spectrum rather than holding the middle back.
                    # See SynthProperties.bloom_gain.
                    if pdelay > 0.0 and props.bloom_gain > 0.0:
                        bg = props.bloom_gain_for(hf)
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
                        _LATE[0] = True
                        # ...AND FALLS AT ITS OWN RATE where the voice sets one
                        # (bloom_decay_dbs: a tanpura's jawari swirl is a burst
                        # in its band, risen and gone within a second while the
                        # string rings on), as the feedback copy below does
                        _bdb = getattr(props, 'bloom_decay_dbs', 0.0)
                        if _bdb > 0.0:
                            _blr = math.log(T.db_ratio(_bdb))
                            emit_partial(2*math.pi*hf/SR, gL*bg, gR*bg, gM*bg, hf, non_m+pd, noff,
                                         bfade, rel_r, chiff_r, _blr, _blr, 0.0, 0.0,
                                         cvp, cc_r, crl, sjit, csc, gr, cr)
                        else:
                            emit_partial(2*math.pi*hf/SR, gL*bg, gR*bg, gM*bg, hf, non_m+pd, noff,
                                         bfade, rel_r, chiff_r, logr, logrA, aftL, rp.sustain_level,
                                         cvp, cc_r, crl, sjit, csc, gr, cr)
                        _LATE[0] = False
                    # FEEDBACK (tonelib.Feedback: GS 30.8, 31.8): the loop's
                    # partial and its own series, a late copy swelling in at the
                    # loop's onset and held, sinking at its own rate, until the
                    # note is let go -- at the fundamental's pluck level, so it
                    # does not inherit this partial's own
                    _fbk = props.feedback_harmonic(f0) if hasattr(props, 'feedback_harmonic') else 0
                    if _fbk and m % _fbk == 0:
                        _fbs = dict(props.feedback_series).get(m // _fbk, 0.0)
                        _fon = non_m + props.feedback_delay_s * SR
                        if _fbs > 0.0 and _fon < noff and hv > 0.0:
                            _fs = props.feedback_gain * _fbs * hv_sub(1) / hv
                            _fdb = props.feedback_dbs
                            _flr = math.log(T.db_ratio(_fdb)) if _fdb > 0 else 0.0
                            _LATE[0] = True
                            emit_partial(2*math.pi*hf/SR, gL*_fs, gR*_fs, gM*_fs, hf, _fon, noff,
                                         max(1e-4, props.feedback_swell_s)*SR, rel_r, chiff_r,
                                         _flr, _flr, 0.0, 0.0, cvp, cc_r, crl, sjit, csc, gr, cr)
                            _LATE[0] = False
                    transverse.append((hf, hv, dbps))
                    # A DRONE IS THE PART, NOT THE NOTE: emit it once for the
                    # channel, spanning its whole range, and skip it on every
                    # later note. See SynthProperties.unison_spans_part.
                    _spans_part = getattr(props, 'unison_spans_part', False)
                    _pi, _pspan = _phrase_of(ch, on) if _spans_part else (0, None)
                    _uv = () if (_spans_part and (ch, _pi) in _SPANNED) \
                        else props.unison_voices(f0, m, dbps)
                    _udrop = getattr(props, 'unison_drop_late', False)
                    _ofm = getattr(props, 'unison_onset_fraction_max', 0.25)
                    for ui, (gm, off_hz, dr, ud, uph) in enumerate(_uv):
                        # A STRIKE THE NOTE DOES NOT REACH, OR THAT MISSES THIS
                        # MODE, IS NOT EMITTED (unison_drop_late: a telephone's
                        # clapper strikes for as long as the ring is written,
                        # and each stroke rings one gong) -- not moved to the
                        # note's end, where a short ring's later strokes piled
                        if _udrop and (gm <= 0.0 or (onsets and ui + 1 < len(onsets)
                                                     and onsets[ui + 1] >= _ofm * dur)):
                            continue
                        vb = props.voice_vibrato(f0, ui + 1)
                        _VB[0], _VB[1], _VB[2] = vb if vb else (0.0, 5.5, 0.0)
                        uf, ulr = unison_partial(hf, off_hz, dr, ud)
                        if uf <= 0 or uf > SR/2: continue
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
                        # How late an extra voice may enter is a property: a
                        # section's scatter must not begin after a short note
                        # ends, but a telephone's clapper strikes for the whole
                        # ring. See SynthProperties.unison_onset_fraction_max.
                        non_u = non_r + (min(onsets[ui+1], _ofm*dur)*SR
                                         if (onsets and ui+1 < len(onsets)) else 0.0)
                        noff_u = noff
                        if _spans_part:
                            # The channel's whole range, not this note's. Emitted
                            # only once per channel -- see the guard above.
                            non_u = _pspan[0]*SR
                            noff_u = _pspan[1]*SR
                        emit_partial(2*math.pi*uf/SR, ugL, ugR, gM*gm, uf, non_u, noff_u, pfade, rel, chiff,
                                     ulr, logrA, aftL, props.sustain_level, cvp, cc, crl, sjit, csc, gr, cr,
                                     2*math.pi*uph + (_mph_course if _ushare else
                                                      2.0 * math.pi * _pps * _prng.random()
                                                      if _prng is not None else 0.0))
                    _VB[0], _VB[1], _VB[2] = 0.0, 5.5, 0.0    # main voice only within this harmonic
                    _PL[0] = 0
                    _PX[0] = getattr(props,'position_x',0.0)
                    if seats:
                        _DL[0] = seats[0][2]*SR; _DL[1] = seats[0][3]*SR
        # MARKED AFTER THE WHOLE NOTE, not inside the harmonic loop: the guard
        # above runs once per harmonic, so marking it there would emit the drone
        # for harmonic 1 and skip it for every other.
        if getattr(props, 'unison_spans_part', False):
            _SPANNED.add((ch, _phrase_of(ch, on)[0]))
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
        _rel0 = len(A['om'])
        if cdb is not None and props.release_click_modes:
            cg = gain * (10.0 ** (cdb / 20.0))
            cdec = math.log(T.db_ratio(props.release_click_decay_db))
            # ONE CLICK A JACK (tonelib.HarpsichordProperties.jack_offset_ms): on
            # a voice with choirs, every stop drawn at the key-up has its own
            # jack falling back, at its own offset and its own phase -- in phase
            # a few ms apart, identical clicks would comb. Otherwise one click.
            _jacks = [(0.0, None)]
            if organ and getattr(props, 'string_choirs', None) and _orgk in rankev_of:
                _jacks = [(T.contact_offset_s(props, r[0], note), r[0]) for r in props.stop_ranks
                          if next((v for t, v in reversed(rankev_of[_orgk][r[0]]) if t <= _raw_off), 0.0) >= 0.5]
            for _jo, _jr in _jacks:
                _j0 = len(A['om'])
                import zlib as _zl
                _jph = (random.Random(_zl.crc32(("%s|%d|click" % (_jr, note)).encode())).random()
                        * 2.0 * math.pi) if _jr is not None else 0.0
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
                    _non = noff + _jo * SR
                    emit_partial(2 * math.pi * chz / SR, a_ * props.hrtf_gain(chz, li),
                                 a_ * props.hrtf_gain(chz, ri), a_, chz,
                                 _non, _non + props.release_click_s * SR,
                                 max(1e-4, 0.0005) * SR, max(1e-4, 0.002) * SR, chiff,
                                 cdec, cdec, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, csc, -1, 0,
                                 ph0=_jph)
                # whose jack: live's organ path stamps the drawn stops' own
                if _jr is not None and len(A['om']) > _j0:
                    _REL_JACKS.append((_j0, len(A['om']), _jr, _jo))
        if len(A['om']) > _rel0:
            _REL_ROWS.append((_rel0, len(A['om'])))
    _REV[0] = None
    _NOTE_END = [len(A['om'])]   # the last note's rows end here (stroke_rows)
    _snd_finish(_SND_PEND[0])      # the last note's CC71/74/75, as the loop gives the others
    _push_finish(_PUSH_PEND[0])
    if _HT_PEND[0] is not None:
        _HT_ROWS.append((_HT_PEND[0], len(A['om']))); _HT_PEND[0] = None
    # the last strike's rows end here -- before the stream hears them
    if _REG_OPEN[0] is not None:
        _REG_OPEN[0]['rows'] = (_REG_OPEN[0]['rows'][0], len(A['om'])); _REG_OPEN[0] = None
    _gsw = _GSD_OPEN[0]
    if _GSD_OPEN[0] is not None:
        if len(A['om']) > _GSD_OPEN[0][0]:
            _GSDN.append((_GSD_OPEN[0][0], len(A['om']), _GSD_OPEN[0][2], _GSD_OPEN[0][1]))
        _GSD_OPEN[0] = None
    _par_close(_gsw)
    if sink is not None:
        if _S0[0] is not None:
            sink(A, _S0[0], len(A['om']), None)
        # the note rows only, so far: the post-passes and the windowed render
        # are the next phases of the streaming renderer
        return dict(N=N, nblk=nblk, P=len(A['om']), notes=len(notes),
                    # which post-passes this file would run, by channel
                    effects={k: sorted(v) for k, v in (
                        ('sympathetic', _SYM_CH), ('mf104', {i for i, _, _ in _MF104}), ('tubeamp', _AMP_CH),
                        ('clavinet', _CLAV_CH), ('harmonium tremolo', _HTREM_CH), ('tremolo', _TREM_CH),
                        ('chorus', _CHORUS_CH), ('cabinet', _CAB_CH), ('leslie', _LESLIE_CH),
                        ('filter', _FILTER_CH)) if v})

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
    cons_bursts = [_cons_expand(_bi, _b) for _bi, _b in enumerate(cons_bursts)]

    # THE NOTES NOBODY HIT, AND THEY RUN BEFORE THE AMPLIFIER. A sympathetic
    # note is part of what the instrument produces, so it is part of what an
    # amplifier would be handed -- and part of what a room would hear. See
    # sympathetic.py, and note that a steelpan's coupling turned out to be a
    # mechanical kick through shared steel rather than resonance.
    _sym0 = _sym1 = len(A['om'])         # the sympathetic rows: [_sym0, _sym1)
    if _SYM_CH:
        import sympathetic as _SYM
        # The table in force at each strike -- the tuner's, or under gm2 the
        # channel's MTS table -- rather than one global FREQ for the piece.
        # ...and an Indian instrument's under a secondary tuning, the raga's
        _ns = _SYM.expand(A, _SYM_CH, SR, PARTIAL_COLS + ('az', 'dr'),
                          table=_F_SYM)
        _sym1 = len(A['om'])
        if _ns:
            print("  sympathetic: %d channel(s), %d partials from notes nobody hit"
                  % (len(_SYM_CH), _ns))
    # THE FREE-STRING REGISTER, right after: the strings nobody struck, each a
    # string the note loop would have emitted (string_partial and its kin), at
    # the tuning in force. See register.py.
    if _REG_CH and sink is None:
        import register as _REG
        _rc = {}
        _cols = PARTIAL_COLS + ('az', 'dr')
        for _c, _R in _REG_CH.items():
            _C = _REG.channel_for(_c, _R, SR, BLK, _cols, REGISTER_SCALE,
                                  (string_partial, partial_decay, unison_partial))
            for _x in _R['strikes']:
                if _x['rows'][1] is None:
                    continue
                _r0, _r1 = _x['rows']
                _rows = _strike_rows(A, _r0, _r1, _cols, _x.get('gr'))
                _C.strike(_x['key'], _x['on'], _x['held'], _x['av'], _rows, _x.get('plucked'),
                          [_x['grc'][int(g)] for g in _rows['gr']] if _x.get('grc') else None)
            _rc[_c] = _C
        _nr = _REG.expand(A, _rc, SR, BLK, _cols)
        print("  register: %d channel(s), %d partials from the free strings" % (len(_rc), _nr))

    # THE AMPLIFIER, AND IT RUNS FIRST. A Leslie's chain is organ -> amp ->
    # crossover -> rotors, so the valve is upstream of the rotor; here that is
    # simply which of two passes goes first, because both work on partials.
    # Distortion products emitted now are picked up by the rotor pass below and
    # given their Doppler and their level swing exactly as any other partial.
    # THE MF-104M ANALOG DELAY, AND IT RUNS FIRST: the pedal is plugged
    # straight into the Moog, so a valve after it (the charang's) hears the
    # echoes, and every pass after this treats a repeat as any partial. A
    # repeat whose note has pitch or shape rows reads a copy of its FT row
    # whose row offsets are D later -- exact, D being whole grid points
    # (mf104.GRID). The render grows to hold the last echo's release.
    if _MF104:
        _MF = _MFD
        _mfdup = {}
        def _mf_dup(fx, d):
            ft = _MOOG_FT[fx]
            fl = int(ft[12])
            if not fl & (1 | 14):        # no pitch or shape rows: the contours
                return None              # run from the copy's own onset already
            if (fx, d) not in _mfdup:
                g = d // _MF.GRID
                _MOOG_FT.append(list(ft))
                _mpi = list(_MOOG_MPI[fx])
                if fl & 1:
                    _mpi[1] += g
                _MOOG_MPI.append(_mpi)
                _mki = list(_MOOG_MKI[fx])
                if fl & 14:
                    _mki[1] += g
                _MOOG_MKI.append(_mki)
                _mfdup[(fx, d)] = len(_MOOG_FT) - 1
            return _mfdup[(fx, d)]
        _nm, _mlast = _MF.expand(A, _MF104, SR, PARTIAL_COLS + ('az', 'dr'), dup_fx=_mf_dup)
        if _mlast + SR // 2 > N:
            N = _mlast + SR // 2         # nblk stays: the kernel clamps every per-block row
        print("  MF-104M: %d note(s), %d repeats" % (len(_MF104), _nm))
    if _GSDN:
        # THE GS DELAY's repeats (gsdelay.py), after the MF-104M's: of each
        # sending note's own rows, as the stream makes them
        _ng, _glast = _GSD.expand(A, _GSDN, SR, PARTIAL_COLS + ('az', 'dr'), gsd_place)
        if _glast + SR // 2 > N:
            N = _glast + SR // 2
        print("  GS delay: %d note(s), %d repeats" % (len(_GSDN), _ng))

    # ...and on to where the last partial dies (RING_FLOOR), in chunks so a
    # long piece's table is never copied whole
    _rl = 0
    for _j in range(0, len(A['om']), 1 << 20):
        _rl = max(_rl, ring_last({k: A[k][_j:_j + (1 << 20)] for k in
                                  ('aL', 'aR', 'sus', 'aft', 'logr', 'logrA', 'non', 'noff', 're', 'delL', 'delR')}))
    _rl = min(_rl + BLK, int((total + RING_MAX) * SR))
    if _rl > N:
        N = _rl                          # nblk stays, as above

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
                # a typed column is scaled where it lies (asarray is a view
                # of it); a list is rebuilt, as it always was
                v = np.asarray(A[col]); v[sel] *= g
                if isinstance(A[col], list):
                    A[col] = list(v)
                del v           # a live view would stop the column growing (BufferError)
            print("  clavinet: %s, %d partials through the tone section"
                  % (T.CLAV_TONE[setting][0], int(sel.sum())))

    # THE TREMOLO, and on a Rhodes it is a stereo pan rather than a level
    # swing. After the amplifier so that a valve works on the carrier and not
    # on the sidebands, before the speaker so the speaker colours them. See
    # tremolo.py, which argues both placements.
    if _HT_ROWS:
        import tremolo as _TRM
        _hm = np.zeros(len(A['om']), bool)
        for _a, _b in _HT_ROWS:
            _hm[_a:_b] = True
        _nt = _TRM.expand(A, _HTREM_CH, SR, PARTIAL_COLS + ('az', 'dr'), rows=_hm)
        if _nt:
            print("  harmonium tremolo: %d notes, %d sidebands" % (len(_HT_ROWS), _nt))
    if _TREM_CH:
        import tremolo as _TRM
        _nt = _TRM.expand(A, _TREM_CH, SR, PARTIAL_COLS + ('az', 'dr'))
        if _nt:
            _r0 = list(_TREM_CH.values())[0]
            print("  tremolo: %.1f Hz, depth %.2f%s, %d sidebands"
                  % (_r0[0], _r0[1], " (stereo pan)" if _r0[2] else "", _nt))

    # THE SCANNER IS INSIDE THE ORGAN, ahead of any chorus pedal, the cabinet
    # and the Leslie, whose copies inherit its row
    if _SCAN_CH:
        import scanner as _SCN
        _ns = _SCN.expand(A, _SCAN_CH, SR, PARTIAL_COLS + ('az', 'dr'))
        print("  scanner: %s, %d chorus copies (the circuit's dry share under them)"
              % (", ".join("ch%d %s%d" % (c, "C" if v[2] else "V", v[1]) for c, v in _SCAN_CH.items()), _ns))

    # THE CHORUS SITS BEFORE THE SPEAKER, which is where a chorus pedal sits:
    # the cabinet colours whatever reaches it, copies included.
    if _CHORUS_CH:
        _nc = _CHR.expand(A, _CHORUS_CH, SR, PARTIAL_COLS + ('az', 'dr'), place=gsd_place)
        if _nc:
            _c0 = list(_CHORUS_CH.values())[0]
            print("  chorus: %d channel(s), %d copies %s"
                  % (len(_CHORUS_CH), _nc, "through the GS chorus" if len(_c0) > 2 and _c0[2] == 'gs'
                     else "at %s cents" % "/".join("%+.0f" % c for c in _c0[1])))

    # THE INSERTION EFFECT's EQ, after its OD and amp (gsefx.eq_gain): every
    # partial of the part, the valve's products and the copies included
    if _EFXEQ_CH:
        _mq = np.asarray(A['mch']); _fq = np.asarray(A['nf'], float)
        for _qc, _qe in _EFXEQ_CH.items():
            _qs = np.flatnonzero(_mq == _qc)
            if len(_qs):
                _qg = _GSX.eq_gain(_fq[_qs], _qe)
                for _col in ('aL', 'aR', 'aM'):
                    if isinstance(A[_col], list):
                        for _i, _g in zip(_qs.tolist(), _qg.tolist()):
                            A[_col][_i] *= _g
                    else:
                        np.asarray(A[_col])[_qs] *= _qg
        # ...and its views of the table let go: a pass after it (the Leslie,
        # a Rotary's) extends the columns, which a live view forbids
        del _mq, _fq
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
        _n = _LES.expand(A, _LESLIE_CH, SR, PARTIAL_COLS + ('az', 'dr'), flips=_LFLIP, place=gsd_place)
        if _n:
            print("  leslie: %d channel(s), %d sideband partials, %d speed change(s)"
                  % (len(_LESLIE_CH), _n,
                     sum(len(v['horn'] if isinstance(v, dict) else v) - 1 for v in _LESLIE_CH.values())))

    P = len(A["om"])
    def arr(k,dt):
        col = A[k]
        if getattr(col, 'typecode', None) == {'f4': 'f', 'i4': 'i'}.get(dt) and len(col):
            a = np.frombuffer(col, dt)      # stored as it ends: no copy
        else:
            a = np.ascontiguousarray(np.array(col, dt))
        A[k] = None             # each column freed as it is converted: never both at once
        return a
    # Effective Q per band: direct energy over energy fed to the room. One
    # number per octave, derived from what this piece actually radiated rather
    # than guessed once for the whole orchestra.
    room_q = []
    for i, f in enumerate(ROOM_BANDS):
        d, r = _QACC[i]
        room_q.append((f, (d / r) if r > 0.0 else 1.0, d))
    # MASTER VOLUME, the device's own fader: every channel, after everything.
    # A GM System On puts it back to full. Kept as (sample, gain) steps and
    # ramped where it is applied, in synth_window.
    mvol = _mvol()
    _mt = _moog_tables()
    FT, KN, MPI, MPC, MPR, MKI, MPK = (_mt[k] for k in ('FT', 'KN', 'MPI', 'MPC', 'MPR', 'MKI', 'MPK'))
    prep = dict(lib=lib, P=P, N=N, nblk=nblk, total=total, sh=sh, G=G, S=S, BR=BR, BC=BC, BL=BL,
                FT=FT, KN=KN, knk=_mt['knk'], kb0=_mt['kb0'], MPI=MPI, MPC=MPC, MPR=MPR, MKI=MKI, MPK=MPK,
                mvol=mvol,
                cons_bursts=cons_bursts,
                room_q=room_q, reverb_send=dict(_REVERB_CH), reverb_steps=dict(_REVERB_STEPS),
                fader_rows=dict(_LROW),      # THE CHANNEL FADER: {channel: row}
                # which rows are sympathetic strings' (live's meend leaves them
                # at their own pitch: Live._meend_retune)
                sym_rows=(_sym0, _sym1), ring_rows=list(_RING), push_rows=list(_PUSH_ROWS), leslie_flip=list(_LFLIP),
                grain_rows=list(_GRAIN_ROWS),
                # the scanner's rows by channel (live: its slots onto a part's
                # own scanner row -- a template's row index means nothing there)
                scan_rows={c: v[0] for c, v in _SCAN_CH.items()},
                # ...AND A STROKED NOTE'S STROKES (rasp_strokes: a machine gun's
                # train, a bark's pulses, the guiro's ridges): each keeps its
                # place in the note, where live had put them all at the press
                stroke_rows=[(_a, _b) for (_a, _s), (_b, _) in
                             zip(_NOTE_ROW0, _NOTE_ROW0[1:] + [(_NOTE_END[0], False)]) if _s and _b > _a],
                rel_rows=list(_REL_ROWS), rel_jacks=list(_REL_JACKS))
    for k,dt in FINAL_DTYPES:
        prep[k] = arr(k, dt)
    # THE LESLIE'S LOBE (leslie.lobe_columns): each row's rotor and lobe, and
    # the rotors' angles on the grid -- the kernel swings the level
    if A.get('lsr') is not None:
        import leslie as _LES
        for k, dt, _ in _LES.LOBE_COLS:
            prep[k] = arr(k, dt)
        prep['LANG'] = _LES.angle_table(_LESLIE_CH, _LES.make_rotors(_LESLIE_CH), N, SR, BLK)
    if _FILTER_CH:
        filter_prep(prep, _FILTER_CH, N)
    if _BUS_CH:
        prep['bus'] = dict(_BUS_CH)
    return prep


def filter_prep(prep, channels, n):
    """A MOVING FILTER's columns and control table (efxfilter) on a kernel
    table: the filter columns from its rows' channels, FCT for the file's
    length -- and, where the table has no rotor, the Leslie's columns on no
    rotor, so the lobe kernel (which carries the filter) can take it."""
    import efxfilter as _EF
    import leslie as _LES
    P = len(prep['mch'])
    for k, v in _EF.columns(prep['mch'], channels).items():
        prep[k] = np.ascontiguousarray(v)
    prep['FCT'] = _EF.table(channels, n, SR, _LES.rotor_grid(BLK))[0]
    if prep.get('LANG') is None:
        for k, dt, v in _LES.LOBE_COLS:
            prep[k] = np.full(P, v, dt)
        prep['LANG'] = np.zeros((1, 1), np.float32)

# The table's columns as the kernel takes them (prepare's last step; a
# streamed window's table is converted the same way, streamrender)
FINAL_DTYPES = (("az","f4"),("om","f8"),("p0","f8"),("aL","f4"),("aR","f4"),("aM","f4"),("mch","i4"),("br","i4"),
                ("px","f4"),("pz","f4"),("nf","f4"),
                ("non","i8"),("noff","i8"),("fa","f4"),("re","f4"),("ch","f4"),
                ("logr","f4"),("logrA","f4"),("aft","f4"),("sus","f4"),
                ("cv","f4"),("cc","f4"),("crl","f4"),("sj","f4"),("csc","f4"),("cbw","f4"),
                ("tbav","f4"),("tau","f4"),("tcut","f4"),
                ("gb","f4"),("gt","f4"),("gc","f4"),("vd","f4"),("vdl","f4"),("vr","f4"),("vp","f4"),("delL","f4"),("delR","f4"),
                ("gr","i4"),("cr","i4"),("p0R","f8"),("pl","i4"),("fx","i4"),("mk","i4"),("rdl","f4"),
                ("fmw","f8"),("fmp","f8"),("fmpR","f8"),("nfr","f4"))

# How long a Master Volume change takes to arrive. A step in gain is a step in
# the waveform, and a step is a click -- the same argument RETRIGGER_FADE makes
# for a cut note. Five milliseconds is under anything a fader could be heard
# to glide and over anything a click needs.
MASTER_RAMP_S = 0.005


def master_curve(mvol, n0, n):
    """Master Volume over samples [n0, n0+n), or None if the file never set it.

    Each change ramps linearly from the gain before it over MASTER_RAMP_S.
    """
    if not mvol:
        return None
    ramp = max(1, int(MASTER_RAMP_S * SR))
    g = np.empty(n, np.float32)
    prev = 1.0
    idx = np.arange(n0, n0 + n, dtype=np.int64)
    g[:] = prev
    for s0, v in mvol:
        if s0 >= n0 + n:
            break
        frac = np.clip((idx - s0) / float(ramp), 0.0, 1.0)
        live = idx >= s0
        g[live] = (prev + (v - prev) * frac[live]).astype(np.float32)
        prev = v
    return g


# THE GPU, for a whole file: --gpu or TUNING_GPU=1 (gpurender.FileRenderer).
# Never the default -- it is held to the CPU at ~1e-5, not bit for bit, and
# the corpus and its golden hashes are the CPU's.
# (--gpu is read only when this file is run: live.py --gpu is live's own.)
RENDER_GPU = os.environ.get('TUNING_GPU', '') not in ('', '0')
_GPU = [None]


def _gpu():
    """The OpenCL device, made once; None (and why, once) when there is none."""
    if _GPU[0] is None:
        try:
            import gpurender
            _GPU[0] = gpurender.Gpu()
            print("  gpu: %s" % _GPU[0].name)
        except Exception as e:
            print("  gpu: not available (%s: %s) -- rendering on the CPU" % (type(e).__name__, e))
            _GPU[0] = False
    return _GPU[0] or None


# THE PER-ROW COLUMNS a subset of a kernel table takes (prep_rows): the final
# columns, the rotor's and a moving filter's -- by name, for a table such as
# the Moog's FT is a flat array whose length may happen to equal P
def _row_keys():
    import leslie as _LES, efxfilter as _EF
    return ([k for k, _ in FINAL_DTYPES] + [k for k, _, _ in _LES.LOBE_COLS]
            + [k for k, _, _ in _EF.FILTER_COLS] + ['sw'])


def prep_rows(prep, mask):
    """prep with only the rows `mask` selects (a part's own bus)."""
    out = dict(prep)
    P = prep['P']
    for k in _row_keys():
        v = prep.get(k)
        if isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == P:
            out[k] = np.ascontiguousarray(v[mask])
    out['P'] = int(np.count_nonzero(mask))
    return out


def render_partials(prep, n0, winlen, L, R):
    """Every partial of prep into L/R over [n0, n0+winlen): on the GPU when
    asked for and the window is the whole file from 0, else synth_partials.
    A PART WITH A BUS OF ITS OWN (prep['bus'], efxbus) renders apart and is
    processed before it joins the rest -- the whole window in one call here,
    so each bus is made fresh (the stream keeps its own across windows)."""
    bus = prep.get('bus')
    if bus:
        import efxbus as _EB
        mch = np.asarray(prep['mch'])
        on = np.isin(mch, list(bus))
        _render_partials(prep_rows(prep, ~on), n0, winlen, L, R)
        for ch, spec in bus.items():
            m = mch == ch
            if not m.any():
                continue
            bL = np.zeros(winlen, np.float32); bR = np.zeros(winlen, np.float32)
            _render_partials(prep_rows(prep, m), n0, winlen, bL, bR)
            oL, oR = _EB.Bus(spec, SR, T.master_gain).process(bL, bR, n0)
            L += oL; R += oR
        return
    _render_partials(prep, n0, winlen, L, R)


def _render_partials(prep, n0, winlen, L, R):
    if prep['P'] == 0:
        return
    if RENDER_GPU and n0 == 0 and _gpu() is not None:
        import gpurender
        gL, gR, _, _ = gpurender.FileRenderer(prep, _gpu()).render(winlen)
        L += gL; R += gR
    else:
        synth_partials(prep, n0, winlen, 0, prep['P'], L, R)


def synth_window(prep, n0, winlen):
    """Synthesise absolute samples [n0, n0+winlen) -> (L, R) float32, gained and
    clipped. Stateless (analytic phase), so a player calls it per audio block."""
    L=np.zeros(winlen,np.float32); R=np.zeros(winlen,np.float32)
    render_partials(prep, n0, winlen, L, R)
    # Friction is not a partial. The consonant bursts are generated and mixed
    # here rather than scheduled as voices -- see noisegen.py for why.
    _NG.mix(L, R, n0, prep.get('cons_bursts'), SR)
    _mg = master_curve(prep.get('mvol'), n0, winlen)
    if _mg is not None:
        L *= _mg; R *= _mg
    L*=T.master_gain; R*=T.master_gain; np.clip(L,-1,1,L); np.clip(R,-1,1,R)
    return L,R

# THE KERNEL'S TIME CHUNKS (its OpenMP splits a window into them) ARE A WHOLE
# NUMBER OF BLOCKS: 86 x 512 = 44 032 samples, just under a second. They were
# a second, 44 100, which no block divides, so the block a chunk edge fell in
# was set up in two halves -- and a note whose onset landed exactly on the
# edge lost the ramp that every other mid-block onset has (its first half was
# a chunk in which the note did not yet exist): 251 blocks of Mars, up to
# 2.4e-2. Whole blocks render alike however a render is cut -- the file, live
# a block at a time, and the GPU.
def _chunk():
    return BLK * max(1, SR // BLK)


def synth_partials(prep, n0, winlen, i0, i1, L, R, SndL=None, SndR=None):
    """Render partials [i0,i1) of `prep` into L/R, with no master gain and no
    clip. Partials are independent and the kernel accumulates into the buffers,
    so a caller can split the table across threads and sum the results -- which
    is what live.py does, because ctypes releases the GIL. Splitting changes the
    ORDER of the float sum and so the last bits of the output; render() takes the
    whole table in one call and is unaffected."""
    a=prep; lib=a['lib']; CHUNK=_chunk()
    fp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    # ROWS FASTER THAN A BLOCK (_xdec_rows) render through synth_voice_xdec, the
    # rest as they always did; a table with none makes the one call below
    xr = _xdec_rows(a, i0, i1)
    if len(xr):
        keep = np.setdiff1d(np.arange(i0, i1), xr)
        _synth_rows(a, keep, n0, winlen, L, R, SndL, SndR, None)
        _synth_rows(a, xr, n0, winlen, L, R, SndL, SndR, ensure_xdec_lib().synth_voice_xdec)
        return
    if i0 or i1 != a['P']:
        sl = lambda k: a[k][i0:i1]
    else:
        sl = lambda k: a[k]
    # a table with a Leslie: synth_voice_lobe, the rotor rows swung by their lobe
    lobe = a.get('LANG') is not None
    fn = ensure_lobe_lib().synth_voice_lobe if lobe else lib.synth_voice
    fn(fp(L),fp(R),ctypes.c_long(n0),ctypes.c_long(winlen),
                    *_voice_args(a, sl, i1-i0, lobe),
                    ctypes.c_long(CHUNK),
                    # the live room's send bus: NULL unless asked for (see synthkernel.c)
                    fp(sl('sw')) if SndL is not None else None,
                    fp(SndL) if SndL is not None else None,
                    fp(SndR) if SndL is not None else None)


def _synth_rows(a, rows, n0, winlen, L, R, SndL, SndR, fn):
    """Rows `rows` of the table (an index array) through FN, or through the
    table's own function (synth_voice, or the Leslie's) when FN is None."""
    if not len(rows):
        return
    fp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    sl = lambda k: np.ascontiguousarray(a[k][rows])
    lobe = fn is None and a.get('LANG') is not None
    if fn is None:
        fn = ensure_lobe_lib().synth_voice_lobe if lobe else a['lib'].synth_voice
    fn(fp(L),fp(R),ctypes.c_long(n0),ctypes.c_long(winlen),
                    *_voice_args(a, sl, len(rows), lobe),
                    ctypes.c_long(_chunk()),
                    fp(sl('sw')) if SndL is not None else None,
                    fp(SndL) if SndL is not None else None,
                    fp(SndR) if SndL is not None else None)


def _voice_args(a, sl, P, lobe=True):
    """synth_voice's arguments from BLK to the shutter's four scalars -- the
    run voice_block (the GPU's block setup) takes too, in the same order --
    and with lobe, the Leslie's seven after them and a moving filter's seven
    (synth_voice_lobe and voice_block take them; synth_voice does not)."""
    dp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_double)); fp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    lp=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_long)); ip=lambda x:x.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    return (BLK,a['nblk'],P,
                    dp(sl('om')),dp(sl('p0')),dp(sl('p0R')),fp(sl('aL')),fp(sl('aR')),fp(sl('nf')),
                    lp(sl('non')),lp(sl('noff')),fp(sl('fa')),fp(sl('re')),fp(sl('ch')),fp(sl('logr')),fp(sl('logrA')),fp(sl('aft')),fp(sl('sus')),
                    fp(sl('cv')),fp(sl('cc')),fp(sl('crl')),fp(sl('sj')),fp(sl('csc')),fp(sl('cbw')),
                    fp(sl('tbav')),fp(sl('tau')),fp(sl('tcut')),
                    fp(sl('gb')),fp(sl('gt')),fp(sl('gc')),
                    fp(sl('vd')),fp(sl('vr')),fp(sl('vp')),fp(sl('vdl')),fp(sl('delL')),fp(sl('delR')),
                    ip(sl('gr')),ip(sl('cr')),fp(a['G']),fp(a['S']),
                    ip(sl('br')),fp(a['BR']),dp(a['BC']),
                    # the wind's level on a bend row, at block edges (wind.py); NULL: none
                    fp(a['BL']) if a.get('BL') is not None else None,
                    # the Moog's filter and contours (moog.py): NULL fx is no
                    # Moog in this table, and the kernel never reads FT or KN
                    ip(sl('fx')) if a.get('FT') is not None else None,
                    fp(a['FT'] if a.get('FT') is not None else _NO_ROWS),
                    fp(a['KN'] if a.get('KN') is not None else _NO_ROWS),
                    ctypes.c_long(a.get('knk', 1)), ctypes.c_long(a.get('kb0', 0)),
                    fp(sl('aLp')) if 'aLp' in a else None, fp(sl('aRp')) if 'aRp' in a else None,
                    ip(sl('mk')) if (a.get('FT') is not None and 'mk' in a) else None,
                    # a Moog note's pitch rows (moog.pitch_rows); NULL: none
                    ip(a['MPI']) if a.get('MPI') is not None else None,
                    dp(a['MPC']) if a.get('MPI') is not None else None,
                    fp(a['MPR']) if a.get('MPI') is not None else None,
                    # its shape rows (moog.shape_rows); NULL: none moves
                    ip(a['MKI']) if a.get('MKI') is not None else None,
                    fp(a['MPK']) if a.get('MKI') is not None else None,
                    # 1 -> 2 FM's OSC 1 angle per partial; NULL: no Moog table
                    dp(sl('fmw')) if (a.get('FT') is not None and 'fmw' in a) else None,
                    dp(sl('fmp')) if (a.get('FT') is not None and 'fmw' in a) else None,
                    dp(sl('fmpR')) if (a.get('FT') is not None and 'fmw' in a) else None,
                    ctypes.c_float(a['sh'][0]),ctypes.c_float(a['sh'][1]),ctypes.c_float(a['sh'][2]),ctypes.c_float(a['sh'][3]),
                    # the Leslie's lobe (leslie.lobe_columns): each row's rotor
                    # and lobe, the rotors' angles; NULL: no rotor in this table
                    # synth_voice_lobe and voice_block's (lobe; synth_voice has none)
                    *(() if not lobe else
                      (ip(sl('lsr')), fp(sl('lph')), fp(sl('lfl')), fp(sl('lsh')), fp(sl('lnm')),
                       fp(a['LANG']), ctypes.c_long(a['LANG'].shape[1]))
                      if a.get('LANG') is not None else (None,) * 6 + (ctypes.c_long(0),)),
                    # ...and a moving filter's (efxfilter: FILTER_COLS, FCT); NULL: none
                    *(() if not lobe else
                      (ip(sl('fsr')), ip(sl('fty')), fp(sl('fpa')), fp(sl('fpb')), fp(sl('fpc')),
                       fp(a['FCT']), ctypes.c_long(a['FCT'].shape[1]))
                      if a.get('FCT') is not None else (None,) * 6 + (ctypes.c_long(0),)))

_NO_ROWS = np.zeros(16, np.float32)

_LAST_PREP = {}


# STREAMED by default (streamrender): the partials rendered a window at a time
# as the notes are emitted, so memory is what sounds at once, not the piece --
# bit for bit the whole table's render. TUNING_STREAM=0 builds the whole table;
# a file using a pass the stream does not reproduce yet builds it anyway.
RENDER_STREAM = os.environ.get('TUNING_STREAM', '1') not in ('0', 'off', '')
# THE FREE-STRING REGISTER (register.py): a piano's undamped strings answering
# its strikes -- the pedal's halo, true to the tuning. ON BY DEFAULT: only the
# pianos have a coupling, so nothing else pays for it. TUNING_REGISTER=0 turns
# it off (a pedalled piano piece renders some four times faster without it).
REGISTER = os.environ.get('TUNING_REGISTER', '1') not in ('0', 'off', '')
# THE ORGAN'S WIND, per pipe (examples/organ_wind_measure.py, sources.md): each
# partial of a registered rank wears a narrow band of noise -- the jet's
# turbulence, filtered by the pipe's own resonance -- so it flutters on its own
# a few times a second, as Pitea's pipes do (their partials' level wobbles are
# uncorrelated: turbulence, not the bellows). TUNING_WIND=1 turns it on, a
# number scales it; off by default until Ben has heard it.
WIND = os.environ.get('TUNING_WIND', '0') not in ('0', 'off', '')
# ...unset, a pipe organ whose class says shared_wind has it at its own
# flexibility (wind_flex); 0/off turns every chest's swing off
WIND_OFF = os.environ.get('TUNING_WIND') in ('0', 'off')
try:
    WIND_SCALE = float(os.environ.get('TUNING_WIND', '1')) if WIND else 1.0
except ValueError:
    WIND_SCALE = 1.0
WIND_PARTIALS = 16          # the skirts' cost is a row a partial: the lower ones carry it
# ...and the reeds' attack rush with it (wind_attack_db), unless this is 0:
# so the burst can be heard against the wind without it
WIND_ATTACK = os.environ.get('TUNING_WIND_ATTACK', '1') not in ('0', 'off', '')
_VERBOSE_WIND = os.environ.get('TUNING_WIND_VERBOSE', '0') not in ('0', '')
# ...and its LEVEL: TUNING_REGISTER=4 is on, with the class's coupling and
# knock times 4 (Ben's ear set 1, against 4, on Ondine)
try:
    REGISTER_SCALE = float(os.environ.get('TUNING_REGISTER', '1')) if REGISTER else 1.0
except ValueError:
    REGISTER_SCALE = 1.0


def wind_scale_for(pc):
    """THE SHARED WIND's swing scale for an organ class (wind.py): TUNING_WIND
    if set, else the class's own flexibility where it has the shared wind by
    default, else none. Both renderers ask this."""
    if WIND:
        return WIND_SCALE
    if WIND_OFF or not getattr(pc, 'shared_wind', False):
        return 0.0
    return float(getattr(pc, 'wind_flex', 1.0))


_RECORD = {}


def _record_clicks(props, t_end):
    """A RECORD'S CLICKS to t_end s: [(t, dB, balance)] on one timeline for the
    whole render (tonelib.PhonoNoiseProperties), drawn a revolution at a time
    from a seed of that revolution: strike_flam_rate a second at times
    uniform within it, levels from strike_flam_levels' quantiles (percent,
    dB) -- uniform under strike_flam_db where it has none -- and a balance
    uniform over the quarter turn; each of the last revolution's clicks
    clicking AGAIN a revolution on with strike_flam_recur's probability (a
    speck met on the next turn), its balance kept. Cached and extended."""
    import random
    rate = float(props.strike_flam_rate)
    per, pr = getattr(props, 'strike_flam_recur', None) or (1.8, 0.0)
    q = tuple(getattr(props, 'strike_flam_levels', ()) or ())
    key = (rate, per, pr, q, float(props.strike_flam_db))
    st = _RECORD.setdefault(key, {'clicks': [], 'last': [], 'rev': 0})
    while st['rev'] * per < t_end + per:
        r = st['rev']
        rr = random.Random(0xD15C0 + r)
        new = []
        for _t, _l, _b in st['last']:
            if rr.random() < pr:
                new.append((_t + per, _l + rr.uniform(-1.0, 1.0), _b))
        for _ in range(int(round(rate * per))):
            u = rr.random()
            if q:
                lv = float(np.interp(100.0 * u, [a for a, _ in q], [b for _, b in q]))
            else:
                lv = -props.strike_flam_db * u
            new.append((r * per + rr.random() * per, lv, rr.uniform(0.0, 0.5 * math.pi)))
        st['clicks'].extend(new)
        st['last'] = [c for c in new if r * per <= c[0] < (r + 1) * per]
        st['rev'] += 1
    return st['clicks']


def render(path, tuner='hybrid440'):
    if RENDER_STREAM:
        import streamrender as _STR
        try:
            t0 = time.time()
            L, R, s = _STR.render(path, tuner, B=sys.modules[__name__],
                                  gpu=_gpu() if RENDER_GPU else None)
            kdt = time.time() - t0
            _LAST_PREP.clear()
            _LAST_PREP.update(_STR.result(s))
            return L, R, s.ctx['total'], s.rows_total, kdt
        except _STR.NotStreamable as e:
            print("  stream: the %s pass is not streamed yet -- rendering the whole table" % e)
    prep = prepare(path, tuner)
    _LAST_PREP.clear()
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
    """{MIDI channel: row mask} over the partial table -- a parallel type's
    branch B (its virtual channel, gsefx.VIRT) in its part's."""
    mch = prep['mch'] % _GSX.VIRT
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
    mch = prep['mch'].astype(np.int64) % _GSX.VIRT          # branch B in its part
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
    if prep.get('LANG') is not None:       # the Leslie's lobe, per row
        for k in ('lsr', 'lph', 'lfl', 'lsh', 'lnm'):
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
    if '--gpu' in sys.argv:
        RENDER_GPU = True
        sys.argv.remove('--gpu')
    if '--map' in sys.argv:
        # THE STANDARD map 0 plays (DEFAULT_MAP): ours, sc55, sc88, sc88pro,
        # sc8850, or the map's number
        _i = sys.argv.index('--map')
        DEFAULT_MAP = map_number(sys.argv[_i + 1])
        os.environ['TUNING_MAP'] = str(DEFAULT_MAP)     # ...for `import blockrender` elsewhere too
        del sys.argv[_i:_i + 2]
    inp,outp=sys.argv[1],sys.argv[2]; tuner=sys.argv[3] if len(sys.argv)>3 else 'hybrid440'
    # Optional 4th argument sets the pitch everything tunes to: "a=432" names the
    # frequency of A4, "c=256" the frequency of middle C. Which end you give
    # matters -- a temperament's own A-to-C ratio is not equal temperament's, so
    # c=256 lands on a different A in each one. Omit it to keep each
    # temperament's own reference. See tunelib.set_reference.
    # eastern=raga:<system>[/<raga>]@<Sa>[:Hz] anywhere after the tuner: the
    # secondary tuning for the Eastern instruments (ragas.py)
    for _a in list(sys.argv[3:]):
        if _a.lower().startswith('eastern='):
            EASTERN = _a.split('=', 1)[1]
            sys.argv.remove(_a)
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
        if RENDER_STREAM and not RENDER_GPU:
            # STREAMED: every part written as it renders (streamrender.render_stems)
            import streamrender as _STR
            _s, _parts = _STR.render_stems(inp, tuner, outdir, objects=(mode == 'objects'), by=by,
                                           B=sys.modules[__name__])
            _LAST_PREP.clear(); _LAST_PREP.update(_STR.result(_s))
            for ch, pos, f, p in _parts:
                rec = {"file": os.path.basename(f), "channel": ch, "partials": p}
                if pos is not None:
                    rec["x_m"], rec["z_m"] = round(pos[0], 4), round(pos[1], 4)
                manifest.append(rec)
                print("  ch%-3d %s%8d partials -> %s"
                      % (ch, "" if pos is None else "x=%+6.2f z=%+5.2f " % pos, p, f))
                n += 1; P += p
            tot = _s.N / float(SR)
        for ch, pos, L, R, p in (() if (RENDER_STREAM and not RENDER_GPU) else
                                 render_parts(inp, tuner, objects=(mode == 'objects'), by=by)):
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
    t0=time.time()
    _streamed = False
    if RENDER_STREAM:
        # STREAMED TO DISK: the mix and its reverb send written as they render,
        # so memory is what sounds, not the length of the piece; the send kept
        # below only if the channels heard send differently
        import streamrender as _STR
        _send_tmp = os.path.splitext(outp)[0] + '.send.wav.part'
        try:
            _, _, _s = _STR.render(inp, tuner, B=sys.modules[__name__], out=outp, send_out=_send_tmp,
                                   gpu=_gpu() if RENDER_GPU else None)
            _LAST_PREP.clear(); _LAST_PREP.update(_STR.result(_s))
            total, P, kdt = _s.ctx['total'], _s.rows_total, time.time() - t0
            _streamed = True
        except _STR.NotStreamable as e:
            print("  stream: %s -- rendering the whole table" % e)
            if os.path.exists(_send_tmp):
                os.remove(_send_tmp)
    if not _streamed:
        L,R,total,P,kdt=render(inp,tuner)
        write_wav(outp, L, R)
    dt=time.time()-t0
    _rq = _LAST_PREP.get('room_q')
    _rs = _LAST_PREP.get('reverb_send') or {}
    if _rq:
        import json
        with open(os.path.splitext(outp)[0] + '.room.json', 'w') as fh:
            _sd = {str(k): v for k, v in _rs.items()}
            if _rs:
                _hh = sorted(set(int(_c) for _c in np.unique(_LAST_PREP['mch'])))
                _vv = send_values(_rs, _LAST_PREP.get('reverb_steps'), _hh)
                if len(_vv) == 1:
                    # One number for every channel that sounds: roomtail scales
                    # the mix it already has and nothing extra is rendered.
                    _sd = {str(_c): next(iter(_vv)) for _c in _hh}
            _rx = dict(_GS_ROOM)
            json.dump(dict({'bands': [{'hz': f, 'q': q, 'energy': e} for f, q, e in _rq],
                            'send': _sd}, **_rx), fh, indent=1)
    # THE REVERB SEND BUS. Each channel feeds the room in proportion to how far
    # away it stands, and the room's IR is the same shape for all of them --
    # so the whole send is one weighted sum, convolved once.
    #
    # Rendered only when the channels actually DIFFER. If every channel sends
    # the same amount (which includes the usual case of none of them sending at
    # all), the bus is a scalar multiple of the dry mix and roomtail can scale
    # what it already has. That keeps the common file at exactly one render.
    _mch = _LAST_PREP['mch'] if _rs else None
    if _rs:
        # Uniform against WHAT ACTUALLY SOUNDS, not against the table. A file
        # where one channel sends 100 and the others send nothing is uniform if
        # only that channel has notes -- and comparing the send table alone
        # would call it split and pay for a second render.
        _heard = sorted(set(int(_c) for _c in np.unique(_mch)))
        _vals = send_values(_rs, _LAST_PREP.get('reverb_steps'), _heard)
    _ss = _LAST_PREP.get('stream_send')
    if _rs and len(_vals) > 1 and _ss is not None:
        # streamed: the bus was rendered beside the mix, in the same kernel call
        if isinstance(_ss, str):
            os.replace(_ss, os.path.splitext(outp)[0] + '.send.wav')
        else:
            write_wav(os.path.splitext(outp)[0] + '.send.wav', _ss[0], _ss[1])
        print("  reverb send: %d channel(s) at their own distance, bus written"
              % len(_rs))
    elif _rs and len(_vals) > 1:
        _g = send_weights(_rs, _LAST_PREP.get('reverb_steps'), _mch, _LAST_PREP['non'])
        _sav = (_LAST_PREP['aL'].copy(), _LAST_PREP['aR'].copy())
        _LAST_PREP['aL'] *= _g
        _LAST_PREP['aR'] *= _g
        _bl = np.zeros(_LAST_PREP['N'], np.float32)
        _br = np.zeros(_LAST_PREP['N'], np.float32)
        render_partials(_LAST_PREP, 0, _LAST_PREP['N'], _bl, _br)
        _LAST_PREP['aL'][:], _LAST_PREP['aR'][:] = _sav
        # The room hears the device's output, so a master fader that moves
        # moves the send too -- otherwise fading a piece out would leave its
        # reverb standing at full.
        _mg = master_curve(_LAST_PREP.get('mvol'), 0, _LAST_PREP['N'])
        if _mg is not None:
            _bl *= _mg; _br *= _mg
        # ...and the master gain, as the mix has it (streamrender._emit)
        _bl *= T.master_gain; _br *= T.master_gain
        write_wav(os.path.splitext(outp)[0] + '.send.wav', _bl, _br)
        print("  reverb send: %d channel(s) at their own distance, bus written"
              % len(_rs))
    if _streamed and os.path.exists(_send_tmp):
        os.remove(_send_tmp)            # one send for all: roomtail scales the mix
    print("blockrender: %.1fs audio, %d partials, kernel %.2fs, total %.2fs = %.1fx realtime -> %s"%(total,P,kdt,dt,total/dt,outp))
