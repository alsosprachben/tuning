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
                ('room', C * 10), ('ahz', C * 6), ('alpha', C * 36), ('scat', C * 36)]


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
    srcs = ([os.path.join(HERE, 'native', f) for f in ('tone.c', 'voice.c', 'pycompat.h')]
            + [os.path.join(HERE, 'roomcore.c')])
    so = os.path.join(HERE, 'libnative.so')
    if not os.path.exists(so) or max(os.path.getmtime(s) for s in srcs) > os.path.getmtime(so):
        tmp = '%s.%d.tmp' % (so, os.getpid())
        # no -ffast-math, no fused multiply-adds: Python's order of operations;
        # no builtins: pow(x, 2.0) is libm's pow, as Python's x ** 2 is (gcc's
        # x*x is correctly rounded where pow, at 0.52 ULP, is not always)
        subprocess.check_call(['gcc', '-O2', '-march=native', '-ffp-contract=off', '-fno-builtin', '-shared', '-fPIC',
                               srcs[0], '-o', tmp, '-lm'])
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
                            ctypes.c_void_p, D])):
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
    return s
