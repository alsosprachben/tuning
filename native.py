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
NCOLS = 50          # native/nv.h: blockrender.EMIT_COLS
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
                ('phantom_note_max_hz', C), ('phantom_gain_floor', C), ('phantom_max_order', I),
                ('board_kind', I), ('board_low_order', C), ('bridge_gain', C), ('bridge_corner_hz', C),
                ('bridge_order', C), ('bridge_force_power', C)]


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
                                    'strike_len_s', 'strike_at_s', 'strike_cal_db')]
                + [('room_planes', C * 6), ('room_order', I), ('damper_pedal', I), ('detune_lo', C),
                   ('detune_hi', C), ('detune_wheel', I)]
                + [('reg_gain', C), ('reg_knock', C), ('reg_fall', C), ('damper_top', I), ('reg_floor', C),
                   ('reg_release', C)])


class NoteIn(ctypes.Structure):
    """native/engine.cpp's NoteIn: a note as its file and channel give it."""
    _fields_ = ([(f, C) for f in ('f0', 'pan', 'vel', 'chan_vol', 'effort', 'on', 'off', 'nx')]
                + [(f, I) for f in ('has_nx', 'mcut', 'slurred', 'slur_out')]
                + [('detune_lo', C), ('detune_hi', C), ('soft_pedal_down', I), ('fixed_touch', I)]
                + [(f, C) for f in ('sr', 'retrigger_fade', 'channel', 'br', 'nyq_om')]
                + [('sv', C * 2), ('sound_vib_depth_cents', C), ('vibrato_delay', C), ('gl', C * 3)]
                + [(f, C) for f in ('fx', 'mk', 'fm_omega', 'fm_phase')]
                + [('room_bands', C * 9), ('reflect', I), ('no_reflections', I), ('ch', LL), ('note', I),
                   ('damper_pedal', I), ('key_off', C), ('planes', C * 6), ('order', I), ('from_song', I), ('song_index', I)])


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
    srcs = ([os.path.join(HERE, 'native', f) for f in ('tone.c', 'voice.c', 'pycompat.h', 'nv.h', 'engine.cpp',
                                                       'channel.cpp', 'room.cpp', 'midi.cpp', 'strings.c', 'exactmath.c',
                                                       'register.cpp', 'prepare.cpp', 'render.cpp',
                                                       'live.cpp', 'slab.cpp', 'live.h')]
            + [os.path.join(HERE, 'roomcore.c'), os.path.join(HERE, 'registercore.c')])
    so = os.path.join(HERE, 'libnative.so')
    if not os.path.exists(so) or max(os.path.getmtime(s) for s in srcs) > os.path.getmtime(so):
        tmp = '%s.%d.tmp' % (so, os.getpid())
        # no -ffast-math, no fused multiply-adds: Python's order of operations;
        # no builtins: pow(x, 2.0) is libm's pow, as Python's x ** 2 is (gcc's
        # x*x is correctly rounded where pow, at 0.52 ULP, is not always).
        # The C core (tone.c, with voice.c) and the C++ engine (engine.cpp)
        # under the same flags, linked into one library.
        flags = ['-O2', '-march=native', '-ffp-contract=off', '-fno-builtin', '-fPIC']
        objs = [tmp + '.tone.o', tmp + '.engine.o', tmp + '.channel.o', tmp + '.room.o', tmp + '.midi.o',
                tmp + '.register.o', tmp + '.prepare.o', tmp + '.render.o', tmp + '.live.o', tmp + '.slab.o',
                tmp + '.registercore.o']
        try:
            subprocess.check_call(['gcc'] + flags + ['-c', srcs[0], '-o', objs[0]])
            for src, o in zip(srcs[4:8] + [os.path.join(HERE, 'native', f)
                                           for f in ('register.cpp', 'prepare.cpp', 'render.cpp', 'live.cpp',
                                                     'slab.cpp')],
                              objs[1:10]):
                subprocess.check_call(['g++', '-std=c++17'] + flags + ['-c', src, '-o', o])
            # register.py's C core, under ITS flags (register._load_core's): the same arithmetic
            subprocess.check_call(['gcc', '-O3', '-march=native', '-ffp-contract=off', '-fopenmp-simd',
                                   '-fno-math-errno', '-mprefer-vector-width=512', '-fPIC', '-c',
                                   os.path.join(HERE, 'registercore.c'), '-o', objs[10]])
            subprocess.check_call(['g++', '-shared'] + objs + ['-o', tmp, '-lmvec', '-lm'])
        finally:
            for o in objs:
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
            ('nv_song_play', I, [ctypes.c_void_p, ctypes.POINTER(NoteClass), ctypes.POINTER(NoteIn),
                                 ctypes.POINTER(PyRandomState), I, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p, D, ctypes.POINTER(NoteOut),
                                 ctypes.POINTER(I)]),
            ('nv_images', I, [D, I, C, C, C, I, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_read', ctypes.c_void_p, [ctypes.c_char_p, LL, ctypes.POINTER(I)]),
            ('nv_midi_free', None, [ctypes.c_void_p]), ('nv_midi_total', C, [ctypes.c_void_p]),
            ('nv_midi_n_notes', I, [ctypes.c_void_p]), ('nv_midi_n_ccs', I, [ctypes.c_void_p]),
            ('nv_midi_n_pws', I, [ctypes.c_void_p]), ('nv_midi_gs', I, [ctypes.c_void_p]),
            ('nv_midi_note', None, [ctypes.c_void_p, I, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_cc', None, [ctypes.c_void_p, I, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_pw', None, [ctypes.c_void_p, I, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_song', None, [ctypes.c_void_p, ctypes.c_void_p, D]),
            ('nv_strings', I, [ctypes.POINTER(VoiceInit), P, D, C, C, C, ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_exp_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_pow_n', None, [ctypes.c_long, ctypes.c_void_p, I, ctypes.c_void_p, I, ctypes.c_void_p]),
            ('nv_cabs_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_log_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_prepare', LL, [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(NoteIn), D, I,
                                ctypes.POINTER(PyRandomState), ctypes.POINTER(D), ctypes.c_void_p, D,
                                ctypes.c_void_p, C, C, C, C, LL, C, C, C, ctypes.c_void_p, C, C, C, C,
                                ctypes.POINTER(ctypes.c_void_p), I]),
            ('nv_template', LL, [ctypes.c_void_p, ctypes.POINTER(NoteIn), D, D, I, I, I, I,
                                 ctypes.POINTER(ctypes.POINTER(ctypes.c_double)), ctypes.c_void_p, C, C, C, C, LL,
                                 C, C, ctypes.c_void_p, C, C, C, C, ctypes.POINTER(ctypes.c_void_p)]),
            ('nv_tcache_new', ctypes.c_void_p, [ctypes.c_void_p, ctypes.POINTER(NoteIn), D, D, ctypes.c_void_p,
                                                ctypes.c_void_p, C, C, C, C, LL, C, C, C, C, C, C]),
            ('nv_tcache_free', None, [ctypes.c_void_p]),
            ('nv_tcache_warm', ctypes.c_long, [ctypes.c_void_p, I, I, I, I, ctypes.c_void_p, I]),
            ('nv_tcache_get', ctypes.c_void_p, [ctypes.c_void_p, I, I, I, ctypes.POINTER(LL)]),
            ('nv_tmpl_col', ctypes.c_void_p, [ctypes.c_void_p, I, I]),
            ('nv_render', I, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, I, I, LL,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_long, C, C, C, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_slab_new', ctypes.c_void_p, [ctypes.c_long, C]), ('nv_slab_free', None, [ctypes.c_void_p]),
            ('nv_slab_stamp', I, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, LL, LL, LL, LL, LL, C, LL, I,
                                  C]),
            ('nv_slab_release', None, [ctypes.c_void_p, LL, LL, LL, LL, LL]),
            ('nv_slab_reap', None, [ctypes.c_void_p, LL, LL]),
            ('nv_slab_col', None, [ctypes.c_void_p, I, I, ctypes.c_void_p]),
            ('nv_slab_free_list', ctypes.c_long, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]),
            ('nv_lp_new', ctypes.c_void_p, [ctypes.c_void_p, LL, C, I, I, I, I, I, C, C, ctypes.c_long, C, D, C]),
            ('nv_lp_free', None, [ctypes.c_void_p]),
            ('nv_lp_event', None, [ctypes.c_void_p, I, I, I, I]),
            ('nv_lp_block', None, [ctypes.c_void_p, LL, LL]),
            ('nv_lp_slab', ctypes.c_void_p, [ctypes.c_void_p]),
            ('nv_song_new', ctypes.c_void_p, []), ('nv_song_free', None, [ctypes.c_void_p]),
            ('nv_song_cc', None, [ctypes.c_void_p, LL, C, I, I]),
            ('nv_song_note', None, [ctypes.c_void_p, LL, I, C, C, I, C, C, C, C, I, I]),
            ('nv_play', I, [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(NoteIn), D, I,
                            ctypes.POINTER(PyRandomState), ctypes.c_void_p, LL, ctypes.c_void_p, D,
                            ctypes.POINTER(LL), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_void_p]),
            ('nv_play_full', LL, [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(NoteIn), D, I,
                                  ctypes.POINTER(PyRandomState), ctypes.POINTER(D), ctypes.c_void_p, D,
                                  ctypes.c_void_p, C, C, C, C, LL, ctypes.POINTER(LL), ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_buf_free', None, [ctypes.c_void_p]),
            ('nv_song_tuning', None, [ctypes.c_void_p, LL, C, D]),
            ('nv_song_channel', None, [ctypes.c_void_p, LL, C, D, I]),
            ('nv_song_pitch_level', I, [ctypes.c_void_p, I, I, D]),
            ('nv_song_finish', None, [ctypes.c_void_p, C]),
            ('nv_song_note_off', C, [ctypes.c_void_p, LL, I, C, C, I, I, C, ctypes.POINTER(I)]),
            ('nv_song_soft_at', I, [ctypes.c_void_p, LL, C]),
            ('nv_song_next_same', I, [ctypes.c_void_p, LL, I, C, D]),
            ('nv_phantom', I, [P, ctypes.POINTER(ToneIn), ctypes.c_void_p, I, I, ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p, D])):
        f = getattr(d, name)
        f.restype, f.argtypes = res, args
    return d


def supported(props):
    """Whether the native voice plays this voice: the grand piano so far
    (GrandPianoProperties), and none of the features not ported yet."""
    import tonelib as T
    if not isinstance(props, T.GrandPianoProperties) or _board_kind(type(props)) is None:
        return False
    return (props.mode_gains is None and props.mode_ratios is None and not props.harmonic_touch
            and not props.bore_corner_hz and not props.pickup_points and bool(props.strike_point)
            and len(props.note_detune_cents) <= 4 and len(props.string_gain) == 2
            and len(props.string_break_hz) == 2 and props.max_harmonic is not None)


_BOARD = {'GrandPianoProperties': 0, 'UprightPianoProperties': 1, 'ElectricGrandProperties': 2}


def _board_kind(cls):
    """Which soundboard_gain cls has (VoiceSnap.board_kind), or None."""
    for k in cls.__mro__:
        if 'soundboard_gain' in k.__dict__:
            return _BOARD.get(k.__name__)
    return None


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
    s.board_kind = _board_kind(type(p))
    if s.board_kind == 1:
        s.board_low_order = p.board_low_order
    elif s.board_kind == 2:
        s.bridge_gain, s.bridge_corner_hz, s.bridge_order = p.bridge_gain, p.bridge_corner_hz, p.bridge_order
        s.bridge_force_power = p.bridge_force_power or 0.0
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
             'strike_noise_layers', 'transposed_from_hz', 'one_shot', 'gate_time', 'tape_length_s',
             'open_string_ring', 'course_keys', 'key_bridge', 'bridge_partner', 'buff_choirs',
             'register_knock_tilt', 'register_knock_profile')
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
        k.damper_pedal = int(bool(getattr(cls, 'damper_pedal', True)))
        k.detune_lo, k.detune_hi = cls.string_detune_range
        k.detune_wheel = int(bool(getattr(cls, 'detune_wheel', False)))
        import register as _RG
        k.reg_gain = float(getattr(cls, 'register_gain', 0.0))
        k.reg_knock = float(getattr(cls, 'register_knock_gain', 0.0))
        k.reg_fall = float(getattr(cls, 'register_knock_falloff', 0.0))
        k.damper_top = int(getattr(cls, 'damper_top', 128))
        k.reg_floor = _RG.floor_of(cls)
        k.reg_release = float(getattr(cls, 'release_valve_time', 0.12) or 0.12)
        got = _NOTE[cls] = [k, None]
    if got is False:
        return None
    v = _class(cls)          # its room current
    if got[1] is not v[3]:
        got[0].tmpl = v[1]
        got[1] = v[3]
    got[0].room_planes[:] = room_walls(v[2])
    got[0].room_order = int(v[2].reflection_order)
    return got[0]


def _ev_key(e):
    """A note event as the song knows it: (channel, key, on, off, velocity,
    (v7, v11, pan), program as an int)."""
    return (int(e[0]), int(e[1]), e[2], e[3], int(e[4]), tuple(e[5]), int(e[6]))


class Song(object):
    """native/channel.cpp's Song: a file's controller events and notes, and
    what a note asks of its channel -- its end once the pedals have had their
    say, the soft pedal at its onset, its key's next strike."""

    def __init__(self, ccs, notes, total, freq=None, mts=None, btun=None, otun=None, faders=(), trim=None,
                 finish=True):
        """ccs, notes and total as blockrender's; the tuning: freq the file's
        128-key table, mts {channel: [(t, table)]}, btun {channel: ratio},
        otun {channel: 12 cents}; faders the channels whose fader is a row;
        trim(program) the program's trim on the channel volume."""
        d = self.d = lib()
        self.p = d.nv_song_new()
        for c, evs in ccs.items():
            for t, cc, v in evs:
                d.nv_song_cc(self.p, int(c), float(t), int(cc), int(v))
        self._idx = {}
        for i, e in enumerate(notes):
            self._idx.setdefault(_ev_key(e), []).append(i)
            v7, v11, pan = e[5]
            import percussion_map as _PM
            d.nv_song_note(self.p, int(e[0]), int(e[1]), float(e[2]), float(e[3]), int(e[4]), float(v7),
                           float(v11), float(pan), float(trim(e[6]) if trim else 1.0), int(e[6]),
                           int(_PM.is_drum(e[6])))
        T128 = ctypes.c_double * 128
        def row(tab):           # a table as 128 numbers, 0 for a key it lacks
            return T128(*[float(tab[k]) if k in tab else 0.0 for k in range(128)])
        if freq is not None:
            d.nv_song_tuning(self.p, -1, 0.0, row(freq))
        for c, tl in (mts or {}).items():
            for t, tab in tl:
                d.nv_song_tuning(self.p, int(c), float(t), row(tab))
        for c in set(btun or ()) | set(otun or ()) | set(faders):
            ot = (otun or {}).get(c)
            d.nv_song_channel(self.p, int(c), float((btun or {}).get(c) or 0.0),
                              (ctypes.c_double * 12)(*ot) if ot else None, int(c in faders))
        if finish:
            d.nv_song_finish(self.p, float(total))

    def take(self, ev):
        """The index of note event ev (a tuple of the notes given) in the
        song, each index given once: two identical events, in the order
        asked. None for an event it was not given."""
        q = self._idx.get(_ev_key(ev))
        return q.pop(0) if q else None

    def pitch_level(self, index, effort_tilt):
        """(f0, velocity, pan, channel volume, effort) of the song's note at
        index, or None"""
        o = (ctypes.c_double * 5)()
        if index is None or not self.d.nv_song_pitch_level(self.p, int(index), int(bool(effort_tilt)), o):
            return None
        return tuple(o)

    def __del__(self):
        if getattr(self, 'p', None):
            self.d.nv_song_free(self.p)
            self.p = None

    def note_off(self, ch, note, on, off, damper_pedal, mcut, retrigger_fade):
        """(the note's end, whether a half-pedalled note meets the band)"""
        b = ctypes.c_int(0)
        r = self.d.nv_song_note_off(self.p, int(ch), int(note), float(on), float(off), int(bool(damper_pedal)),
                                    int(bool(mcut)), float(retrigger_fade), ctypes.byref(b))
        return r, bool(b.value)

    def soft_at(self, ch, t):
        return bool(self.d.nv_song_soft_at(self.p, int(ch), float(t)))

    def next_same(self, ch, note, on):
        o = ctypes.c_double(0.0)
        return o.value if self.d.nv_song_next_same(self.p, int(ch), int(note), float(on), ctypes.byref(o)) else None


def room_walls(props):
    """The room's walls as nv_images takes them: WALLS' signed planes."""
    return [sgn * getattr(props, attr) for _, _, attr, sgn in props.WALLS]


def images(props, sx, sy, sz, cap=64):
    """nv_images: (nsurf, surf, img, mir) as _images_for packs them, or None
    over cap."""
    import numpy as np
    pl = (ctypes.c_double * 6)(*room_walls(props))
    o = int(props.reflection_order)
    nsurf = np.zeros(cap, np.int32)
    surf = np.zeros(cap * max(o, 1), np.int32)
    img = np.zeros(3 * cap)
    mir = np.zeros(3 * cap)
    n = lib().nv_images(pl, o, float(sx), float(sy), float(sz), cap, nsurf.ctypes.data, surf.ctypes.data,
                        img.ctypes.data, mir.ctypes.data)
    if n < 0:
        return None
    return nsurf[:n], surf[:int(nsurf[:n].sum())], img[:3 * n], mir[:3 * n]


MIDI_REFUSED = {-1: 'malformed', -2: 'type 2', -3: 'ports', -4: 'an exclusive', -5: 'a bank',
                -6: 'an NRPN or MPE', -7: 'mono mode'}


class Midi(object):
    """native/midi.cpp's reading of a MIDI file (bytes, a path, or a
    mido.MidiFile): blockrender.parse's for a GM file, its notes after
    _prep_notes_off. .error is why it was refused (MIDI_REFUSED), else 0."""

    def __init__(self, src):
        if isinstance(src, (bytes, bytearray)):
            b = bytes(src)
        elif isinstance(src, str):
            with open(src, 'rb') as f:
                b = f.read()
        else:
            import io
            buf = io.BytesIO()
            src.save(file=buf)
            b = buf.getvalue()
        d = self.d = lib()
        e = ctypes.c_int(0)
        self.p = d.nv_midi_read(b, len(b), ctypes.byref(e))
        self.error = e.value

    def __del__(self):
        if getattr(self, 'p', None):
            self.d.nv_midi_free(self.p)
            self.p = None

    def total(self):
        return self.d.nv_midi_total(self.p)

    def notes(self):
        """[(channel, key, on, off, velocity, (v7, v11, pan), program, drum)]"""
        I5, D5 = ctypes.c_int * 5, ctypes.c_double * 5
        out = []
        for i in range(self.d.nv_midi_n_notes(self.p)):
            iv, dv = I5(), D5()
            self.d.nv_midi_note(self.p, i, iv, dv)
            out.append((iv[0], iv[1], dv[0], dv[1], iv[2], (dv[2], dv[3], dv[4]), iv[3], iv[4]))
        return out

    def ccs(self):
        """{channel: [(t, control, value)]}, in message order"""
        I5 = ctypes.c_int * 5
        out = {}
        for i in range(self.d.nv_midi_n_ccs(self.p)):
            iv, t = I5(), ctypes.c_double()
            self.d.nv_midi_cc(self.p, i, iv, ctypes.byref(t))
            out.setdefault(iv[0], []).append((t.value, iv[1], iv[2]))
        return out

    def pws(self):
        """{channel: [(t, pitch)]}"""
        I5 = ctypes.c_int * 5
        out = {}
        for i in range(self.d.nv_midi_n_pws(self.p)):
            iv, t = I5(), ctypes.c_double()
            self.d.nv_midi_pw(self.p, i, iv, ctypes.byref(t))
            out.setdefault(iv[0], []).append((t.value, iv[1]))
        return out

    def song(self, total, trim, freq=None, mts=None, btun=None, otun=None, faders=()):
        """A Song (above) from this reading: trim(program, drum) the channel
        volume's trim; the tuning as Song's."""
        s = Song({}, [], None, freq=freq, mts=mts, btun=btun, otun=otun, faders=faders, finish=False)
        tr = (ctypes.c_double * 256)(*([float(trim(p, False)) for p in range(128)]
                                       + [float(trim(p, True)) for p in range(128)]))
        self.d.nv_midi_song(self.p, s.p, tr)
        for i, e in enumerate(self.notes()):
            s._idx.setdefault(_ev_key(e), []).append(i)
        self.d.nv_song_finish(s.p, float(total))
        return s


def play(song, classes, tmpl, br, cap, register=False, scale=1.0):
    """nv_play: every note of song through the engine, in the note loop's
    order. classes(program, key) -> the voice class, or None; tmpl a NoteIn
    with the emitter's constants; br {channel: bend (or fader) row}; cap the
    rows the store holds; register: the free strings' rows after the notes'
    (nv_play_full; scale the render's register scale). (rows, qacc,
    azimuth), or (None, i) where note i could not be the engine's (-1: the
    store too small)."""
    import random
    import numpy as np
    d = lib()
    K = (ctypes.c_void_p * (128 * 128))()
    keep = []
    for prog in range(128):
        for key in range(128):
            cls = classes(prog, key)
            k = note_class(cls) if cls is not None else None
            if k is not None:
                keep.append(k)
                K[128 * prog + key] = ctypes.addressof(k)
    nbr = max([int(c) + 1 for c in br] + [1])
    B = (ctypes.c_double * nbr)(*[float(br.get(c, -1)) for c in range(nbr)])
    random.seed(0)
    rs = random_state()
    qacc = np.zeros(18)
    az = ctypes.c_double(0.0)
    nr = ctypes.c_longlong(0)
    if register:
        import blockrender as BR
        import damper as DM
        kind = (ctypes.c_int * NCOLS)(*[1 if c in BR._COL_F4 else 2 if c in BR._COL_I4 else 0
                                        for c in BR.EMIT_COLS])
        buf = ctypes.POINTER(ctypes.c_double)()
        n = d.nv_play_full(song.p, K, ctypes.byref(tmpl), B, nbr, ctypes.byref(rs), ctypes.byref(buf),
                           qacc.ctypes.data, ctypes.byref(az), kind, float(scale), DM.FULL_DB_S, DM.RESIDUAL,
                           DM.BETA, BR.BLK, None, None, None, None, None, 1)
        try:
            if n < 0:
                return None, (-n - 1 if n > -1000000000 else -1)
            rows = np.ctypeslib.as_array(buf, shape=(n, NCOLS)).copy() if n else np.zeros((0, NCOLS))
        finally:
            d.nv_buf_free(buf)
        return rows, qacc, az.value
    while True:
        rows = np.empty((cap, NCOLS))
        random.seed(0)
        rs = random_state()
        qacc[:] = 0.0
        az.value = 0.0
        n = d.nv_play(song.p, K, ctypes.byref(tmpl), B, nbr, ctypes.byref(rs), rows.ctypes.data, cap,
                      qacc.ctypes.data, ctypes.byref(az), ctypes.byref(nr), None, None, None, None)
        if n != -2000000000:
            break
        cap *= 2            # the store was too small: again, from the start
    if n < 0:
        return None, -n - 1
    return rows[:nr.value], qacc, az.value


class StringMode(ctypes.Structure):
    """native/strings.c's StringMode: one mode of the register's string bank."""
    _fields_ = [('key', LL), ('string', LL), ('harm', LL)] + [(f, C) for f in (
        'f', 'alpha', 'w', 'hl', 'hr', 'dl', 'dr', 'px')]


def strings(cls, table, pan, chan_vol, sr):
    """register.Strings' arrays for a piano class from native/strings.c:
    {name: numpy array} (key, string, harm, f, alpha, w, hl, hr, dl, dr, px,
    W), or None where the class is not the engine's. table {key: Hz}; the
    honky-tonk's detune as the module's honky_detune stands."""
    import numpy as np
    import tonelib as T
    got = _class(cls)
    if got is None:
        return None
    c = VoiceInit.from_buffer_copy(got[0])
    lo, hi = cls.string_detune_range
    if issubclass(cls, T.HonkyTonkProperties):
        lo, hi = lo * T.honky_detune, hi * T.honky_detune
    c.detune_lo, c.detune_hi = lo, hi
    c.fixed_touch = int(bool(T.FIXED_TOUCH))
    tab = (ctypes.c_double * 128)(*[float(table[k]) if k in table else 0.0 for k in range(128)])
    cap = 88 * 4 * 130
    out = (StringMode * cap)()
    tmp = (StringMode * cap)()
    n = lib().nv_strings(ctypes.byref(c), ctypes.byref(got[1]), tab, float(pan), float(chan_vol), float(sr),
                         out, tmp, cap)
    if n < 0:
        return None
    a = np.frombuffer(out, dtype=np.dtype([('key', 'i8'), ('string', 'i8'), ('harm', 'i8')] + [
        (f, 'f8') for f in ('f', 'alpha', 'w', 'hl', 'hr', 'dl', 'dr', 'px')]), count=n)
    r = {k: np.array(a[k]) for k in a.dtype.names}
    r['W'] = 2.0 * math.pi * r['f']
    return r


# ------------------------------------------------------------------ exact array math
#
# numpy's float64 exp, power and complex abs over arrays are its own SIMD
# routines (SVML on AVX-512), a last bit away from libm on a fifth of their
# values -- and differently on another machine. xexp, xpow and xabs are
# libm's, element by element (native/exactmath.c): the same bits on every
# platform, and what a C port computes. numpy's where the library is not
# there.

def xexp(x):
    import numpy as np
    x = np.ascontiguousarray(x, np.float64)
    d = lib()
    if d is None:
        return np.exp(x)
    out = np.empty_like(x)
    d.nv_exp_n(x.size, x.ctypes.data, out.ctypes.data)
    return out


def xlog(x):
    import numpy as np
    x = np.ascontiguousarray(x, np.float64)
    d = lib()
    if d is None:
        return np.log(x)
    out = np.empty_like(x)
    d.nv_log_n(x.size, x.ctypes.data, out.ctypes.data)
    return out


def xpow(x, y):
    import numpy as np
    xa, ya = np.asarray(x, np.float64), np.asarray(y, np.float64)
    d = lib()
    if d is None:
        return np.power(xa, ya)
    shape = np.broadcast(xa, ya).shape
    if xa.ndim and ya.ndim and xa.shape != ya.shape:
        xa, ya = np.broadcast_arrays(xa, ya)
    xa, ya = np.ascontiguousarray(xa), np.ascontiguousarray(ya)
    out = np.empty(shape, np.float64)
    # a one-element operand is the scalar every element takes
    d.nv_pow_n(out.size, xa.ctypes.data, int(xa.size > 1), ya.ctypes.data, int(ya.size > 1), out.ctypes.data)
    return out if shape else float(out)


def xabs(z):
    import numpy as np
    z = np.ascontiguousarray(z, np.complex128)
    d = lib()
    if d is None:
        return np.abs(z)
    out = np.empty(z.shape, np.float64)
    d.nv_cabs_n(z.size, z.ctypes.data, out.ctypes.data)
    return out


def prepare(song, classes, tmpl, br, total, scale=1.0):
    """nv_prepare: blockrender.prepare's result for a piano song, as far as
    the engine has it -- {column: array} (EMIT_COLS, cast as the table
    stores them), N, nblk, P, total, room_q, sym_rows -- or (None, i) where
    note i is not the engine's."""
    import random
    import numpy as np
    import blockrender as BR
    import damper as DM
    d = lib()
    K = (ctypes.c_void_p * (128 * 128))()
    keep = []
    for prog in range(128):
        for key in range(128):
            cls = classes(prog, key)
            k = note_class(cls) if cls is not None else None
            if k is not None:
                keep.append(k)
                K[128 * prog + key] = ctypes.addressof(k)
    nbr = max([int(c) + 1 for c in br] + [1])
    B = (ctypes.c_double * nbr)(*[float(br.get(c, -1)) for c in range(nbr)])
    random.seed(0)
    rs = random_state()
    qacc = np.zeros(18)
    az = ctypes.c_double(0.0)
    kind = (ctypes.c_int * NCOLS)(*[1 if c in BR._COL_F4 else 2 if c in BR._COL_I4 else 0 for c in BR.EMIT_COLS])
    out = (ctypes.c_double * 48)()
    buf = ctypes.POINTER(ctypes.c_double)()
    dm = (ctypes.c_void_p * 6)()
    n = d.nv_prepare(song.p, K, ctypes.byref(tmpl), B, nbr, ctypes.byref(rs), ctypes.byref(buf), qacc.ctypes.data,
                     ctypes.byref(az), kind, float(scale), DM.FULL_DB_S, DM.RESIDUAL, DM.BETA, BR.BLK, float(total),
                     BR.RING_FLOOR, BR.RING_MAX, out, DM.KNEE_DB, DM.LN10_20, float(BR.XDEC_NEPERS),
                     float(BR.SR), dm, 1)
    try:
        if n < 0:
            return None, (-n - 1 if n > -1000000000 else -1)
        rows = np.ctypeslib.as_array(buf, shape=(n, NCOLS)).copy() if n else np.zeros((0, NCOLS))
    finally:
        d.nv_buf_free(buf)
    dt = {c: (np.float32 if c in BR._COL_F4 else np.int32 if c in BR._COL_I4 else np.float64)
          for c in BR.EMIT_COLS}
    P = {c: rows[:, j].astype(dt[c]) for j, c in enumerate(BR.EMIT_COLS)}
    nd = int(out[41])
    if nd:
        # THE HALF-PEDAL'S TRACKS (dk, dg per row; DM, DMO, DMB, DMN), as onto_tracks returns them
        nrow, ntr, ndm = int(out[2]), int(out[40]), nd
        a = lambda i, t, k: np.ctypeslib.as_array(ctypes.cast(dm[i], ctypes.POINTER(t)), shape=(k,)).copy()  # noqa
        P.update(dk=a(0, ctypes.c_int32, nrow), dg=a(1, ctypes.c_float, nrow), DM=a(2, ctypes.c_float, ndm),
                 DMO=a(3, ctypes.c_int64, ntr), DMB=a(4, ctypes.c_int64, ntr), DMN=a(5, ctypes.c_int64, ntr))
        for i in range(6):
            d.nv_buf_free(dm[i])
    P.update(N=int(out[0]), nblk=int(out[1]), P=int(out[2]), total=float(total),
             sym_rows=(int(out[3]), int(out[3])),
             room_q=[(out[4 + 3 * i], out[5 + 3 * i], out[6 + 3 * i]) for i in range(9)])
    return P


_VF = ('aL', 'aR', 'nf', 'fa', 're', 'ch', 'logr', 'logrA', 'aft', 'sus', 'cv', 'cc', 'crl', 'sj', 'csc', 'cbw',
       'tbav', 'tau', 'tcut', 'gb', 'gt', 'gc', 'vd', 'vr', 'vp', 'vdl', 'delL', 'delR', 'dg')


def final(P):
    """A native.prepare result in prepare's final column types (FINAL_DTYPES),
    as blockrender hands the kernel: the trivial side tables of a song with
    no bend, swell or chest rows (G, S, BR 1; BC 0), and its shutter."""
    import numpy as np
    import blockrender as BR
    out = dict(P)
    for k, dt in BR.FINAL_DTYPES:
        if k in P:
            out[k] = np.ascontiguousarray(np.asarray(P[k], np.float64 if dt.startswith('i') else None).astype(dt)
                                          if dt.startswith('i') else np.asarray(P[k]).astype(dt))
    out['G'] = np.ones((1, 1), np.float32)
    out['S'] = np.ones((1, 1), np.float32)
    out['BR'] = np.ones((1, 1), np.float32)
    out['BC'] = np.zeros((1, 1), np.float64)
    out['sh'] = BR.SHUTTER if hasattr(BR, 'SHUTTER') else (0.06, 1.6, 3.5, 1500.0)
    return out


def render(F):
    """nv_render: the table F (final types: native.final, or blockrender.prepare's
    own) to (L, R) float32 over [0, N) -- synthkernel.c's three entries as
    blockrender builds them, routed as synth_partials does, the master gain
    and the clip: synth_window(F, 0, N) on the CPU."""
    import numpy as np
    import blockrender as BR
    d = lib()
    n = int(F['N'])
    L = np.empty(n, np.float32)
    R = np.empty(n, np.float32)
    keep = []

    def ptrs(t, cols, dt):
        arr = (ctypes.c_void_p * len(cols))()
        for j, c in enumerate(cols):
            if c in F and F[c] is not None:
                a = np.ascontiguousarray(F[c], dt)
                keep.append(a)
                arr[j] = a.ctypes.data
        return arr
    D = ptrs(None, ('om', 'p0', 'p0R'), np.float64)
    Fp = ptrs(None, _VF, np.float32)
    Lp = ptrs(None, ('non', 'noff'), np.int64)
    Ip = ptrs(None, ('gr', 'cr', 'br', 'dk'), np.int32)
    tabs = [np.ascontiguousarray(F[k], t) for k, t in (('G', np.float32), ('S', np.float32), ('BR', np.float32),
                                                       ('BC', np.float64))]
    keep.extend(tabs)
    sh = (ctypes.c_float * 4)(*[float(x) for x in F['sh']])
    has = F.get('DM') is not None
    dm = [np.ascontiguousarray(F[k], t) for k, t in (('DM', np.float32), ('DMO', np.int64), ('DMB', np.int64),
                                                     ('DMN', np.int64))] if has else [None] * 4
    keep.extend([a for a in dm if a is not None])
    fn = lambda f: ctypes.cast(f, ctypes.c_void_p).value       # noqa: E731
    sv = fn(BR.ensure_lib().synth_voice)
    sx = fn(BR.ensure_xdec_lib().synth_voice_xdec)
    sd = fn(BR.ensure_damp_lib().synth_voice_damp)
    d.nv_render(sv, sx, sd, n, BR.BLK, int(F['nblk']), int(F['P']), D, Fp, Lp, Ip, tabs[0].ctypes.data,
                tabs[1].ctypes.data, tabs[2].ctypes.data, tabs[3].ctypes.data, BR._NO_ROWS.ctypes.data, sh,
                BR._chunk(), float(BR.XDEC_NEPERS), float(BR.SR), float(BR.T.master_gain),
                *[a.ctypes.data if a is not None else None for a in dm], L.ctypes.data, R.ctypes.data)
    return L, R


def build_nvrender():
    """native/nvrender (the standalone renderer), built beside libnative.so
    when a source is newer: its path."""
    lib()
    src = os.path.join(HERE, 'native', 'nvrender.cpp')
    exe = os.path.join(HERE, 'nvrender')
    so = os.path.join(HERE, 'libnative.so')
    if not os.path.exists(exe) or max(os.path.getmtime(src), os.path.getmtime(so)) > os.path.getmtime(exe):
        tmp = '%s.%d.tmp' % (exe, os.getpid())
        subprocess.check_call(['g++', '-std=c++17', '-O2', '-march=native', '-ffp-contract=off', '-fno-builtin',
                               src, '-o', tmp, '-L' + HERE, '-lnative', '-ldl', '-Wl,-rpath,$ORIGIN'])
        os.replace(tmp, exe)
    return exe


def template(program, note, vel, tuner='hybrid440'):
    """nv_template: live's template table for a key (live.Voice._raw_template's
    blockrender.prepare of a one-note file, fixed touch, no register), from
    the engine -- {column: array} in prepare's final types, N, nblk, P,
    room_q -- or None where the key is not the engine's."""
    import math
    import numpy as np
    import blockrender as BR
    import damper as DM
    import patch_map as PM
    import percussion_map as PCM
    import tonelib as T
    d = lib()
    cls = BR.property_class_for_note(program, note)
    k = note_class(cls) if cls is not None else None
    if k is None:
        return None
    K = (ctypes.c_void_p * (128 * 128))()
    K[128 * program + note] = ctypes.addressof(k)
    t = NoteIn()
    t.sr, t.retrigger_fade, t.nyq_om = BR.SR, BR.RETRIGGER_FADE, 0.98 * math.pi
    t.sv[:] = [0.0, 1.0]
    t.sound_vib_depth_cents, t.vibrato_delay = T.SOUND_VIB_DEPTH_CENTS, 0.0
    t.gl[:] = [0.0, 0.05, 0.0]
    t.fx, t.mk, t.fm_omega, t.fm_phase = -1.0, 0.0, 0.0, 0.0
    t.room_bands[:] = [63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0]
    t.reflect = int(os.environ.get("TUNING_REFLECT", "1") not in ("0", "off", ""))
    t.fixed_touch = 1                       # live builds its templates at fixed touch
    freq = BR.tuning_table(tuner)
    F = (ctypes.c_double * 128)(*[float(freq[q]) if q in freq else 0.0 for q in range(128)])
    tr = (ctypes.c_double * 256)(*([float(PM.program_trim(p, False)) for p in range(128)]
                                   + [float(PM.program_trim(PCM.DrumProgram(p), True)) for p in range(128)]))
    kind = (ctypes.c_int * NCOLS)(*[1 if c in BR._COL_F4 else 2 if c in BR._COL_I4 else 0 for c in BR.EMIT_COLS])
    out = (ctypes.c_double * 48)()
    buf = ctypes.POINTER(ctypes.c_double)()
    dm = (ctypes.c_void_p * 6)()
    n = d.nv_template(K, ctypes.byref(t), F, tr, int(program), int(note), int(vel), -1, ctypes.byref(buf), kind,
                      float(os.environ.get("TUNING_REGISTER", "1") or 1), DM.FULL_DB_S, DM.RESIDUAL, DM.BETA,
                      BR.BLK, BR.RING_FLOOR, BR.RING_MAX, out, DM.KNEE_DB, DM.LN10_20, float(BR.XDEC_NEPERS),
                      float(BR.SR), dm)
    try:
        if n < 0:
            return None
        rows = np.ctypeslib.as_array(buf, shape=(n, NCOLS)).copy() if n else np.zeros((0, NCOLS))
    finally:
        d.nv_buf_free(buf)
    dt = {c: (np.float32 if c in BR._COL_F4 else np.int32 if c in BR._COL_I4 else np.float64)
          for c in BR.EMIT_COLS}
    P = {c: rows[:, j].astype(dt[c]) for j, c in enumerate(BR.EMIT_COLS)}
    P.update(N=int(out[0]), nblk=int(out[1]), P=int(out[2]), sym_rows=(int(out[3]), int(out[3])),
             room_q=[(out[4 + 3 * i], out[5 + 3 * i], out[6 + 3 * i]) for i in range(9)])
    return final(P)


LIVE_F8 = ("om", "p0", "p0R", "fmw", "fmp", "fmpR")
LIVE_F4 = ("aL", "aR", "nf", "fa", "re", "ch", "logr", "logrA", "aft", "sus", "cv", "cc", "crl", "sj", "csc",
           "cbw", "tbav", "tau", "tcut", "vd", "vr", "vp", "delL", "delR", "az", "rdl", "nfr")
LIVE_F4N = ("gb", "gt", "gc", "vdl")
LIVE_I4 = ("gr", "cr", "br", "pl", "fx", "mk")
SLAB_BOOK = ("sw", "aL0", "aR0", "sg", "sre", "hrel", "vbase", "vrbase", "vsc")


class Slab(object):
    """native/slab.cpp's slab: live.Slab's core for a piano -- stamp, release,
    reap -- and its columns read back as live.Slab's names them."""

    def __init__(self, capacity, headroom=1.0):
        self.d = lib()
        self.cap = capacity
        self.p = self.d.nv_slab_new(capacity, float(headroom))

    def __del__(self):
        if getattr(self, 'p', None):
            self.d.nv_slab_free(self.p)
            self.p = None

    def stamp(self, tmpl, key, n0, vel_scale):
        import numpy as np
        n = int(tmpl["P"])
        keep = []

        def arr(cols, dt):
            a = (ctypes.c_void_p * len(cols))()
            for j, c in enumerate(cols):
                v = np.ascontiguousarray(tmpl[c], dt) if c in tmpl and tmpl[c] is not None else np.zeros(n, dt)
                keep.append(v)
                a[j] = v.ctypes.data
            return a
        f8 = arr(LIVE_F8, np.float64)
        f4 = arr(LIVE_F4, np.float32)
        i8 = arr(("non", "noff"), np.int64)
        i4 = arr(LIVE_I4, np.int32)
        hr = np.ascontiguousarray(tmpl["hrel"], np.float32)
        snd = tmpl.get("send")
        part, ch, note, layer = key[0], key[1], key[2], key[3]
        return bool(self.d.nv_slab_stamp(self.p, f8, f4, i8, i4, hr.ctypes.data, n, int(part), int(ch), int(note),
                                         -1 if layer is None else int(layer), int(n0), float(vel_scale),
                                         int(tmpl.get("dur", 0)), int(bool(tmpl.get("oneshot"))),
                                         float("nan") if snd is None else float(snd)))

    def release(self, key, n):
        self.d.nv_slab_release(self.p, int(key[0]), int(key[1]), int(key[2]),
                               -1 if key[3] is None else int(key[3]), int(n))

    def reap(self, n, blk):
        self.d.nv_slab_reap(self.p, int(n), int(blk))

    def col(self, name):
        import numpy as np
        for g, (cols, dt) in enumerate(((LIVE_F8, np.float64), (LIVE_F4, np.float32), (LIVE_F4N, np.float32),
                                        (("non", "noff"), np.int64), (LIVE_I4, np.int32),
                                        (SLAB_BOOK, np.float32), (("dk", "slot_ch", "busy"), np.int32))):
            if name in cols:
                out = np.empty(self.cap, dt)
                self.d.nv_slab_col(self.p, g, cols.index(name), out.ctypes.data)
                return out
        raise KeyError(name)

    def free_list(self):
        import numpy as np
        out = np.empty(self.cap, np.int64)
        n = self.d.nv_slab_free_list(self.p, out.ctypes.data, self.cap)
        return out[:n].tolist()


class TemplateCache(object):
    """native/live.cpp's template cache: live.Patch's for a piano program --
    each key at every velocity bucket's centre and every wheel step, built
    once (warm) and looked up (get) -- its templates as live's dicts."""

    def __init__(self, program, tuner='hybrid'):
        import math
        import blockrender as BR
        import damper as DM
        import patch_map as PM
        import percussion_map as PCM
        import tonelib as T
        self.d = lib()
        self.program = program
        self.keep = []
        K = (ctypes.c_void_p * (128 * 128))()
        for key in range(128):
            cls = BR.property_class_for_note(program, key)
            k = note_class(cls) if cls is not None else None
            if k is not None:
                self.keep.append(k)
                K[128 * program + key] = ctypes.addressof(k)
        t = NoteIn()
        t.sr, t.retrigger_fade, t.nyq_om = BR.SR, BR.RETRIGGER_FADE, 0.98 * math.pi
        t.sv[:] = [0.0, 1.0]
        t.sound_vib_depth_cents, t.vibrato_delay = T.SOUND_VIB_DEPTH_CENTS, 0.0
        t.gl[:] = [0.0, 0.05, 0.0]
        t.fx, t.mk, t.fm_omega, t.fm_phase = -1.0, 0.0, 0.0, 0.0
        t.room_bands[:] = [63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0]
        t.reflect = int(os.environ.get("TUNING_REFLECT", "1") not in ("0", "off", ""))
        t.fixed_touch = 1
        freq = BR.tuning_table(tuner)
        F = (ctypes.c_double * 128)(*[float(freq[q]) if q in freq else 0.0 for q in range(128)])
        tr = (ctypes.c_double * 256)(*([float(PM.program_trim(p, False)) for p in range(128)]
                                       + [float(PM.program_trim(PCM.DrumProgram(p), True)) for p in range(128)]))
        kind = (ctypes.c_int * NCOLS)(*[1 if c in BR._COL_F4 else 2 if c in BR._COL_I4 else 0
                                        for c in BR.EMIT_COLS])
        fin = dict(BR.FINAL_DTYPES)
        fn = (ctypes.c_int * NCOLS)(*[{'f8': 0, 'f4': 1, 'i8': 2, 'i4': 3}.get(fin.get(c), -1)
                                      for c in BR.EMIT_COLS])
        self.p = self.d.nv_tcache_new(K, ctypes.byref(t), F, tr, kind, fn,
                                      float(os.environ.get("TUNING_REGISTER", "1") or 1), DM.FULL_DB_S,
                                      DM.RESIDUAL, DM.BETA, BR.BLK, BR.RING_FLOOR, BR.RING_MAX, DM.KNEE_DB,
                                      DM.LN10_20, float(BR.XDEC_NEPERS), float(BR.SR))

    def __del__(self):
        if getattr(self, 'p', None):
            self.d.nv_tcache_free(self.p)
            self.p = None

    def warm(self, lo, hi, nbuckets, speeds=(None,)):
        sp = (ctypes.c_int * len(speeds))(*[-1 if v is None else int(v) for v in speeds])
        return self.d.nv_tcache_warm(self.p, int(self.program), int(lo), int(hi), int(nbuckets), sp, len(speeds))

    def get(self, note, bucket, speed=None):
        """The template as live's dict (the piano's fields), or None."""
        import numpy as np
        o = (LL * 3)()
        t = self.d.nv_tcache_get(self.p, int(note), int(bucket), -1 if speed is None else int(speed), o)
        if not t:
            return None
        n = int(o[0])
        out = dict(P=n, dur=int(o[1]), vel=int(o[2]), oneshot=False, send=None, scatter_ms=0.0, FT=None, KN=None,
                   panel=None, grain=None, gof=None, sof=None, cof=None, rof=None, ranks={}, rel=None,
                   rel_rank={})

        def col(g, i, dt):
            p = self.d.nv_tmpl_col(t, g, i)
            return np.ctypeslib.as_array(ctypes.cast(p, ctypes.POINTER(dt)), shape=(n,)).copy() if n else \
                np.zeros(0, np.dtype(dt))
        for i, c in enumerate(LIVE_F8):
            out[c] = col(0, i, ctypes.c_double)
        for i, c in enumerate(LIVE_F4):
            out[c] = col(1, i, ctypes.c_float)
        for i, c in enumerate(LIVE_F4N):
            out[c] = col(2, i, ctypes.c_float)
        for i, c in enumerate(("non", "noff")):
            out[c] = col(3, i, ctypes.c_int64)
        for i, c in enumerate(LIVE_I4):
            out[c] = col(4, i, ctypes.c_int32)
        out["hrel"] = col(5, 0, ctypes.c_float)
        out["fa_at"] = col(6, 0, ctypes.c_int8).astype(bool)
        out["sym"] = np.zeros(n, bool)
        out["ring"] = np.zeros(n, bool)
        out["push"] = np.zeros(n, bool)
        out["lflip"] = np.zeros(n, bool)
        return out


class LivePiano(object):
    """native/slab.cpp's piano part, live: its template cache, its slab, and
    live.Live's events for it block by block. The slab reads back as a
    native.Slab's does."""

    def __init__(self, cache, pid, level_db, nbuckets, speed, damper_pedal, soft_drop, soft_top, rate,
                 capacity=16384, headroom=1.0):
        import live as L
        import blockrender as BR
        tab = L.pan_table()
        pt = (ctypes.c_double * (128 * 3))(*[float(x) for row in tab for x in row])
        self.d = lib()
        self.cache = cache
        self.p = self.d.nv_lp_new(cache.p, int(pid), float(level_db), int(nbuckets),
                                  -1 if speed is None else int(speed), int(bool(damper_pedal)), int(soft_drop),
                                  int(soft_top), float(rate), float(BR.RETRIGGER_FADE), int(capacity),
                                  float(headroom), pt, float(L._PAN_BETA))
        self.slab = Slab.__new__(Slab)
        self.slab.d, self.slab.cap, self.slab.p = self.d, capacity, self.d.nv_lp_slab(self.p)

    def __del__(self):
        if getattr(self, 'p', None):
            self.slab.p = None              # the part owns its slab
            self.d.nv_lp_free(self.p)
            self.p = None

    def event(self, msg):
        """A mido message for the next block (note-on, note-off, control change)."""
        if msg.type == "note_on" and msg.velocity > 0:
            self.d.nv_lp_event(self.p, 0, msg.channel, msg.note, msg.velocity)
        elif msg.type in ("note_on", "note_off"):
            self.d.nv_lp_event(self.p, 1, msg.channel, msg.note, 0)
        elif msg.type == "control_change":
            self.d.nv_lp_event(self.p, 2, msg.channel, msg.control, msg.value)

    def block(self, n0, blk):
        self.d.nv_lp_block(self.p, int(n0), int(blk))
