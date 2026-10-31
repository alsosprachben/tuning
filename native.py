"""The native engine's Python side: native/ built and loaded, a note's voice
taken as numbers for it, and what it supports.

The engine is being ported out of Python a piece at a time (toward iOS,
macOS and a GPU-heavy embedded board), each piece checked against the
Python it replaces -- bit-identical where the arithmetic can be (the same
libm calls in the same order, CPython's sum and random streams: see
native/pycompat.h), by tolerance where it cannot.

    snapshot(props) -> VoiceSnap, or None where the voice uses a feature not
                       ported yet (Python plays it)
    lib()           -> the library (ctypes), or None where it cannot be built

TUNING_NATIVE=0: never use it.
"""
import ctypes
import math
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = [None]

C = ctypes.c_double
I = ctypes.c_int
LL = ctypes.c_longlong


class VoiceSnap(ctypes.Structure):
    """native/voice.c's VoiceSnap, field for field."""
    _fields_ = [('gain', C), ('max_harmonic', I), ('odd_only', I), ('even_db_set', I),
                ('even_harmonic_db', C), ('strike_point', C), ('strike_depth', C), ('strike_fills', I),
                ('strike_fill_fraction', C), ('attack_volume', C), ('attack_dampening', C),
                ('frequency_x', C), ('octave_position', C),
                ('decay_db', C), ('harmonic_decay_db', C), ('harmonic_decay_dampening', C),
                ('decay_register_factor', C),
                ('hammer_corner_hz', C), ('hammer_open_lo', C), ('hammer_open_slope', C),
                ('hammer_register_slope', C), ('hammer_order', C),
                ('board_body_gain', C), ('board_body_hz', C), ('board_body_width', C), ('board_high_hz', C),
                ('board_high_order', C), ('board_low_hz', C),
                ('string_gain', C * 2), ('string_break_hz', C * 2), ('string_crossfade_semitones', C),
                ('soft_pedal_strings', I), ('soft_pedal_down', I), ('n_detune', I),
                ('note_detune_cents', C * 4), ('unison_beat_scatter', I), ('unison_beat_hz', C * 2),
                ('unison_key', LL), ('aftersound_level', C * 3), ('aftersound_decay_ratio', C),
                ('chiff_span_set', I), ('chiff_harmonic_span', C), ('chiff_harmonic_power', C),
                ('bloom_seconds', C), ('bloom_center_hz', C), ('bloom_octaves', C), ('bloom_shape', C),
                ('exp_vibrato_cents', C), ('solo_vibrato_spread', C), ('solo_vibrato_hz', C),
                ('section_salt', LL),
                ('radiation_distance', C), ('position_x', C), ('position_z', C), ('hrtf_beta', C),
                ('room', C * 10), ('ahz', C * 6), ('alpha', C * 36), ('scat', C * 36),
                ('phantom_coupling', C), ('phantom_register_power', C), ('phantom_ref_hz', C),
                ('phantom_note_max_hz', C), ('phantom_gain_floor', C), ('phantom_max_order', I)]


class ToneIn(ctypes.Structure):
    """native/tone.c's ToneIn: the note, and the emitter's state for it."""
    _fields_ = ([(f, C) for f in ('f0', 'B', 'gain', 'non', 'noff', 'fade', 'rel', 'chiff', 'cv', 'cc', 'crl',
                                  'sjit', 'csc', 'li', 'ri', 'sustain_level', 'gr', 'cr', 'sr',
                                  'jitter_scale', 'nyq_om')]
                + [('transposed', I), ('reflect', I)]
                + [(f, C) for f in ('dl', 'dr', 'pos_x0', 'pos_x_props', 'pos_z', 'channel', 'cbw0', 'cbw1')]
                + [('tb', C * 3), ('gl', C * 3), ('sv', C * 2)]
                + [(f, C) for f in ('sound_vib_depth_cents', 'vibrato_delay', 'br', 'fx', 'mk', 'fm_omega',
                                    'fm_phase', 'listener_distance', 'head_radius', 'pan_angle')]
                + [('room_bands', C * 9)])


class VoiceInit(ctypes.Structure):
    """native/voice.c's VoiceInit: a class's constants for its constructor."""
    _fields_ = ([(f, C) for f in ('tonal_dampening', 'octave_dampening')] + [('octave_modulo', I)]
                + [(f, C) for f in ('octave_width', 'seat_x', 'decay_register_slope', 'pitch_jitter_cents',
                                    'timing_jitter_seconds', 'tension_bend', 'tension_bend_max',
                                    'tension_bend_ref_hz', 'tension_bend_slope')]
                + [('inharmonicity_dynamic', I)]
                + [(f, C) for f in ('inharmonicity_coefficient', 'ia', 'ib', 'ic', 'id', 'ie', 'effort',
                                    'effort_tilt', 'effort_tilt_up')]
                + [('effort_tilt_up_set', I), ('even_db_set', I)]
                + [(f, C) for f in ('even_harmonic_db', 'even_harmonic_db_per_octave')]
                + [('touch_sensitive', I), ('fixed_touch', I)]
                + [(f, C) for f in ('initial_gain', 'octave_gain', 'projection_db', 'register_effort_db',
                                    'register_tilt_db', 'register_center_hz', 'register_half_octaves',
                                    'listener_distance', 'head_radius', 'position_z', 'sound_speed',
                                    'max_partial_hz', 'bloom_seconds', 'bloom_slope', 'bloom_stretch_max',
                                    'detune_lo', 'detune_hi')]
                + [('key_jitter', I), ('soft_pedal_down', I), ('b_law', I)]
                + [(f, C) for f in ('wound_k', 'wound_p', 'plain_k', 'plain_p', 'break_hz', 'scale_constant_hz_m',
                                    'reference_string_max_m', 'case_string_max_m')]
                + [('upright', I), ('n_level', I)]
                + [(f, C) for f in ('attack_time', 'hammer_soft_s', 'hammer_hard_s')]
                + [('level_hz', C * 32), ('level_db', C * 32)])


class VoiceNote(ctypes.Structure):
    """native/voice.c's VoiceNote: what the note setup reads of a voice besides its VoiceSnap."""
    _fields_ = [(f, C) for f in ('pitch_jitter', 'attack_jitter', 'pan_angle', 'left_incidence',
                                 'right_incidence', 'left_hrtf_delay', 'right_hrtf_delay',
                                 'inharmonicity_coefficient', 'B', 'tension_bend', 'attack_time')]


class PyRandomState(ctypes.Structure):
    """pycompat.h's PyRandom: CPython's Mersenne Twister, its 624 words and index."""
    _fields_ = [('mt', ctypes.c_uint32 * 624), ('i', I)]


class NoteClass(ctypes.Structure):
    """native/engine.cpp's NoteClass: what a voice class is to a note's setup."""
    _fields_ = ([('init', VoiceInit), ('tmpl', VoiceSnap), ('chiff_max_valve_time', C), ('release_valve_set', I),
                 ('release_valve_time', C), ('speech_cycles', C), ('legato_set', I), ('legato_attack_s', C),
                 ('attack_fraction_max', C), ('release_fraction_set', I), ('release_fraction_max', C),
                 ('slur_cuts_release', I), ('chiff_width_set', I)]
                + [(f, C) for f in ('chiff_width', 'chiff_width_cycles', 'chiff_volume', 'chiff_cycle',
                                    'chiff_release', 'sustain_jitter', 'cbw0', 'cbw1', 'tension_bend_power')]
                + [('tension_bend_slurs', I), ('tension_settle_time', C), ('tension_settle_cutoff', C),
                   ('tension_log', I), ('tbend_cut_scale', C), ('sustain_level', C), ('reflection_order', I),
                   ('n_strike', I), ('strike_hz', C * 32), ('strike_db', C * 32), ('strike_noise_dbs', C),
                   ('strike_span_set', I)]
                + [(f, C) for f in ('strike_span_lo', 'strike_span_hi', 'strike_octave_db', 'strike_fade_s',
                                    'strike_len_s', 'strike_at_s', 'strike_cal_db')])


class NoteIn(ctypes.Structure):
    """native/engine.cpp's NoteIn: a note as its file and channel give it."""
    _fields_ = ([(f, C) for f in ('f0', 'pan', 'vel', 'chan_vol', 'effort', 'on', 'off', 'nx')]
                + [(f, I) for f in ('has_nx', 'mcut', 'slurred', 'slur_out')]
                + [('detune_lo', C), ('detune_hi', C), ('soft_pedal_down', I), ('fixed_touch', I)]
                + [(f, C) for f in ('sr', 'retrigger_fade', 'channel', 'br', 'nyq_om')]
                + [('sv', C * 2), ('sound_vib_depth_cents', C), ('vibrato_delay', C), ('gl', C * 3)]
                + [(f, C) for f in ('fx', 'mk', 'fm_omega', 'fm_phase')]
                + [('room_bands', C * 9), ('reflect', I), ('no_reflections', I)])


class NoteOut(ctypes.Structure):
    """native/engine.cpp's NoteOut: what the note's setup worked out."""
    _fields_ = ([(f, I) for f in ('n_knock', 'n_tone', 'n_phantom')]
                + [(f, C) for f in ('non', 'noff', 'fade', 'rel', 'chiff', 'jitter_scale', 'dl', 'dr', 'li',
                                    'ri', 'pos_x', 'pos_z', 'B', 'cv', 'cc', 'crl', 'sjit', 'csc')]
                + [('tb', C * 3), ('cbw', C * 2)])


def lib():
    """native/ as a library, built when a source is newer; None if it cannot be."""
    if _LIB[0] is None:
        _LIB[0] = False
        if os.environ.get('TUNING_NATIVE', '1') not in ('0', 'off', ''):
            try:
                _LIB[0] = _load()
            except (OSError, subprocess.CalledProcessError) as e:
                print("  native: unavailable (%s)" % e)
    return _LIB[0] or None


def _load():
    srcs = ([os.path.join(HERE, 'native', f) for f in ('tone.c', 'voice.c', 'pycompat.h', 'nv.h', 'engine.cpp')]
            + [os.path.join(HERE, 'roomcore.c')])
    so = os.path.join(HERE, 'libnative.so')
    if not os.path.exists(so) or max(os.path.getmtime(s) for s in srcs) > os.path.getmtime(so):
        tmp = '%s.%d.tmp' % (so, os.getpid())
        # no -ffast-math, no fused multiply-adds: Python's order of operations;
        # no builtins: pow(x, 2.0) is libm's pow, as Python's x ** 2 is (gcc's
        # x*x is correctly rounded where pow, at 0.52 ULP, is not always).
        # The C core (tone.c, with voice.c) and the C++ engine (engine.cpp)
        # under the same flags, linked into one library.
        flags = ['-O2', '-march=native', '-ffp-contract=off', '-fno-builtin', '-fPIC']
        oc, ocpp = tmp + '.tone.o', tmp + '.engine.o'
        try:
            subprocess.check_call(['gcc'] + flags + ['-c', srcs[0], '-o', oc])
            subprocess.check_call(['g++', '-std=c++17'] + flags + ['-c', srcs[4], '-o', ocpp])
            subprocess.check_call(['g++', '-shared', oc, ocpp, '-o', tmp, '-lm'])
        finally:
            for o in (oc, ocpp):
                if os.path.exists(o):
                    os.remove(o)
        os.replace(tmp, so)
    d = ctypes.CDLL(so)
    P = ctypes.POINTER(VoiceSnap)
    D = ctypes.POINTER(C)
    for name, res, args in (
            ('nv_series_volume', C, [P, I]), ('nv_harmonic_volume', C, [P, I]),
            ('nv_harmonic_decay', C, [P, I]), ('nv_mode_ratio', C, [P, I]),
            ('nv_aftersound', None, [P, C, C, D]), ('nv_unison_voices', I, [P, C, I, C, D]),
            ('nv_radiation_gain', C, [P, C, C, I]), ('nv_hrtf_gain', C, [P, C, C]),
            ('nv_chiff_harmonic_gain', C, [P, C]), ('nv_bloom_delay_for', C, [P, C]),
            ('nv_voice_vibrato', I, [P, C, I, D]), ('nv_string_partial', I, [P, C, C, I, C, D]),
            ('nv_partial_decay', None, [P, C, I, D]), ('nv_unison_partial', None, [C, C, C, C, D]),
            ('nv_random_check', None, [LL, I, D]),
            ('nv_tone', I, [P, ctypes.POINTER(ToneIn), I, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p, ctypes.POINTER(I),
                            ctypes.c_void_p, D]),
            ('nv_strike', I, [P, ctypes.POINTER(ToneIn), I, ctypes.c_void_p, ctypes.c_void_p, C, C, C, C, C, C, C,
                              C, ctypes.c_void_p, I, ctypes.c_void_p, D]),
            ('nv_voice_init', None, [ctypes.POINTER(VoiceInit), P, C, C, C, C, C, ctypes.POINTER(PyRandomState),
                                     P, ctypes.POINTER(VoiceNote)]),
            ('nv_note', I, [ctypes.POINTER(NoteClass), ctypes.POINTER(NoteIn), ctypes.POINTER(PyRandomState), I,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I,
                            ctypes.c_void_p, D, ctypes.POINTER(NoteOut)]),
            ('nv_phantom', I, [P, ctypes.POINTER(ToneIn), ctypes.c_void_p, I, I, ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p, D])):
        f = getattr(d, name)
        f.restype, f.argtypes = res, args
    return d


def supported(props):
    """Whether the native voice plays this voice: the grand piano so far
    (GrandPianoProperties), and none of the features not ported yet."""
    import tonelib as T
    if not isinstance(props, T.GrandPianoProperties):
        return False
    return (props.mode_gains is None and props.mode_ratios is None and not props.harmonic_touch
            and not props.bore_corner_hz and not props.pickup_points and bool(props.strike_point)
            and len(props.note_detune_cents) <= 4 and len(props.string_gain) == 2
            and len(props.string_break_hz) == 2 and props.max_harmonic is not None)


def snapshot(props):
    """props as a VoiceSnap; None where the voice is not supported."""
    import tonelib as T
    if not supported(props):
        return None
    s = VoiceSnap()
    p = props
    s.gain = p.gain
    s.max_harmonic = int(p.max_harmonic or 0)
    s.odd_only = int(bool(p.odd_only))
    s.even_db_set = int(p.even_harmonic_db is not None)
    s.even_harmonic_db = p.even_harmonic_db or 0.0
    s.strike_point, s.strike_depth = p.strike_point, p.strike_depth
    s.strike_fills = int(bool(p.strike_fills_with_force))
    s.strike_fill_fraction, s.attack_volume, s.attack_dampening = (
        p.strike_fill_fraction, p.attack_volume, p.attack_dampening)
    s.frequency_x, s.octave_position = p.frequency_x, p.octave_position
    s.decay_db, s.harmonic_decay_db = p.decay_db, p.harmonic_decay_db
    s.harmonic_decay_dampening, s.decay_register_factor = p.harmonic_decay_dampening, p.decay_register_factor
    for f in ('hammer_corner_hz', 'hammer_open_lo', 'hammer_open_slope', 'hammer_register_slope', 'hammer_order',
              'board_body_gain', 'board_body_hz', 'board_body_width', 'board_high_hz', 'board_high_order',
              'board_low_hz', 'string_crossfade_semitones', 'aftersound_decay_ratio', 'chiff_harmonic_power',
              'bloom_seconds', 'bloom_center_hz', 'bloom_octaves', 'bloom_shape', 'exp_vibrato_cents',
              'solo_vibrato_spread', 'solo_vibrato_hz', 'radiation_distance', 'hrtf_beta'):
        setattr(s, f, getattr(p, f))
    s.string_gain[:] = list(p.string_gain)
    s.string_break_hz[:] = list(p.string_break_hz)
    s.soft_pedal_strings = int(p.soft_pedal_strings)
    s.soft_pedal_down = int(bool(T.soft_pedal_down))
    s.n_detune = len(p.note_detune_cents)
    for i, c in enumerate(p.note_detune_cents):
        s.note_detune_cents[i] = c
    s.unison_beat_scatter = int(bool(p.unison_beat_scatter))
    s.unison_beat_hz[:] = list(p.unison_beat_hz)
    s.unison_key = int(p._unison_key)
    s.aftersound_level[:] = [p.aftersound_level_1, p.aftersound_level_2, p.aftersound_level_3]
    s.chiff_span_set = int(p.chiff_harmonic_span is not None)
    s.chiff_harmonic_span = p.chiff_harmonic_span or 0.0
    s.section_salt = int(p._section_salt())
    s.position_x = getattr(p, 'position_x', 0.0)
    s.position_z = getattr(p, 'position_z', 0.0)
    R, AHZ, ALPHA, SCAT = p._room_pack()
    s.room[:] = [float(x) for x in R]
    s.ahz[:] = [float(x) for x in AHZ]
    s.alpha[:] = [float(x) for x in ALPHA]
    s.scat[:] = [float(x) for x in SCAT]
    s.phantom_coupling = getattr(p, 'phantom_coupling', 0.0)
    s.phantom_register_power = getattr(p, 'phantom_register_power', 0.0)
    s.phantom_ref_hz = getattr(p, 'phantom_ref_hz', 65.0)
    s.phantom_note_max_hz = getattr(p, 'phantom_note_max_hz', 0.0)
    s.phantom_gain_floor = getattr(p, 'phantom_gain_floor', 3e-3)
    s.phantom_max_order = int(getattr(p, 'phantom_max_order', 16))
    return s


_INIT_OWN = ('SynthProperties', 'GrandPianoProperties', 'UprightPianoProperties', 'HonkyTonkProperties', 'object')
_BASE_OWN = {'place': 'SynthProperties', 'hrtf_at': 'SynthProperties', 'register_effort': 'SynthProperties',
             'register_effort_at': 'SynthProperties', 'pan': 'SynthProperties',
             'inharmonicity_coefficient_func': 'InharmonicStringProperties'}
_CLASS = {}


def _owner(cls, name):
    for k in cls.__mro__:
        if name in k.__dict__:
            return k.__name__
    return None


def init_supported(cls):
    """Whether native/voice.c's nv_voice_init builds this class's voice: a
    piano constructor (SynthProperties', the grand's, the honky-tonk's), the
    base class's placing and laws, and none of the branches not ported."""
    import tonelib as T
    if not issubclass(cls, T.GrandPianoProperties) or not T.hrtf:
        return False
    if any(k.__name__ not in _INIT_OWN for k in cls.__mro__ if '__init__' in k.__dict__):
        return False
    if any(_owner(cls, n) != o for n, o in _BASE_OWN.items()):
        return False
    if _b_law(cls) is None:
        return False
    c = cls
    if (issubclass(cls, T.UprightPianoProperties) and len(cls.register_level_db or ()) > 32) or c.attack_time is None:
        return False
    return not ((c.strike_noise_slope and c.chiff_volume) or (c.bloom_gain > 0.0 and c.bloom_gain_slope)
                or (c.strike_wobble_hz > 0.0 and c.strike_wobble_gain > 0.0) or c.strike_volume_trim_db)


def _b_law(cls):
    """Which inharmonicity_coefficient_for_frequency cls has (VoiceInit.b_law), or None."""
    own = _owner(cls, 'inharmonicity_coefficient_for_frequency')
    return {'InharmonicStringProperties': 0, 'UprightPianoProperties': 1, 'ElectricGrandProperties': 2}.get(own)


def _class(cls):
    """(VoiceInit, the class's VoiceSnap template, a prototype voice) for cls,
    or None: made once, the template's room refilled when the room changes."""
    import random
    import tonelib as T
    got = _CLASS.get(cls)
    if got is None:
        if not init_supported(cls):
            _CLASS[cls] = False
            return None
        st = random.getstate()
        try:
            proto = cls(261.6, 0.0, 0.5, 1.0)
        finally:
            random.setstate(st)
        tmpl = snapshot(proto)
        if tmpl is None:
            _CLASS[cls] = False
            return None
        c = VoiceInit()
        for f, _ in VoiceInit._fields_:
            if getattr(cls, f, None) is not None:
                setattr(c, f, getattr(cls, f) if not isinstance(getattr(cls, f), bool) else int(getattr(cls, f)))
        c.ia, c.ib, c.ic, c.id, c.ie = cls.a, cls.b, cls.c, cls.d, cls.e
        c.octave_modulo = int(bool(cls.octave_modulo))
        c.inharmonicity_dynamic = int(bool(cls.inharmonicity_dynamic))
        c.effort_tilt_up_set = int(cls.effort_tilt_up is not None)
        c.effort_tilt_up = cls.effort_tilt_up or 0.0
        c.even_db_set = int(cls.even_harmonic_db is not None)
        c.even_harmonic_db = cls.even_harmonic_db or 0.0
        c.touch_sensitive = int(bool(cls.touch_sensitive))
        c.max_partial_hz = cls.max_partial_hz or 0.0
        c.sound_speed = proto.sound_speed
        c.key_jitter = 1
        c.b_law = _b_law(cls)
        c.attack_time = cls.attack_time
        if issubclass(cls, T.UprightPianoProperties):
            c.upright = 1
            c.hammer_soft_s, c.hammer_hard_s = cls.hammer_contact_s
            pts = cls.register_level_db or ()
            c.n_level = len(pts)
            for i, (f, db) in enumerate(pts):
                c.level_hz[i], c.level_db[i] = f, db
        if c.b_law == 1:
            (c.wound_k, c.wound_p), (c.plain_k, c.plain_p) = cls.wound_B, cls.plain_B
            c.break_hz = cls.upright_break_hz
        elif c.b_law == 2:
            c.scale_constant_hz_m = cls.scale_constant_hz_m
            c.reference_string_max_m, c.case_string_max_m = cls.reference_string_max_m, cls.case_string_max_m
        got = _CLASS[cls] = [c, tmpl, proto, proto._room_pack()]
    if got is False:
        return None
    room = got[2]._room_pack()
    if room is not got[3]:
        R, AHZ, ALPHA, SCAT = room
        t = got[1]
        t.room[:] = [float(x) for x in R]
        t.ahz[:] = [float(x) for x in AHZ]
        t.alpha[:] = [float(x) for x in ALPHA]
        t.scat[:] = [float(x) for x in SCAT]
        got[3] = room
    return got


def voice(cls, frequency, channel_pan, attack_volume, channel_volume, effort=0.0, state=None):
    """cls(frequency, channel_pan, attack_volume, channel_volume, effort) in C:
    (VoiceSnap, VoiceNote), or None where the class is not supported. state:
    a PyRandomState for the global stream, drawn from as the constructor
    draws (None: the snapshot alone, the stream untouched)."""
    import tonelib as T
    d = lib()
    got = _class(cls) if d is not None else None
    if got is None:
        return None
    c, tmpl = got[0], got[1]
    lo, hi = cls.string_detune_range
    if '__init__' in getattr(T, 'HonkyTonkProperties', object).__dict__ and issubclass(cls, T.HonkyTonkProperties):
        lo, hi = lo * T.honky_detune, hi * T.honky_detune
    c.detune_lo, c.detune_hi = lo, hi
    c.fixed_touch = int(bool(T.FIXED_TOUCH))
    c.soft_pedal_down = int(bool(T.soft_pedal_down))
    s, o = VoiceSnap(), VoiceNote()
    d.nv_voice_init(ctypes.byref(c), ctypes.byref(tmpl), float(frequency), float(channel_pan),
                    float(attack_volume), float(channel_volume), float(effort),
                    ctypes.byref(state) if state is not None else None, ctypes.byref(s), ctypes.byref(o))
    return s, o


def random_state():
    """The global random stream as a PyRandomState."""
    import random
    st = random.getstate()[1]
    r = PyRandomState()
    r.mt[:] = st[:624]
    r.i = st[624]
    return r


_NOTE = {}
# a class attribute that, set, means a note of the class takes a path the
# engine does not have (blockrender plays it): the tone's extras
# (_tone_native), the knock's (_strike_native), the note setup's
_NOTE_OFF = ('bloom_seconds', 'speech_harmonic_exp', 'speech_harmonic_exp_per_octave', 'wind_skirt_always',
             'unison_spans_part', 'unison_drop_late', 'strike_phase_spread', 'partial_phase_spread',
             'stroke_scatter', 'string_choirs', 'unison_shares_phase', 'directivity_radius', 'strike_in_s',
             'jitter_by_partial', 'mode_lock_spread', 'played_backwards', 'fold_restrike', 'hammer_legato',
             'strike_flam_rate', 'strike_flam_times', 'strike_flam_people', 'strike_noise_tail',
             'strike_noise_layers', 'transposed_from_hz', 'one_shot', 'gate_time')
_NOTE_ABSENT = ('pre_pluck_s', 'feedback_harmonic')


def note_class(cls):
    """native/engine.cpp's NoteClass for cls, or None where its notes are not
    the engine's: made once, its template's room kept current."""
    import tonelib as T
    import blockrender as BR
    got = _NOTE.get(cls)
    if got is None:
        v = _class(cls)
        ok = (v is not None and not any(getattr(cls, a, None) for a in _NOTE_OFF)
              and not any(hasattr(cls, a) for a in _NOTE_ABSENT)
              and getattr(cls, 'mode_phase', None) is None and int(getattr(cls, 'strike_flam', 0) or 0) <= 1
              and len(getattr(cls, 'strike_noise_db', ()) or ()) <= 32)
        if ok:
            # a section's players and their onsets: none for one instrument (its prototype asked)
            p = v[2]
            ok = not (hasattr(p, 'section_seats') and p.section_seats()) and not any(
                hasattr(p, 'section_onsets_at') and p.section_onsets_at(f) for f in (27.5, 261.6, 4186.0))
        if not ok:
            _NOTE[cls] = False
            return None
        k = NoteClass()
        k.init = v[0]
        k.chiff_max_valve_time = cls.chiff_max_valve_time
        k.release_valve_set = int(cls.release_valve_time is not None)
        k.release_valve_time = cls.release_valve_time or 0.0
        k.speech_cycles = cls.speech_cycles
        lg = getattr(cls, 'legato_attack_s', None)
        k.legato_set, k.legato_attack_s = int(lg is not None), lg or 0.0
        k.attack_fraction_max = getattr(cls, 'attack_fraction_max', 0.45)
        rfm = getattr(cls, 'release_fraction_max', 0.45)
        k.release_fraction_set, k.release_fraction_max = int(rfm is not None), rfm or 0.0
        k.slur_cuts_release = int(bool(getattr(cls, 'slur_cuts_release', False)))
        k.chiff_width_set = int(cls.chiff_width is not None)
        k.chiff_width = cls.chiff_width or 0.0
        k.chiff_width_cycles = cls.chiff_width_cycles
        k.chiff_volume, k.chiff_cycle = cls.chiff_volume, cls.chiff_cycle
        k.chiff_release = getattr(cls, 'chiff_release', 1.0) or 0.0
        k.sustain_jitter = cls.sustain_jitter
        k.cbw0 = getattr(cls, 'chiff_bandwidth', None) or BR.RAND_GRAN
        k.cbw1 = getattr(cls, 'chiff_bandwidth_hz', None) or 0.0
        k.tension_bend_power = cls.tension_bend_power
        k.tension_bend_slurs = int(bool(getattr(cls, 'tension_bend_slurs', True)))
        k.tension_settle_time = getattr(cls, 'tension_settle_time', 0.28) or 0.28
        k.tension_settle_cutoff = getattr(cls, 'tension_settle_cutoff', 1.8)
        k.tension_log = int(bool(getattr(cls, 'tension_log', False)))
        k.tbend_cut_scale = BR.TBEND_CUT_SCALE
        k.sustain_level = cls.sustain_level
        k.reflection_order = int(bool(cls.reflection_order))
        tab = getattr(cls, 'strike_noise_db', ()) or ()
        k.n_strike = len(tab)
        for i, b in enumerate(tab):
            k.strike_hz[i], k.strike_db[i] = float(b[0]), float(b[1])
        if tab:
            k.strike_noise_dbs = cls.strike_noise_dbs
            sp = getattr(cls, 'strike_noise_span_hz', None)
            k.strike_span_set = int(bool(sp))
            if sp:
                k.strike_span_lo, k.strike_span_hi = sp
            k.strike_octave_db = getattr(cls, 'strike_noise_octave_db', cls.strike_noise_slope)
            k.strike_fade_s = cls.strike_noise_fade_s
            k.strike_len_s = getattr(cls, 'strike_noise_len_s', None) or 0.25
            k.strike_at_s = getattr(cls, 'strike_noise_at', 0.0) or 0.0
            k.strike_cal_db = getattr(cls, 'strike_noise_cal_db', 0.0) or 0.0
        got = _NOTE[cls] = [k, None]
    if got is False:
        return None
    v = _class(cls)          # its room current
    if got[1] is not v[3]:
        got[0].tmpl = v[1]
        got[1] = v[3]
    return got[0]
