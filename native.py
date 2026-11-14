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
                ('bridge_order', C), ('bridge_force_power', C),
                ('kind', I), ('unison_gain', C), ('n_unison', I), ('unison_detune', C * 8),
                ('n_modes', I), ('modes', (C * 3) * 128), ('n_click', I), ('click_per_band', I),
                ('click_db', C * 32), ('click_hz0', C), ('click_cal_db', C), ('click_scatter', C),
                ('click_dbs', C), ('click_stroke_slope', C), ('stroke_ref_db', C),
                ('slow_share', C), ('slow_dbs', C), ('slow_max_hz', C),
                ('noisy', I), ('hf_corner_hz', C), ('hf_order', C), ('nyquist', C), ('n_trim', I), ('trim', (C * 2) * 32),
                ('snare', I), ('fund_dbs', C), ('head_dbs', C), ('wire_jitter', C), ('head_jitter', C),
                ('rim_from', I), ('rim_dbs', C), ('measured', I), ('ring_scale', C), ('mode_scatter_db', C),
                ('jit_sus', I), ('jit_from', I), ('tamb', I), ('retarget', I), ('decay_target', C),
                ('mm_harm', I), ('n_mm', I), ('mm_ratio', C * 400), ('mm_gain', C * 400), ('cymbal', I),
                ('ring_peak_hz', C), ('ring_decay_below', C), ('ring_decay_above', C), ('ring_decay_floor', C),
                ('aftersound_fraction', C), ('aftersound_dbs', C), ('aftersound_ratio', C),
                ('bloom_gain', C), ('bloom_banded', I), ('bloom_swell', C), ('bloom_scatter', C),
                ('bloom_decay_dbs', C), ('bore_corner_hz', C), ('bore_order', C), ('bell_cutoff_hz', C),
                ('bell_order', C), ('bore_norm', C),
                ('blare_db_per_khz', C), ('blare_knee_hz', C), ('blare_cap_db', C), ('blare_norm', C), ('pea', I), ('pea_vibrato_cents', C), ('pea_vibrato_hz', C),
                ('n_bar', I), ('bar_n', I * 16), ('bar_g', C * 16),
                ('n_md', I), ('n_ma', I), ('n_mp', I), ('mode_decays', C * 400), ('mode_after', (C * 2) * 400),
                ('mode_phases', C * 400), ('throat', I), ('n_mb', I), ('stroke_tilt_db', C),
                ('formant_scale', C), ('formant_morph', C), ('breath_volume', C), ('mb', (C * 2) * 128),
                ('fbody', I), ('n_fm', I), ('n_afm', I), ('n_bt', I), ('formant_floor', C), ('fm', (C * 3) * 16),
                ('afm', (C * 3) * 8), ('bt', (C * 2) * 32), ('comb', C * 257),
                ('sect_n', I), ('sect_vib', I), ('sect_seats', I), ('sect_spread_cents', C), ('sect_vib_cents', C),
                ('sect_vib_hz', C * 2), ('sect_onset_ms', C), ('sect_ofm', C), ('sect_dx', C * 16),
                ('n_pts', I), ('n_ptg', I), ('low_set', I), ('n_low', I), ('pts_n', I * 8), ('pts_hz', C * 8), ('pts_g', (C * 64) * 8),
                ('low_g', C * 64), ('low_hz', C * 2), ('pipe_g', C * 64), ('n_pipe', I),
                ('reed', I), ('reed_points', I), ('n_reed', I), ('n_bank', I),
                ('reed_gate', C), ('reed_edge', C), ('reed_spread', C), ('reed_direct', C), ('reed_gate_oct', C),
                ('reed_spread_oct', C), ('reed_scatter', C), ('reed_scatter_oct', C),
                ('reed_s', C * 1025), ('bank_g', C * 4), ('bank_cents', C * 4), ('bank_oct', C * 4),
                ('bank_ratio', C * 4), ('sh_exp', C), ('sh_exp_oct', C), ('sh_cap', I),
                ('skirt', I), ('sk_max', I), ('sk_db', C), ('sk_hdb', C), ('sk_hz', C), ('sk_rel', C),
                ('ep_kind', I), ('ep_harm', I), ('ep_terms', I), ('n_tb', I), ('n_lay', I), ('ep_p', C * 5),
                ('ep_defl', C), ('ep_defl_slope', C), ('ep_defl_power', C), ('ep_defl_max', C), ('ep_rho', C),
                ('ep_max_hz', C), ('ep_floor_db', C), ('ep_share', C), ('tb_coeff', C), ('tb_power', C),
                ('tb_decay', C), ('tb_ratio', C * 8), ('tb_g', C * 8), ('ep_a0', C), ('ep_r', C * 408),
                ('ep_n', C * 400), ('ep_w', C * 400),
                ('elec', I), ('n_pk', I), ('pk_vel', I), ('n_os', I), ('eg_sp', C), ('eg_depth', C),
                ('pk_q0', C * 4), ('pk_sign', C * 4), ('pk_turns', C), ('pk_width', C), ('pk_res_hz', C),
                ('pk_qf', C), ('lp_hz', C), ('lp_order', C), ('os_hz', C * 8), ('fret_max', C), ('pk_sp', C),
                ('pk_q', C * 4), ('n_touch', I), ('touches', I * 4), ('touch0', I), ('touch', I), ('leak_set', I),
                ('leak_db', C), ('leak_dbs', C), ('ml_spread', C), ('ml_knee', C), ('ml_time', C),
                ('n_mute', I), ('mute', (C * 2) * 24), ('n_tube', I), ('tube_ref_hz', C), ('tube', (C * 4) * 32),
                ('or_set', I), ('or_share', C), ('or_db', C * 2), ('or_lowest_hz', C), ('or_g', C),
                ('dul_n', I), ('dhz_set', I), ('dul_beat', C * 2), ('dhz_db', C), ('dhz_pow', C), ('pps', C),
                ('ushare', I), ('mst', C), ('mst_ref', C),
                ('clav', I), ('cl_sel', I), ('cl_nt', I), ('cl_nk', I),
                ('cl_ref_m', C), ('cl_ref_hz', C), ('cl_pow', C), ('cl_bridge', C), ('cl_c0', C), ('cl_c1', C),
                ('cl_qmax', C), ('cl_tdb', C), ('cl_thump', C * 8), ('cl_kh', C * 8), ('cl_ka', C * 8),
                ('vk_n', I), ('vk_hz', C * 16), ('vk_amp', C * 16),
                ('hit_n', I), ('hit_cents', C * 8), ('hit_gain', C),
                ('pd_max_hz', C), ('pd_dbs', C), ('pd_share', C), ('pap_hz', C), ('pap_n', I),
                ('tap_kind', I), ('n_tap', I), ('n_gong', I), ('tap_drop', I), ('tap_t', C * 192),
                ('tap_gain', C), ('tap_jit', C), ('tap_ldb', C), ('gong', I * 16),
                ('n_hvt', I), ('hvt', C * 512), ('hvt_bore', I), ('chiff_bore', I), ('fv_set', I), ('fv_cents', C), ('fv_hz', C),
                ('wow_set', I), ('wow_cents', C), ('wow_hz', C),
                ('pick_set', I), ('pick_hz', C), ('pick_slope_db', C), ('pick_boost_max_db', C), ('pick_dbs', C),
                ('pick_stagger', C), ('crs_kind', I), ('crs_split', C), ('crs_oct_gain', C), ('crs_oct_cents', C),
                ('crs_uni_gain', C), ('crs_uni_cents', C), ('crs_seed', C), ('crs_lo', C), ('crs_hi', C),
                ('church', I), ('church_slope', C),
                ('fb_set', I), ('fb_fixed', I), ('n_fbs', I), ('fb_band_hz', C), ('fb_delay', C), ('fb_swell', C),
                ('fb_gain', C), ('fb_dbs', C), ('fbs', (C * 2) * 8), ('sw_set', I), ('sw_cents', C),
                ('sw_hz', C * 2), ('mm_pts', I), ('mr_law', I), ('mr_a', C * 2), ('mr_b', C * 2), ('mr_lo', C * 2),
                ('mr_ref', C), ('mr_body', C * 3), ('crs_ntrio', I), ('crs_trio', C * 4),
                ('swp_set', I), ('swp_share', C), ('swp_tog', C * 2), ('swp_swept', C * 2), ('swp_step', C)]


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
                + [('room_bands', C * 9), ('pjit', I), ('sps', C), ('dur', C), ('ssc', I)]
                + [('rev', I), ('rev_n0', C), ('rev_arr', C), ('planes', C * 6), ('order', I), ('radius', C),
                   ('has_radius', I), ('pps_seed', ctypes.c_longlong), ('dist', C), ('cls', ctypes.c_longlong),
                   ('hammer_on', C), ('gs_eq', C * 4), ('fx_comp', C * 3), ('alias_br', C * 32), ('n_alias', I)])


class VoiceInit(ctypes.Structure):
    """native/voice.c's VoiceInit: a class's constants for its constructor."""
    _fields_ = ([(f, C) for f in ('tonal_dampening', 'octave_dampening')] + [('octave_modulo', I)]
                + [(f, C) for f in ('octave_width', 'seat_x', 'decay_register_slope', 'pitch_jitter_cents',
                                    'timing_jitter_seconds', 'tape_key_cents', 'tension_bend', 'tension_bend_max',
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
                + [('level_hz', C * 32), ('level_db', C * 32)] + [('kind', I)]
                + [('bloom_gain', C), ('bloom_gain_slope', C)]
                + [('chiff_volume', C), ('sustain_jitter', C), ('strike_noise_slope', C), ('n_vtrim', I),
                   ('vtrim_v', C * 16), ('vtrim_db', C * 16)]
                + [('strike_wobble_hz', C), ('strike_wobble_gain', C), ('strike_wobble_slope', C)]
                + [('rnd', I)] + [(f, C) for f in ('rnd_level_db', 'rnd_effort_db', 'rnd_cents', 'rnd_timing_s')]
                + [('rnd_draws', C * 4), ('law_k', C), ('law_p', C), ('bb_hz', C), ('bb_B', C),
                   ('has_course', I), ('course', ctypes.c_ubyte * 128),
                   ('n_open', I), ('open_st', C * 8), ('pluck_open', C),
                   ('vbody', I), ('n_vb', I), ('vb_fm', (C * 3) * 16)]
                + [(f, C) for f in ('vb_tract', 'vb_sigma', 'vb_mb', 'vb_xhz', 'vb_xoct', 'vb_ftop', 'vb_sfhz')]
                + [('part_set', I), ('part_ratio', C), ('part_cluster', C), ('sung_hz', C)])


class VoiceNote(ctypes.Structure):
    """native/voice.c's VoiceNote: what the note setup reads of a voice besides its VoiceSnap."""
    _fields_ = [(f, C) for f in ('pitch_jitter', 'attack_jitter', 'pan_angle', 'left_incidence',
                                 'right_incidence', 'left_hrtf_delay', 'right_hrtf_delay',
                                 'inharmonicity_coefficient', 'B', 'tension_bend', 'attack_time',
                                 'chiff_volume', 'sustain_jitter')]


class PyRandomState(ctypes.Structure):
    """pycompat.h's PyRandom: CPython's Mersenne Twister, its 624 words and
    index, and random.gauss's kept second value (gauss_next)."""
    _fields_ = [('mt', ctypes.c_uint32 * 624), ('i', I), ('has_gauss', I), ('gauss_next', C)]


class MoogLayer(ctypes.Structure):
    """native/nv.h's MoogLayer: one Messenger's panel as a note reads it (moog_spec)."""
    _fields_ = [('t', C), ('foot1', C), ('foot2', C), ('o2f', C), ('lvl', C * 4),
                ('c1', (C * 2) * 64), ('c2', (C * 2) * 64), ('cs', (C * 2) * 32),
                ('n_noise', I), ('noise_hz', C * 32), ('noise_amp', C * 32),
                ('self_amp', C), ('self_cut', C), ('self_eg', C), ('kb_track', C),
                ('fm_index', C), ('fm_r1', C), ('fm_ph', C), ('ft', C * 30), ('kn', C * 9), ('rel_span', C),
                ('fmax_hz', C), ('kb_ref_hz', C), ('noise_bw', C),
                ('pitch_on', I), ('shape_on', I), ('pitch_p', C * 9), ('shape_par', C * 25),
                ('knob', C * 5), ('span', C * 5), ('eg_v', C * 11), ('eg_log', C * 11),
                ('atk_to_1', C), ('cut_lo', C), ('cut_oct', C), ('k_max', C), ('res_per_unit', C),
                ('self_from', C), ('self_amp_max', C), ('eg_under', C), ('body', I),
                ('pre', I), ('bp_gain', C), ('bp_corner', C), ('hp_gain', C), ('hp_corner', C), ('hp_leak', C),
                ('mf_on', I), ('mf', C * 7), ('mf_grid', C), ('mf_max', C), ('mf_floor', C), ('mf_poles', C),
                ('u_n', I), ('u_cents', C), ('u_mix', C), ('u_dc', C), ('u_dhz', C * 2), ('u_width', C),
                ('pn', C * 51)]


class MoogSpec(ctypes.Structure):
    _fields_ = [('n_layer', I), ('L', MoogLayer * 2)]


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
                   ('reg_release', C)]
                + [('reg_keyed', I), ('reg_kb', I * 128), ('reg_partner', I * 128), ('reg_cross', C),
                   ('reg_partner_k', C), ('reg_ktilt', C), ('reg_nkp', I), ('reg_kp_x', C * 64), ('reg_kp_db', C * 64)]
                + [('one_shot', I), ('one_shot_hold', C), ('tape_s', C), ('pjit', I), ('sps', C),
                   ('ssc', I), ('gate_time', C), ('held_texture', I), ('shake', I), ('n_nb', I),
                   ('noise_rows', I), ('nb_hz', C * 32), ('nb_db', C * 32)]
                + [(f, C) for f in ('shake_min_s', 'shake_frac', 'shake_xfade_s', 'rise_s', 'settle_db',
                                    'settle_s', 'noise_rel')]
                + [('n_flam', I), ('flam_s', C), ('flam_db', C), ('flam_rate', C), ('flam_exp', C),
                   ('people_n', I), ('pk_set', I), ('people_lo', C), ('people_hi', C), ('people_jit', C),
                   ('people_db', C), ('pk_lo', C), ('pk_hi', C), ('pk_db', C), ('pk_q', C),
                   ('n_nev', I), ('nev', (C * 4) * 64), ('nev_ramp_s', C)]
                + [('n_ft', I), ('ft_bal', I), ('ft_t', C * 64), ('ft_db', C * 64), ('ft_c', C * 64)]
                + [('n_layer', I), ('lay_n', I * 32), ('lay_hz', (C * 32) * 32), ('lay_db', (C * 32) * 32),
                   ('lay_rise', C * 32), ('lay_dbs', C * 32), ('lay_len', C * 32), ('played_backwards', I)]
                + [('n_bn', I), ('bn_rows', I), ('bn_low_set', I), ('bn_low', C * 64), ('bn_low_hz', C * 2),
                   ('bn_fade_s', C), ('bn_hz', C * 64), ('bn_db', C * 64)]
                + [('bendable', I), ('snd_mask', I), ('snd_bias', C * 8), ('snd_time_range', C),
                   ('snd_rate_range', C), ('snd_delay_s', C), ('glide_mech', I), ('glide_reach', C),
                   ('porta_fast', C), ('porta_slow', C), ('porta_d_semi', C), ('porta_settle', C),
                   ('organ', ctypes.c_void_p), ('leslie', I), ('scanner', I), ('amp_drive', C),
                   ('amp_reference', C), ('amp_imbalance', C), ('wheel_swell', I)]
                + [(f, C) for f in ('push_gain', 'push_rise_s', 'push_dbs', 'push_settle_db', 'push_tilt',
                                    'push_tilt_oct')]
                + [('breath', I), ('breath_p', C * 8), ('trem_hz', C), ('trem_depth', C), ('trem_scatter', C),
                   ('trem_stereo', I), ('trem_intrinsic', I), ('touch_sensitive', I),
                   ('cab_set', I), ('n_cab_fm', I), ('n_cab_afm', I), ('cab_floor', C), ('cab_fm', C * 3 * 4),
                   ('cab_afm', C * 3 * 4), ('cab_corner', C), ('cab_order', C), ('cab_cut', C), ('cab_bell', C),
                   ('cab_ref', C), ('n_click', I), ('click_jacks', I), ('click_db', C), ('click_hz', C * 16),
                   ('click_amp', C * 16), ('click_dec', C), ('click_s', C), ('pre_pluck', I),
                   ('moog', MoogSpec), ('brass', I), ('bn_slur', I),
                   ('os_floor_db', C), ('os_max_s', C), ('tail_set', I), ('tail_db', C), ('tail_dbs', C),
                   ('clav_panel', I), ('wheel_vibrato', I),
                   ('sh_et', C), ('sh_corner', C), ('sh_order', C), ('sh_sp', C), ('sh_sd', C), ('sh_B', C),
                   ('sh_mq', C), ('sh_mhz', C), ('sh_mdb', C), ('sh_popen', C), ('sh_pluck', I), ('sh_mh', I),
                   ('sh_nopen', I), ('sh_open', C * 8), ('scatter_ms', C),
                   ('sl_on', I), ('sl_idx', I), ('sl_nm', I), ('sl_db', C), ('sl_rise', C), ('sl_dbs', C),
                   ('sl_lo', C), ('sl_hi', C), ('sl', ctypes.c_void_p), ('n_cho', I), ('cho_cents', C * 8),
                   ('sym_kind', I), ('sym_n', I), ('sym_top', I), ('sym_nobend', I), ('sym_floor', C),
                   ('sym_pitch', I * 32), ('sym_d', C * 32), ('sym_cents', C * 32),
                   ('ring_n', I), ('ring_hz', C * 48), ('ring_db', C * 48), ('ring_dps', C * 48),
                   ('ring_skip', C), ('ring_nown', I), ('ring_own', C * 16), ('indian', I),
                   ('sym_tonic', I), ('sym_g', C), ('sym_wmin', C), ('meend', I),
                   ('meend_range', C), ('meend_strength', C), ('meend_tonic', I), ('key_pan_spread', C),
                   ('n_grain', I), ('grain', (C * 9) * 8),
                   ('pulse', I), ('pulse_lo_ms', C), ('pulse_hi_ms', C), ('pulse_peak', C), ('pulse_fmax', C),
                   ('pulse_taper', C), ('sounding_oct', C), ('xf', C), ('sfx_prog', I), ('sfx_key', I),
                   ('scale_n', I), ('scale_tonic', I), ('scale_off', I * 32), ('scale_c', C * 32),
                   ('si_set', I), ('si0', C), ('si1', C),
                   ('n_drone', I), ('drone_note', I * 4), ('drone_k', I * 4), ('part_break_s', C),
                   ('n_dchoice', I), ('dchoice_def', I), ('dchoice', I * 16), ('dchoice_var', I),
                   ('drone_wheel', I), ('n_dratio', I), ('drone_ratio', C * 4), ('drone_gain', C * 4),
                   ('rd_set', I), ('reverb_dist', C), ('hammer', I),
                   ('fall_cents', C), ('fall_at_s', C), ('fall_s', C), ('fall_fade_db', C), ('fall_smear', C),
                   ('rip_cents', C), ('rip_s', C), ('rip_start_db', C), ('rip_smear', C),
                   ('cut_semi', I), ('cut_s', C),
                   ('cho_send', C), ('pair_set', I), ('pair_lo', C), ('pair_hi', C),
                   ('tp_hz', C), ('tp_up_db', C), ('tp_jit', C), ('siren', I),
                   ('efx_set', I), ('efx_eq_set', I), ('efx_level', C), ('efx_od', C), ('efx_eq', C * 5),
                   ('efx_rev', C), ('efx_raw', I), ('efx_raw_ty', I * 2), ('efx_raw_p', I * 21), ('efx_cf', I), ('cf_p', C * 40), ('efx_dly', I), ('dly_p', C * 24),
                   ('efx_place', C * 13), ('efx_trem', I), ('trem_cfg', C * 4),
                   ('flt_set', I), ('flt_ty', I), ('flt_k', I), ('flt_p', C * 3), ('flt_c', C * 5),
                   ('n_mouth', I), ('mouth_seed', I), ('mouth_st', C * 3 * 16), ('mouth_cdf', C * 16),
                   ('mouth_wst', C * 3 * 16), ('mouth_dw', C * 2), ('mouth_glide', C),
                   ('efx_bus', I), ('bus_p', C * 12), ('fold_restrike', I), ('alias_sweep', C * 5),
                      ('flam_record', I), ('n_rq', I), ('rec_per', C), ('rec_pr', C), ('rec_qx', C * 8), ('rec_qy', C * 8),
                      ('bn_oct', C), ('bn_ref', C), ('osr_n', I), ('osr_open', C * 8), ('osr_cap', C),
                      ('ng_set', I), ('ng_p', C * 12), ('sym_per_mode', I), ('sym_bw', C),
                      ('n_dstop', I), ('dstop_def', I), ('dstr_note', I), ('dstr_k', I), ('dstr_db', C),
                      ('dstr_ring', C)])


class NoteIn(ctypes.Structure):
    """native/engine.cpp's NoteIn: a note as its file and channel give it."""
    _fields_ = ([(f, C) for f in ('f0', 'pan', 'vel', 'chan_vol', 'effort', 'on', 'off', 'nx')]
                + [(f, I) for f in ('has_nx', 'mcut', 'slurred', 'slur_out')]
                + [('detune_lo', C), ('detune_hi', C), ('soft_pedal_down', I), ('fixed_touch', I)]
                + [(f, C) for f in ('sr', 'retrigger_fade', 'channel', 'br', 'nyq_om')]
                + [('sv', C * 2), ('sound_vib_depth_cents', C), ('vibrato_delay', C), ('gl', C * 3)]
                + [(f, C) for f in ('fx', 'mk', 'fm_omega', 'fm_phase')]
                + [('room_bands', C * 9), ('reflect', I), ('no_reflections', I), ('ch', LL), ('note', I),
                   ('damper_pedal', I), ('key_off', C), ('planes', C * 6), ('order', I), ('from_song', I), ('song_index', I),
                   ('seat', C), ('held', C), ('rnd_draws', C * 4), ('stroke_tilt', C), ('stroke_mouth', C),
                   ('stroke_morph', C), ('snd_at', C), ('snd_rt', C), ('rank_gr', C * 32), ('rank_sp', C * 32),
                   ('rank_skip', I * 32), ('rank_rel1', I * 32), ('organ_cr', C), ('rank_br', C * 32),
                   ('carry_radius', C), ('organ_hx', C), ('organ_perc', I), ('bbr_set', I), ('bbr', C),
                   ('rank_drawn_off', I * 32), ('snd_moog', I), ('snd_d', C * 8),
                   ('sung_hz', C), ('part', I), ('dist', C), ('gliss_lv', C),
                   ('ring_on', I), ('ring_f', C * 48), ('fbr', C),
                   ('sym_drv', ctypes.c_void_p), ('blk', C), ('xp', C),
                   ('hammered', I), ('reslur', I), ('hammer_on', C), ('siren_set', I), ('siren_end', C),
                   ('press', C), ('gs_eq', C * 4), ('fx_set', I), ('fx_level', C), ('fx_od', C),
                   ('fx_comp', C * 3), ('fx_p3d', I), ('fx_angle', C), ('alias_br', C * 32), ('n_alias', I)])


class NoteOut(ctypes.Structure):
    """native/engine.cpp's NoteOut: what the note's setup worked out."""
    _fields_ = ([(f, I) for f in ('n_knock', 'n_tone', 'n_phantom')]
                + [(f, C) for f in ('non', 'noff', 'fade', 'rel', 'chiff', 'jitter_scale', 'dl', 'dr', 'li',
                                    'ri', 'pos_x', 'pos_z', 'B', 'cv', 'cc', 'crl', 'sjit', 'csc')]
                + [('tb', C * 3), ('cbw', C * 2), ('radius', C), ('n_push', I), ('f0', C)]
                + [('n_click', I), ('n_jack', I), ('jack_n', I * 32), ('jack_rank', I * 32), ('jack_off', C * 32),
                   ('n_ft', I), ('lay_rows', I * 2), ('ft', (C * 30) * 2), ('kn', (C * 9) * 2),
                   ('ring0', I), ('ring1', I), ('grain0', I), ('grain1', I)])


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



def _build_objects(units):
    """Each unit (name, compiler and flags, source) compiled to .nvbuild/NAME.o
    unless its stamp still holds -- the hash of its command and of the contents
    of every file the compiler read for it (its -MMD list) -- the stale ones at
    once (NV_BUILD_JOBS, default the cores, at most 8). Each written under a
    name of this process's and moved in whole, so builds running side by side
    never see a half-written object. Returns the objects, in the units' order."""
    import concurrent.futures
    import hashlib
    bdir = os.path.join(HERE, '.nvbuild')
    os.makedirs(bdir, exist_ok=True)

    def stamp(cmd, dep):
        try:
            with open(dep) as f:
                text = f.read().replace('\\\n', ' ')
        except OSError:
            return None
        h = hashlib.sha256('\0'.join(cmd).encode())
        for path in text.split(':', 1)[1].split() if ':' in text else ():
            try:
                with open(path, 'rb') as f:
                    h.update(path.encode() + b'\0' + hashlib.sha256(f.read()).digest())
            except OSError:
                return None
        return h.hexdigest()

    def held(name, cmd):
        o, d, st = (os.path.join(bdir, name + x) for x in ('.o', '.d', '.stamp'))
        try:
            with open(st) as f:
                old = f.read()
        except OSError:
            return False
        return os.path.exists(o) and old == stamp(cmd, d)

    def compile_one(name, cmd, src):
        o, d, st = (os.path.join(bdir, name + x) for x in ('.o', '.d', '.stamp'))
        pid = '.%d.tmp' % os.getpid()
        try:
            subprocess.check_call(cmd + ['-c', src, '-o', o + pid, '-MMD', '-MF', d + pid])
            # (the .d names the object it was written as: the stamp reads only its list)
            new = stamp(cmd + ['-c', src], d + pid)
            os.replace(o + pid, o)
            os.replace(d + pid, d)
            with open(st + pid, 'w') as f:
                f.write(new or '')
            os.replace(st + pid, st)
        finally:
            for x in (o + pid, d + pid, st + pid):
                if os.path.exists(x):
                    os.remove(x)

    todo = [(n, c + ['-c', s], c, s) for n, c, s in units]
    stale = [(n, c, s) for n, key, c, s in todo if not held(n, key)]
    if stale:
        jobs = int(os.environ.get('NV_BUILD_JOBS') or min(8, os.cpu_count() or 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(jobs, len(stale)))) as ex:
            for f in [ex.submit(compile_one, n, c, s) for n, c, s in stale]:
                f.result()
    return [os.path.join(bdir, n + '.o') for n, c, s in units]

def _load():
    srcs = ([os.path.join(HERE, 'native', f) for f in ('tone.c', 'voice.c', 'pycompat.h', 'nv.h', 'engine.cpp',
                                                       'channel.cpp', 'room.cpp', 'midi.cpp', 'strings.c', 'exactmath.c',
                                                       'register.cpp', 'prepare.cpp', 'render.cpp',
                                                       'live.cpp', 'slab.cpp', 'live.h', 'livereg.cpp', 'gpu.cpp',
                                                       'tuner.cpp', 'tunertables.h', 'bend.cpp', 'organ.c',
                                                       'npyrandom.c', 'npyrandom.h', 'pocketfft.c', 'efxrev.c', 'leslie.cpp', 'tubeamp.cpp', 'scanner.cpp', 'reed.cpp',
                                                       'epiano.cpp', 'efxchain.cpp', 'roomtail.cpp', 'host.cpp', 'hostint.h', 'hostlive.h', 'host.h', 'livebus.cpp')]
            + [os.path.join(HERE, 'roomcore.c'), os.path.join(HERE, 'registercore.c'), os.path.join(HERE, 'tapkernel.c')])
    so = os.path.join(HERE, 'libnative.so')
    if not os.path.exists(so) or max(os.path.getmtime(s) for s in srcs) > os.path.getmtime(so):
        tmp = '%s.%d.tmp' % (so, os.getpid())
        # no -ffast-math, no fused multiply-adds: Python's order of operations;
        # no builtins: pow(x, 2.0) is libm's pow, as Python's x ** 2 is (gcc's
        # x*x is correctly rounded where pow, at 0.52 ULP, is not always).
        # The C core (tone.c, with voice.c) and the C++ engine (engine.cpp)
        # under the same flags, linked into one library.
        flags = ['-O2', '-march=native', '-ffp-contract=off', '-fno-builtin', '-fPIC']
        cxx = ['g++', '-std=c++17'] + flags
        nat = lambda f: os.path.join(HERE, 'native', f)
        units = ([('tone', ['gcc'] + flags, nat('tone.c'))]
                 + [(f[:-4], cxx, nat(f)) for f in ('engine.cpp', 'channel.cpp', 'room.cpp', 'midi.cpp', 'register.cpp',
                                                    'prepare.cpp', 'render.cpp', 'live.cpp', 'slab.cpp')]
                 # register.py's C core, under ITS flags (register._load_core's): the same arithmetic
                 + [('registercore', ['gcc', '-O3', '-march=native', '-ffp-contract=off', '-fopenmp-simd',
                                      '-fno-math-errno', '-mprefer-vector-width=512', '-fPIC'],
                     os.path.join(HERE, 'registercore.c'))]
                 + [(f[:-4], cxx, nat(f)) for f in ('livereg.cpp', 'gpu.cpp', 'tuner.cpp', 'bend.cpp', 'leslie.cpp',
                                                    'tubeamp.cpp', 'scanner.cpp', 'reed.cpp', 'epiano.cpp',
                                                    'efxchain.cpp')]
                 # live.py's tap kernel (the insertion effect's copies), under ITS
                 # flags (live.ensure_tap_lib's): the same arithmetic
                 + [('tapkernel', ['gcc', '-O3', '-march=native', '-fPIC'], os.path.join(HERE, 'tapkernel.c'))]
                 # roomtail.py's late field (live.room_irs's), drawn natively; the
                 # live host (host.h: nvlive's, as a library); a part's own bus live
                 # (live.LiveBus: efxbus's processors, block by block)
                 + [(f[:-4], cxx, nat(f)) for f in ('roomtail.cpp', 'host.cpp', 'livebus.cpp')])
        objs = _build_objects(units)
        try:
            subprocess.check_call(['g++', '-shared'] + objs + ['-o', tmp, '-lmvec', '-lm', '-ldl'])
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        os.replace(tmp, so)
    d = ctypes.CDLL(so)
    P = ctypes.POINTER(VoiceSnap)
    D = ctypes.POINTER(C)
    for name, res, args in (
            ('nv_series_volume', C, [P, I]), ('nv_harmonic_volume', C, [P, I]),
            ('nv_harmonic_decay', C, [P, I]), ('nv_mode_ratio', C, [P, I]),
            ('nv_aftersound', None, [P, C, C, D]), ('nv_unison_voices', I, [P, C, I, C, D]),
            ('nv_radiation_gain', C, [P, C, C, I]), ('nv_hrtf_gain', C, [P, C, C]),
            ('nv_chiff_harmonic_gain', C, [P, C]), ('nv_bloom_delay_for', C, [P, C]), ('nv_bloom_gain_for', C, [P, C]),
            ('nv_voice_vibrato', I, [P, C, I, D]), ('nv_string_partial', I, [P, C, C, I, C, D]),
            ('nv_partial_decay', None, [P, C, I, D]), ('nv_unison_partial', None, [C, C, C, C, D]),
            ('nv_random_check', None, [LL, I, D]),
            ('nv_tone', I, [P, ctypes.POINTER(ToneIn), I, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p, ctypes.POINTER(I),
                            ctypes.c_void_p, D]),
            ('nv_moog_ladder', C, [ctypes.POINTER(MoogLayer), C, C, C, I, I]),
            ('nv_moog_apply', None, [ctypes.POINTER(MoogLayer), ctypes.c_void_p, ctypes.POINTER(MoogLayer)]),
            ('nv_moog_tables', None, [ctypes.c_void_p]),
            ('nv_moog_build', I, [ctypes.c_void_p, ctypes.POINTER(MoogLayer), ctypes.POINTER(MoogLayer)]),
            ('nv_moog_tone', I, [P, ctypes.POINTER(ToneIn), ctypes.POINTER(MoogLayer), C, C, I, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I,
                                 ctypes.c_void_p, D]),
            ('nv_strike', I, [P, ctypes.POINTER(ToneIn), I, ctypes.c_void_p, ctypes.c_void_p, C, C, C, C, C, C, C,
                              C, ctypes.c_void_p, I, ctypes.c_void_p, D]),
            ('nv_voice_init', None, [ctypes.POINTER(VoiceInit), P, C, C, C, C, C, ctypes.POINTER(PyRandomState),
                                     P, ctypes.POINTER(VoiceNote)]),
            ('nv_voice_bodies_set', I, [I, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_voice_body', I, [ctypes.c_char_p]),
            ('nv_voice_part', I, [I, ctypes.POINTER(C), ctypes.POINTER(C)]),
            ('nv_note', I, [ctypes.POINTER(NoteClass), ctypes.POINTER(NoteIn), ctypes.POINTER(PyRandomState), I,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I,
                            ctypes.c_void_p, D, ctypes.POINTER(NoteOut)]),
            ('nv_song_play', I, [ctypes.c_void_p, ctypes.POINTER(NoteClass), ctypes.POINTER(NoteIn),
                                 ctypes.POINTER(PyRandomState), I, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p, D, ctypes.POINTER(NoteOut),
                                 ctypes.POINTER(I)]),
            ('nv_images', I, [D, I, C, C, C, I, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_read', ctypes.c_void_p, [ctypes.c_char_p, LL, ctypes.POINTER(I)]),
            ('nv_midi_map_kits', None, [ctypes.POINTER(I), I]), ('nv_midi_map_kits_play', None, [I]),
            ('nv_midi_free', None, [ctypes.c_void_p]), ('nv_midi_total', C, [ctypes.c_void_p]),
            ('nv_midi_n_notes', I, [ctypes.c_void_p]), ('nv_midi_n_ccs', I, [ctypes.c_void_p]),
            ('nv_midi_n_pws', I, [ctypes.c_void_p]), ('nv_midi_gs', I, [ctypes.c_void_p]),
            ('nv_midi_n_events', I, [ctypes.c_void_p]),
            ('nv_midi_sysex', I, [ctypes.c_void_p, I, ctypes.c_void_p, I]), ('nv_midi_master', I, [ctypes.c_void_p]),
            ('nv_midi_event', None, [ctypes.c_void_p, I, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_event_x', ctypes.c_double, [ctypes.c_void_p, I]),
            ('nv_midi_note', None, [ctypes.c_void_p, I, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_cc', None, [ctypes.c_void_p, I, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_pw', None, [ctypes.c_void_p, I, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_midi_song', None, [ctypes.c_void_p, ctypes.c_void_p, D]),
            ('nv_pulse_series', I, [C, C, C, C, C, ctypes.c_void_p, I]),
            ('nv_midi_banked', I, [ctypes.c_void_p]), ('nv_midi_note_bsel', I, [ctypes.c_void_p, I]),
            ('nv_midi_chprog_bsel', I, [ctypes.c_void_p, I]),
            ('nv_song_vars', None, [ctypes.c_void_p, I] + [ctypes.c_void_p] * 5),
            ('nv_song_slot_organs', None, [ctypes.c_void_p, I, ctypes.c_void_p]),
            ('nv_strings', I, [ctypes.POINTER(VoiceInit), P, D, C, C, C, ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_strings_og', I, [ctypes.POINTER(VoiceInit), P, ctypes.c_void_p, D, C, C, C, ctypes.c_void_p,
                                  ctypes.c_void_p, I]),
            ('nv_exp_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_pow_n', None, [ctypes.c_long, ctypes.c_void_p, I, ctypes.c_void_p, I, ctypes.c_void_p]),
            ('nv_cabs_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_atan_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_log_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_log10_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_cexp_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_cangle_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_tuning_table', I, [ctypes.c_char_p, I, C, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_tanhf_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_tanh_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_prepare', LL, [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(NoteIn), D, I,
                                ctypes.POINTER(PyRandomState), ctypes.POINTER(D), ctypes.c_void_p, D,
                                ctypes.c_void_p, C, C, C, C, LL, C, C, C, ctypes.c_void_p, C, C, C, C,
                                ctypes.POINTER(ctypes.c_void_p), I]),
            ('nv_template', LL, [ctypes.c_void_p, ctypes.POINTER(NoteIn), D, D, I, I, I, I,
                                 ctypes.POINTER(ctypes.POINTER(ctypes.c_double)), ctypes.c_void_p, C, C, C, C, LL,
                                 C, C, ctypes.c_void_p, C, C, C, C, ctypes.POINTER(ctypes.c_void_p),
                                 ctypes.c_void_p]),
            ('nv_tcache_new', ctypes.c_void_p, [ctypes.c_void_p, ctypes.POINTER(NoteIn), D, D, ctypes.c_void_p,
                                                ctypes.c_void_p, C, C, C, C, LL, C, C, C, C, C, C]),
            ('nv_tcache_free', None, [ctypes.c_void_p]),
            ('nv_tcache_warm', ctypes.c_long, [ctypes.c_void_p, I, I, I, I, ctypes.c_void_p, I]),
            ('nv_tcache_get', ctypes.c_void_p, [ctypes.c_void_p, I, I, I, ctypes.POINTER(LL)]),
            ('nv_tmpl_scatter', C, [ctypes.c_void_p]),
            ('nv_tmpl_rank', ctypes.c_void_p, [ctypes.c_void_p, I, ctypes.POINTER(LL)]),
            ('nv_sphere_mean', C, [C, C, C, C]),
            ('nv_npy_normals', None, [ctypes.c_ulonglong, ctypes.c_long, ctypes.c_void_p]),
            ('nv_efx_reverb_ir', LL, [C, I, C, I, C, ctypes.c_void_p, ctypes.c_void_p, LL]),
            ('nv_efx_gate_ir', LL, [C, I, C, C, ctypes.c_void_p, ctypes.c_void_p, LL]),
            ('nv_efx_conv', I, [ctypes.c_void_p, LL, ctypes.c_void_p, LL, LL, LL, ctypes.c_void_p]),
            ('nv_tmpl_col', ctypes.c_void_p, [ctypes.c_void_p, I, I]),
            ('nv_tcache_kits', None, [ctypes.c_void_p, D, D, ctypes.POINTER(ctypes.c_ulonglong),
                                      ctypes.POINTER(I), D, C]),
            ('nv_render', I, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, I, I, LL,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p,
                              ctypes.c_long, C, C, C, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_long, ctypes.c_void_p, I]),
            ('nv_leslie_expand', LL, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p,
                                      ctypes.c_void_p, ctypes.c_void_p, C, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_amp_synth', None, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_long,
                                    C, ctypes.c_void_p]),
            ('nv_amp_window', None, [ctypes.c_long, ctypes.c_void_p]),
            ('nv_rfft', I, [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]),
            ('nv_cfft', I, [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]),
            ('nv_reed_series', I, [C, C, C, I, I, C, ctypes.c_void_p]),
            ('nv_ep_layers_cached', I, [I, ctypes.c_void_p, C, C, C, C, I, I, C, C, I, ctypes.c_void_p, I]),
            ('nv_tgamma_n', None, [ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_amp_expand', LL, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p,
                                   ctypes.c_void_p, C]),
            ('nv_scan_rows', None, [ctypes.c_void_p, ctypes.c_long, I, C, I, I, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_tcache_leslie', None, [ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_part_leslie', None, [ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_part_scan', None, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]),
            ('nv_leslie_angles', ctypes.c_long, [I, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, C, I,
                                                 ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_slab_new', ctypes.c_void_p, [ctypes.c_long, C]), ('nv_slab_free', None, [ctypes.c_void_p]),
            ('nv_slab_stamp', I, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, LL, LL, LL, LL, LL, C, LL, I,
                                  C]),
            ('nv_slab_release', None, [ctypes.c_void_p, LL, LL, LL, LL, LL]),
            ('nv_slab_reap', None, [ctypes.c_void_p, LL, LL]),
            ('nv_slab_col', None, [ctypes.c_void_p, I, I, ctypes.c_void_p]),
            ('nv_slab_free_list', ctypes.c_long, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]),
            ('nv_part_new', ctypes.c_void_p, [ctypes.c_void_p, LL, C, I, I, I, I, I, C, C, ctypes.c_long, C, D, C]),
            ('nv_part_program', None, [ctypes.c_void_p, I]),
            ('nv_part_toggle_stop', None, [ctypes.c_void_p, I, LL]),
            ('nv_part_swap', None, [ctypes.c_void_p, I, ctypes.c_void_p, I, I, I, I, I, I, I, I, ctypes.c_void_p,
                                  ctypes.c_void_p]),
            ('nv_part_swap_bank', None, [ctypes.c_void_p, ctypes.c_void_p, I, D, I, I, ctypes.c_void_p, I,
                                       ctypes.c_void_p, C, I, ctypes.c_void_p]),
            ('nv_part_free', None, [ctypes.c_void_p]),
            ('nv_part_register', None, [ctypes.c_void_p, ctypes.c_void_p, I, C, C, C, C, I, C, I, C, C, C, C, LL,
                                      ctypes.c_void_p]),
            ('nv_part_reg_dropped', ctypes.c_long, [ctypes.c_void_p]),
            ('nv_part_bend_rows', I, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_part_reg_choirs', None, [ctypes.c_void_p, I, ctypes.c_void_p, C, I, ctypes.c_void_p]),
            ('nv_part_reg_keys', None, [ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_part_swap_bank_keys', None, [ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_part_event', None, [ctypes.c_void_p, I, I, I, I]),
            ('nv_part_block', None, [ctypes.c_void_p, LL, LL]),
            ('nv_part_moog_kernel', None, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_part_moog_table', ctypes.c_long, [ctypes.c_void_p, I, ctypes.c_void_p, ctypes.c_long]),
            ('nv_part_slab', ctypes.c_void_p, [ctypes.c_void_p]),
            ('nv_part_render', None, [ctypes.c_void_p, LL, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p, LL, C]),
            ('nv_part_damper', None, [ctypes.c_void_p, C, C, C, C, C]),
            ('nv_part_press_db', None, [ctypes.c_void_p, C]),
            ('nv_part_detune_wheel', None, [ctypes.c_void_p, I]),
            ('nv_part_room', None, [ctypes.c_void_p] * 5 + [ctypes.c_long, ctypes.c_void_p, ctypes.c_long, I]),
            ('nv_part_post', None, [ctypes.c_void_p, C, C, C]),
            ('nv_part_amp_ahead', None, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
            ('nv_part_output', None, [ctypes.c_void_p, LL, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, LL, C]),
            ('nv_part_gpu', None, [ctypes.c_void_p] + [ctypes.c_void_p] * 6 + [ctypes.c_long, I]),
            ('nv_part_moogx', None, [ctypes.c_void_p] * 5),
            ('nv_part_on_gpu', I, [ctypes.c_void_p]),
            ('nv_part_shed', ctypes.c_long, [ctypes.c_void_p, LL, C]),
            ('nv_part_govern', ctypes.c_long, [ctypes.c_void_p, C, C, LL]),
            ('nv_cl_new', ctypes.c_void_p, [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_char_p, I]),
            ('nv_cl_free', None, [ctypes.c_void_p]),
            ('nv_part_dm', None, [ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_rt_new', ctypes.c_void_p, []),
            ('nv_rt_add', None, [ctypes.c_void_p, I, I, I, I, I, I, I]),
            ('nv_rt_feed', I, [ctypes.c_void_p, I, I, I, I, ctypes.c_void_p, I]),
            ('nv_rt_free', None, [ctypes.c_void_p]),
            ('nv_lreg_new', ctypes.c_void_p, [ctypes.c_void_p, I, C, C, C, C, C, I, C]),
            ('nv_lreg_strike', I, [ctypes.c_void_p, LL, I, C, I, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_void_p, I]),
            ('nv_lreg_release', I, [ctypes.c_void_p, LL, C, ctypes.c_void_p, I]),
            ('nv_lreg_pluck', I, [ctypes.c_void_p, LL, I, C, I, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I,
                                  ctypes.c_void_p, I, ctypes.c_void_p]),
            ('nv_lreg_choirs', None, [ctypes.c_void_p, I, ctypes.c_void_p, C, I, ctypes.c_void_p]),
            ('nv_lreg_damp', None, [ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_lreg_felt', I, [ctypes.c_void_p, C, ctypes.c_void_p, ctypes.c_void_p, I]),
            ('nv_lreg_answer', I, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, D]),
            ('nv_lreg_forced', None, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_void_p]),
            ('nv_lreg_free', None, [ctypes.c_void_p]),
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
            ('nv_song_kits', None, [ctypes.c_void_p, D, D]),
            ('nv_song_chokes', None, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulonglong)]),
            ('nv_song_choke', I, [ctypes.c_void_p, LL, I, C, D]),
            ('nv_song_legato', None, [ctypes.c_void_p, LL, I, I]),
            ('nv_song_note_stroke', None, [ctypes.c_void_p, I, C, I]),
            ('nv_song_strokes', None, [ctypes.c_void_p, ctypes.POINTER(I), D]),
            ('nv_song_slur', I, [ctypes.c_void_p, I, ctypes.POINTER(I)]),
            ('nv_song_finish', None, [ctypes.c_void_p, C]),
            ('nv_song_organ', None, [ctypes.c_void_p, LL, ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_song_n_organs', I, [ctypes.c_void_p]), ('nv_song_n_grows', I, [ctypes.c_void_p]),
            ('nv_song_organ_wind_rows', I, [ctypes.c_void_p, I]),
            ('nv_song_organ_rows', I, [ctypes.c_void_p, ctypes.c_long, I, C, C, ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_void_p]),
            ('nv_song_organ_wind', None, [ctypes.c_void_p, ctypes.c_long, I, C, ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_void_p, ctypes.c_void_p]),
            ('nv_song_organ_note', I, [ctypes.c_void_p, I, I, ctypes.c_void_p]),
            ('nv_song_note_off', C, [ctypes.c_void_p, LL, I, C, C, I, I, C, ctypes.POINTER(I)]),
            ('nv_song_soft_at', I, [ctypes.c_void_p, LL, C]),
            ('nv_song_next_same', I, [ctypes.c_void_p, LL, I, C, D]),
            ('nv_partial_jitter', C, [P, I]), ('nv_stroke_scatter_db', C, [P, I]),
            ('nv_phantom', I, [P, ctypes.POINTER(ToneIn), ctypes.c_void_p, I, I, ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, I, ctypes.c_void_p, D])):
        f = getattr(d, name)
        f.restype, f.argtypes = res, args
    return d


# A KIT DRUM'S METHODS, as native/voice.c ports them (VoiceSnap.kind 1): a
# class whose own methods are these, on SynthProperties' series volume and
# unison -- not one with a noise layer (the snare's NoisyPercussionMixin) or
# physics of its own past them
_KIT_OWN = {'mode_ratio': 'KitDrumProperties', 'series_volume': 'KitDrumProperties',
            'harmonic_decay': 'KitDrumProperties', 'aftersound': 'KitDrumProperties',
            'aftersound_partial': 'KitDrumProperties', '_click': 'KitDrumProperties',
            '_stroke_db': 'KitDrumProperties', '_f0': 'KitDrumProperties',
            'harmonic_volume': 'SynthProperties', 'unison_voices': 'SynthProperties'}


# ...AND A SNARE'S (AcousticSnareProperties on NoisyPercussionMixin: the
# roll-off and band trim, the head's rates, the shell's remainder, each
# partial's jitter; a side stick's rim)
_SNARE_OWN = dict(_KIT_OWN, harmonic_volume='NoisyPercussionMixin', _hf_rolloff='NoisyPercussionMixin',
                  _band_trim='NoisyPercussionMixin', chiff_harmonic_gain='NoisyPercussionMixin',
                  partial_jitter='AcousticSnareProperties', aftersound='AcousticSnareProperties')


# ...AND A MEASURED MODE SET'S ON SYNTHPROPERTIES, a noise's (the clap: its
# mode silent, its sound the strike's flam; the cymbals and hats, with
# CymbalProperties' decay and aftersound; the woods), a key's decay
# retargeted or not
_MODAL_OWN = {'mode_ratio': 'SynthProperties', 'series_volume': 'SynthProperties',
              'harmonic_volume': 'NoisyPercussionMixin', '_hf_rolloff': 'NoisyPercussionMixin',
              '_band_trim': 'NoisyPercussionMixin', 'chiff_harmonic_gain': 'NoisyPercussionMixin',
              'aftersound': 'SynthProperties', 'unison_voices': 'SynthProperties'}


def decay_target(cls):
    """A key class's retargeted decay (percussion_map: harmonic_decay scaled
    so its first mode's is the target): the target, else None."""
    own = next((k for k in cls.__mro__ if 'harmonic_decay' in k.__dict__), None)
    hd = own.__dict__.get('harmonic_decay') if own is not None else None     # (a subclass's: its key class's)
    dd = getattr(hd, '__defaults__', None)
    if hd is None or not dd or len(dd) != 2 or not isinstance(dd[0], type):
        return None
    return float(dd[1]) if _owner(dd[0], 'harmonic_decay') in ('SynthProperties', 'CymbalProperties') else None


# ...AND A SAMBA WHISTLE'S (SambaWhistleProperties: a pipe's mode set
# through its bore, the pea's comb and flutter)
_WHISTLE_OWN = {'mode_ratio': 'SynthProperties', 'series_volume': 'SynthProperties',
                'harmonic_volume': 'SynthProperties', 'bore_gain': 'SynthProperties',
                '_bore_norm': 'SynthProperties', 'harmonic_decay': 'SynthProperties',
                'aftersound': 'SynthProperties', 'chiff_harmonic_gain': 'SynthProperties',
                'unison_voices': 'SambaWhistleProperties', 'voice_vibrato': 'SambaWhistleProperties'}


# ...AND A CUICA'S (CuicaProperties: a friction drum, bowed -- a gain table on
# the harmonic series, its upper partials rough)
_CUICA_OWN = {'mode_ratio': 'SynthProperties', 'series_volume': 'SynthProperties',
              'harmonic_volume': 'SynthProperties', 'chiff_harmonic_gain': 'SynthProperties',
              'aftersound': 'SynthProperties', 'unison_voices': 'SynthProperties',
              'partial_jitter': 'CuicaProperties', 'bore_gain': 'SynthProperties'}


# ...AND A DRUM MACHINE'S (TR808Properties, the TR-808 engine's: the 808,
# 909, 707, 606 and CR-78 voices, the jingle bell; SimmonsProperties, the
# SDS-V's: each mode its own decay,
# aftersound and phase; its knock a burst train and a layer; its sweep the
# tension bend)
_JINGLE_OWN = {'mode_ratio': 'SynthProperties', 'series_volume': 'SynthProperties',
               'harmonic_volume': 'SynthProperties', 'chiff_harmonic_gain': 'SynthProperties',
               'aftersound': 'SynthProperties', 'unison_voices': 'SynthProperties',
               'harmonic_decay': 'ModeDecays', 'aftersound_partial': 'TR808Properties',
               'mode_phase': 'TR808Properties', 'bore_gain': 'SynthProperties'}


def breath_noise(cls):
    """Whether native/tone.c's nv_breath plays cls's breath (NoteClass.n_bn):
    a noise voice whose sound is its table alone (breath_noise_db; the scratch,
    the weather) -- its tone silent, so its rows keep their order, and none
    of the table's laws (a low register, an octave slope, a wobble, a slur's
    swell) nor the other noises after it (grains, events, a pulse, a ring)."""
    return (bool(getattr(cls, 'breath_noise_db', ())) and len(cls.breath_noise_db) <= 64
            and 1 <= int(getattr(cls, 'breath_noise_rows', 1)) <= 8
            # (its tone silent -- or an organ's, whose ranks follow the breath as Python's do)
            # (...or a free reed's or a played pipe's, its tone after its breath as Python's is)
            and (all(g == 0.0 for g in (cls.mode_gains or (1.0,))) or getattr(cls, 'registerable', False)
                 or _blown(cls) or issubclass(cls, __import__('tonelib').SfxWeatherProperties))
            # (a sung body's own: SynthProperties' but under a sung text's other
            # vowel, which the engine refuses -- sung_voice)
            and (_owner(cls, 'breath_noise_at') == 'SynthProperties'
                 or (_owner(cls, 'breath_noise_at') == '_VocalBody' and sung_voice(cls)))
            and _owner(cls, '_breath_noise_rows') == 'SynthProperties'
            # (a low register's table only on the same bands: a blown voice's)
            and (not getattr(cls, 'breath_noise_low_db', None)
                 or (_blown(cls) and len(cls.breath_noise_low_db) == len(cls.breath_noise_db)
                     and all(a[0] == b[0] for a, b in zip(cls.breath_noise_low_db, cls.breath_noise_db))))
            # (an octave law -- BreathyTnr.'s: the engine's, NoteClass.bn_oct)
            # (a wobble on its own row only for a blown voice: NoteIn.bbr; its slur's
            # legato attack, NoteClass.bn_slur, too)
            # (...or a silent tone's: the ocean drum's swell, the breath's own row)
            and (not getattr(cls, 'breath_noise_wobble_db', 0.0) or _blown(cls)
                 or all(g == 0.0 for g in (cls.mode_gains or (1.0,))))
            and (not getattr(cls, 'breath_noise_slur', False) or _blown(cls))
            and (not getattr(cls, 'grains', None) or grains_of(cls))
            and not any(getattr(cls, a, None) for a in ('noise_events', 'pulse', 'ring_db',
                                                         'struck_layer', 'touch_leak_db')))


def grains_of(cls):
    """cls's grains as the engine plays them (NoteClass.grain), () if none or
    not: up to 8 rows of 6, 8 (a glide) or 9 (a cluster) fields."""
    g = tuple(getattr(cls, 'grains', None) or ())
    if len(g) > 8 or any(len(r) not in (6, 8, 9) for r in g):
        return ()
    return g


def _blown(cls):
    """A voice whose breath the engine plays beside its tone: a free reed's,
    a played pipe's (wind_voice), a measured pipe's outside an organ."""
    return reed_voice(cls) or wind_voice(cls) or (pipe_voice(cls) and not getattr(cls, 'registerable', False))


def _tube(cls):
    """A chime's tube (TubularBellProperties: its modes by register), as
    native/voice.c reads it (VoiceSnap.tube): up to 32 modes."""
    import tonelib as T
    return (issubclass(cls, T.TubularBellProperties) and _owner(cls, '_tube_oct') == 'TubularBellProperties'
            and len(cls.TUBE_MODES) <= 32)


def timpani_voice(cls):
    """A kettle (tonelib.TimpaniProperties, GM 47): its membrane's measured
    modes, each its own decay, tilted by the stroke (mode_stroke_tilt)."""
    import tonelib as T
    return issubclass(cls, T.TimpaniProperties) and len(cls.mode_decays or ()) <= 400


def _bar_by_register(cls):
    """A ModeDecays struck bar whose modes go by register (the balafon's, the
    log drum's): its mode_gains_points within the anchors' tables (8 x 64),
    its own mode_ratio the balafon's or the log drum's -- or neither, its
    gains the register's alone"""
    import tonelib as T
    if not (issubclass(cls, T.ModeDecays) and issubclass(cls, T.StruckBarProperties)):
        return False
    pts = getattr(cls, 'mode_gains_points', None) or ()
    mro = _owner(cls, 'mode_ratio')
    if mro == 'BalafonProperties' and len(getattr(cls, 'mode_ratio_laws', ())) != 2:
        return False
    if mro == 'LogDrumProperties' and len(getattr(cls, 'body_modes_hz', ())) != 3:
        return False
    return ((pts or mro in ('BalafonProperties', 'LogDrumProperties'))
            and mro in ('SynthProperties', 'BalafonProperties', 'LogDrumProperties')
            and len(pts) <= 8 and all(len(g) <= 64 for _, g in pts)
            and all(len(g) == len(cls.mode_gains) for _, g in pts))


def _modal_drum(cls):
    import tonelib as T
    gam = issubclass(cls, T.ModeDecays) and issubclass(cls, (T.MetalPercussionProperties, T.StruckBarProperties))
    # (a kettle's membrane: its measured modes, each its own decay -- ModeDecays'
    # arithmetic, the timpani's own copy -- and the stroke's tilt across them)
    kettle = timpani_voice(cls)
    gam = gam or kettle
    if issubclass(cls, (T.TR808Properties, T.SimmonsProperties)) or gam:
        mg, mr = cls.mode_gains, cls.mode_ratios
        # (a Simmons: the 808's without its modes' phases and aftersounds;
        # the gamelan's bronze -- a gong, a bonang's kettle, a gender's bar
        # under its mallet's roll-off (the bore's) -- the Simmons')
        own = (_JINGLE_OWN if issubclass(cls, T.TR808Properties)
               else dict(_JINGLE_OWN, aftersound_partial=None, mode_phase=None))
        if gam:
            own = dict(own, _bore_norm='SynthProperties', mode_gains_here='SynthProperties')
            if kettle:
                own['harmonic_decay'] = 'TimpaniProperties'
            # (the music box's own over SynthProperties' -- past the class that
            # defines it, so a variation of it, routed with settings, is it too)
            _mgo = next((k for k in cls.__mro__ if 'mode_gains_here' in k.__dict__), None)
            if (_owner(cls, 'mode_gains_here') == 'MusicBoxProperties' and len(cls.mode_gains) >= 7
                    and next(k.__name__ for k in cls.__mro__[cls.__mro__.index(_mgo) + 1:]
                             if 'mode_gains_here' in k.__dict__) == 'SynthProperties'):
                own['mode_gains_here'] = 'MusicBoxProperties'      # (a comb tooth's octave below)
        if tap_voice(cls):                      # (its repeats its own: VoiceSnap.tap_*)
            own = dict(own, unison_voices=_owner(cls, 'unison_voices'))
        # (a struck bar's modes by register: its gains' tables and its ratios' own law)
        bar = gam and _bar_by_register(cls)
        if bar:
            own = dict(own, mode_ratio=_owner(cls, 'mode_ratio'))
        return (all(_owner(cls, n) == o for n, o in own.items())
                and mg is not None and mr is not None and len(mg) == len(mr) <= 400
                and len(cls.mode_decays) <= 400 and len(getattr(cls, 'mode_after', ())) <= 400
                and len(getattr(cls, 'mode_phases', ())) <= 400
                and (not getattr(cls, 'mode_gains_points', None) or bar) and cls.mode_gains_low is None
                and (not cls.mode_stroke_tilt or kettle or (gam and issubclass(cls, T.StruckBarProperties)))
                and (gam or not cls.bore_corner_hz)
                and not cls.harmonic_touch and not cls.pickup_points and len(cls.unison_detune or ()) <= 8)
    # (a plucked tine: a formant body on a measured mode set -- the kalimba's;
    # or a struck metal sheet's, no body -- the steelpan's)
    if ((issubclass(cls, T.FormantBody) or issubclass(cls, T.MetalPercussionProperties))
            and issubclass(cls, T.PluckedStringProperties)
            and cls.mode_gains is not None and cls.mode_ratios is not None):
        _own = (_HARMONIC_OWN if issubclass(cls, T.FormantBody)
                else dict(_HARMONIC_OWN, bore_gain='SynthProperties', _body_trim=None))
        if tap_voice(cls):                      # (a bird's chirps: VoiceSnap.tap_*)
            _own = dict(_own, unison_voices=_owner(cls, 'unison_voices'))
        # (one it does not take goes on to the families below: a kit's triangle)
        if (all(_owner(cls, n) == o for n, o in _own.items())
                and _owner(cls, 'aftersound_partial') is None
                and len(cls.mode_gains) == len(cls.mode_ratios) <= 400
                and not getattr(cls, 'mode_gains_points', None) and cls.mode_gains_low is None
                and not cls.mode_stroke_tilt and not cls.harmonic_touch and not cls.pickup_points
                and not (cls.unison_detune or ()) and not cls.inharmonicity_dynamic and not cls.blare_db_per_khz
                and len(getattr(cls, 'formants', ()) or ()) <= 16 and len(getattr(cls, 'antiformants', ()) or ()) <= 8
                and len(getattr(cls, 'body_trim_db', ()) or ()) <= 32
                and not any(getattr(cls, a, None) for a in ('breath_noise_db', 'grains', 'noise_events', 'pulse',
                                                             'struck_layer', 'touch_leak_db', 'hammer_legato',
                                                             'bend_detents', 'amp_drive'))):
            return True
    if issubclass(cls, T.CuicaProperties):
        return (all(_owner(cls, n) == o for n, o in _CUICA_OWN.items())
                and (_owner(cls, 'harmonic_decay') == 'SynthProperties' or decay_target(cls) is not None)
                and cls.mode_gains is not None and cls.mode_ratios is None and len(cls.mode_gains) <= 320
                and not getattr(cls, 'mode_gains_points', None) and cls.mode_gains_low is None
                and not cls.mode_stroke_tilt and not cls.bore_corner_hz and not cls.harmonic_touch
                and not cls.pickup_points and len(cls.unison_detune or ()) <= 8)
    if issubclass(cls, T.SambaWhistleProperties):
        mg, mr = cls.mode_gains, cls.mode_ratios
        return (all(_owner(cls, n) == o for n, o in _WHISTLE_OWN.items())
                and mg is not None and mr is not None and len(mg) == len(mr) <= 320
                and not getattr(cls, 'mode_gains_points', None) and cls.mode_gains_low is None
                and not cls.mode_stroke_tilt and not cls.blare_db_per_khz and not cls.harmonic_touch
                and not cls.pickup_points and len(cls.unison_detune or ()) <= 8)
    # (the claps, the cymbals and hats, the woods, the triangles, the
    # rattles, a tuned bar's crotales: the other washes are families of their own)
    cym = issubclass(cls, T.CymbalProperties)
    bar = issubclass(cls, T.TunedBarProperties)
    # (a noise voice's breath the engine's -- or none: its tone silent and its
    # sound its strike's bursts alone, an audience's applause)
    # ...or a WEATHER voice's: its tone sounding beside its breath, or with none (the laser)
    if issubclass(cls, T.BreathNoiseProperties):
        _has = bool(getattr(cls, 'breath_noise_db', ()))
        _silent = (isinstance(cls.mode_gains, (tuple, list)) and cls.mode_gains
                   and all(g == 0.0 for g in cls.mode_gains))
        if (_has and not breath_noise(cls)) or (not _has and not _silent
                                                and not issubclass(cls, T.SfxWeatherProperties)):
            return False
        if (issubclass(cls, T.SfxWeatherProperties) and _owner(cls, 'voice_vibrato') != 'SynthProperties'
                and fixed_vibrato(cls) is None):
            return False
    if not (issubclass(cls, T.HandClapProperties) or cym or issubclass(cls, T.WoodPercussionProperties)
            or issubclass(cls, T.SnareDrumProperties) or issubclass(cls, T.BreathNoiseProperties)
            or issubclass(cls, T.TriangleProperties) or issubclass(cls, T.RattleProperties) or bar):
        return False
    own = dict(_MODAL_OWN, aftersound='CymbalProperties') if cym else _MODAL_OWN
    if bar:
        if len(cls.bar_modes) > 16:
            return False
        own = dict(own, series_volume='TunedBarProperties')
        if _tube(cls):
            own = dict(own, series_volume='TubularBellProperties', mode_ratio='TubularBellProperties')
    if not issubclass(cls, T.NoisyPercussionMixin):
        # (a struck metal's: SynthProperties' own, no noise's roll-off)
        own = dict(own, harmonic_volume='SynthProperties', chiff_harmonic_gain='SynthProperties',
                   _hf_rolloff=None, _band_trim=None)
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    # (a TAM-TAM: a cymbal's, each measured mode its own decay -- ModeDecays,
    # past them the cymbal's ring -- and the stroke's tilt across them)
    gong = cym and issubclass(cls, T.ModeDecays) and len(cls.mode_decays) <= 400
    if (_owner(cls, 'harmonic_decay') not in ('SynthProperties', 'CymbalProperties')
            and not (gong and _owner(cls, 'harmonic_decay') == 'ModeDecays')
            and decay_target(cls) is None
            and not (_tube(cls) and _owner(cls, 'harmonic_decay') in ('TubularBellProperties', 'ChurchBellProperties'))):
        return False
    mg, mr = cls.mode_gains, cls.mode_ratios
    if heartbeat_voice(cls):
        mg = cls.ECG_GAINS                      # (its gains a property: the ECG's, fixed)
    if _tube(cls) and mg is None:
        mg = mr = ()                    # (its modes are its tube's)
    # (a tuned bar's modes may be its bar_modes alone, on the harmonic series:
    # the vibraphone's, the marimba's, the xylophone's)
    if bar and mg is None and mr is None:
        mg = mr = ()
    # (...and a wood block's, none: its series, the pluck's comb -- GM 115's)
    if issubclass(cls, T.WoodPercussionProperties) and mg is None and mr is None:
        mg = mr = ()
    return (isinstance(mg, (tuple, list)) and isinstance(mr, (tuple, list)) and len(mg) == len(mr) <= 320
            and not getattr(cls, 'mode_gains_points', None) and cls.mode_gains_low is None
            and (not cls.mode_stroke_tilt or gong) and not cls.bore_corner_hz and not cls.harmonic_touch
            and not cls.pickup_points and len(getattr(cls, 'band_trim_db', ())) <= 32
            and len(cls.unison_detune or ()) <= 8)


# ...AND A MEASURED STROKE'S (MeasuredStrokeProperties: the hand drums,
# the agogos, the cowbell): its modes' ring, each partial's jitter, each
# weak mode's level scattered by stroke
_MEASURED_OWN = dict(_KIT_OWN, harmonic_volume='NoisyPercussionMixin', _hf_rolloff='NoisyPercussionMixin',
                     _band_trim='NoisyPercussionMixin', chiff_harmonic_gain='NoisyPercussionMixin',
                     partial_jitter='MeasuredStrokeProperties', stroke_scatter_db='MeasuredStrokeProperties',
                     harmonic_decay='MeasuredStrokeProperties')


# ...AND A SHAKER'S (ShakenNoiseProperties: a harmonic series on
# SynthProperties, whose sound is its shake -- the noise in place of the tone)
_SHAKEN_OWN = {'mode_ratio': 'SynthProperties', 'series_volume': 'SynthProperties',
               'harmonic_volume': 'NoisyPercussionMixin', '_hf_rolloff': 'NoisyPercussionMixin',
               '_band_trim': 'NoisyPercussionMixin', 'chiff_harmonic_gain': 'NoisyPercussionMixin',
               'harmonic_decay': 'SynthProperties', 'aftersound': 'SynthProperties',
               'unison_voices': 'SynthProperties', 'bore_gain': 'SynthProperties'}


def _shaken(cls):
    import tonelib as T
    if not issubclass(cls, T.ShakenNoiseProperties) or not getattr(cls, 'shake_noise', False):
        return False
    return (all(_owner(cls, n) == o for n, o in _SHAKEN_OWN.items())
            and cls.mode_gains is None and cls.mode_ratios is None and not cls.plucked_harmonic
            and not cls.strike_point and not cls.harmonic_touch and not cls.pickup_points
            and cls.even_harmonic_db is None and not cls.bore_corner_hz and len(cls.band_trim_db) <= 32
            and len(cls.noise_bands) <= 32 and len(cls.unison_detune or ()) <= 8)


# A HARMONIC VOICE'S METHODS (VoiceSnap.kind 4: a guitar): SynthProperties'
# series, decay and vibrato, on a FormantBody's body
_HARMONIC_OWN = {'series_volume': 'SynthProperties', 'harmonic_volume': 'SynthProperties',
                 'mode_ratio': 'SynthProperties', 'harmonic_decay': 'SynthProperties',
                 'aftersound': 'SynthProperties', 'unison_voices': 'SynthProperties',
                 'chiff_harmonic_gain': 'SynthProperties', '_bore_norm': 'SynthProperties',
                 'bore_gain': 'FormantBody', '_body_trim': 'FormantBody', 'voice_vibrato': 'SynthProperties',
                 'mode_gains_here': 'SynthProperties', 'radiation_gain': 'SynthProperties',
                 'partial_jitter': 'SynthProperties'}


# ...AND A SECTION'S (SectionMixin): its players' entries and desks, SynthProperties'
_SECTION_OWN = {'section_onsets_at': 'SynthProperties', 'section_seats': 'SynthProperties',
                'section_position_x': 'SynthProperties', 'hrtf_at': 'SynthProperties',
                '_section_salt': 'SynthProperties'}


def reed_voice(cls):
    """Whether native/voice.c plays cls as a free reed (kind 4 with the flow
    spectrum: native/reed.cpp): the accordions and the harmonica -- a
    FormantBody's body, its reed banks (AccordionProperties.unison_voices)
    or none, and none of the extras a harmonic voice refuses."""
    import tonelib as T
    if not (issubclass(cls, T.FreeReedProperties) and issubclass(cls, T.FormantBody)):
        return False
    own = dict(_HARMONIC_OWN, series_volume='FreeReedProperties')
    if _owner(cls, 'unison_voices') == 'AccordionProperties':
        own['unison_voices'] = 'AccordionProperties'
        if len(cls.reed_bank_gain) > 4:
            return False
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    return (cls.mode_gains is None and cls.mode_ratios is None and not cls.strike_point
            and not cls.harmonic_touch and not cls.pickup_points and not (cls.unison_detune or ())
            and bool(cls.bore_corner_hz) and 1 <= (cls.max_harmonic or 0) <= 128
            and len(cls.formants) <= 16 and len(cls.antiformants) <= 8 and len(cls.body_trim_db or ()) <= 32
            and not cls.inharmonicity_dynamic
            and not any(getattr(cls, a, None) for a in ('grains', 'noise_events', 'pulse', 'ring_db', 'struck_layer',
                                                         'touch_leak_db', 'strike_noise_db', 'release_click_db',
                                                         'hammer_legato', 'bend_detents', 'amp_drive')))


# AN ELECTRIC PIANO'S METHODS (VoiceSnap.kind 5): its pickup's layers,
# SynthProperties' generic rest, no body
_EP_OWN = dict(_HARMONIC_OWN, bore_gain='SynthProperties', _body_trim=None, series_volume='ElectricPianoProperties',
               harmonic_decay='ElectricPianoProperties', mode_phase='ElectricPianoProperties',
               harmonic_level='ElectricPianoProperties', _level_law='ElectricPianoProperties',
               _deflection='ElectricPianoProperties', _pickup_layers='ElectricPianoProperties')


def ep_kind(cls):
    """Which pickup native/epiano.cpp reads cls's through (VoiceSnap.ep_kind):
    1 the Rhodes' tip over its magnet, 2 the Wurlitzer's slot; else 0."""
    import tonelib as T
    if not issubclass(cls, T.ElectricPianoProperties):
        return 0
    if issubclass(cls, T.RhodesProperties) and all(T._ep_owner(cls, n) is T.RhodesProperties
                                                   for n in ('pickup_flux', '_face', '_field')):
        return 1
    if issubclass(cls, T.WurlitzerProperties) and T._ep_owner(cls, 'pickup_flux') is T.WurlitzerProperties:
        return 2
    return 0


def ep_voice(cls):
    """Whether native/voice.c plays cls as an electric piano (kind 5): a
    pickup it knows (ep_kind), its layers native/epiano.cpp's -- the tonebar
    a mode set after them -- on SynthProperties' generic rest, and none of
    the extras but a strike's noise (the Wurlitzer's action)."""
    import tonelib as T
    if not ep_kind(cls) or T.ep_control or T.ep_voicing != "":
        return False
    if any(_owner(cls, n) != o for n, o in _EP_OWN.items()):
        return False
    if any(k.__name__ not in ('SynthProperties', 'ElectricPianoProperties', 'object') for k in cls.__mro__
           if '__init__' in k.__dict__):
        return False
    return (cls.mode_gains is None and cls.mode_ratios is None and not cls.strike_point and not cls.harmonic_touch
            and not cls.pickup_points and not (cls.unison_detune or ()) and not cls.blare_db_per_khz
            and not cls.bore_corner_hz and not cls.inharmonicity_dynamic and not cls.max_partial_hz
            and len(cls.tonebar_mode_ratios) == len(cls.tonebar_gains) <= 8
            and cls.pickup_harmonics * cls.pickup_layer_terms <= 400
            and not any(getattr(cls, a, None) for a in ('breath_noise_db', 'grains', 'noise_events', 'pulse',
                                                         'ring_db', 'struck_layer', 'touch_leak_db',
                                                         'release_click_db', 'hammer_legato', 'bend_detents',
                                                         'amp_drive')))


# A STOPPED STRING's CONSTRUCTOR (tonelib.stopped_pluck_point): the strike
# point from the note's open string, nv_voice_init's (VoiceInit.open_st)
_STOPPED_INITS = ('AcousticBassProperties', 'PizzicatoStringsProperties')


def stopped_voice(cls):
    """A class whose own constructor is a stopped string's pluck point alone
    (the upright's, the pizzicato's), on at most 8 open strings."""
    return _owner(cls, '__init__') in _STOPPED_INITS and len(getattr(cls, 'open_strings', ()) or ()) <= 8


# THE FIXED VIBRATOS (a voice_vibrato that is its class's depth and rate)
_FIXED_VIB = {'SfxSkidProperties': ('skid_vibrato_cents', 'skid_vibrato_hz'),
              'SfxStarshipProperties': ('starship_vibrato_cents', 'starship_vibrato_hz'),
              'SfxScreamProperties': ('scream_vibrato_cents', 'scream_vibrato_hz')}


def _tape_own(cls, own):
    """own (a voice's methods' owners) for a MELLOTRON's tape over the voice
    (tonelib.MellotronMixin): its voice_vibrato the mixin's, over the one
    expected of the voice under it (the capstan's wow where that one has no
    depth: VoiceSnap.wow_*)."""
    if _owner(cls, 'voice_vibrato') == 'MellotronMixin' and 'voice_vibrato' in own:
        import tonelib as T
        mro = cls.__mro__[cls.__mro__.index(T.MellotronMixin) + 1:]
        if next((k.__name__ for k in mro if 'voice_vibrato' in k.__dict__), None) == own['voice_vibrato']:
            return dict(own, voice_vibrato='MellotronMixin')
    return own


def fixed_vibrato(cls):
    """(cents, Hz) of a voice's own fixed vibrato (VoiceSnap.fv_*), None none."""
    a = _FIXED_VIB.get(_owner(cls, 'voice_vibrato'))
    return None if a is None else (float(getattr(cls, a[0])), float(getattr(cls, a[1])))


def noisy_harmonic(cls):
    """A harmonic voice under NoisyPercussionMixin (the fret noise): its
    partials rolled off and trimmed after the body, its wash its own or the
    mixin's -- VoiceSnap.noisy (and chiff_bore)."""
    import tonelib as T
    return (issubclass(cls, T.NoisyPercussionMixin) and _owner(cls, 'harmonic_volume') == 'NoisyPercussionMixin'
            and _owner(cls, '_hf_rolloff') == 'NoisyPercussionMixin' and _owner(cls, '_band_trim') == 'NoisyPercussionMixin'
            and _owner(cls, 'chiff_harmonic_gain') in ('NoisyPercussionMixin', 'GuitarFretNoiseProperties')
            and len(getattr(cls, 'band_trim_db', ()) or ()) <= 32)


_EFX = {}
# a file's insertion effect's parameters by name (gsefx.chain's), the
# export's per-type numbers in this order (nvrender's FxKey)
EFX_KEYS = ("Level", "Drive", "Amp Sw", "Low Gain", "Hi Gain", "Cmp Atck", "Cmp Sus", "Cmp Level", "Cmp Sw",
            "OD Sel", "OD Drive", "OD Amp Sw", "OD Sw", "EQ L Gain", "EQ M Fq", "EQ M Q", "EQ M Gain", "EQ H Gain",
            "OD L Gain", "OD H Gain", "CF Sel", "CF Rate", "CF Depth", "CF Fb", "CF Mix", "Dly Time", "Dly Fb",
            "Dly Mix", "EH Sens", "TP Sw", "Azimuth", "Speed", "Turn", "Clockwise", "Attack", "Sustain",
            "Post Gain", "Type", "Pre Dly", "Time", "HF Damp", "Balance", "Gate Time", "L.Bal", "Pre Dly 1",
            "Pre Dly 2", "EFX Pan 1", "EFX Pan 2", "Coarse 1", "Fine 1", "Coarse 2", "Fine 2", "EFX Pan",
            "P.Coarse", "P.Fine", "Feedback", "Wah Fil", "Wah Man", "Wah Peak", "Wah Sw", "Rate", "Depth", "Phase",
            "Pre Filter", "Cutoff", "Pre Dly Dev", "Depth Dev", "Pan Dev", "Cho Rate", "Cho Depth", "Trem Rate",
            "Trem Sep", "Mod Wave", "Mod Rate", "Mod Depth", "Low Freq", "Hi Freq", "M1 Freq", "M1 Q", "M1 Gain",
            "M2 Freq", "M2 Q", "M2 Gain", "Band 1", "Band 2", "Band 3", "Band 4", "Band 5", "Band 6", "Band 7",
            "Band 8", "Width", "Dly Tm L", "Dly Tm R", "Fb Mode", "Phase L", "Phase R", "Dly Tm C", "Dly Lev C",
            "Dly Lev L", "Dly Lev R", "Dly Tm 1", "Dly Tm 2", "Dly Tm 3", "Dly Tm 4", "Dly Lev 1", "Dly Lev 2",
            "Dly Lev 3", "Dly Lev 4", "Mod Phase", "Manual", "Reso", "Mix", "Fil Type", "Sens", "Peak", "Polarity",
            "Step Rate", "Drive Sw", "Vowel", "Accel", "Lo-Fi Type", "Post Filter", "Threshold", "Ratio", "Release",
            "EH Mix", "TP Sel", "TP Mod WV", "TP Mod RT", "TP Mod Dep", "AW Sw", "AW Filter", "AW Peak", "AW Man",
            "AW Depth", "AW Rate", "PH Mix", "PH Reso", "PH Man", "PH Depth", "PH Rate", "Low Slow", "Low Fast",
            "Low Accl", "Low Level", "Hi Slow", "Hi Fast", "Hi Accl", "Hi Level", "Separate", "RT L Slow",
            "RT L Fast", "RT Lo Accl", "RT Lo Lev", "RT H Slow", "RT H Fast", "RT Hi Accl", "RT Hi Lev", "RT Sept",
            "RT Speed", "RM Mod Freq 0 - 50 - 127", "RM Bal", "PS Coarse", "PS Fine", "PS Bal", "R.Detune",
            "R.Nz Lev", "W/P Sel", "W/P LPF", "W/P Level", "Disc Type", "Disc LPF", "Disc Nz Lev", "Hum Type",
            "Hum LPF", "Hum Level", "M/S", "Pan(Mono)", "DS Drive", "DS Amp Sw",
            "Cho Dly", "Cho Bal", "FL Rate", "FL Depth", "FL Dly", "FL Bal", "FL Fb", "Dly Bal", "Dly HF", "OD1 Drive",
            "OD1 Sel", "OD1 Amp Sw Off/On", "OD2 Drive", "OD2 Sel", "OD2 Amp Sw Off/On", "AW Sens", "AW Pol",
            "Cho Level", "FL Level", "Dly Level", "OD Level", "OD1 Level", "OD2 Level", "RT Level", "PH Level",
            "AW Level", "Cho Pan", "FL Pan", "Dly Pan", "OD Pan", "OD1 Pan", "OD2 Pan", "RT Pan", "PH Pan",
            "AW Pan")


def efx_chain(cls):
    """A tone's own insertion effect as the engine plays it (gsefx.chain of
    its tone_state), or None: one with no stage past the core and an OD
    (level, EQ, cabinet, sends) -- a chorus device, a delay, a moving
    filter, a bus, a tremolo, a compressor, a branch or a rotary are
    Python's -- its EQ the plain five."""
    if cls in _EFX:
        return _EFX[cls]
    import gsefx as G
    e = getattr(cls, 'insertion_efx', None)
    ch = G.chain(G.tone_state(*e)) if e else None
    if ch is not None and (any(ch.get(a) for a in ('comp', 'par', 'rotary'))
                           or (ch.get('bus') and ch['bus'][0] not in ('lofi', 'comp', 'limit'))
                           or (ch.get('filter') and not (
                               (ch['filter']['ctrl'][0] == 'sweep' and not ch['filter']['ctrl'][5])
                               or ch['filter']['ctrl'][0] == 'wah'))
                           or (ch.get('trem') and not (
                               len(ch['trem']) == 4 or (len(ch['trem']) == 5 and (
                                   ch['trem'][4] is None or [tuple(x) for x in ch['trem'][4]] == [(1, 1.0, 0.0)]))))
                           or (ch.get('dly') and not (
                               len(ch['dly']['taps']) <= 4 and not ch['dly'].get('cross') and not ch['dly'].get('mod')
                               and all(len(t) == 4 and isinstance(t[2], str) and t[2] in ('l', 'r', 'c')
                                       for t in ch['dly']['taps'])))
                           or (ch['eq'] is not None and len(ch['eq']) != 5)
                           or (ch.get('cf') and not (len(ch['cf'][0].get('taps') or ()) <= 5 and all(
                               isinstance(t[0], str) and t[0] in ('l', 'r', 'c')
                               for t in (ch['cf'][0].get('taps') or (('l',), ('r',))))))):
        ch = None
    _EFX[cls] = ch
    return ch


def feedback_voice(cls):
    """A guitar held into feedback (tonelib.Feedback): its loop the class's own."""
    import tonelib as T
    return (issubclass(cls, T.Feedback) and _owner(cls, 'feedback_harmonic') == 'Feedback'
            and len(cls.feedback_series) <= 8 and all(int(k) == k and k >= 1 for k, _ in cls.feedback_series))


def plectrum_voice(cls):
    """A string struck by a pick (tonelib.Plectrum): its methods Plectrum's own
    -- or the taishogoto's (TaishoKotoProperties: its volume Plectrum's where
    its low string is not tilted, its onsets the pick's sweep, VoiceSnap.swp_*)."""
    import tonelib as T
    return (issubclass(cls, T.Plectrum) and all(_owner(cls, n) == 'Plectrum' or taisho_voice(cls) and (
        n in ('harmonic_volume', 'section_onsets_at') and _owner(cls, n) == 'TaishoKotoProperties') for n in (
        'harmonic_volume', 'harmonic_decay', 'aftersound_partial', 'section_onsets_at', 'strike_noise_db',
        'strike_noise_dbs')))


def taisho_voice(cls):
    """The taishogoto (tonelib.TaishoKotoProperties): its octave trio, its
    sweep, an untilted low string (its harmonic_volume then Plectrum's)."""
    import tonelib as T
    K = getattr(T, 'TaishoKotoProperties', None)
    return (K is not None and issubclass(cls, K) and _owner(cls, 'unison_voices') == 'TaishoKotoProperties'
            and not getattr(cls, 'low_string_tilt_db', 0.0) and 1 <= len(cls.octave_trio_cents) <= 4)


def class_value(cls, name, default=None):
    """cls's name, a property read on the class (Plectrum's strike_noise_db:
    its class's constants), else the attribute."""
    a = getattr(cls, name, default)
    return a.fget(cls) if isinstance(a, property) else a


def harmonic_voice(cls):
    """Whether native/voice.c plays cls as a harmonic voice (kind 4): a
    plucked string's series through its pluck's comb, on a FormantBody (the
    guitars), or a bowed string's (the violin family: a section of players,
    each a few cents off, with its own vibrato, entry and desk) -- its B the
    class's, or the steel's law -- and none of the extras a note of it would
    take elsewhere."""
    import tonelib as T
    if not issubclass(cls, T.FormantBody):
        return False
    own = _HARMONIC_OWN
    if issubclass(cls, (T.ViolinProperties, T.ViolaProperties, T.CelloProperties, T.ContrabassProperties)):
        if not 1 <= cls.section_players <= 16:
            return False
        own = dict(own, unison_voices='SectionMixin', voice_vibrato='SectionMixin', **_SECTION_OWN)
    elif issubclass(cls, T.PizzicatoStringsProperties):
        # (a section plucking: its players as the bowed sections', and its slow stage)
        if not 1 <= cls.section_players <= 16:
            return False
        own = dict(own, unison_voices='SectionMixin', voice_vibrato='SectionMixin',
                   aftersound='PizzicatoStringsProperties', **_SECTION_OWN)
    elif not issubclass(cls, T.PluckedStringProperties):
        return False
    if noisy_harmonic(cls):                     # (the fret noise: the mixin's roll-off, its own wash)
        own = dict(own, harmonic_volume='NoisyPercussionMixin', chiff_harmonic_gain=_owner(cls, 'chiff_harmonic_gain'))
    dul = dulcimer_voice(cls)
    if dul:
        # (a dulcimer's courses and its decay by each mode's frequency)
        own = dict(own, unison_voices='HammeredDulcimerProperties', harmonic_decay='HammeredDulcimerProperties')
    elif _owner(cls, 'harmonic_decay') == 'PromptDecay':
        # (a two-stage decay, PromptDecay's, over the law it falls to)
        _mro = cls.__mro__[cls.__mro__.index(T.PromptDecay) + 1:]
        if next((k.__name__ for k in _mro if 'harmonic_decay' in k.__dict__), None) != 'SynthProperties':
            return False
        own = dict(own, harmonic_decay='PromptDecay')
    if _owner(cls, 'voice_vibrato') == 'UkuleleProperties' and len(cls.string_wander_hz) == 2:
        own = dict(own, voice_vibrato='UkuleleProperties')     # (a string's wander: VoiceSnap.sw_*)
    if plectrum_voice(cls):
        # (a pick's boost, fall and ring over SynthProperties' own; its courses)
        _mro = cls.__mro__[cls.__mro__.index(T.Plectrum) + 1:]
        if any(next((k.__name__ for k in _mro if n in k.__dict__), None) != 'SynthProperties'
               for n in ('harmonic_volume', 'harmonic_decay', 'section_onsets_at')):
            return False
        own = dict(own, harmonic_volume=_owner(cls, 'harmonic_volume') if taisho_voice(cls) else 'Plectrum',
                   harmonic_decay='Plectrum')
        if _owner(cls, 'unison_voices') in ('TwelveStringProperties', 'MandolinProperties', 'TaishoKotoProperties'):
            own['unison_voices'] = _owner(cls, 'unison_voices')
    elif _owner(cls, 'aftersound_partial') not in (None, 'PromptDecay'):
        return False
    if _owner(cls, 'unison_voices') in ('KanunProperties', 'OudProperties'):
        own = dict(own, unison_voices=_owner(cls, 'unison_voices'))     # (its courses: VoiceSnap.crs_*)
    own = _tape_own(cls, own)
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    law = _owner(cls, 'inharmonicity_coefficient_for_frequency')
    if cls.inharmonicity_dynamic and not (law in ('SteelGuitarProperties', 'HammeredDulcimerProperties')
                                          and getattr(cls, 'inharmonicity_law', None)):
        return False
    # (a quill's comb: a strike point whose notch does not fill with force --
    # the harpsichord's, its clicks the note's key-up's)
    return (cls.mode_gains is None and cls.mode_ratios is None
            and not (cls.strike_point and cls.strike_fills_with_force)
            and not cls.harmonic_touch and not cls.pickup_points and not ((cls.unison_detune or ()) and not dul)
            and bool(cls.bore_corner_hz) and 1 <= (cls.max_harmonic or 0) <= 256     # (the comb's: VoiceSnap.comb)
            and len(cls.formants) <= 16 and len(cls.antiformants) <= 8 and len(cls.body_trim_db or ()) <= 32
            and len(getattr(cls, 'release_click_modes', ()) or ()) <= 16
            and len(getattr(cls, 'ring_db', ()) or ()) <= 48
            and not any(getattr(cls, a, None) for a in ('breath_noise_db', 'grains', 'noise_events', 'pulse',
                                                         'struck_layer', 'touch_leak_db', 'amp_drive')))


def hit_voice(cls):
    """An orchestra hit (tonelib.OrchestraHitProperties, GM 55): a registered
    voice on a struck base, every rank a borrowed spectrum (so its own series
    is never sounded), its section a few cents each way in the ratio slot
    (unison_voices: section_cents at unison_gain) -- played as a harmonic
    voice (kind 4) with SynthProperties' bore, through organ.c's ranks."""
    import tonelib as T
    H = getattr(T, 'OrchestraHitProperties', None)
    return (H is not None and issubclass(cls, H) and getattr(cls, 'registerable', False)
            and not issubclass(cls, T.FormantBody)
            and _owner(cls, 'unison_voices') == 'OrchestraHitProperties' and len(cls.section_cents) <= 8
            and all(len(r) > 3 and r[3] is not None for r in cls.stop_ranks))


def dulcimer_voice(cls):
    """A hammered dulcimer (tonelib.HammeredDulcimerProperties): its courses
    (string_count strings, their beats drawn by key), its decay by each mode's
    frequency, its bass bridge's B -- and, for the register, its courses'
    keys, two bridges by key, each key's partner past the treble bridge, the
    knock's measured profile and tilt."""
    import tonelib as T
    return (issubclass(cls, T.HammeredDulcimerProperties) and 2 <= int(cls.string_count) <= 9
            and _owner(cls, 'unison_voices') == 'HammeredDulcimerProperties'
            and _owner(cls, 'harmonic_decay') == 'HammeredDulcimerProperties'
            and _owner(cls, 'inharmonicity_coefficient_for_frequency') == 'HammeredDulcimerProperties'
            and _owner(cls, 'key_bridge') == 'HammeredDulcimerProperties'
            and len(getattr(cls, 'register_knock_profile', None) or ()) <= 64)


_CLAV_SEL = {'centre': 0, 'bridge': 1, 'both': 2, 'anti': 3}


def clav_voice(cls):
    """A Clavinet (tonelib.ClavinetProperties, GM 7) on the electric path:
    its coil a fraction of the note's speaking length, its key-up's thumps
    and harmonics the note's (VoiceSnap.clav) -- the pick's comb, the coil's
    width and velocity, SynthProperties' decay and the string's B as the
    guitars'. (Its panel's rockers, CC1, are a post-pass of their own.)"""
    import tonelib as T
    if not issubclass(cls, T.ClavinetProperties) or issubclass(cls, T.FormantBody):
        return False
    own = dict(_HARMONIC_OWN, bore_gain='SynthProperties', _body_trim=None, pickup_gain='SynthProperties',
               inharmonicity_coefficient_for_frequency='InharmonicStringProperties')
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    if any(k.__name__ not in ('SynthProperties', 'ClavinetProperties', 'object') for k in cls.__mro__
           if '__init__' in k.__dict__):
        return False
    return (cls.clav_pickup in _CLAV_SEL and cls.mode_gains is None and cls.mode_ratios is None
            and bool(cls.strike_point) and not cls.strike_fills_with_force and not cls.harmonic_touch
            and not cls.inharmonicity_dynamic and not (cls.unison_detune or ()) and not cls.blare_db_per_khz
            and not cls.bore_corner_hz and 1 <= (cls.max_harmonic or 0) <= 128 and not cls.max_partial_hz
            and not cls.pickup_resonance_hz and not cls.lowpass_hz and cls.pickup_turns == 1.0
            and len(cls.keyup_thump_hz) <= 8 and len(cls.keyup_string_harmonics) <= 8
            and not any(getattr(cls, a, None) for a in ('breath_noise_db', 'grains', 'noise_events', 'pulse',
                                                         'ring_db', 'struck_layer', 'hammer_legato',
                                                         'bend_detents', 'touch_leak_db')))


def electric_voice(cls):
    """Whether native/voice.c plays cls as an electric guitar (kind 4,
    VoiceSnap.elec): a plucked string's series through the pick's comb and
    the coils (pickup_gain), both moved by the note's fret (its __init__), no
    body, its B the k f^p law -- or a TOUCHED HARMONIC's (GM 31: the note's
    touch chosen among up to four, its series the string's modes n m, the
    killed modes' leak, the pick's noise) -- and none of the other extras."""
    import tonelib as T
    if clav_voice(cls):
        return True
    if not issubclass(cls, T.ElectricGuitarProperties) or issubclass(cls, T.FormantBody):
        return False
    touched = bool(cls.harmonic_touch or getattr(cls, 'touches', ()))
    # (GuitarHarmonicsProperties' decay is SynthProperties' own, by the partial heard)
    own = dict(_HARMONIC_OWN, bore_gain='SynthProperties', _body_trim=None,
               harmonic_decay='GuitarHarmonicsProperties' if touched else 'ElectricGuitarProperties',
               pickup_gain='SynthProperties', inharmonicity_coefficient_for_frequency='ElectricGuitarProperties')
    if plectrum_voice(cls) and not touched:
        # (a pick over the electric's own -- the pedal steel's bar and pick,
        # GM 2's 26.8: Plectrum's boost, fall and ring wrapping them, VoiceSnap.pick_*)
        _mro = cls.__mro__[cls.__mro__.index(T.Plectrum) + 1:]
        if any(next((k.__name__ for k in _mro if n in k.__dict__), None) != own[n]
               for n in ('harmonic_volume', 'harmonic_decay')):
            return False
        own = dict(own, harmonic_volume='Plectrum', harmonic_decay='Plectrum')
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    inits = ('SynthProperties', 'ElectricGuitarProperties', 'object') + (('GuitarHarmonicsProperties',) if touched else ())
    if any(k.__name__ not in inits for k in cls.__mro__ if '__init__' in k.__dict__):
        return False
    if touched and not (len(getattr(cls, 'touches', ()) or ()) <= 4 and cls.open_strings_hz
                        and all(int(n) == n and n >= 1 for n in (getattr(cls, 'touches', ()) or ()))):
        return False
    pts, sg = tuple(cls.pickup_points or ()), getattr(cls, 'pickup_signs', None)
    return (cls.mode_gains is None and cls.mode_ratios is None and bool(cls.strike_point)
            and not cls.strike_fills_with_force and 1 <= len(pts) <= 4
            and (sg is None or len(sg) == len(pts)) and len(cls.open_strings_hz or ()) <= 8
            and not (cls.unison_detune or ()) and not cls.blare_db_per_khz and not cls.bore_corner_hz
            and 1 <= (cls.max_harmonic or 0) <= 128 and not cls.max_partial_hz
            and not (cls.inharmonicity_dynamic and not getattr(cls, 'inharmonicity_law', None))
            and not any(getattr(cls, a, None) for a in ('breath_noise_db', 'grains', 'noise_events', 'pulse',
                                                         'ring_db', 'struck_layer', 'release_click_db',
                                                         'bend_detents')))


# AN ORGAN PIPE'S METHODS (a kind 2 mode set by register): SynthProperties' all
_PIPE_OWN = dict(_HARMONIC_OWN, bore_gain='SynthProperties', _body_trim=None, mode_gains_at='SynthProperties',
                 mode_lock_offset_for='SynthProperties', speech_time='SynthProperties', chiff_time='SynthProperties',
                 register_low_share='SynthProperties', _blend_db='SynthProperties',
                 inharmonicity_coefficient_for_frequency='StoppedPipeProperties')


def tonewheel_voice(cls):
    """Whether native/voice.c plays cls as a tonewheel (kind 4 with no body):
    SynthProperties' plain series -- the pluck's comb at its plucked
    harmonic, the tonal dampening, no bore -- a Hammond's wheel, or its
    percussion tap's."""
    import tonelib as T
    if not issubclass(cls, T.TonewheelProperties) or issubclass(cls, T.FormantBody):
        return False
    own = dict(_HARMONIC_OWN, bore_gain='SynthProperties', _body_trim=None)
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    return (cls.mode_gains is None and cls.mode_ratios is None and not cls.strike_point and not cls.harmonic_touch
            and not cls.pickup_points and not (cls.unison_detune or ()) and not cls.blare_db_per_khz
            and not cls.bore_corner_hz and not cls.inharmonicity_dynamic and 1 <= (cls.max_harmonic or 0) <= 128
            and len(getattr(cls, 'contact_noise_db', ()) or ()) <= 16)


def measured_series(cls):
    """A played pipe whose series is a measured table (HelicopterProperties.
    harmonic_volume: gain x mode_gains[h - 1], nothing past it): VoiceSnap.hvt."""
    return (_owner(cls, 'harmonic_volume') == 'HelicopterProperties' and isinstance(cls.mode_gains, (tuple, list))
            and 1 <= len(cls.mode_gains) <= 512 and cls.mode_ratios is None)


def bore_table(cls):
    """A played pipe whose series is a measured table under its bore
    (SynthProperties.series_volume over mode_gains_here: the table, blended
    toward its low register's, mode_gains_low, under register_low_hz; then
    harmonic_volume's bore): VoiceSnap.hvt_bore, each note's table at init."""
    lo = cls.mode_gains_low
    return (all(_owner(cls, n) == 'SynthProperties' for n in ('harmonic_volume', 'series_volume',
                                                                 'mode_gains_here', 'mode_gains_at',
                                                                 'register_low_share', 'mode_ratio'))
            and isinstance(cls.mode_gains, (tuple, list)) and 1 <= len(cls.mode_gains) <= 64
            and (lo is None or (isinstance(lo, (tuple, list)) and 1 <= len(lo) <= 64))
            and cls.mode_ratios is None and not getattr(cls, 'mode_gains_points', None)
            and not cls.mode_stroke_tilt)


def wind_voice(cls):
    """Whether native/voice.c plays cls as a played pipe (kind 4): a flute's,
    a reed's, a brass instrument's -- SynthProperties' series through the
    bore (and a sax's or bassoon's FormantBody, a trumpet's mute), no
    measured table, its B the pipe's; a section of them (a bowed string's
    players) -- outside an organ, and none of the extras a harmonic voice
    refuses."""
    import tonelib as T
    if (not issubclass(cls, T.StoppedPipeProperties) or issubclass(cls, T.FreeReedProperties)
            or getattr(cls, 'registerable', False)):
        return False
    own = dict(_PIPE_OWN)
    if _owner(cls, 'unison_voices') == 'BagpipeProperties':
        own['unison_voices'] = 'BagpipeProperties'      # (none: the drones are notes of the part)
    mes = measured_series(cls) or bore_table(cls)
    if mes:
        own['harmonic_volume'] = _owner(cls, 'harmonic_volume')     # (its table: VoiceSnap.hvt)
    if issubclass(cls, T.SectionMixin):
        # (a section of players: a brass section's, as a bowed string's)
        if not 1 <= cls.section_players <= 16:
            return False
        own.update(unison_voices='SectionMixin', voice_vibrato='SectionMixin', **_SECTION_OWN)
    if issubclass(cls, T.FormantBody):
        own.update(bore_gain='FormantBody', _body_trim='FormantBody')
    elif _owner(cls, 'bore_gain') == 'MutedTrumpetProperties' and len(cls.mute_response) <= 24:
        own.update(bore_gain='MutedTrumpetProperties')      # (a mute in the bell)
    own = _tape_own(cls, own)
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    pts = getattr(cls, 'mode_gains_points', None) or ()
    return ((cls.mode_gains is None or mes) and cls.mode_ratios is None and not pts and not cls.strike_point
            and not cls.harmonic_touch and not cls.pickup_points and not (cls.unison_detune or ())
            and bool(cls.bore_corner_hz)
            and 1 <= (cls.max_harmonic or 0) <= (512 if mes else 256)
            and not cls.inharmonicity_dynamic and not cls.mode_stroke_tilt
            and len(getattr(cls, 'formants', ()) or ()) <= 16 and len(getattr(cls, 'antiformants', ()) or ()) <= 8
            and len(getattr(cls, 'body_trim_db', ()) or ()) <= 32
            and not any(getattr(cls, a, None) for a in ('grains', 'noise_events', 'pulse', 'ring_db', 'struck_layer',
                                                         'touch_leak_db', 'strike_noise_db', 'release_click_db',
                                                         'hammer_legato', 'bend_detents')))


def mallet_voice(cls):
    """Whether native/voice.c plays cls as a struck bar's plain series (kind
    4 with no body): SynthProperties' series at the bar's stiffness -- the
    pluck's comb at its plucked harmonic, no bore -- a glockenspiel's."""
    import tonelib as T
    if (not issubclass(cls, T.MalletProperties) or issubclass(cls, (T.FormantBody, T.TunedBarProperties, T.ModeDecays))
            or issubclass(cls, T.NoisyPercussionMixin)):
        return False
    own = dict(_HARMONIC_OWN, bore_gain='SynthProperties', _body_trim=None)
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    return (cls.mode_gains is None and cls.mode_ratios is None and not cls.strike_point and not cls.harmonic_touch
            and not cls.pickup_points and not (cls.unison_detune or ()) and not cls.blare_db_per_khz
            and not cls.bore_corner_hz and not cls.inharmonicity_dynamic and 1 <= (cls.max_harmonic or 0) <= 256
            and not any(getattr(cls, a, None) for a in ('breath_noise_db', 'grains', 'noise_events', 'pulse',
                                                         'ring_db', 'struck_layer', 'touch_leak_db', 'strike_noise_db',
                                                         'release_click_db', 'hammer_legato', 'bend_detents',
                                                         'amp_drive')))


def free_reed_series(cls):
    """A free reed's flow spectrum where it is one table whatever the key
    (FreeReedProperties._reed_series with no register laws and no scatter:
    numpy's FFT, Python's to compute), else None."""
    import tonelib as T
    if (not issubclass(cls, T.FreeReedProperties) or cls.mode_gains is not None or cls.reed_gate_per_octave
            or cls.reed_spread_per_octave or cls.reed_scatter or cls.reed_scatter_per_octave
            or cls.even_harmonic_db is not None):
        return None
    return _class_proto(cls)._reed_series()


def _class_proto(cls):
    return cls(261.6, 0.5, 1.0, 1.0)


def pipe_voice(cls):
    """Whether native/voice.c plays cls as an organ pipe: a measured mode
    set on the harmonic series, its tables by register (mode_gains_points,
    or mode_gains_low), on SynthProperties' own methods -- or a reed organ's
    free reed, its series one table (free_reed_series)."""
    import tonelib as T
    if not issubclass(cls, (T.OrganProperties, T.StoppedPipeProperties, T.FreeReedProperties)):
        return False
    own = _PIPE_OWN
    if issubclass(cls, T.FreeReedProperties):
        own = dict(own, inharmonicity_coefficient_for_frequency=None, series_volume='FreeReedProperties')
    if any(_owner(cls, n) != o for n, o in own.items()):
        return False
    pts = getattr(cls, 'mode_gains_points', None) or ()
    if issubclass(cls, T.FreeReedProperties) and cls.mode_gains is None and not free_reed_series(cls):
        return False
    # (or a stopped pipe with no table at all: SynthProperties' series, a
    # hit's flutes -- tonelib.OrchestraHitProperties' borrowed spectrum)
    return (cls.mode_ratios is None and (cls.mode_gains is not None or pts or issubclass(cls, T.FreeReedProperties)
                                         or (issubclass(cls, T.StoppedPipeProperties) and cls.mode_gains is None
                                             and not cls.mode_gains_low))
            and len(pts) <= 8 and all(len(g) <= 64 for _, g in pts) and len(cls.mode_gains or ()) <= 64
            and len(cls.mode_gains_low or ()) <= 64 and not cls.mode_stroke_tilt and not cls.strike_point
            and not cls.harmonic_touch and not cls.pickup_points and not (cls.unison_detune or ())
            and not getattr(cls, 'strike_noise_db', None))


_MOOG = {}


# moog.PANEL's keys in its order: nv.h's NV_MK_*
MOOG_KNOBS = ('osc1_octave', 'osc1_wave', 'osc2_octave', 'osc2_wave', 'osc2_freq', 'tune', 'sub_wave',
              'osc1_level', 'osc2_level', 'sub_level', 'noise_level', 'cutoff', 'resonance', 'eg_amount',
              'kb_track', 'mode', 'res_bass', 'f_attack', 'f_decay', 'f_sustain', 'f_release', 'a_attack',
              'a_decay', 'a_sustain', 'a_release', 'glide', 'sync', 'lfo1_rate', 'lfo1_shape', 'lfo1_depth',
              'lfo1_dest', 'lfo1_reset', 'mod_amount', 'mod_dest', 'mf104_on', 'mf104_time', 'mf104_range',
              'mf104_feedback', 'mf104_mix', 'mf104_rate', 'mf104_amount', 'mf104_wave', 'a_vel',
              'lfo2_rate', 'lfo2_pitch', 'lfo2_cut', 'lfo2_amp', 'f_loop', 'a_loop', 'f_vel', 'multitrig')


def moog_tables():
    """nv_moog_tables' array (the export's MTAB): Q, osc_spectrum's and
    sub_spectrum's coefficients at every knob position (moog.py caches them
    by position: a harmonic's is the same however many are asked for), then
    the laws' constants (tone.c's MC_*)."""
    import numpy as np
    import moog as MG
    assert tuple(MG.PANEL) == MOOG_KNOBS
    q = int(MG.Q)
    osc = np.array([MG._osc_cached(i, 64) for i in range(q + 1)], np.complex128)
    sub = np.array([MG._sub_cached(i, 32) for i in range(q + 1)], np.complex128)
    k = [MG.SEMIS, MG.EG_CURVE, MG.LFO_RATE_LO, MG.LFO_RATE_SPAN, MG.LFO_CUT_CUBE, MG.LFO_PITCH_CUBE,
         MG.LFO_KNOB_CUBE, MG.MOD_PITCH_OCTAVES, MG.MOD_WAVE_REACH]
    k += list(MG.SUS_V) + list(MG.SUS_TARGET) + list(MG.FM_INDEX_V) + list(MG.FM_INDEX_I)
    assert len(k) == 47 and len(MG.SUS_V) == 6 and len(MG.FM_INDEX_V) == 13
    return np.concatenate([[float(q)], osc.view(np.float64).ravel(), sub.view(np.float64).ravel(),
                           np.array(k, np.float64)])


def moog_spec(cls):
    """A Moog class's panels as its notes read them (nv.h MoogSpec), one a
    layer (moog.layers_of), at TUNING_MOOG_PANEL's knobs as moog.panel_of
    takes them -- or None where a panel has what the native note has not
    (moog_voice). The waveshapes' coefficients are moog.py's own at 64 (and
    32) harmonics: a harmonic's is the same however many are asked for."""
    # (keyed by its panels as well as the class: a class's messenger dict, or
    # TUNING_MOOG_PANEL, changed while running -- the selftest's checks turn
    # MoogSawLead's knobs -- is another panel, not the one first worked out)
    key = (cls, repr(sorted((getattr(cls, 'messenger', None) or {}).items())),
           repr(sorted((getattr(cls, 'messenger_b', None) or {}).items())),
           os.environ.get('TUNING_MOOG_PANEL'), os.environ.get('TUNING_MOOG_PANEL_B'))
    got = _MOOG.get(key)
    if got is None:
        import cmath
        import moog as MG
        import mf104
        spec = MoogSpec()
        lays = MG.layers_of(cls)
        ok = 1 <= len(lays) <= 2
        for i, lay in enumerate(lays if ok else ()):
            pn = MG.panel_of(cls, layer=lay)
            mfs = mf104.settings(pn)
            if (len(MG.NOISE_HZ) > 32
                    or (mfs is not None and (MG.pitch_params(pn) is not None or MG.shape_flags(pn)))):
                ok = False
                break
            L = spec.L[i]
            L.t = 2.0 ** (MG.bipolar(pn['tune'], MG.SEMIS) / 12.0)
            L.foot1 = MG.FOOT.get(int(pn['osc1_octave']), 1.0)
            L.foot2 = MG.FOOT.get(int(pn['osc2_octave']), 1.0)
            L.o2f = 2.0 ** (MG.bipolar(pn['osc2_freq'], MG.SEMIS) / 12.0)
            # SYNC: OSC 2 restarts at each of OSC 1's periods -- it sounds on
            # OSC 1's harmonics (f1 exactly: foot1, x 1.0), its coefficients the
            # synced wave's at OSC 2 FREQ's ratio (moog.partials' f2 / f1, the
            # same to sync_spectrum's 1e-4 at every key)
            sync = bool(pn['sync'])
            r12 = MG.osc_ratio(pn, MG.OSC2) / MG.osc_ratio(pn, MG.OSC1)
            if sync:
                L.foot2, L.o2f = L.foot1, 1.0
            L.lvl[:] = [float(pn['osc1_level']), float(pn['osc2_level']), float(pn['sub_level']),
                        float(pn['noise_level'])]
            for arr, c in ((L.c1, MG.osc_spectrum(pn['osc1_wave'], MG.OSC_HARMONICS)),
                           (L.c2, MG.sync_spectrum(pn['osc2_wave'], r12, MG.OSC_HARMONICS) if sync
                            else MG.osc_spectrum(pn['osc2_wave'], MG.OSC_HARMONICS)),
                           (L.cs, MG.sub_spectrum(pn['sub_wave'], MG.SUB_HARMONICS))):
                for k, z in enumerate(c):
                    arr[k][0], arr[k][1] = float(z.real), float(z.imag)
            L.n_noise = len(MG.NOISE_HZ)
            L.noise_hz[:L.n_noise] = [float(x) for x in MG.NOISE_HZ]
            L.noise_amp[:L.n_noise] = [float(x) for x in MG.NOISE_AMP]
            L.self_amp = MG.self_amp(pn['resonance'])
            L.self_cut = MG.knob_cutoff(pn['cutoff'])
            L.self_eg = 2.0 ** (MG.eg_octaves(pn['eg_amount']) * MG.sustain_level(pn['f_sustain']))
            L.kb_track = float(pn['kb_track'])
            L.fm_index = MG.fm_index(pn)
            L.fm_r1 = MG.osc_ratio(pn, MG.OSC1)
            L.fm_ph = cmath.phase(MG.osc_spectrum(pn['osc1_wave'], 1)[0]) if L.fm_index else 0.0
            pp, sf = MG.pitch_params(pn), MG.shape_flags(pn)
            L.pitch_on, L.shape_on = int(pp is not None), int(sf)
            if pp is not None:
                L.pitch_p[:] = [float(x) for x in pp]
            if sf:
                L.shape_par[:] = [float(x) for x in MG.shape_params(pn)]
            pre = bool(getattr(cls, 'amp_drive', 0.0))     # (a valve after the ladder: FT slot 11)
            L.pre = int(pre)
            L.bp_gain, L.bp_corner, L.hp_gain, L.hp_corner, L.hp_leak = (MG.BP_GAIN, MG.BP_CORNER, MG.HP_GAIN,
                                                                         MG.HP_CORNER, MG.HP_LEAK)
            L.ft[:] = [float(x) for x in MG.ft_row(pn, MG.KB_REF_HZ, 0, pre,
                                                   (MG.FT_PITCH if pp is not None else 0) | sf)]
            L.kn[:] = [float(x) for x in MG.kn_row(pn)]
            L.rel_span = MG.release_span(pn)
            L.fmax_hz, L.kb_ref_hz, L.noise_bw = MG.FMAX_HZ, MG.KB_REF_HZ, MG.NOISE_BW
            # GM's sound controllers on its knobs (moog.apply_gm), and their laws
            gs = list(MG.GM_SOUND.values())
            L.knob[:] = [float(pn[kb]) for kb, _ in gs]
            L.span[:] = [float(sp) for _, sp in gs]
            L.eg_v[:] = [float(x) for x in MG._EG_V]
            L.eg_log[:] = [float(x) for x in MG._EG_LOG]
            L.atk_to_1, L.cut_lo, L.cut_oct = MG._ATK_TO_1, MG.CUT_LO_HZ, MG.CUT_OCT
            L.k_max, L.res_per_unit = MG.K_MAX, MG.RES_PER_UNIT
            L.self_from, L.self_amp_max, L.eg_under = MG.SELF_FROM, MG.SELF_AMP, MG.EG_UNDER
            L.body = int(getattr(cls, 'moog_body', None) is not None)       # (the voice's bore: moog_bodied)
            # THE UNISON (moog.unison): its spec, each note's voices drawn in C
            us = dict(MG.UNISON, **(getattr(cls, 'moog_unison', None) or {}))
            L.u_n = int(us['voices'])
            L.u_cents, L.u_mix, L.u_dc = float(us['cents']), float(us['mix']), float(us['drift_cents'])
            L.u_dhz[:] = [float(x) for x in us['drift_hz']]
            L.u_width = float(us['width'])
            L.pn[:] = [float(pn[k]) for k in MOOG_KNOBS]      # (its panel: a knob turned live builds from it)
            if mfs is not None:                 # the MF-104M after it (its repeats: native/prepare.cpp)
                L.mf_on = 1
                L.mf[:] = [float(mfs[k]) for k in ('time', 'fc', 'fb', 'wet', 'dry', 'rate', 'amount')]
                L.mf_grid, L.mf_max, L.mf_floor, L.mf_poles = (float(mf104.GRID), float(mf104.MAX_REPEATS),
                                                               float(mf104.REPEAT_FLOOR), float(mf104.FILTER_POLES))
        spec.n_layer = len(lays) if ok else 0
        got = _MOOG[key] = spec if ok else False
    return got or None


def _section_desks(s, p):
    """A section's desks on VoiceSnap s (section_position_x, less the voice's
    place: the note's is added): sect_seats, sect_dx."""
    import random
    n = int(p.section_players)
    s.sect_seats = int(bool(p.section_width_m) and n > 1)
    if s.sect_seats:
        w = p.section_width_m
        for i in range(n):
            rng = random.Random(0x5EA7 + i * 7919 + p._section_salt() * 65537)
            s.sect_dx[i] = w * ((2.0 * i / float(n - 1)) - 1.0 + rng.uniform(-0.5, 0.5) / n)


def moog_bodied(cls):
    """Whether cls's Moog sounds through a FORMANT BODY the engine has: its
    moog_body FormantBody's bore times SynthProperties' norm (bore_gain *
    _bore_norm), on SynthProperties' series with the pluck's comb."""
    import inspect
    if getattr(cls, 'moog_body', None) is None:
        return False
    try:
        src = inspect.getsource(cls.moog_body)
    except (OSError, TypeError):
        return False
    if 'return self.bore_gain(partial_hz) * self._bore_norm()' not in src or src.count('return') != 1:
        return False
    if (_owner(cls, 'bore_gain') != 'FormantBody' or _owner(cls, '_bore_norm') != 'SynthProperties'
            or _owner(cls, 'series_volume') != 'SynthProperties'):
        return False
    return (not cls.strike_point and cls.mode_gains is None and not cls.harmonic_touch and not cls.pickup_points
            and cls.bore_corner_hz and 0 < int(cls.max_harmonic or 0) <= 128)


def moog_voice(cls):
    """Whether native/voice.c plays cls as a Moog (kind 6: moog.py's
    Messenger, native/tone.c nv_moog_tone): SynthProperties' constructor,
    gains and vibrato (a section's of one player), and only what the native
    Moog note has of its panels -- the oscillators, noise, the ladder's own
    sine, the contours, 1 -> 2 FM, the mod section's pitch and shape rows,
    one layer or two, a formant body (moog_bodied), a valve after the ladder
    (the file's amp on its rows), the MF-104M (not on a note whose pitch or
    shapes move), SYNC (OSC 2 on OSC 1's harmonics, synced), a unison (moog.unison's voices)."""
    import tonelib as T
    if not getattr(cls, 'moog', False):
        return False
    if any(k.__name__ not in ('SynthProperties', 'object') for k in cls.__mro__ if '__init__' in k.__dict__):
        return False
    if any(_owner(cls, n) != 'SynthProperties' for n in ('radiation_gain', 'hrtf_gain', 'chiff_harmonic_gain')):
        return False
    if _owner(cls, 'voice_vibrato') not in ('SynthProperties', 'SectionMixin'):
        return False
    if any(_owner(cls, n) != o for n, o in _BASE_OWN.items() if n != 'inharmonicity_coefficient_func'):
        return False
    if getattr(cls, 'moog_body', None) is not None and not moog_bodied(cls):
        return False
    # (nothing beside its partials: no knock, breath, struck layer, ring or click)
    if any(getattr(cls, a, None) for a in ('strike_noise_db', 'breath_noise_db', 'struck_layer', 'ring_db',
                                           'release_click_db', 'touch_leak_db', 'shake_noise')):
        return False
    return moog_spec(cls) is not None


def kit_drum(cls):
    """Which voice native/voice.c plays cls as (VoiceSnap.kind) past a
    piano's: 1 a kit drum, 2 a measured mode set's (the clap, the cymbals,
    the woods...), 3 a shaker, 4 a harmonic voice (a guitar), 5 an electric
    piano, 6 a Moog; else 0."""
    import tonelib as T
    if moog_voice(cls):
        return 6
    if ep_voice(cls):
        return 5
    if hit_voice(cls):
        return 4
    if (harmonic_voice(cls) or tonewheel_voice(cls) or reed_voice(cls) or electric_voice(cls) or wind_voice(cls)
            or mallet_voice(cls)):
        return 4
    if pipe_voice(cls):
        return 2
    if _modal_drum(cls):
        return 2
    if _shaken(cls):
        return 3
    if pulse_voice(cls):
        return 7
    if not issubclass(cls, T.KitDrumProperties):
        return 0
    if issubclass(cls, T.NoisyPercussionMixin) and issubclass(cls, T.MeasuredStrokeProperties):
        if len(cls.band_trim_db) > 32:
            return 0
        own = dict(_MEASURED_OWN)
        if issubclass(cls, T.PlayedAtPitchMixin):
            own['_band_trim'] = 'PlayedAtPitchMixin'        # (its colour at the recorded pitch)
        if issubclass(cls, T.SfxThroatProperties):
            # (a throat's: its mouth, its vowel and its tilt on the stroke's, its
            # breath tilted with it -- the vowel's second set as long as its first)
            own = dict(own, mode_ratio='SfxThroatProperties', harmonic_volume='SfxThroatProperties',
                       chiff_volume='SfxThroatProperties')
            if cls.DRUM_MODES_B and len(cls.DRUM_MODES_B) != len(cls.DRUM_MODES):
                return 0
    elif issubclass(cls, T.NoisyPercussionMixin) and issubclass(cls, T.TambourineProperties):
        if len(cls.band_trim_db) > 32:
            return 0
        own = dict(_MEASURED_OWN, partial_jitter='TambourineProperties',
                   stroke_scatter_db='TambourineProperties', harmonic_decay='TambourineProperties')
    elif issubclass(cls, T.NoisyPercussionMixin):
        if not issubclass(cls, T.AcousticSnareProperties) or len(cls.band_trim_db) > 32:
            return 0
        own = dict(_SNARE_OWN, harmonic_decay=_owner(cls, 'harmonic_decay'))
        if own['harmonic_decay'] not in ('AcousticSnareProperties', 'SideStickProperties'):
            return 0
    else:
        own = dict(_KIT_OWN, chiff_harmonic_gain='SynthProperties')
    if any(_owner(cls, n) != o for n, o in own.items()):
        return 0
    return int(len(cls.DRUM_MODES) <= 128 and len(cls.CLICK_DB) <= 32 and len(cls.unison_detune or ()) <= 8
            and not cls.bore_corner_hz and not cls.harmonic_touch and not cls.pickup_points)


def tap_voice(cls):
    """A STRUCK VOICE REPEATED: 1 a bird's chirps (BirdTweetProperties), 2 a
    telephone's clapper (TelephoneRingProperties) -- their unison_voices and
    section_onsets_at the engine's (VoiceSnap.tap_*); else 0."""
    for k, name in ((1, 'BirdTweetProperties'), (2, 'TelephoneRingProperties')):
        if (_owner(cls, 'unison_voices') == name and _owner(cls, 'section_onsets_at') == name
                and (k == 1 or _owner(cls, '_stroke') == name)):
            taps = cls.chirp_taps if k == 1 else cls.ring_taps
            if len(taps) <= 192 and len(getattr(cls, 'GONG', ()) or ()) <= 16:
                return k
    return 0


NV_K_DRONE = 2 * 16384
DRONES = []                 # the drone classes K's drone region holds, in the order first met


def drone_index(cls):
    """cls's place in K's drone region (native_export's DRON), registered."""
    if cls not in DRONES:
        DRONES.append(cls)
    return DRONES.index(cls)


def drones_ok(cls):
    """A class whose drones the engine sounds (Song::drones): up to four,
    each a class it plays -- or one whose note the wheel chooses (the pungi),
    of up to 16 choices."""
    dc = getattr(cls, 'drone_classes', None) or ()
    return (not dc or (len(dc) <= 4
                       and (not getattr(cls, 'drone_note_wheel', False)
                            or 1 <= len(tuple(cls.drone_note_choices)) <= 16)
                       and all(note_class(c) is not None for _, c in dc)))


def heartbeat_voice(cls):
    """The heartbeat (SfxHeartbeatProperties): its ECG a mode set with each
    mode's own phase, its gains a property of fixed values, its blood flow
    timed noise bands (NoteClass.nev)."""
    return (_owner(cls, 'mode_phase') == 'SfxHeartbeatProperties' and _owner(cls, 'mode_gains') == 'SfxHeartbeatProperties'
            and _owner(cls, 'noise_events') == 'SfxHeartbeatProperties' and len(cls.FLOW_EVENTS) <= 64
            and len(cls.ECG_PHASES) <= 400)


def pulse_voice(cls):
    """A voice whose tone is a PRESSURE PULSE (pulse: the gunshot's N-wave,
    blockrender._note_pulse) in place of its series: kind 7, SynthProperties'
    own construction -- its series never sounded, so its laws are not read --
    a percussion voice's knock beside it."""
    import tonelib as T
    return (bool(getattr(cls, 'pulse', False)) and issubclass(cls, T.PercussionProperties)
            and _owner(cls, 'pulse_length') == 'GunshotProperties'
            and not issubclass(cls, (T.KitDrumProperties, T.FormantBody)))


def _voiced_spec(syllables, f0, shape, dur, rise, fall_db, jitter=0.01, shimmer_db=0.0, bright=None,
                 mouth=None, level=None, morph=None):
    """percussion_map._voiced's arguments as native/channel.cpp's voiced reads
    them: f0, dur, rise, fall dB, jitter, shimmer dB; the shape (0, bend,
    time constant; or 1, n, its n (s, semitones)); the syllables (n, then
    each one's time, dB, semitones, and 1 and its own shape and length, or
    0); then the bright, mouth, level and morph contours, each n and its n
    (s, value) (0: none)."""
    def shp(sh):
        if isinstance(sh[0], tuple):
            return [1.0, float(len(sh))] + [float(x) for pt in sh for x in pt]
        return [0.0, float(sh[0]), float(sh[1])]

    def contour(pts):
        return [float(len(pts or ()))] + [float(x) for pt in (pts or ()) for x in pt]
    out = [float(f0), float(dur), float(rise), float(fall_db), float(jitter), float(shimmer_db)] + shp(shape)
    out.append(float(len(syllables)))
    for syl in syllables:
        out += [float(syl[0]), float(syl[1]), float(syl[2])]
        out += [1.0] + shp(syl[3]) + [float(syl[4])] if len(syl) > 3 else [0.0]
    for c in (bright, mouth, level, morph):
        out += contour(c)
    return out


def stroke_spec(note, kit):
    """The gesture percussion_map.rasp_strokes plays this set's key as, as
    the song's strokes take it (native/channel.cpp Song::strokes): (kind,
    [up to SPAR - 4 numbers]) -- 1 a rasp (dur, n, the shape's length, its
    dB), 2 a cascade (span, n, semitones), 3 an impact train (rate, secs,
    fall, jitter, scatter, strike dB, side set, side dB, side slope), 4 a
    roll (_snare_roll's eleven), 5 a pattern (n, then each stroke's time, dB,
    semitones and length, NaN where it runs to the next), 6 a voice's pulses
    (_voiced_spec); (0, []) none; None a gesture the song does not have (a
    rattle)."""
    import percussion_map as PCM
    tabs = PCM.KIT_STROKES.get(kit, {}) if kit in PCM.KIT_ONLY else None
    if tabs is None and note in PCM.KITS.get(kit, {}):
        tabs = PCM.KIT_STROKES.get(kit, {})

    def table(name, std):
        return tabs.get(name, {}).get(note) if tabs is not None else std.get(note)
    c = table("cascade", PCM.PERCUSSION_CASCADE)
    if c is not None:
        return 2, [float(c[0]), float(c[1]), float(c[2])]
    tr = table("train", PCM.PERCUSSION_TRAIN)
    if tr is not None:
        rate, secs, fall, jit, sc = tr[:5]
        strike = tr[5] if len(tr) > 5 else 0.0
        side = tr[6] if len(tr) > 6 else None
        slope = tr[7] if len(tr) > 7 else 0.0
        return 3, [float(rate), float(secs), float(fall), float(jit), float(sc), float(strike),
                   float(side is not None), float(side or 0.0), float(slope)]
    ro = table("roll", PCM.PERCUSSION_ROLL)
    bu = tabs.get("build", {}).get(note) if tabs is not None and ro is None else None
    if bu is not None:
        return 7, [float(x) for x in bu]
    if ro is not None:
        return 4, [float(x) for x in ro] + [0.0] * (11 - len(ro))
    vo = tabs.get("voiced", {}).get(note) if tabs is not None else None
    if vo is not None:
        vs = _voiced_spec(*vo)
        return (6, vs) if len(vs) <= SPAR - 4 else None
    pa = tabs.get("pattern", {}).get(note) if tabs is not None else None
    if pa is not None:
        if 1 + 4 * len(pa) > SPAR - 4:
            return None
        return 5, [float(len(pa))] + [float(x) for st in pa
                                      for x in (st[0], st[1], st[2], st[3] if len(st) > 3 else math.nan)]
    if table("rattle", PCM.PERCUSSION_RATTLE) is not None:
        return None
    r = table("rasp", PCM.PERCUSSION_RASP)
    if r is None:
        return 0, []
    shape = PCM.PERCUSSION_RASP_SHAPE.get(note) if tabs is None else None
    if shape is not None and len(shape) > 21:
        return None
    return 1, [float(r[0]), float(r[1]), float(len(shape or ()))] + [float(x) for x in (shape or ())]


_KITS = []
SPAR = 136          # a drum key's gesture row (native/nv.h NV_SPAR): its strokes, then its layers


# THE PER-CLASS MEMOS (made once a class, reused, never state): what
# memo_scope lets go -- _FAMILIES is not one (its ids are handed out in order)
_MEMOS = ('_CLASS', '_NOTE', '_ORGAN', '_SL_CLS', '_EFX', '_MOOG')


class memo_scope(object):
    """A run of per-class work whose classes are not wanted after it (the
    export's VLIV: each variation's live.Patch, its probe notes rendered):
    the memos as they were before it, the entries it added let go -- so a
    walk over every variation holds one variation's, not all of theirs."""

    def __enter__(self):
        self.keep = {n: set(globals()[n]) for n in _MEMOS}
        return self

    def __exit__(self, *exc):
        g = globals()
        for n, ks in self.keep.items():
            d = g[n]
            for k in [k for k in d if k not in ks]:
                del d[k]
        return False


def kits():
    """The drum sets as the engine's song and K tables take them, for each
    drum program p and key (q = 128 p + key, the set kit_for_program(p)):
    (classes, f0, seat, choke, skind, spar) -- the class the engine plays
    there (None where it does not: no drum, a drum not native, or a key with
    more than its sound -- a gesture the song does not expand, a siren, a
    sweep) and, for every drum the set maps, its pitch and its pan
    in the set (seat); f0 0 where none; the keys a strike on it stops
    (choke_group), as bits (choke[2 q + w], bit k: key 64 w + k); its
    gesture (stroke_spec: skind[q], spar[SPAR q..]); and the keys a strike
    on it also sounds (key_layers), in the row's last four: spar[SPAR (q + 1)
    - 4] how many, the keys after."""
    if _KITS:
        return _KITS[0]
    import percussion_map as PCM
    _KITS.append(kit_tables([PCM.kit_for_program(p) for p in range(128)]))
    return _KITS[0]


def map_kits():
    """The maps' own drum sets (percussion_map.KITS past 127, sorted: the
    sets kit_in_map reads in a part's map), as kits() gives the GS sets:
    (ids, classes, f0, seat, choke, skind, spar), set j's key at 128 j + key."""
    import percussion_map as PCM
    ids = sorted(k for k in PCM.KITS if k >= 128)
    return (ids,) + kit_tables([PCM.kit_for_program(k) for k in ids])


def kit_tables(kitlist):
    """kits()'s tables for a list of drum sets, set p's key at q = 128 p + key."""
    import percussion_map as PCM
    n = 128 * len(kitlist)
    classes, f0, seat = [None] * n, (ctypes.c_double * n)(), (ctypes.c_double * n)()
    choke = (ctypes.c_ulonglong * (2 * n))()
    skind, spar = (ctypes.c_int * n)(), (ctypes.c_double * (SPAR * n))()
    for p, kit in enumerate(kitlist):
        for key in range(128):
            d = PCM.percussion_for_note(key, kit)
            if not d:
                continue
            q = 128 * p + key
            f0[q], seat[q] = float(d[2]), float(d[3])
            for k in PCM.choke_group(key, kit) or ():
                choke[2 * q + k // 64] |= 1 << (k % 64)
            cls = d[1]
            ss = stroke_spec(key, kit)
            if ss:
                skind[q] = ss[0]
                assert len(ss[1]) <= SPAR - 4
                spar[SPAR * q:SPAR * q + len(ss[1])] = ss[1]
            ly = PCM.key_layers(key, kit)
            if len(ly) > 3:
                continue
            spar[SPAR * (q + 1) - 4] = len(ly)
            spar[SPAR * (q + 1) - 3:SPAR * (q + 1) - 3 + len(ly)] = [float(k) for k in ly]
            if (kit_drum(cls) and ss is not None
                    and getattr(cls, 'siren_rotor', None) in (None, 'fire')):
                classes[q] = cls
    # (a key the engine plays only where it plays every layer with it)
    for q in range(n):
        if classes[q] is not None and any(classes[128 * (q // 128) + int(k)] is None
                                          for k in spar[SPAR * (q + 1) - 3:SPAR * (q + 1) - 3
                                                        + int(spar[SPAR * (q + 1) - 4])]):
            classes[q] = None
    return (classes, f0, seat, choke, skind, spar)


def k_table(classes, programs=range(128)):
    """The engine's K: K[128 * program + key] the NoteClass of classes(program,
    key) for each of programs, K[16384 + 128 * program + key] a drum set's
    (kits()). (K, the NoteClasses it points at, to keep)."""
    K = (ctypes.c_void_p * (2 * 16384))()
    keep = []
    for prog in programs:
        for key in range(128):
            cls = classes(prog, key)
            k = note_class(cls) if cls is not None else None
            if k is not None:
                keep.append(k)
                K[128 * prog + key] = ctypes.addressof(k)
    for q, cls in enumerate(kits()[0]):
        k = note_class(cls) if cls is not None else None
        if k is not None:
            keep.append(k)
            K[16384 + q] = ctypes.addressof(k)
    return K, keep


def supported(props):
    """Whether the native voice plays this voice: the grand piano
    (GrandPianoProperties) and the kit drums (kit_drum), and none of the
    features not ported yet."""
    import tonelib as T
    if kit_drum(type(props)):
        return True
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


def _blare_snap(s, p):
    """A voice's blare (SynthProperties._blare) into its snapshot: its law and its norm."""
    if p.blare_db_per_khz:
        s.blare_db_per_khz, s.blare_knee_hz, s.blare_cap_db = p.blare_db_per_khz, p.blare_knee_hz, p.blare_cap_db
        s.blare_norm = p._blare_norm()


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
    # (a drum has no strike point: its series is its own, and reads none of these)
    s.strike_point, s.strike_depth = p.strike_point or 0.0, p.strike_depth or 0.0
    s.strike_fills = int(bool(p.strike_fills_with_force))
    s.strike_fill_fraction, s.attack_volume, s.attack_dampening = (
        p.strike_fill_fraction or 0.0, p.attack_volume, p.attack_dampening or 0.0)
    s.frequency_x, s.octave_position = p.frequency_x, p.octave_position
    s.decay_db, s.harmonic_decay_db = p.decay_db, p.harmonic_decay_db
    s.harmonic_decay_dampening, s.decay_register_factor = p.harmonic_decay_dampening, p.decay_register_factor
    for f in ('chiff_harmonic_power', 'bloom_seconds', 'bloom_center_hz', 'bloom_octaves', 'bloom_shape',
              'exp_vibrato_cents', 'solo_vibrato_spread', 'solo_vibrato_hz', 'radiation_distance', 'hrtf_beta',
              'bloom_gain', 'bloom_swell', 'bloom_scatter'):
        setattr(s, f, getattr(p, f))
    s.bloom_banded = int(bool(p.bloom_banded))
    s.bloom_decay_dbs = getattr(p, 'bloom_decay_dbs', 0.0) or 0.0
    s.kind = kit_drum(type(p))
    s.nyquist = p._nyquist if isinstance(p, T.SampledBreak) else 0.0
    # a played reed's or pipe's wind (wind_skirt_always: the harmonica's, a
    # recorder's), on its first WIND_PARTIALS
    if s.kind in (2, 4) and getattr(p, 'wind_skirt_always', False) and getattr(p, 'wind_skirt_db', None) is not None:
        import blockrender as _BR
        s.skirt, s.sk_max = 1, int(_BR.WIND_PARTIALS)
        s.sk_db, s.sk_hdb = float(p.wind_skirt_db), float(p.wind_skirt_harmonic_db)
        s.sk_hz, s.sk_rel = float(p.wind_skirt_hz), float(getattr(p, 'wind_skirt_rel', None) or 0.0)
    if s.kind == 3:
        # a harmonic series on SynthProperties: the noise's roll-off, its unison
        s.unison_gain = p.unison_gain
        s.n_unison = len(p.unison_detune or ())
        for i, x in enumerate(p.unison_detune or ()):
            s.unison_detune[i] = x
        s.noisy, s.hf_corner_hz, s.hf_order = 1, p.hf_corner_hz, p.hf_order
        s.n_trim = len(p.band_trim_db)
        for i, (f, db) in enumerate(p.band_trim_db):
            s.trim[i][:] = [float(f), float(db)]
    elif s.kind == 2:
        # the measured mode set: (ratio, linear gain), SynthProperties' decay,
        # its unison
        if _owner(type(p), 'bore_gain') == 'FormantBody':     # (a tine's body: the kalimba's)
            s.fbody, s.formant_floor = 1, p.formant_floor
            s.n_fm, s.n_afm, s.n_bt = len(p.formants), len(p.antiformants), len(p.body_trim_db or ())
            for i, row in enumerate(p.formants):
                s.fm[i][:] = [float(x) for x in row]
            for i, row in enumerate(p.antiformants):
                s.afm[i][:] = [float(x) for x in row]
            for i, row in enumerate(p.body_trim_db or ()):
                s.bt[i][:] = [float(x) for x in row]
        s.unison_gain = p.unison_gain
        s.n_unison = len(p.unison_detune or ())
        for i, x in enumerate(p.unison_detune or ()):
            s.unison_detune[i] = x
        mg = p.mode_gains_here() if pipe_voice(type(p)) else p.mode_gains
        if mg is None and pipe_voice(type(p)) and isinstance(p, T.FreeReedProperties):
            mg = p._reed_series()[1:]           # (a free reed's flow spectrum, harmonic 1 first)
        mg = () if mg is None else mg       # (a tuned bar's: its bar modes on the harmonic series)
        s.n_mm = len(mg)
        if p.mode_ratios is None:
            s.mm_harm = 1                   # (a gain table on the harmonic series)
        else:
            s.mm_ratio[:s.n_mm] = [float(r) for r in p.mode_ratios][:s.n_mm]   # (a tube's: its own, VoiceSnap.tube)
        s.mm_gain[:s.n_mm] = [float(g) for g in mg]
        if not s.n_mm and not getattr(s, 'or_set', 0) and (pipe_voice(type(p))
                                                            or isinstance(p, T.WoodPercussionProperties)):
            # (a stopped pipe with no table, a wood block: SynthProperties' series, the pluck's comb)
            for h in range(1, min(256, int(p.max_harmonic or 64)) + 1):
                s.comb[h] = T._pluck_comb(p.plucked_harmonic, p.pluck_dampening, h)
        if pipe_voice(type(p)):
            # an organ pipe's register: its tables by pitch, or a low one
            pts = getattr(p, 'mode_gains_points', None) or ()
            s.n_pts = len(pts)
            s.n_ptg = max((len(g) for _, g in pts), default=0)
            for i, (f, g) in enumerate(pts):
                s.pts_hz[i], s.pts_n[i] = float(f), len(g)
                s.pts_g[i][:len(g)] = [float(x) for x in g]
            pg = p.mode_gains if p.mode_gains is not None else mg      # (a free reed's: its one table)
            s.n_pipe = len(pg)
            s.pipe_g[:s.n_pipe] = [float(x) for x in pg]
            if p.mode_gains_low is not None:
                s.low_set, s.n_low = 1, len(p.mode_gains_low)
                s.low_g[:s.n_low] = [float(x) for x in p.mode_gains_low]
                s.low_hz[:] = [float(x) for x in p.register_low_hz]
        if isinstance(p, T.CuicaProperties):
            # its partials' jitter: the sustain's under rough_from, rough above
            s.head_jitter, s.wire_jitter, s.jit_from, s.jit_sus = (p.sustain_jitter, p.rough_jitter,
                                                                   int(p.rough_from), 1)
        if isinstance(p, T.CymbalProperties):
            s.cymbal = 1
            for f in ('ring_peak_hz', 'ring_decay_below', 'ring_decay_above', 'ring_decay_floor',
                      'aftersound_fraction', 'aftersound_dbs', 'aftersound_ratio'):
                setattr(s, f, getattr(p, f))
        dt = decay_target(type(p))
        s.retarget, s.decay_target = int(dt is not None), dt or 0.0
        if isinstance(p, T.NoisyPercussionMixin):
            s.noisy, s.hf_corner_hz, s.hf_order = 1, p.hf_corner_hz, p.hf_order
            s.n_trim = len(p.band_trim_db)
            for i, (f, db) in enumerate(p.band_trim_db):
                s.trim[i][:] = [float(f), float(db)]
        if p.bore_corner_hz:
            s.bore_corner_hz, s.bore_order = p.bore_corner_hz, p.bore_order
            s.bell_cutoff_hz, s.bell_order = p.bell_cutoff_hz or 0.0, p.bell_order
            s.bore_norm = p._bore_norm()
            _blare_snap(s, p)
        if isinstance(p, T.SambaWhistleProperties):
            s.pea, s.pea_vibrato_cents, s.pea_vibrato_hz = 1, p.pea_vibrato_cents, p.pea_vibrato_hz
        if _owner(type(p), 'mode_gains_here') == 'MusicBoxProperties':
            # a comb tooth's octave below, by key (its gain the note's: nv_voice_init)
            s.or_set, s.or_share, s.or_lowest_hz = 1, float(p.octave_ring_share), float(p.octave_ring_lowest_hz)
            s.or_db[:] = [float(x) for x in p.octave_ring_db]
            s.or_g = float(p.mode_gains_here()[6])
        if _tube(type(p)):
            # a chime's tube: its modes' lines in octaves, their decays mode_decays
            s.n_tube, s.tube_ref_hz = len(p.TUBE_MODES), float(p.TUBE_REF_HZ)
            for i, row in enumerate(p.TUBE_MODES):
                s.tube[i][:] = [float(x) for x in row[:4]]
            s.n_md = len(p.TUBE_MODES)
            s.mode_decays[:s.n_md] = [float(row[4]) for row in p.TUBE_MODES]
            if _owner(type(p), 'harmonic_decay') == 'ChurchBellProperties':     # (a church bell's own law)
                s.church, s.church_slope = 1, float(p.decay_register_slope)
        if timpani_voice(type(p)) or (isinstance(p, (T.CymbalProperties, T.StruckBarProperties))
                                      and isinstance(p, T.ModeDecays) and p.mode_stroke_tilt):
            s.mst, s.mst_ref = float(p.mode_stroke_tilt), float(p.mode_stroke_ref_db)
        if _bar_by_register(type(p)):
            # a struck bar's modes by register: its gains' tables by pitch, its ratios' law
            pts = getattr(p, 'mode_gains_points', None) or ()
            if pts:
                s.mm_pts, s.n_pts = 1, len(pts)
                s.n_ptg = max(len(g) for _, g in pts)
                for i, (f, g) in enumerate(pts):
                    s.pts_hz[i], s.pts_n[i] = float(f), len(g)
                    s.pts_g[i][:len(g)] = [float(x) for x in g]
            mro = _owner(type(p), 'mode_ratio')
            if mro == 'BalafonProperties':
                s.mr_law, s.mr_ref = 1, 415.0
                for i, (a, b, lo) in enumerate(p.mode_ratio_laws):
                    s.mr_a[i], s.mr_b[i], s.mr_lo[i] = float(a), float(b), float(lo)
            elif mro == 'LogDrumProperties':
                s.mr_law = 2
                s.mr_body[:] = [float(x) for x in p.body_modes_hz]
        if isinstance(p, T.ModeDecays) or timpani_voice(type(p)):
            ma, mp = getattr(p, 'mode_after', ()), getattr(p, 'mode_phases', ())
            s.n_md, s.n_ma, s.n_mp = len(p.mode_decays), len(ma), len(mp)
            s.mode_decays[:s.n_md] = [float(x) for x in p.mode_decays]
            for i, (sh, d) in enumerate(ma):
                s.mode_after[i][:] = [float(sh), float(d)]
            s.mode_phases[:s.n_mp] = [float(x) for x in mp]
        if isinstance(p, T.TunedBarProperties):
            # (a mode off the series -- the xylophone's 6.43 -- is never a harmonic: it never sounds)
            bm = [(bn, bg) for bn, bg in p.bar_modes if bn == int(bn)]
            s.n_bar = len(bm)
            for i, (bn, bg) in enumerate(bm):
                s.bar_n[i], s.bar_g[i] = int(bn), float(bg)
    elif s.kind == 4:
        # a harmonic voice: the pluck's comb, the body
        s.comb[0] = 0.0
        if _owner(type(p), 'unison_voices') == 'HammeredDulcimerProperties':
            s.dul_n, s.dul_beat[:] = int(p.string_count) - 1, [float(x) for x in p.unison_beat_hz]
            s.unison_gain = p.unison_gain
        if hit_voice(type(p)):                  # (a hit's section: OrchestraHitProperties.unison_voices)
            s.hit_n, s.hit_gain = len(p.section_cents), float(p.unison_gain)
            s.hit_cents[:s.hit_n] = [float(x) for x in p.section_cents]
        if _owner(type(p), 'harmonic_decay') == 'HammeredDulcimerProperties':
            s.dhz_set, s.dhz_db, s.dhz_pow = 1, float(p.decay_hz_db), float(p.decay_hz_power)
        if _owner(type(p), 'harmonic_decay') == 'PromptDecay' and p.prompt_max_hz:
            s.pd_max_hz, s.pd_dbs, s.pd_share = (float(p.prompt_max_hz), float(p.prompt_dbs),
                                                 float(p.aftersound_share))
        s.pps = float(getattr(p, 'partial_phase_spread', 0.0) or 0.0)
        s.ushare = int(bool(getattr(p, 'unison_shares_phase', False)))
        if _owner(type(p), 'aftersound') == 'PizzicatoStringsProperties':
            s.aftersound_fraction, s.aftersound_ratio = float(p.aftersound_fraction), float(p.aftersound_ratio)
        # (a played pipe's modes pulled into lock: mode_lock_offset_for)
        s.ml_spread = float(getattr(p, 'mode_lock_spread', 0.0) or 0.0)
        s.ml_knee, s.ml_time = float(getattr(p, 'mode_lock_knee', 3.0)), float(getattr(p, 'mode_lock_time', 0.035))
        if _owner(type(p), 'bore_gain') == 'MutedTrumpetProperties':
            s.n_mute = len(p.mute_response)
            for i, (f, db) in enumerate(p.mute_response):
                s.mute[i][:] = [float(f), float(db)]
        if feedback_voice(type(p)):             # FEEDBACK: the loop's partial, its series
            s.fb_set, s.fb_fixed = 1, int(p.feedback_fixed_harmonic or 0)
            s.fb_band_hz, s.fb_delay, s.fb_swell = p.feedback_band_hz, p.feedback_delay_s, p.feedback_swell_s
            s.fb_gain, s.fb_dbs = p.feedback_gain, p.feedback_dbs
            s.n_fbs = len(p.feedback_series)
            for i, (k, g) in enumerate(p.feedback_series):
                s.fbs[i][:] = [float(k), float(g)]
        if plectrum_voice(type(p)):             # A PICK, and its courses
            s.pick_set, s.pick_hz, s.pick_slope_db = 1, p.pick_hz, p.pick_slope_db
            s.pick_boost_max_db, s.pick_dbs, s.pick_stagger = p.pick_boost_max_db, p.pick_dbs, p.course_stagger_s
            s.sect_ofm = getattr(p, 'unison_onset_fraction_max', 0.25)
            _uo = _owner(type(p), 'unison_voices')
            if _uo == 'MandolinProperties':
                s.crs_kind, s.crs_uni_gain, s.crs_uni_cents = 1, p.unison_partner_gain, p.unison_partner_cents
            elif _uo == 'TwelveStringProperties':
                s.crs_kind, s.crs_split = 2, p.course_split
                s.crs_oct_gain, s.crs_oct_cents = p.octave_partner_gain, p.octave_partner_cents
                s.crs_uni_gain, s.crs_uni_cents = p.unison_partner_gain, p.unison_partner_cents
            elif _uo == 'TaishoKotoProperties':
                # (every even harmonic its octave trio, each a third of the sum's power)
                s.crs_kind, s.crs_oct_gain = 5, p.octave_partner_gain
                s.crs_ntrio = len(p.octave_trio_cents)
                s.crs_trio[:s.crs_ntrio] = [float(c) for c in p.octave_trio_cents]
            if _owner(type(p), 'section_onsets_at') == 'TaishoKotoProperties':
                s.swp_set, s.swp_share, s.swp_step = 1, p.sweep_share, p.sweep_step_s
                s.swp_tog[:] = [float(x) for x in p.sweep_together_s]
                s.swp_swept[:] = [float(x) for x in p.sweep_swept_s]
        _uo = _owner(type(p), 'unison_voices')
        if _uo in ('KanunProperties', 'OudProperties'):
            # THE KANUN's COURSES, two strings a key, one sharp, one flat; the
            # OUD's, one partner either side -- each key's cents its own draw
            s.crs_kind = 3 if _uo == 'KanunProperties' else 4
            s.crs_seed = float(0x6A2B0 if _uo == 'KanunProperties' else 0x0D0D0)
            s.crs_lo, s.crs_hi = float(p.course_cents[0]), float(p.course_cents[1])
            s.crs_uni_gain = float(getattr(p, 'course_partner_gain', 1.0))
        # (a reed's has none, nor a quill's: its comb is the strike point's)
        for h in range(1, min(256, int(p.max_harmonic)) + 1 if not (reed_voice(type(p)) or p.strike_point) else 0):
            s.comb[h] = T._pluck_comb(p.plucked_harmonic, p.pluck_dampening, h)
        s.bore_corner_hz, s.bore_order = p.bore_corner_hz, p.bore_order
        s.bell_cutoff_hz, s.bell_order = p.bell_cutoff_hz or 0.0, p.bell_order
        s.bore_norm = p._bore_norm() if p.bore_corner_hz else 0.0     # (read only through a bore)
        if p.bore_corner_hz:
            _blare_snap(s, p)
        if electric_voice(type(p)):
            # an electric guitar: its pick and coils as the class has them (the note's fret moves them)
            c = type(p)
            s.elec, s.eg_sp, s.eg_depth = 1, float(c.strike_point), float(c.strike_depth)
            _pc = p if clav_voice(c) else c         # (a Clavinet's coils are the note's)
            s.n_pk = len(_pc.pickup_points)
            if _pc is c:
                s.pk_q0[:s.n_pk] = [float(q) for q in c.pickup_points]
            s.pk_sign[:s.n_pk] = [float(x) for x in (getattr(_pc, 'pickup_signs', None) or (1.0,) * s.n_pk)]
            s.pk_turns, s.pk_width, s.pk_vel = float(c.pickup_turns), float(c.pickup_width or 0.0), int(bool(c.pickup_velocity))
            s.pk_res_hz, s.pk_qf = float(c.pickup_resonance_hz or 0.0), float(getattr(c, 'pickup_q', 0.0) or 0.0)
            s.lp_hz, s.lp_order = float(c.lowpass_hz or 0.0), float(c.lowpass_order)
            _osh = getattr(c, 'open_strings_hz', None) or ()
            s.n_os = len(_osh)
            s.os_hz[:s.n_os] = [float(o) for o in _osh]
            s.fret_max = float(getattr(c, 'fret_max', 0.0) or 0.0)
            s.pk_sp = float(p.strike_point)                         # (the note's: its fret)
            s.pk_q[:s.n_pk] = [float(q) for q in p.pickup_points]
            # ...touched: the touches a player chooses among, the note's, the killed modes' leak
            s.n_touch = len(getattr(c, 'touches', ()) or ())
            s.touches[:s.n_touch] = [int(n) for n in (getattr(c, 'touches', ()) or ())]
            s.touch0, s.touch = int(c.harmonic_touch or 0), int(p.harmonic_touch or 0)
            s.leak_set = int(c.touch_leak_db is not None)
            s.leak_db, s.leak_dbs = float(c.touch_leak_db or 0.0), float(getattr(c, 'touch_leak_dbs', 0.0) or 0.0)
            if clav_voice(c):
                # (a Clavinet's coil and key-up by the note: nv_voice_init's)
                s.clav, s.cl_sel = 1, _CLAV_SEL[c.clav_pickup]
                s.cl_ref_m, s.cl_ref_hz = float(c.speaking_length_ref_m), float(c.speaking_length_ref_hz)
                s.cl_pow, s.cl_bridge = float(c.speaking_length_power), float(c.pickup_bridge_m)
                s.cl_c0, s.cl_c1 = (float(x) for x in c.pickup_centre_m)
                s.cl_qmax, s.cl_tdb = float(c.pickup_fraction_max), float(c.keyup_thump_db_per_semitone)
                s.cl_nt, s.cl_nk = len(c.keyup_thump_hz), len(c.keyup_string_harmonics)
                s.cl_thump[:s.cl_nt] = [float(x) for x in c.keyup_thump_hz]
                s.cl_kh[:s.cl_nk] = [float(h) for h, _ in c.keyup_string_harmonics]
                s.cl_ka[:s.cl_nk] = [float(a) for _, a in c.keyup_string_harmonics]
                rcm = p.release_click_modes
                s.vk_n = len(rcm)
                s.vk_hz[:s.vk_n] = [float(hz) for hz, _ in rcm]
                s.vk_amp[:s.vk_n] = [float(a) for _, a in rcm]
        if isinstance(p, T.FormantBody):
            s.fbody, s.formant_floor = 1, p.formant_floor
            s.n_fm, s.n_afm, s.n_bt = len(p.formants), len(p.antiformants), len(p.body_trim_db or ())
            for i, row in enumerate(p.formants):
                s.fm[i][:] = [float(x) for x in row]
            for i, row in enumerate(p.antiformants):
                s.afm[i][:] = [float(x) for x in row]
            for i, row in enumerate(p.body_trim_db or ()):
                s.bt[i][:] = [float(x) for x in row]
        if reed_voice(type(p)):
            # a free reed: its geometry and laws (the note's series, its init's), its banks
            s.reed, s.reed_points = 1, int(p.reed_points)
            for f in ('reed_gate', 'reed_edge', 'reed_spread', 'reed_direct', 'reed_scatter'):
                setattr(s, f, float(getattr(p, f)))
            s.reed_gate_oct, s.reed_spread_oct = float(p.reed_gate_per_octave), float(p.reed_spread_per_octave)
            s.reed_scatter_oct = float(p.reed_scatter_per_octave)
            # its upper harmonics late (speech_harmonic_exp: the bandoneon's bloom)
            s.sh_exp = float(getattr(p, 'speech_harmonic_exp', 0.0) or 0.0)
            s.sh_exp_oct = float(getattr(p, 'speech_harmonic_exp_per_octave', 0.0) or 0.0)
            s.sh_cap = int(getattr(p, 'speech_harmonic_cap', None) or 0)
            ser = p._reed_series()              # (this voice's: its key's geometry)
            s.n_reed = len(ser)
            s.reed_s[:len(ser)] = [float(x) for x in ser]
            if _owner(type(p), 'unison_voices') == 'AccordionProperties':
                slope = getattr(p, 'reed_detune_per_octave', None) or (0.0,) * len(p.reed_bank_gain)
                s.n_bank = len(p.reed_bank_gain)
                for i, (g, c, r, o) in enumerate(zip(p.reed_bank_gain, p.reed_detune_cents, p.reed_bank_ratio, slope)):
                    s.bank_g[i], s.bank_cents[i], s.bank_ratio[i], s.bank_oct[i] = float(g), float(c), float(r), float(o)
        if isinstance(p, T.SectionMixin):
            # a section: its players, their vibratos and entries, their desks
            # (section_position_x, less the voice's place: the note's is added)
            n = int(p.section_players)
            s.sect_n, s.sect_vib = n, 1
            s.sect_spread_cents, s.sect_vib_cents = p.section_spread_cents, p.section_vibrato_cents
            s.sect_vib_hz[:] = [float(x) for x in p.section_vibrato_hz]
            s.sect_onset_ms = p.section_onset_ms
            s.sect_ofm = getattr(p, 'unison_onset_fraction_max', 0.25)
            _section_desks(s, p)
    elif s.kind == 5:
        # an electric piano: its pickup, swing, fit and tonebar (the note's
        # layers its init's; the prototype's here)
        c = type(p)
        s.ep_kind = ep_kind(c)
        prm = p._native_flux()[1]
        s.ep_p[:len(prm)] = [float(x) for x in prm]
        s.ep_defl, s.ep_defl_slope = float(c.pickup_deflection), float(c.deflection_register_slope)
        s.ep_defl_power, s.ep_defl_max = float(c.deflection_velocity_power), float(c.pickup_deflection_max)
        s.ep_rho, s.ep_share = float(c.swing_damping), float(c.level_swing_share)
        s.ep_harm, s.ep_terms = int(c.pickup_harmonics), int(c.pickup_layer_terms)
        s.ep_max_hz, s.ep_floor_db = float(c.pickup_max_hz or 0.0), float(c.pickup_floor_db)
        s.tb_coeff, s.tb_power, s.tb_decay = float(c.tonebar_hz_coeff), float(c.tonebar_hz_power), float(c.tonebar_decay_db)
        s.n_tb = len(c.tonebar_gains)
        for i, (r, g) in enumerate(zip(c.tonebar_mode_ratios, c.tonebar_gains)):
            s.tb_ratio[i], s.tb_g[i] = float(r), float(g)
        s.ep_a0 = p._deflection()
        s.n_lay = len(p._layers)
        for i, (k, n, w, ph) in enumerate(p._layers):
            s.ep_n[i], s.ep_w[i] = float(n), float(w)
        for i, r in enumerate(p.mode_ratios):
            s.ep_r[i] = float(r)
        s.n_mp = len(p.mode_ratios)
        for i in range(s.n_mp):
            s.mode_phases[i] = p.mode_phase(i + 1)
    elif s.kind == 6:
        # a Moog: its partials are its panel's (moog_spec); of the voice, a
        # section's vibrato for its one player -- and a formant body's bore,
        # its series (the pluck's comb) for the bore's norm
        if moog_bodied(type(p)):
            s.comb[0] = 0.0
            for h in range(1, int(p.max_harmonic) + 1):
                s.comb[h] = T._pluck_comb(p.plucked_harmonic, p.pluck_dampening, h)
            s.bore_corner_hz, s.bore_order = p.bore_corner_hz, p.bore_order
            s.bell_cutoff_hz, s.bell_order = p.bell_cutoff_hz or 0.0, p.bell_order
            s.bore_norm = p._bore_norm()
            s.fbody, s.formant_floor = 1, p.formant_floor
            s.n_fm, s.n_afm, s.n_bt = len(p.formants), len(p.antiformants), len(p.body_trim_db or ())
            for i, row in enumerate(p.formants):
                s.fm[i][:] = [float(x) for x in row]
            for i, row in enumerate(p.antiformants):
                s.afm[i][:] = [float(x) for x in row]
            for i, row in enumerate(p.body_trim_db or ()):
                s.bt[i][:] = [float(x) for x in row]
        if isinstance(p, T.SectionMixin):
            # ...and a section's desks: the note is its first player, at
            # that player's place (blockrender's em.player 0)
            s.sect_n, s.sect_vib = int(p.section_players), 1
            s.sect_vib_cents = p.section_vibrato_cents
            s.sect_vib_hz[:] = [float(x) for x in p.section_vibrato_hz]
            _section_desks(s, p)
    elif s.kind == 7:
        pass                    # a pulse voice: SynthProperties' alone, its series not read
    elif s.kind == 1:
        if isinstance(p, T.SfxThroatProperties):
            # a throat's pulse: its tilt, mouth and vowel (the note's, nv_note), its breath
            s.throat = 1
            # (the class's: a note's own arrive in its NoteIn)
            k = type(p)
            s.stroke_tilt_db, s.formant_scale, s.formant_morph = (k.stroke_tilt_db, k.stroke_formant_scale,
                                                                  k.stroke_formant_morph)
            s.breath_volume = p.breath_volume
            mb = p.DRUM_MODES_B or ()
            s.n_mb = len(mb)
            for i, row in enumerate(mb):
                s.mb[i][:] = [float(row[0]), float(row[1])]
        # KitDrumProperties' tables, and SynthProperties' unison
        s.unison_gain = p.unison_gain
        s.n_unison = len(p.unison_detune or ())
        for i, x in enumerate(p.unison_detune or ()):
            s.unison_detune[i] = x
        s.n_modes = len(p.DRUM_MODES)
        for i, row in enumerate(p.DRUM_MODES):
            s.modes[i][:] = [float(x) for x in row]
        s.n_click, s.click_per_band = len(p.CLICK_DB), int(p.click_per_band)
        for i, x in enumerate(p.CLICK_DB):
            s.click_db[i] = float(x)
        s.click_hz0, s.click_cal_db, s.click_scatter = p.CLICK_HZ0, p.click_cal_db, p.click_scatter
        s.click_dbs, s.click_stroke_slope, s.stroke_ref_db = p.click_dbs, p.click_stroke_slope, p.stroke_ref_db
        s.slow_share, s.slow_dbs, s.slow_max_hz = p.slow_share, p.slow_dbs, p.slow_max_hz or 0.0
        if isinstance(p, T.NoisyPercussionMixin):
            s.noisy, s.hf_corner_hz, s.hf_order = 1, p.hf_corner_hz, p.hf_order
            s.n_trim = len(p.band_trim_db)
            for i, (f, db) in enumerate(p.band_trim_db):
                s.trim[i][:] = [float(f), float(db)]
            if isinstance(p, T.PlayedAtPitchMixin) and p.band_trim_db:
                s.pap_hz, s.pap_n = float(p.RECORDED_HZ), len(p.DRUM_MODES)
        if isinstance(p, T.MeasuredStrokeProperties):
            s.measured, s.ring_scale, s.mode_scatter_db = 1, p.ring_scale, p.mode_scatter_db
            s.head_jitter, s.wire_jitter, s.jit_sus = p.mode_jitter, p.sustain_jitter, 2
        if isinstance(p, T.TambourineProperties):
            # (the jingles: the measured stroke's, by other names)
            s.measured, s.tamb, s.ring_scale, s.mode_scatter_db = 1, 1, p.jingle_scale, p.jingle_scatter_db
            s.head_jitter, s.wire_jitter, s.jit_sus = p.jingle_jitter, p.sustain_jitter, 2
        if isinstance(p, T.AcousticSnareProperties):
            s.snare, s.fund_dbs, s.head_dbs = 1, p.fund_dbs, p.head_dbs
            s.wire_jitter, s.head_jitter, s.jit_sus = p.wire_jitter, p.sustain_jitter, 1
            if _owner(type(p), 'harmonic_decay') == 'SideStickProperties':
                s.rim_from, s.rim_dbs = int(p.RIM_FROM), p.rim_dbs
    else:
        for f in ('hammer_corner_hz', 'hammer_open_lo', 'hammer_open_slope', 'hammer_register_slope',
                  'hammer_order', 'board_body_gain', 'board_body_hz', 'board_body_width', 'board_high_hz',
                  'board_high_order', 'board_low_hz', 'string_crossfade_semitones', 'aftersound_decay_ratio'):
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
    if s.kind == 2 and pipe_voice(type(p)) and not getattr(p, 'registerable', False):
        s.pps = float(getattr(p, 'partial_phase_spread', 0.0) or 0.0)    # (a blown pipe's: a drone's)
        s.ml_spread = float(getattr(p, 'mode_lock_spread', 0.0) or 0.0)
        s.ml_knee, s.ml_time = float(getattr(p, 'mode_lock_knee', 3.0)), float(getattr(p, 'mode_lock_time', 0.035))
    if s.kind == 4 and noisy_harmonic(type(p)):         # A NOISY HARMONIC VOICE: the roll-off, the trim, its wash
        s.noisy, s.hf_corner_hz, s.hf_order = 1, p.hf_corner_hz, p.hf_order
        s.n_trim = len(p.band_trim_db)
        for i, (f, db) in enumerate(p.band_trim_db):
            s.trim[i][:] = [float(f), float(db)]
        s.chiff_bore = int(_owner(type(p), 'chiff_harmonic_gain') == 'GuitarFretNoiseProperties')
    if s.kind == 4 and measured_series(type(p)):        # A MEASURED SERIES: its table
        s.n_hvt = len(p.mode_gains)
        s.hvt[:s.n_hvt] = [float(x) for x in p.mode_gains]
    elif s.kind == 4 and bore_table(type(p)):           # ...UNDER ITS BORE: each note's table at init
        s.hvt_bore = 1
        s.n_pipe = len(p.mode_gains)
        s.pipe_g[:s.n_pipe] = [float(x) for x in p.mode_gains]
        if p.mode_gains_low is not None:
            s.low_set, s.n_low = 1, len(p.mode_gains_low)
            s.low_g[:s.n_low] = [float(x) for x in p.mode_gains_low]
            s.low_hz[:] = [float(x) for x in p.register_low_hz]
    if s.kind == 2 and heartbeat_voice(type(p)):        # ITS MODES' OWN PHASES (the ECG's)
        s.n_mp = len(p.mode_ratios)
        for i in range(s.n_mp):
            s.mode_phases[i] = p.mode_phase(i + 1)
    fv = fixed_vibrato(type(p))
    if fv:                                      # A FIXED VIBRATO of its own
        s.fv_set, s.fv_cents, s.fv_hz = 1, fv[0], fv[1]
    if not p.pickup_points and p.lowpass_hz:     # A LOW PASS WITH NO PICKUP (series_volume's: a tape's)
        s.lp_hz, s.lp_order = float(p.lowpass_hz), float(p.lowpass_order)
    if _owner(type(p), 'voice_vibrato') == 'MellotronMixin':     # A MELLOTRON's CAPSTAN WOW
        s.wow_set, s.wow_cents, s.wow_hz = 1, float(p.tape_wow_cents), float(p.tape_wow_hz)
    if _owner(type(p), 'voice_vibrato') == 'UkuleleProperties':     # A STRING'S WANDER
        s.sw_set, s.sw_cents = 1, float(p.string_wander_cents)
        s.sw_hz[:] = [float(x) for x in p.string_wander_hz]
    tk = tap_voice(type(p))
    if tk:                                      # A STRUCK VOICE REPEATED: its taps, gongs, strokes
        c = type(p)
        taps = c.chirp_taps if tk == 1 else c.ring_taps
        s.tap_kind, s.n_tap = tk, len(taps)
        s.tap_t[:len(taps)] = [float(x) for x in taps]
        s.tap_gain = float(c.chirp_gain if tk == 1 else c.ring_gain)
        if tk == 2:
            s.tap_jit, s.tap_ldb = float(c.ring_jitter_s), float(c.ring_level_db)
            s.n_gong = len(c.GONG)
            s.gong[:s.n_gong] = [int(x) for x in c.GONG]
        s.tap_drop = int(bool(getattr(c, 'unison_drop_late', False)))
        s.sect_ofm = float(getattr(c, 'unison_onset_fraction_max', 0.25))
    s.board_kind = _board_kind(type(p)) if s.kind == 0 else 0
    if s.kind == 0 and s.board_kind == 1:
        s.board_low_order = p.board_low_order
    elif s.kind == 0 and s.board_kind == 2:
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
        if name in k.__dict__ and not (k.__name__ == 'SampledBreak' and name in _BREAK_CUT):
            return k.__name__
    return None


# A SAMPLED BREAK'S (tonelib.SampledBreak: a voice through a sampler) two
# methods: the voice's own, nothing at or above the moved Nyquist
# (VoiceSnap.nyquist), so the voice under it decides
_BREAK_CUT = ('harmonic_volume', 'chiff_harmonic_gain')


def sung_voice(cls):
    """Whether cls is a sung voice whose body the engine draws per note
    (tonelib._VocalBody: VoiceInit.vbody) -- its tract, its singer's formant,
    its formant tuning; not a render of the source alone (TUNING_VOCAL_FLAT)."""
    import tonelib as T
    v = getattr(T, '_VocalBody', None)
    if any(os.environ.get(e) for e in ('TUNING_LYRIC_LANG', 'TUNING_VOCALISE', 'TUNING_VOICE_PARTS')):
        return False                    # (a sung text, a vocalise, declared parts: Python's)
    ok = (v is not None and issubclass(cls, v) and not cls.vocal_flat
          and _owner(cls, '_sung_formants') == '_VocalBody' and _owner(cls, '_formant_tune') == '_VocalBody'
          and len(cls.formants or ()) <= 16)
    if ok:
        voice_bodies(lib())
    return ok


_VB_SET = [False]


def voice_bodies(d):
    """tonelib's voice parts into the engine (nv_voice_bodies_set): VOICE_BODIES'
    names, ratios and clusters, _NOT_A_VOICE's strings -- once, the first time
    a sung class is the engine's (the library loads before tonelib has them)."""
    import tonelib as T
    if _VB_SET[0] or d is None:
        return 1
    _VB_SET[0] = True
    names = list(T.VOICE_BODIES)
    blob = b"".join(os.fsencode(x) + b"\0" for x in names + list(T._NOT_A_VOICE))
    r = (C * len(names))(*[float(T.VOICE_BODIES[x]) for x in names])
    c = (C * len(names))(*[float(T.VOICE_CLUSTER.get(x, 1.0)) for x in names])
    return d.nv_voice_bodies_set(len(names), blob, r, c, len(T._NOT_A_VOICE))


def init_supported(cls):
    """Whether native/voice.c's nv_voice_init builds this class's voice: a
    piano constructor (SynthProperties', the grand's, the honky-tonk's) or a
    kit drum's (SynthProperties' alone), the base class's placing and laws,
    and none of the branches not ported."""
    import tonelib as T
    if kit_drum(cls):
        # (a dynamic B: the steel's law, or a pipe's -- the piano's polynomial, borrowed)
        if not T.hrtf or (cls.inharmonicity_dynamic and kit_drum(cls) != 4 and not pipe_voice(cls)):
            return False
        # (and [RND]'s, RandomStrike: its four draws the caller's, VoiceInit.rnd_draws)
        if any(k.__name__ not in ('SynthProperties', 'object', 'RandomStrike', 'MellotronMixin') for k in cls.__mro__
               if '__init__' in k.__dict__ and not (k.__name__ == 'ElectricPianoProperties' and ep_voice(cls))
               and not (k.__name__ in ('ElectricGuitarProperties', 'GuitarHarmonicsProperties') and electric_voice(cls))
               and not (k.__name__ == 'ClavinetProperties' and clav_voice(cls))
               and not (k.__name__ in _STOPPED_INITS and stopped_voice(cls) and harmonic_voice(cls))
               and not (k.__name__ == '_VocalBody' and sung_voice(cls))):
            return False
        if any(_owner(cls, n) != o for n, o in _BASE_OWN.items() if n != 'inharmonicity_coefficient_func'):
            return False
        c = cls
        # (the stroke's chiff, jitter, bloom, wobble and trim are the constructor's)
        return len(c.strike_volume_trim_db or ()) <= 16
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
    return not ((c.strike_noise_slope and c.chiff_volume)
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
        st, rst = random.getstate(), T.RND_STREAM.getstate()
        try:
            proto = cls(261.6, 0.0, 0.5, 1.0)
        finally:
            random.setstate(st)
            T.RND_STREAM.setstate(rst)
        tmpl = snapshot(proto)
        if tmpl is None:
            _CLASS[cls] = False
            return None
        c = VoiceInit()
        for f, _ in VoiceInit._fields_:
            if isinstance(getattr(cls, f, None), property):
                setattr(c, f, getattr(proto, f))       # (a throat's breath: the prototype's)
            elif getattr(cls, f, None) is not None:
                setattr(c, f, getattr(cls, f) if not isinstance(getattr(cls, f), bool) else int(getattr(cls, f)))
        if not kit_drum(cls) or pipe_voice(cls):
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
        c.kind = kit_drum(cls)
        if issubclass(cls, T.RandomStrike):
            c.rnd = 1
            c.rnd_level_db, c.rnd_effort_db = cls.rnd_level_db, cls.rnd_effort_db
            c.rnd_cents, c.rnd_timing_s = cls.rnd_cents, cls.rnd_timing_s
        c.key_jitter = int(c.kind == 0)
        c.b_law = _b_law(cls) if c.kind == 0 else 0
        if c.kind == 4 and cls.inharmonicity_dynamic:
            c.b_law = 3                         # (the steel's law)
            c.law_k, c.law_p = cls.inharmonicity_law
            if _owner(cls, 'inharmonicity_coefficient_for_frequency') == 'HammeredDulcimerProperties':
                c.b_law = 4                     # (...under the dulcimer's bass bridge, its own)
                c.bb_hz, c.bb_B = float(cls.bass_bridge_hz), float(cls.bass_bridge_B)
        if sung_voice(cls):
            # A SUNG BODY (_VocalBody): the class's vowel, its body's draw; the
            # note's part (the file's, or the tone's own voice_part) and
            # tessitura are its own (NoteIn.part, sung_hz)
            c.vbody = 1
            c.n_vb = len(cls.formants)
            for i, row in enumerate(cls.formants):
                c.vb_fm[i][:] = [float(x) for x in row]
            c.vb_tract, c.vb_sigma, c.vb_mb = float(cls.tract_ratio), float(cls.tract_sigma), float(cls.mixture_broadening)
            c.vb_xhz, c.vb_xoct = float(cls.voice_crossover_hz), float(cls.voice_crossover_oct)
            c.vb_ftop, c.vb_sfhz = float(cls.female_top_formant), float(cls.singers_formant_hz)
            vp = getattr(cls, 'voice_part', None)
            if vp:
                c.part_set = 1
                c.part_ratio, c.part_cluster = float(T.VOICE_BODIES[vp]), float(T.VOICE_CLUSTER.get(vp, 1.0))
        os_ = getattr(cls, 'open_strings', None) or ()
        if stopped_voice(cls) and getattr(cls, 'pluck_open', None) and os_:
            c.n_open = len(os_)                 # (the note's pluck point: nv_voice_init's)
            c.open_st[:c.n_open] = [float(o) for o in os_]
        else:
            c.pluck_open = 0.0
        if getattr(cls, 'course_keys', None) is not None:
            c.has_course = 1                    # (the register's strings: its courses' keys alone)
            for kk in cls.course_keys:
                if 0 <= int(kk) < 128:
                    c.course[int(kk)] = 1
        # (none: the note's is the valve's, as blockrender's setup takes it)
        c.attack_time = cls.attack_time if cls.attack_time is not None else cls.chiff_max_valve_time
        vt = sorted(cls.strike_volume_trim_db or ())
        c.n_vtrim = len(vt)
        for i, (v, db) in enumerate(vt):
            c.vtrim_v[i], c.vtrim_db[i] = float(v), float(db)
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
        t.radiation_distance = float(got[2].radiation_distance)     # (the room's listener distance too)
        got[3] = room
    return got


def voice(cls, frequency, channel_pan, attack_volume, channel_volume, effort=0.0, state=None, seat=0.0, rnd=None,
          sung=None):
    """cls(frequency, channel_pan, attack_volume, channel_volume, effort) in C:
    (VoiceSnap, VoiceNote), or None where the class is not supported. state:
    a PyRandomState for the global stream, drawn from as the constructor
    draws (None: the snapshot alone, the stream untouched). seat: a seat
    inside the instrument (a kit's drum), placed as blockrender places it.
    rnd: an [RND] voice's four draws (its props' rnd_draws). sung: a sung
    voice's (tessitura Hz, declared part: 1 + its VOICE_BODIES index, 0 none)."""
    import tonelib as T
    d = lib()
    got = _class(cls) if d is not None else None
    if got is None:
        return None
    c, tmpl = VoiceInit.from_buffer_copy(got[0]), got[1]        # (the class's own, untouched by this note)
    lo, hi = getattr(cls, 'string_detune_range', (0.0, 0.0))     # (a drum has no strings)
    if '__init__' in getattr(T, 'HonkyTonkProperties', object).__dict__ and issubclass(cls, T.HonkyTonkProperties):
        lo, hi = lo * T.honky_detune, hi * T.honky_detune
    c.detune_lo, c.detune_hi = lo, hi
    c.fixed_touch = int(bool(T.FIXED_TOUCH))
    c.soft_pedal_down = int(bool(T.soft_pedal_down))
    if seat:
        c.seat_x = c.listener_distance * math.tan(T.stage_angle(seat))
    if rnd is not None:
        c.rnd_draws[:] = [float(x) for x in rnd]
    if c.vbody and sung is not None:
        c.sung_hz = float(sung[0])
        pr, pc = C(), C()
        if sung[1] and d.nv_voice_part(int(sung[1]), ctypes.byref(pr), ctypes.byref(pc)):
            c.part_set, c.part_ratio, c.part_cluster = 1, pr.value, pc.value
    s, o = VoiceSnap(), VoiceNote()
    d.nv_voice_init(ctypes.byref(c), ctypes.byref(tmpl), float(frequency), float(channel_pan),
                    float(attack_volume), float(channel_volume), float(effort),
                    ctypes.byref(state) if state is not None else None, ctypes.byref(s), ctypes.byref(o))
    return s, o


def set_random_state(st):
    """The global random stream set to PyRandomState st."""
    import random
    v = random.getstate()[0]
    random.setstate((v, tuple(st.mt[:]) + (int(st.i),), float(st.gauss_next) if st.has_gauss else None))


def random_state():
    """The global random stream as a PyRandomState."""
    import random
    _, st, g = random.getstate()
    r = PyRandomState()
    r.mt[:] = st[:624]
    r.i = st[624]
    r.has_gauss, r.gauss_next = int(g is not None), (g if g is not None else 0.0)
    return r


_NOTE = {}
# a class attribute that, set, means a note of the class takes a path the
# engine does not have (blockrender plays it): the tone's extras
# (_tone_native), the knock's (_strike_native), the note setup's
_NOTE_OFF = ('bloom_seconds', 'speech_harmonic_exp', 'speech_harmonic_exp_per_octave', 'wind_skirt_always',
             'unison_spans_part', 'unison_drop_late', 'strike_phase_spread', 'partial_phase_spread',
             'stroke_scatter', 'string_choirs', 'unison_shares_phase', 'directivity_radius', 'strike_in_s',
             'jitter_by_partial', 'mode_lock_spread', 'played_backwards', 'fold_restrike',
             'strike_flam_rate', 'strike_flam_times', 'strike_flam_people', 'strike_noise_tail',
             'strike_noise_layers', 'transposed_from_hz', 'one_shot', 'gate_time',
             'course_keys', 'key_bridge', 'bridge_partner', 'buff_choirs',
             'register_knock_tilt', 'register_knock_profile')
_NOTE_ABSENT = ('pre_pluck_s',)


class OrganPipe(ctypes.Structure):
    """native/nv.h's OrganPipe: a class an organ's ranks draw on."""
    _fields_ = ([('init', VoiceInit), ('tmpl', VoiceSnap)]
                + [(f, I) for f in ('attack_set', 'release_set', 'chiff_width_set', 'sh_cap', 'rank_is_pipe',
                                    'rank_speech', 'truncate')]
                + [(f, C) for f in ('attack_time', 'release_valve_time', 'chiff_max_valve_time', 'speech_cycles',
                                    'chiff_width', 'chiff_width_cycles', 'chiff_volume', 'chiff_cycle',
                                    'sustain_level', 'speech_harmonic_exp', 'speech_harmonic_exp_per_octave',
                                    'pipe_ceiling_hz')]
                + [('push_band_set', I), ('n_push_reg', I)]
                + [(f, C) for f in ('push_gain', 'push_rise_s', 'push_dbs', 'push_settle_db', 'push_tilt',
                                    'push_tilt_oct')]
                + [('push_band', C * 2), ('push_reg', (C * 2) * 8)]
                + [('n_pp', I), ('pp_partials', I), ('pp_hz', C * 8), ('pp_s', C * 8), ('pp_db', C),
                   ('pp_snap_s', C)])


class OrganRank(ctypes.Structure):
    """native/nv.h's OrganRank: one of stop_ranks."""
    _fields_ = [('n_ratio', I), ('compound', I), ('ratio', C * 8), ('gain', C), ('spec', I), ('pipe', I),
                ('lo', I), ('hi', I), ('sp_off', C), ('sp_split', C), ('n_comp', I), ('comp_n', I * 64),
                ('comp_hz', C * 64), ('comp_r', (C * 8) * 64), ('rel_band', (C * 3) * 128), ('detune', C * 128),
                ('perc', I), ('contact', C * 128), ('keylen', I), ('only_drawn', I), ('no_leak', I),
                ('stiff', C * 128), ('choir', ctypes.c_char * 16), ('beat', I), ('key', ctypes.c_char * 64)]


class OrganSpec(ctypes.Structure):
    """native/nv.h's OrganSpec: a registered organ's pipes and ranks."""
    _fields_ = ([('n_pipe', I), ('n_rank', I), ('spiral', I), ('own_pitch', I), ('pipe', OrganPipe * 24),
                ('rank', OrganRank * 32), ('spiral_m', C), ('spiral_phase', C), ('drift_m', C),
                ('spatial_default', C * 2), ('pipe_scale_divisor', C), ('sound_speed', C),
                ('mode_lock_spread', C), ('mode_lock_knee', C), ('mode_lock_time', C),
                ('n_wccs', I), ('wccs', I * 4), ('default_stops', I), ('n_order', I), ('order', I * 32), ('swells', I),
                ('family', I), ('swell_law', C * 4),
                ('wind', I), ('trem_rank', I), ('has_ra', I)]
                + [(f, C) for f in ('wsc', 'trem_class_depth', 'wander_rms', 'wa', 'wgain', 'ra', 'reg_restore',
                                    'sag_max', 'sag_per_unit', 'c1', 'c2', 'g', 'trem_hz', 'trem_depth', 'tdecay',
                                    'unit_hz', 'draw_exp', 'blk_s')]
                + [('fam_a', C * 32), ('fam_b', C * 32), ('expr_rank', I), ('perc_rank', I), ('htrem_rank', I),
                   ('expr_tilt', C), ('perc_attack_s', C), ('afm', C), ('pipe_radius', I), ('wheel_trem', C),
                   ('wtrem_hz', C), ('htrem_depth', C), ('htrem_hz', C), ('wtrem_stereo', I),
                   ('wtrem_scatter', C), ('snd_mask', I), ('n_cn', I), ('leak', I), ('cn_hz', C * 16),
                   ('cn_db', C * 16), ('cn_dbs', C), ('leak_db', C), ('phase_spread', C), ('contact_on', I),
                   ('beat_lo', C), ('beat_hi', C), ('n_choir', I), ('choir_pipe', I * 8), ('choir_bridge', I * 8),
                   ('choir_beat', I * 8), ('n_buff', I), ('buff', (I * 2) * 8), ('rank_choir', I * 32),
                   ('choir_ratio', C * 8), ('cross', C), ('choir_cents', (C * 128) * 8),
                   ('choir_stiff', (C * 128) * 8), ('choir_bname', (ctypes.c_char * 16) * 8),
                   ('siren_up', I)])


_ORGAN = {}

# WHAT AN ORGAN NOTE IN C DOES NOT DO (the Python's, where a class asks):
# the wind's skirt, unisons sharing a phase, feedback
_ORGAN_OFF = ('wind_skirt_always', 'unison_shares_phase', 'feedback_harmonic')


def siren_host(cls):
    """Helmholtz's double siren (tonelib.HelmholtzSirenProperties): a mode set
    (kind 2) whose rows of holes are registered ranks, its rotor fed by air,
    its upper disc's ranks on the crank's row (nvrender's)."""
    return (getattr(cls, 'siren_rotor', None) == 'helmholtz' and getattr(cls, 'registerable', False)
            and kit_drum(cls) == 2 and len(getattr(cls, 'stop_ranks', ())) <= 32)


def organ(cls):
    """native/nv.h's OrganSpec for a registered organ cls (its stop_ranks'
    pipes and ranks), or None where its notes are not C's: made once."""
    import tonelib as T
    got = _ORGAN.get(cls)
    if got is not None:
        return got or None
    _ORGAN[cls] = False
    if (not getattr(cls, 'registerable', False)
            or not (pipe_voice(cls) or tonewheel_voice(cls) or harmonic_voice(cls) or hit_voice(cls)
                    or siren_host(cls))
            or _class(cls) is None):
        return None
    if any(getattr(cls, a, None) for a in _ORGAN_OFF):
        return None
    p = _class(cls)[2]
    o = OrganSpec()
    pipes = [cls]

    def pipe_of(k):
        rk = k if k is cls else T.rank_spectrum(k)
        if rk not in pipes:
            if len(pipes) >= 24:
                raise ValueError
            pipes.append(rk)
        return pipes.index(rk)

    def protos(i):
        return p if pipes[i] is cls else _class(pipes[i])[2]
    try:
        ranks = list(p.stop_ranks)
        if len(ranks) > 32:
            return None
        for i, (key, ratio, gain, *rest) in enumerate(ranks):
            r = o.rank[i]
            spec = rest[0] if rest else None
            if len(rest) > 1 and rest[1]:
                return None                         # (a flue-dynamic B on a rank)
            pipe = rest[2] if len(rest) > 2 else None
            kr = rest[3] if len(rest) > 3 else None
            if pipe is not None and getattr(pipe, 'rank_only_when_drawn', False):
                return None
            r.only_drawn = int(spec is not None and bool(getattr(spec, 'rank_only_when_drawn', False)))
            r.keylen, r.no_leak = len(key), int(spec is not None)
            if len(key.encode()) >= 64:
                return None
            r.key = key.encode()                    # (every stop's name, a pipeless one's too)
            r.gain = float(gain)
            r.lo, r.hi = (int(kr[0]), int(kr[1])) if kr is not None else (0, 127)
            if ratio is None:
                r.n_ratio = 0
                continue
            if isinstance(ratio, (list, tuple)):
                r.compound, r.n_ratio = 1, len(ratio)
                r.ratio[:len(ratio)] = [float(x) for x in ratio]
                comp = (getattr(p, 'mixture_compositions', None) or {}).get(key)
                if comp and (len(comp) > 64 or any(len(rs) > 8 for _, rs in comp)):
                    return None
                if comp:
                    r.n_comp = len(comp)
                    for q, (hz, rs) in enumerate(comp):
                        r.comp_hz[q], r.comp_n[q] = float(hz), len(rs)
                        r.comp_r[q][:len(rs)] = [float(x) for x in rs]
            else:
                r.n_ratio, r.ratio[0] = 1, float(ratio)
            # (a choir at another footage with no spectrum of its own is its own
            # string, tonelib.own_string: not C's)
            if getattr(p, 'string_choirs', None) and spec is None and ratio != 1.0:
                return None
            r.spec = pipe_of(spec) if spec is not None else -1
            r.pipe = pipe_of(pipe) if pipe is not None else -1
            if any(_class(pipes[q]) is None for q in (r.spec, r.pipe) if q >= 0):
                return None
            off, split = p.rank_spatial.get(key, p.rank_spatial_default) if getattr(p, 'spiral_spatial', False) \
                else (0.0, 0.0)
            r.sp_off, r.sp_split = float(off), float(split)
            # its speech class, as _note_stops resolves it, and its release band by band
            spv = protos(r.spec) if r.spec >= 0 else None
            rp = protos(r.pipe) if r.pipe >= 0 else (spv if (spv is not None and getattr(spv, 'rank_is_pipe', False))
                                                      else p)
            own = getattr(p, 'rank_speech_own_pitch', False)
            sc = rp if rp is not p else (spv if (own and spv is not None and getattr(spv, 'rank_speech', False)) else p)
            for nt in range(128):
                r.rel_band[nt][:] = [T.release_band_scale(sc, key, nt, m) for m in (2, 5, 9)]
                r.detune[nt] = T.rank_detune_cents(cls, key, nt)
                r.contact[nt] = T.contact_offset_s(cls, key, nt)
            # its choir's wire (a harpsichord's): its stiffness, its partials' scatter
            cho = T.choir_of(cls, key)
            for nt in range(128):
                r.stiff[nt] = T.choir_stiffness(cls, cho, nt) if cho else 1.0
            bc = (getattr(cls, 'buff_choirs', None) or {}).get(cho, cho) if cho else None
            if bc is not None and len(bc.encode()) >= 16:
                return None
            r.choir = (bc or '').encode()
            r.beat = int(bool(cho and getattr(cls, 'choir_beat_hz', None) and bc != 'A'))
            r.perc = int(key in (getattr(cls, 'percussion_ranks', ()) or ()))
            if key in (getattr(cls, 'siren_upper', ()) or ()):
                o.siren_up |= 1 << i                # (the upper disc's: the crank's row)
        o.n_rank = len(ranks)
        for i, k in enumerate(pipes):
            v = _class(k)
            q = o.pipe[i]
            q.init, q.tmpl = v[0], v[1]
            pr = v[2]
            if (v[0].pitch_jitter_cents or v[0].timing_jitter_seconds
                    or (getattr(pr, 'bellows_push_gain', 0.0) and not getattr(pr, 'bellows_push_every_note', False))):
                return None
            q.attack_set, q.attack_time = int(pr.attack_time is not None), pr.attack_time or 0.0
            q.release_set, q.release_valve_time = int(pr.release_valve_time is not None), pr.release_valve_time or 0.0
            q.chiff_max_valve_time, q.speech_cycles = pr.chiff_max_valve_time, pr.speech_cycles
            q.chiff_width_set, q.chiff_width = int(pr.chiff_width is not None), pr.chiff_width or 0.0
            q.chiff_width_cycles = pr.chiff_width_cycles
            q.chiff_volume, q.chiff_cycle, q.sustain_level = pr.chiff_volume, pr.chiff_cycle, pr.sustain_level
            q.speech_harmonic_exp = getattr(pr, 'speech_harmonic_exp', 0.0)
            q.speech_harmonic_exp_per_octave = getattr(pr, 'speech_harmonic_exp_per_octave', 0.0)
            q.sh_cap = int(getattr(pr, 'speech_harmonic_cap', None) or 0)
            q.rank_is_pipe = int(bool(getattr(pr, 'rank_is_pipe', False)))
            q.rank_speech = int(bool(getattr(pr, 'rank_speech', False)))
            q.pipe_ceiling_hz = getattr(pr, 'pipe_ceiling_hz', None) or 0.0
            q.truncate = int(getattr(pr, 'pipe_break_mode', 'fold') == 'truncate')
            q.push_gain = float(getattr(pr, 'bellows_push_gain', 0.0) or 0.0)
            if q.push_gain:
                q.push_rise_s, q.push_dbs = float(pr.bellows_push_rise_s), float(pr.bellows_push_dbs)
                q.push_settle_db = float(getattr(pr, 'bellows_push_settle_db', -20.0))
                q.push_tilt = float(getattr(pr, 'bellows_push_tilt', 0.0))
                q.push_tilt_oct = float(getattr(pr, 'bellows_push_tilt_per_octave', 0.0))
                band = getattr(pr, 'bellows_push_band', None)
                if band:
                    q.push_band_set, q.push_band[:] = 1, [float(x) for x in band]
                reg = getattr(pr, 'bellows_push_register', None) or ()
                if len(reg) > 8:
                    return None
                q.n_push_reg = len(reg)
                for j, (f, db) in enumerate(reg):
                    q.push_reg[j][:] = [float(f), float(db)]
            if hasattr(pr, 'pre_pluck_s'):         # the quill's catch (HarpsiBase.pre_pluck_s's, as it is)
                if type(pr).pre_pluck_s is not T.HarpsiBase.pre_pluck_s or not 1 <= len(pr.pre_pluck_points) <= 8:
                    return None
                q.n_pp, q.pp_partials = len(pr.pre_pluck_points), int(pr.pre_pluck_partials)
                q.pp_hz[:q.n_pp] = [float(a) for a, _ in pr.pre_pluck_points]
                q.pp_s[:q.n_pp] = [float(b) for _, b in pr.pre_pluck_points]
                q.pp_db, q.pp_snap_s = float(pr.pre_pluck_db), float(pr.pre_pluck_snap_s)
        o.n_pipe = len(pipes)
    except ValueError:
        return None
    bh = getattr(p, 'choir_beat_hz', None)
    if bh:
        o.beat_lo, o.beat_hi = float(bh[0]), float(bh[1])
    # ITS CHOIRS, as register.Strings builds their strings
    chs = getattr(p, 'string_choirs', None) or ()
    o.n_choir = len(chs)
    o.cross = float(getattr(p, 'cross_bridge_coupling', 1.0))
    if chs:
        names = [c[0] for c in chs]
        cb = getattr(p, 'choir_bridge', None) or {}
        bc = getattr(p, 'buff_choirs', None) or {}
        buffs = [(names.index(b), names.index(a)) for b, a in bc.items() if b in names and a in names]
        if len(chs) > 8 or len(buffs) > 8:
            return None
        try:
            for ci, (cname, ratio, ccls) in enumerate(chs):
                if ccls is None and ratio != 1.0:
                    return None                     # (the host's string at another footage: own_string)
                o.choir_pipe[ci] = pipe_of(ccls) if ccls is not None else -1
                o.choir_ratio[ci] = float(ratio)
                o.choir_bridge[ci] = int(cb.get(cname, 0))
                bn = bc.get(cname, cname)
                if len(bn.encode()) >= 16:
                    return None
                o.choir_bname[ci].value = bn.encode()
                o.choir_beat[ci] = int(bool(cname and bh and bn != 'A'))
                for key in range(128):
                    o.choir_cents[ci][key] = T.choir_cents(cls, cname, key) if cname else 0.0
                    o.choir_stiff[ci][key] = T.choir_stiffness(cls, cname, key) if cname else 1.0
        except ValueError:
            return None
        if len(pipes) != o.n_pipe:
            return None                         # (a choir's class not among the ranks' pipes)
        o.n_buff = len(buffs)
        for q, (b, a) in enumerate(buffs):
            o.buff[q][:] = [b, a]
        rc = getattr(p, 'rank_choirs', None) or {}
        for i, r in enumerate(ranks):
            nm = rc.get(r[0], r[0])
            o.rank_choir[i] = names.index(nm) if nm in names else -1
    o.spiral = int(bool(getattr(p, 'spiral_spatial', False)))
    o.own_pitch = int(bool(getattr(p, 'rank_speech_own_pitch', False)))
    if o.spiral:
        o.spiral_m, o.spiral_phase, o.drift_m = p.spiral_m, p.spiral_phase, p.drift_m
    o.pipe_radius = int(hasattr(cls, 'pipe_radius'))
    if o.pipe_radius:
        o.pipe_scale_divisor = p.pipe_scale_divisor
    o.sound_speed = p.sound_speed
    o.mode_lock_spread = getattr(p, 'mode_lock_spread', 0.0)
    o.mode_lock_knee, o.mode_lock_time = p.mode_lock_knee, p.mode_lock_time
    # ITS REGISTRATION (registration_blocks')
    import blockrender as BR
    wccs = tuple(getattr(p, 'stop_word_ccs', (11, 43)))
    keys = [r[0] for r in ranks]
    order = getattr(p, 'crescendo_order', keys)
    if len(wccs) > 4 or len(order) > 32 or any(k not in keys for k in order) or len(set(keys)) != len(keys):
        return None
    o.n_wccs = len(wccs)
    o.wccs[:len(wccs)] = list(wccs)
    o.default_stops = int(getattr(p, 'default_stops', 1))
    o.n_order = len(order)
    o.order[:len(order)] = [keys.index(k) for k in order]
    o.swells = int(wccs[0] == 11)
    o.swell_law[:] = [float(p.swell_floor), float(p.swell_gain_power), float(p.swell_hf_max),
                      float(p.swell_hf_ref_hz)]
    o.family = _FAMILIES.setdefault(BR.organ_family(cls), len(_FAMILIES))
    # ITS CHEST'S WIND (_prep_chest_wind's: a pipe organ's, wind.py's constants)
    o.trem_rank = keys.index('tremulant') if 'tremulant' in keys else -1
    # A REED ORGAN'S EFFECT STOPS (the harmonium's Expression, Percussion, Tremolo)
    o.expr_rank = keys.index('expression') if 'expression' in keys else -1
    o.perc_rank = keys.index('percussion') if 'percussion' in keys else -1
    o.htrem_rank = keys.index('tremolo') if 'tremolo' in keys else -1
    o.expr_tilt = T.HARMONIUM_EXPRESSION_TILT
    o.perc_attack_s = float(getattr(cls, 'percussion_attack_s', 0.0) or 0.0)
    o.afm = float(getattr(cls, 'attack_fraction_max', 0.45))
    o.wheel_trem = float(getattr(cls, 'tremolo_depth', 0.0) or 0.0)
    o.wtrem_hz = float(getattr(cls, 'tremolo_hz', 0.0) or 0.0)
    o.wtrem_stereo = int(bool(getattr(cls, 'tremolo_stereo', False)))
    o.htrem_depth = float(getattr(cls, 'stop_tremolo_depth', 0.0) or 0.0)
    o.htrem_hz = float(getattr(cls, 'stop_tremolo_hz', 0.0) or 0.0)
    o.wtrem_scatter = float(getattr(cls, 'tremolo_scatter', 0.0) or 0.0)
    cn = getattr(cls, 'contact_noise_db', ()) or ()
    o.n_cn = len(cn)
    for j, (hz, db) in enumerate(cn):
        o.cn_hz[j], o.cn_db[j] = float(hz), float(db)
    o.cn_dbs = float(getattr(cls, 'contact_noise_dbs', 0.0) or 0.0)
    lk = getattr(cls, 'drawbar_leak_db', None)
    o.leak, o.leak_db = int(lk is not None), float(lk or 0.0)
    o.phase_spread = float(getattr(cls, 'partial_phase_spread', 0.0) or 0.0)
    o.contact_on = int(bool(getattr(cls, 'contact_spread_s', 0.0) or getattr(cls, 'jack_offset_ms', None)))
    _sc = T.sound_controls_of(cls)
    o.snd_mask = (1 if 'attack' in _sc else 0) | (2 if 'release' in _sc else 0) | (4 if 'decay' in _sc else 0)
    o.trem_class_depth = float(getattr(cls, 'tremulant_depth', 0.0) or 0.0)
    if getattr(cls, 'wind_skirt_db', None) is not None and getattr(cls, 'wind_pitch_exp', 0.0):
        import wind as WND
        o.wind = 1
        o.wsc = float(BR.wind_scale_for(cls))
        wd = WND.Wind(cls, BR.BLK / BR.SR, seed=0, scale=o.wsc, wander_scale=(1.0 if o.wsc else 0.0))
        o.wander_rms, o.wa, o.wgain = wd.wander_rms, wd.wa, wd.wgain
        o.has_ra, o.ra = int(wd.ra is not None), wd.ra or 0.0
        o.reg_restore, o.sag_max, o.sag_per_unit = wd.reg_restore, wd.sag_max, wd.sag_per_unit
        o.c1, o.c2, o.g = wd.c1, wd.c2, wd.g
        o.trem_hz, o.trem_depth, o.tdecay = wd.trem_hz, wd.trem_depth, wd.tdecay
        o.unit_hz, o.draw_exp, o.blk_s = WND.UNIT_HZ, WND.DRAW_EXP, wd.blk_s
        if wd.SUB != 8:
            return None
        for i, r in enumerate(ranks):
            if r[1] is None:
                continue
            wc = T.rank_wind_class(cls, r)
            o.fam_a[i], o.fam_b[i] = float(wc.wind_pitch_exp), float(wc.wind_level_exp)
    _ORGAN[cls] = o
    return o


_FAMILIES = {}              # organ_family's name -> its id (OrganSpec.family)


def forget():
    """Every per-class table worked out so far (_CLASS, _NOTE, _ORGAN, _MOOG,
    _SL_CLS) let go, made again at the next use: for a class whose attributes
    were changed while running -- the selftest's, which turn a voice's
    constants and render again. A render's own classes never change under it."""
    for d in (_CLASS, _NOTE, _ORGAN, _MOOG, _SL_CLS):
        d.clear()


_SL_CLS = {}         # a struck layer's class, by the class it is under (native_export's sl_idx)


def note_class(cls):
    """native/engine.cpp's NoteClass for cls, or None where its notes are not
    the engine's: made once, its template's room kept current."""
    import tonelib as T
    import blockrender as BR
    got = _NOTE.get(cls)
    drum = kit_drum(cls)
    if got is None:
        v = _class(cls)
        # (a kit drum's one-shot hold is the engine's, a snare's partials'
        # jitter and signs, a cymbal's bloom, a hand drum's scatter, a
        # gate -- closing the strike's noise with it, not its layers -- and
        # a tape played backwards)
        def drum_has(a):
            if a in ('one_shot', 'jitter_by_partial', 'strike_phase_spread', 'bloom_seconds', 'stroke_scatter',
                     'gate_time', 'played_backwards', 'strike_noise_tail', 'fold_restrike'):
                return True
            # ...a machine's burst train, and up to 32 layers (a Simmons: 21)
            # ...a crowd's bursts through the note (no record's, no exponential levels)
            if a == 'strike_in_s':              # (a drone's strike-in: the engine's attack)
                return True
            if a == 'transposed_from_hz':       # (a kit's sound on a keyboard: the engine's _XP)
                return True
            if a == 'unison_spans_part':        # (a chanter's: its unison none, the drones notes)
                return _owner(cls, 'unison_voices') == 'BagpipeProperties'
            if a == 'unison_drop_late':         # (a telephone's strokes past the note: tone.c's)
                return bool(tap_voice(cls))
            if a == 'strike_flam_rate':         # (a crowd's, or a record's clicks: their table at most 8)
                return (int(getattr(cls, 'strike_flam', 0) or 0) <= 1
                        and len(getattr(cls, 'strike_flam_levels', ()) or ()) <= 8)
            if a == 'strike_flam_people':       # (a few people: their claps and their palms' ring)
                pp = getattr(cls, 'strike_flam_people', None) or ()
                pk = getattr(cls, 'strike_flam_people_peak', None)
                return (len(pp) == 5 and (pk is None or len(pk) == 4)
                        and not getattr(cls, 'strike_flam_record', False)
                        and not (getattr(cls, 'strike_flam_rate', 0.0) or 0.0))
            if a == 'strike_flam_times':
                ft = getattr(cls, 'strike_flam_times', None) or ()
                return len(ft) <= 64 and all(len(b) in (2, 3) for b in ft)
            if a == 'strike_noise_layers':
                ly = getattr(cls, 'strike_noise_layers', ()) or ()
                return len(ly) <= 32 and all(len(l[0]) <= 32 for l in ly)
            return False
        # (an organ's speech and mode lock are its ranks', organ.c's)
        org_has = (lambda a: a in ('speech_harmonic_exp', 'mode_lock_spread', 'partial_phase_spread',
                                   'string_choirs', 'buff_choirs', 'directivity_radius', 'pre_pluck_s')) \
            if getattr(cls, 'registerable', False) else \
            (lambda a: a in ('speech_harmonic_exp', 'speech_harmonic_exp_per_octave', 'wind_skirt_always')) \
            if reed_voice(cls) and getattr(cls, 'wind_attack_db', None) is None \
            else (lambda a: a in ('mode_lock_spread', 'directivity_radius', 'wind_skirt_always',
                                  'partial_phase_spread')) if _blown(cls) \
            else (lambda a: a in ('partial_phase_spread', 'unison_shares_phase', 'course_keys', 'key_bridge',
                                  'bridge_partner', 'register_knock_tilt', 'register_knock_profile')) \
            if dulcimer_voice(cls) \
            else (lambda a: a in ('partial_phase_spread', 'bloom_seconds')) \
            if harmonic_voice(cls) and _owner(cls, 'harmonic_decay') == 'PromptDecay' else (lambda a: False)
        if hit_voice(cls):
            _og = org_has
            org_has = lambda a: _og(a) or a in ('one_shot', 'strike_phase_spread', 'strike_noise_layers')  # noqa: E731
        ok = (v is not None and not (getattr(cls, 'grains', None) and not grains_of(cls))
              and drones_ok(cls) and len(getattr(cls, 'scale_cents', None) or ()) <= 32
              and (not getattr(cls, 'drone_stops', None)
                   or note_class(getattr(T, cls.drone_strike_class)) is not None)
              and (not getattr(cls, 'pulse', False) or pulse_voice(cls))
              and not any(getattr(cls, a, None) for a in _NOTE_OFF
                                        if not (drum and drum_has(a)) and not org_has(a))
              and not any(hasattr(cls, a) for a in _NOTE_ABSENT if not org_has(a))
              and (not hasattr(cls, 'feedback_harmonic') or feedback_voice(cls))
              and (getattr(cls, 'mode_phase', None) is None or issubclass(cls, T.TR808Properties) or drum == 5
                   or heartbeat_voice(cls))
              and (int(getattr(cls, 'strike_flam', 0) or 0) <= 1
                   or (int(cls.strike_flam) <= 64 and not getattr(cls, 'strike_flam_record', False)))
              and len(class_value(cls, 'strike_noise_db', ()) or ()) <= 32)
        if ok:
            # a section's players and their onsets: none for one instrument, or a bowed string's
            p = v[2]
            ok = harmonic_voice(cls) or wind_voice(cls) or tap_voice(cls) or not (hasattr(p, 'section_seats') and p.section_seats()) and not any(
                hasattr(p, 'section_onsets_at') and p.section_onsets_at(f) for f in (27.5, 261.6, 4186.0))
        # (sympathetic strings by coincidence, or per mode: sympathetic.expand's
        # that are not the engine's -- its contact mode is, below)
        _smode = getattr(cls, 'sympathetic_mode', 'coincidence')
        if getattr(cls, 'sympathetic_gain', 0.0) > 0.0 and (
                (_smode != 'contact' and not getattr(cls, 'sympathetic_strings', ()))
                or (getattr(cls, 'tuning_family', None) == 'indian' and _smode == 'contact')
                or len(getattr(cls, 'sympathetic_strings', ()) or ()) > 32):
            ok = False
        if not ok:
            _NOTE[cls] = False
            return None
        k = NoteClass()
        k.init = v[0]
        k.fold_restrike = int(bool(getattr(cls, 'fold_restrike', False)))     # (a gong: emit_partial's _fold_cls)
        _asw = getattr(cls, 'alias_sweep', None)                        # (an aliasing sweep's: _prep_alias_sweep's)
        k.alias_sweep[:] = [float(x) for x in _asw] if _asw else [0.0] * 5
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
        k.chiff_volume = v[2].chiff_volume if isinstance(cls.chiff_volume, property) else cls.chiff_volume
        k.chiff_cycle = cls.chiff_cycle
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
        tab = class_value(cls, 'strike_noise_db', ()) or ()
        k.n_strike = len(tab)
        for i, b in enumerate(tab):
            k.strike_hz[i], k.strike_db[i] = float(b[0]), float(b[1])
        if tab:
            k.strike_noise_dbs = class_value(cls, 'strike_noise_dbs')
            sp = getattr(cls, 'strike_noise_span_hz', None)
            k.strike_span_set = int(bool(sp))
            if sp:
                k.strike_span_lo, k.strike_span_hi = sp
            k.strike_octave_db = getattr(cls, 'strike_noise_octave_db', cls.strike_noise_slope)
            k.strike_fade_s = cls.strike_noise_fade_s
            k.strike_len_s = getattr(cls, 'strike_noise_len_s', None) or 0.25
            k.strike_at_s = getattr(cls, 'strike_noise_at', 0.0) or 0.0
            k.strike_cal_db = getattr(cls, 'strike_noise_cal_db', 0.0) or 0.0
            tl = getattr(cls, 'strike_noise_tail', None)
            if tl:
                k.tail_set, k.tail_db, k.tail_dbs = 1, float(tl[0]), float(tl[1])
        k.clav_panel = int(bool(getattr(cls, 'clav_panel', False)))
        k.wheel_vibrato = int(bool(getattr(cls, 'wheel_vibrato', True)))
        k.scatter_ms = float(getattr(cls, 'section_onset_ms', 0.0) or 0.0)
        # the sound controllers' shaping (tonelib.sound_shape: nv_sound_shape)
        k.sh_et = float(getattr(cls, 'effort_tilt', 0.0) or 0.0)
        k.sh_corner = float(getattr(cls, 'bore_corner_hz', 0.0) or 0.0)
        k.sh_order = float(getattr(cls, 'bore_order', 2.0))
        k.sh_mq = float(getattr(cls, 'mute_resonance_q', 0.0) or 0.0)
        k.sh_mhz = float(getattr(cls, 'mute_resonance_hz', 0.0) or 0.0)
        k.sh_mdb = float(getattr(cls, 'mute_resonance_db', 0.0) or 0.0)
        if getattr(cls, 'pluck_point_control', False):
            # (pluck_shape's cls(f0): its strike point -- a stopped string's
            # from the open strings, else the class's -- depth, B and series)
            k.sh_pluck = 1
            k.sh_sp, k.sh_sd = float(cls.strike_point), float(cls.strike_depth)
            k.sh_B, k.sh_mh = float(cls.inharmonicity_coefficient), int(cls.max_harmonic or 64)
            os_ = getattr(cls, 'open_strings', None) or ()
            if stopped_voice(cls) and getattr(cls, 'pluck_open', None) and os_:
                k.sh_nopen, k.sh_popen = len(os_), float(cls.pluck_open)
                k.sh_open[:k.sh_nopen] = [float(o) for o in os_]
        nf = int(getattr(cls, 'strike_flam', 0) or 0)
        k.n_flam = nf if nf > 1 else 0
        ft = getattr(cls, 'strike_flam_times', None) or ()
        k.n_ft = len(ft)
        k.ft_bal = int(bool(ft) and all(len(b) > 2 for b in ft))
        for i, b in enumerate(ft):
            k.ft_t[i], k.ft_db[i] = float(b[0]), float(b[1])
            k.ft_c[i] = float(b[2]) if len(b) > 2 else 0.0
        lays = getattr(cls, 'strike_noise_layers', ()) or ()
        k.n_layer = len(lays)
        for l, (tab, rise, dbs, ln) in enumerate(lays):
            k.lay_n[l] = len(tab)
            for i, (f, db) in enumerate(tab):
                k.lay_hz[l][i], k.lay_db[l][i] = float(f), float(db)
            k.lay_rise[l], k.lay_dbs[l], k.lay_len[l] = float(rise), float(dbs), float(ln)
        k.flam_s = float(getattr(cls, 'strike_flam_s', 0.0) or 0.0)
        k.flam_db = float(getattr(cls, 'strike_flam_db', 0.0) or 0.0)
        k.flam_rate = float(getattr(cls, 'strike_flam_rate', 0.0) or 0.0)      # (a crowd: bursts a second)
        k.flam_exp = float(getattr(cls, 'strike_flam_exp_db', 0.0) or 0.0)    # (...a crackle's levels)
        if getattr(cls, 'strike_flam_record', False):          # (...or a record's clicks: _record_clicks)
            k.flam_record = 1
            k.rec_per, k.rec_pr = [float(x) for x in (getattr(cls, 'strike_flam_recur', None) or (1.8, 0.0))]
            _rq = tuple(getattr(cls, 'strike_flam_levels', ()) or ())
            k.n_rq = len(_rq)
            for _i, (_qa, _qb) in enumerate(_rq):
                k.rec_qx[_i], k.rec_qy[_i] = float(_qa), float(_qb)
        _pp = getattr(cls, 'strike_flam_people', None)                         # (a few people clapping)
        if _pp:
            k.people_n = int(_pp[0])
            k.people_lo, k.people_hi, k.people_jit, k.people_db = (float(x) for x in _pp[1:5])
            _pk = getattr(cls, 'strike_flam_people_peak', None)
            if _pk:
                k.pk_set = 1
                k.pk_lo, k.pk_hi, k.pk_db, k.pk_q = (float(x) for x in _pk)
        k.pjit = int(bool(getattr(cls, 'jitter_by_partial', False)))
        k.ssc = int(bool(getattr(cls, 'stroke_scatter', False)))
        k.gate_time = float(getattr(cls, 'gate_time', None) or 0.0)
        k.played_backwards = int(bool(getattr(cls, 'played_backwards', False)))
        k.bendable = int(bool(getattr(cls, 'pitch_bendable', True)))
        # its cabinet and amplifier (blockrender's _LESLIE_CH, _SCAN_CH, _AMP_CH)
        k.leslie = (2 if getattr(cls, 'leslie_fast', True) else 1) if getattr(cls, 'leslie', False) else 0
        # (scanner: 0 none; else 1, +2 the switch, +4 x its own depth, +16 its own chorus)
        import scanner as _SCN
        _own = _SCN.parse(getattr(cls, 'scanner', None))
        k.scanner = (0 if not (getattr(cls, 'scanner_switch', False) or getattr(cls, 'scanner', None)) else
                     1 + 2 * int(bool(getattr(cls, 'scanner_switch', False)))
                     + (4 * _own[0] + 16 * int(_own[1]) if _own else 0))
        k.amp_drive = float(getattr(cls, 'amp_drive', 0.0) or 0.0)
        k.wheel_swell = int(bool(getattr(cls, 'wheel_swell', False)))
        # its tremolo (an ordinary voice's: _note_tremolo)
        k.trem_depth = float(getattr(cls, 'tremolo_depth', 0.0) or 0.0)
        k.trem_hz = float(getattr(cls, 'tremolo_hz', 0.0) or 0.0)
        k.trem_stereo = int(bool(getattr(cls, 'tremolo_stereo', False)))
        k.trem_scatter = float(getattr(cls, 'tremolo_scatter', 0.0) or 0.0)
        k.trem_intrinsic = int(bool(getattr(cls, 'tremolo_intrinsic', False)))
        k.touch_sensitive = int(bool(getattr(cls, 'touch_sensitive', True)))
        # its speaker cabinet (cabinet.py: _prep_cabinet), its response's terms
        cab = getattr(cls, 'cabinet', None)
        _ie = getattr(cls, 'insertion_efx', None)
        if _ie:                             # (as set: live's chain, nvlive's to build -- gsefx.tone_state)
            k.efx_raw = 1
            k.efx_raw_ty[:] = [int(_ie[0][0]), int(_ie[0][1])]
            k.efx_raw_p[:] = [-1] * 21
            for _pn, _pv in (_ie[1] or {}).items():
                k.efx_raw_p[int(_pn)] = int(_pv)
        _ex = efx_chain(cls)
        if _ex is not None:                 # ITS OWN INSERTION EFFECT (blockrender's _EFXN)
            k.efx_set, k.efx_level, k.efx_od = 1, float(_ex['level']), float(_ex['od_gain'] or 0.0)
            if _ex['eq'] is not None:
                k.efx_eq_set = 1
                k.efx_eq[:] = [float(x or 0.0) for x in _ex['eq']]      # (None: no mid band)
            import gsefx as _GSX_
            k.efx_rev = float(_ex['sends'].get(_GSX_.SEND_REV, 40))
            if _ex['cabinet']:
                cab = _ex['cabinet']        # (the effect's speaker, in the voice's place)
            if _ex.get('cf') or _ex.get('dly'):     # (the outputs' places: gsd_place's head)
                import gsdelay as _GSDP
                _qp = T.StoppedPipeProperties(261.6, 0, 1, 1)
                k.efx_place[0] = float(_qp.hrtf_beta)
                for _s, _sd in enumerate(('l', 'r', 'c')):
                    _li, _ri, _ld, _rd = _qp.hrtf_at(_GSDP.OUTPUT_X[_sd], 0.0, _qp.listener_distance)
                    k.efx_place[1 + 4 * _s:5 + 4 * _s] = [_li, _ri, _ld * BR.SR, _rd * BR.SR]
            if _ex.get('filter') and not getattr(cls, 'plunger', False):     # ITS MOVING FILTER (efxfilter)
                _fl = _ex['filter']
                _c = _fl['ctrl']
                k.flt_set, k.flt_ty, k.flt_k = 1, int(_fl['ty']), 1 if _c[0] == 'sweep' else 2
                k.flt_p[:] = [float(_fl['pa']), float(_fl['pb']), float(_fl['pc'])]
                if _c[0] == 'sweep':
                    k.flt_c[:] = [float(_c[1]), float(_c[2]), float(_c[3]),
                                  float('nan') if _c[4] is None else float(bool(_c[4])), float(_c[5] or 0.0)]
                else:
                    k.flt_c[0] = float(_c[1])
            if _ex.get('bus'):              # ITS BUS (efxbus: Lo-Fi, a compressor or limiter)
                import efxbus as _EBX
                _pr = _EBX.make(_ex['bus'][0], BR.SR, **_ex['bus'][1])
                _mx = _ex.get('bus_mix') or (0.0, 1.0)
                if _ex['bus'][0] == 'lofi':
                    k.efx_bus = 1
                    k.bus_p[:4] = [_pr.step, _pr.q, _pr.pre.a or 0.0, _pr.post.a or 0.0]
                else:
                    k.efx_bus = 2
                    k.bus_p[:5] = [_pr.t, _pr.r, _pr.ka, _pr.kr, _pr.mk]
                k.bus_p[10], k.bus_p[11] = float(_mx[0]), float(_mx[1])
            if _ex.get('trem'):             # ITS TREMOLO (an Auto Pan's: the tremolo pass)
                k.efx_trem = 1
                k.trem_cfg[:] = [float(x) for x in tuple(_ex['trem'])[:4]]
            if _ex.get('dly'):              # ITS DELAY (gsdelay.expand)
                _dl = _ex['dly']
                k.efx_dly = 1
                k.dly_p[:5] = [float(_dl['level']), float(_dl['fb']), float(_dl['lpf'] or 0.0), float(_dl['tc']),
                               float(len(_dl['taps']))]
                for _i, _t in enumerate(_dl['taps']):
                    k.dly_p[5 + 4 * _i:9 + 4 * _i] = [float(_t[0]), float(_t[1]), float('lrc'.index(_t[2])),
                                                      float(_t[3])]
            if _ex.get('cf'):               # ITS CHORUS DEVICE (chorus.gs_copies)
                import chorus as _CHRX
                import gsdelay as _GSDX
                _dv = _ex['cf'][0]
                _taps = _dv.get('taps') or _CHRX.GS_TAPS
                if _ex.get('cf_share') is not None:
                    _sh = float(_ex['cf_share'])
                else:
                    _a = _ex['cf'][1] if _ex['cf'] is not None else 0.0
                    _sh = _a * _a / (1.0 + _a * _a)
                _q = T.StoppedPipeProperties(261.6, 0, 1, 1)    # (blockrender.gsd_place's head)
                k.efx_cf = 1
                k.cf_p[:8] = [float(_dv['tau']), float(_dv['rate']), float(_dv['vd']), float(_dv['fb']),
                              float(_dv['lpf'] or 0.0), _sh, float(len(_taps)), float(_q.hrtf_beta)]
                for _s, _sd in enumerate(('l', 'r', 'c')):
                    _li, _ri, _ld, _rd = _q.hrtf_at(_GSDX.OUTPUT_X[_sd], 0.0, _q.listener_distance)
                    k.cf_p[8 + 4 * _s:12 + 4 * _s] = [_li, _ri, _ld * BR.SR, _rd * BR.SR]
                for _i, _t in enumerate(_taps):
                    k.cf_p[20 + 4 * _i:24 + 4 * _i] = [float('lrc'.index(_t[0])), float(_t[1]),
                                                       float(_t[2]) if len(_t) > 2 else 0.0,
                                                       float(_t[3]) if len(_t) > 3 else 1.0]
        if getattr(cls, 'noise_gate', None):
            # ITS OWN GATE, keyed (efxbus.NoiseGate, its settings as Python makes them); unkeyed, Python's
            _ngkw = dict(cls.noise_gate)
            if not _ngkw.pop('keyed', False):
                _NOTE[cls] = False
                return None
            import efxbus as _EB
            _ng = _EB.NoiseGate(BR.SR, **_ngkw)
            k.ng_set = 1
            k.ng_p[:] = [float(_ng.hold), float(_ng.fall), 0.0 if _ng.sus is None else 1.0,
                         float(_ng.sus or 0.0), float(_ng.ratio), float(_ng.mk), float(_ng.floor),
                         float(_ng.cmp[0].a), float(_ng.cmp[1].a), float(_ng.gain[0].a), float(_ng.gain[1].a),
                         float(_ng.ref)]
        if getattr(cls, 'plunger', False):  # A PLUNGER (efxfilter.plunger: the channel's aftertouch)
            import efxfilter as _EFP
            k.flt_set, k.flt_ty, k.flt_k = 2, 2, 3
            k.flt_p[:] = [_EFP.PLUNGER_Q, _EFP.PLUNGER_MIX, 0.0]
            k.flt_c[:] = [_EFP.PLUNGER_CLOSED_HZ, _EFP.PLUNGER_MID_HZ, _EFP.PLUNGER_OPEN_HZ, _EFP.PLUNGER_LINEAR,
                          _EFP.PLUNGER_GLIDE_S]
        elif getattr(cls, 'mouth_states', None):   # A DIDGERIDOO's MOUTH (efxfilter.mouth: the wander, or the wheel)
            import efxfilter as _EFP
            import numpy as _np
            st = cls.mouth_states
            if len(st) > 16:
                _NOTE[cls] = False
                return None
            k.flt_set, k.flt_ty, k.flt_k = 2, 5, 4
            k.flt_p[:] = [float(cls.mouth_floor), float(_EFP.mouth_gain(st, cls.mouth_floor)), 0.0]
            _p = _np.asarray([s_[3] for s_ in st], float)
            _p = _p / _p.sum()
            _cdf = _p.cumsum()                      # (Generator.choice's)
            _cdf /= _cdf[-1]
            k.n_mouth, k.mouth_seed = len(st), int(_EFP.MOUTH_SEED_OFFSET[0])
            for i, s_ in enumerate(st):
                k.mouth_st[i][:] = [float(x) for x in s_[:3]]
                k.mouth_cdf[i] = float(_cdf[i])
            for i, s_ in enumerate(sorted(s_[:3] for s_ in st)):
                k.mouth_wst[i][:] = [float(x) for x in s_]
            k.mouth_dw[:] = [float(x) for x in cls.mouth_dwell_s]
            k.mouth_glide = float(cls.mouth_glide_s)
        if cab and os.environ.get('TUNING_CABINET', '1') != '0':
            import cabinet as _CAB
            cb = _CAB.get(cab)
            if len(cb.formants) > 4 or len(cb.antiformants) > 4 or cb.body_trim_db:
                _NOTE[cls] = False
                return None
            k.cab_set, k.n_cab_fm, k.n_cab_afm = 1, len(cb.formants), len(cb.antiformants)
            k.cab_floor = float(cb.formant_floor)
            for i, row in enumerate(cb.formants):
                k.cab_fm[i][:] = [float(x) for x in row]
            for i, row in enumerate(cb.antiformants):
                k.cab_afm[i][:] = [float(x) for x in row]
            k.cab_corner, k.cab_order = float(cb.bore_corner_hz), float(cb.bore_order)
            k.cab_cut, k.cab_bell = float(cb.bell_cutoff_hz or 0.0), float(cb.bell_order)
            k.cab_ref = float(cb._ref)
        # its key-up's click (release_click_db), a jack a drawn stop on a choired organ
        cdb, cm = getattr(cls, 'release_click_db', None), getattr(cls, 'release_click_modes', ()) or ()
        if clav_voice(cls) and cdb is not None:
            # (a Clavinet's modes are the note's: VoiceSnap.vk_*, by its __init__)
            cm = tuple((0.0, 0.0) for _ in range(len(cls.keyup_thump_hz) + len(cls.keyup_string_harmonics)))
        if cdb is not None and cm:
            k.n_click, k.click_db = len(cm), float(cdb)
            for i, (hz, a) in enumerate(cm):
                k.click_hz[i], k.click_amp[i] = float(hz), float(a)
            k.click_dec, k.click_s = float(cls.release_click_decay_db), float(cls.release_click_s)
            k.click_jacks = int(bool(getattr(cls, 'registerable', False) and getattr(cls, 'string_choirs', None)))
        k.pre_pluck = int(hasattr(cls, 'pre_pluck_s'))
        # the player's breath (its rows: nv_breath_rows)
        if (getattr(cls, 'breath_wobble_db', 0.0) > 0.0 or getattr(cls, 'breath_noise_wobble_db', 0.0) > 0.0
                or getattr(cls, 'breath_pitch_cents', 0.0) > 0.0):
            k.breath = 1
            k.breath_p[:] = [float(getattr(cls, a, 0.0) or 0.0) for a in (
                'breath_wobble_db', 'breath_wobble_hz', 'breath_noise_wobble_db', 'breath_noise_wobble_hz',
                'breath_noise_wobble_share', 'breath_pitch_cents', 'breath_pitch_hz', 'breath_pitch_share')]
        # a player's bellows (a standalone voice's push): its laws, the plain one's (no band, no register)
        if getattr(cls, 'bellows_push_gain', 0.0) and not getattr(cls, 'registerable', False):
            if (getattr(cls, 'bellows_push_every_note', False) or getattr(cls, 'bellows_push_band', None)
                    or getattr(cls, 'bellows_push_register', None)):
                _NOTE[cls] = False
                return None
            k.push_gain, k.push_rise_s, k.push_dbs = (float(cls.bellows_push_gain), float(cls.bellows_push_rise_s),
                                                      float(cls.bellows_push_dbs))
            k.push_settle_db = float(getattr(cls, 'bellows_push_settle_db', -20.0))
            k.push_tilt = float(getattr(cls, 'bellows_push_tilt', 0.0))
            k.push_tilt_oct = float(getattr(cls, 'bellows_push_tilt_per_octave', 0.0))
        # its valve against a fixed reference peak (0: each segment's own), and its pair's imbalance
        k.amp_reference = float(getattr(cls, 'amp_reference', None) or 0.0)
        imb = getattr(cls, 'amp_imbalance', None)
        k.amp_imbalance = float(__import__('tubeamp').IMBALANCE if imb is None else imb)
        # the sound controls it answers, and where it starts from
        sc = T.sound_controls_of(cls)
        names = [T.SOUND_CC[c] for c in sorted(T.SOUND_CC)]
        k.snd_mask = sum(1 << i for i, nm in enumerate(names) if nm in sc)
        bias = getattr(cls, 'sound_bias', None) or {}
        k.snd_bias[:] = [float(bias.get(nm, 0.0)) for nm in names]
        k.snd_time_range, k.snd_rate_range, k.snd_delay_s = (T.SOUND_TIME_RANGE, T.SOUND_VIB_RATE_RANGE,
                                                              T.SOUND_VIB_DELAY_S)
        # its glide
        gm = getattr(cls, 'glide_mechanism', None)
        k.glide_mech = 0 if not gm else 2 if gm == 'circuit' else 3 if gm == 'valve' else 1
        gr = getattr(cls, 'glide_reach_semitones', None)
        k.glide_reach = math.nan if gr is None else float(gr)
        k.porta_fast, k.porta_slow = T.PORTA_SEMITONE_FAST, T.PORTA_SEMITONE_SLOW
        k.porta_d_semi, k.porta_settle = T._PORTA_D_SEMI, T.PORTA_SETTLE_TAUS
        # a Moog: its panels (nv.h MoogSpec, in the class itself)
        if kit_drum(cls) == 6:
            k.moog = moog_spec(cls)
        # (the horn's intonation: blockrender._note_class_and_pitch's, by the class's name)
        k.brass = (2 if 'Dark' in cls.__name__ else 1) if cls.__name__.endswith('BrassProperties') else 0
        # a registered organ: its ranks (the pointer the engine reads; the table kept here)
        if getattr(cls, 'registerable', False):
            og = organ(cls)
            if og is None:
                _NOTE[cls] = False
                return None
            k.organ = ctypes.addressof(og)
        # ITS CHORUS's COMB (chorus.offsets_for)
        import chorus as _CHR
        _cc = tuple(_CHR.offsets_for(cls))
        if len(_cc) > 8:
            _NOTE[cls] = False
            return None
        k.n_cho = len(_cc)
        k.cho_cents[:len(_cc)] = [float(x) for x in _cc]
        # ...its own pedal, or a detuned pair, where the part sends no CC93 (_note_chorus_send)
        k.cho_send = float(getattr(cls, 'chorus_send', None) or 0.0)
        _dp = getattr(cls, 'detuned_pair', None)
        if _dp and not k.cho_send:
            k.pair_set, k.pair_lo, k.pair_hi = 1, float(_dp[0]), float(_dp[1])
        k.indian = int(getattr(cls, 'tuning_family', None) == 'indian')     # (FREQ_E's)
        k.meend = int(bool(getattr(cls, 'bend_detents', False)))
        k.meend_range = float(getattr(cls, 'bend_range_semitones', T.BEND_RANGE_SEMITONES))
        k.meend_strength = float(getattr(cls, 'meend_strength', 0.6))
        k.meend_tonic = int(getattr(cls, 'sympathetic_tonic', 60))
        k.key_pan_spread = float(getattr(cls, 'key_pan_spread', 0.0) or 0.0)     # (a wide voice's seats)
        sc = getattr(cls, 'scale_cents', None)        # (its own scale: _note_class_and_pitch's)
        st = getattr(cls, 'scale_tonic_note', None)
        if sc and st is not None:
            k.scale_n, k.scale_tonic = len(sc), int(st)
            for q, (off, cents) in enumerate(sorted(sc.items())):
                k.scale_off[q], k.scale_c[q] = int(off), float(cents)
        si = getattr(cls, 'strike_in_s', None)          # (a strike-in by the hand)
        if si:
            k.si_set, k.si0, k.si1 = 1, float(si[0]), float(si[1])
        k.part_break_s = float(getattr(cls, 'part_break_s', 2.0))
        for q, (dn, dcls) in enumerate(getattr(cls, 'drone_classes', None) or ()):
            k.drone_note[q], k.drone_k[q] = int(dn), NV_K_DRONE + drone_index(dcls)
        k.n_drone = len(getattr(cls, 'drone_classes', None) or ())
        if getattr(cls, 'drone_note_wheel', False):     # (the wheel chooses the drone's note: a pungi)
            _chs = [int(x) for x in cls.drone_note_choices]
            k.n_dchoice, k.dchoice_def = len(_chs), int(cls.drone_note_default)
            k.dchoice[:len(_chs)] = _chs
            k.dchoice_var = int(getattr(cls, 'drone_note_variation', 0))   # (live's: its own patch)
        k.drone_wheel = int(bool(getattr(cls, 'drone_wheel', False)))     # (live's: Patch.drone_wheel)
        _dst = tuple(getattr(cls, 'drone_stops', ()) or ())
        if _dst:                                # (the wheel's drone stops: the taishogoto's struck drone)
            import tonelib as _TL
            k.n_dstop, k.dstop_def = len(_dst), int(cls.drone_stop_default)
            k.dstr_note, k.dstr_db = int(cls.drone_strike_note), float(cls.drone_strike_db)
            k.dstr_ring = float(cls.drone_strike_ring_s)
            k.dstr_k = NV_K_DRONE + drone_index(getattr(_TL, cls.drone_strike_class))
        _dr = tuple(getattr(cls, 'drone_ratios', ()) or ())
        k.n_dratio = min(4, len(_dr))
        k.drone_ratio[:k.n_dratio] = [float(x) for x in _dr[:4]]
        _dg = tuple(getattr(cls, 'drone_gain', ()) or ())
        k.drone_gain[:min(4, len(_dg))] = [float(x) for x in _dg[:4]]
        # (a melodic note's sounding octaves, in the engine's pitch; a drum's pitch is its set's)
        k.sounding_oct = float(getattr(cls, 'sounding_octaves', 0.0) or 0.0)
        k.xf = float(getattr(cls, 'transposed_from_hz', 0.0) or 0.0)      # (a sound transposed whole: _XP)
        k.hammer = int(bool(getattr(cls, 'hammer_legato', False)))      # (the fretting hand's legato)
        k.fall_cents = float(getattr(cls, 'fall_cents', 0.0) or 0.0)    # (a fall, a rip: Song::gliss)
        if k.fall_cents:
            k.fall_at_s, k.fall_s, k.fall_fade_db = float(cls.fall_at_s), float(cls.fall_s), float(cls.fall_fade_db)
            k.fall_smear = float(getattr(cls, 'fall_smear', 0.6))
        _sr = getattr(cls, 'siren_rotor', None)
        if _sr not in (None, 'fire') and not siren_host(cls):
            _NOTE[cls] = False              # (another siren's rotor: Python's)
            return None
        k.siren = {'fire': 1, 'helmholtz': 2}.get(_sr, 0)     # (its rotor: nvrender's rows)
        k.tp_hz = float(getattr(cls, 'tremolo_pick_hz', 0.0) or 0.0)     # (tremolo picking: Song::gliss)
        if k.tp_hz:
            k.tp_up_db, k.tp_jit = float(cls.tremolo_pick_up_db), float(cls.tremolo_pick_jitter)
        k.cut_semi = int(getattr(cls, 'cut_semitones', 0) or 0)      # (a cut: the uilleann's flick)
        k.cut_s = float(getattr(cls, 'cut_s', 0.03))
        k.rip_cents = float(getattr(cls, 'rip_cents', 0.0) or 0.0)
        if k.rip_cents:
            k.rip_s, k.rip_start_db = float(cls.rip_s), float(cls.rip_start_db)
            k.rip_smear = float(getattr(cls, 'rip_smear', 0.8))
        if heartbeat_voice(cls):                # (its blood flow: timed noise bands)
            _ne = v[2].noise_events
            k.n_nev = len(_ne)
            for i, e in enumerate(_ne):
                k.nev[i][:] = [float(x) for x in e]
            k.nev_ramp_s = float(cls.noise_event_ramp_s)
            k.noise_rows, k.noise_rel = int(cls.noise_rows), float(cls.noise_rel)     # (the shake's fields)
        k.sfx_prog, k.sfx_key = sfx_prog_key(cls)                         # (its kit key's strokes)
        if pulse_voice(cls):                    # (its N-wave: _note_pulse)
            k.pulse = 1
            k.pulse_lo_ms, k.pulse_hi_ms = (float(x) for x in cls.pulse_ms_range)
            k.pulse_peak, k.pulse_fmax, k.pulse_taper = float(T.N_WAVE_PEAK), float(cls.pulse_fmax), float(cls.pulse_taper)
        if getattr(cls, 'reverb_distance', None) is not None:    # (its own distance: _src_dist's)
            k.rd_set, k.reverb_dist = 1, float(cls.reverb_distance)
        # its grains (the engine's: breath_noise -- a row's six fields, eight with
        # a glide, nine with a cluster)
        k.n_grain = len(grains_of(cls))
        for i, row in enumerate(grains_of(cls)):
            k.grain[i][:] = [float(x) for x in row[:6]] + (
                [float(row[6]), float(row[7])] if len(row) > 6 else [0.0, 0.0]) + (
                [float(row[8])] if len(row) > 8 else [1.0])
        # ITS OTHER STRINGS (ring_db: _note_ring)
        _rg = getattr(cls, 'ring_db', ()) or ()
        if len(_rg) > 48:
            _NOTE[cls] = False
            return None
        k.ring_n, k.ring_skip = len(_rg), float(getattr(cls, 'ring_skip', 0.03))
        _ro = tuple(cls.mode_ratios or (1.0, 2.0))
        if _rg and len(_ro) > 16:
            _NOTE[cls] = False
            return None
        k.ring_nown = len(_ro[:16])
        k.ring_own[:k.ring_nown] = [float(x) for x in _ro[:16]]
        for _i, (_hz, _db, _dps) in enumerate(_rg):
            k.ring_hz[_i], k.ring_db[_i], k.ring_dps[_i] = float(_hz), float(_db), float(_dps)
        # ITS SYMPATHETIC STRINGS, BY CONTACT (sympathetic.responders): a fixed
        # set's pitches (the tonic's offsets), each string's drive and its own
        # cents -- which answer is the strike's (its key), so the C asks -- or
        # the body's neighbours, the same whatever is struck
        _sg = getattr(cls, 'sympathetic_gain', 0.0)
        if _sg > 0.0:
            import sympathetic as _SYMP
            k.sym_floor = float(getattr(cls, 'sympathetic_floor', 0.02))
            k.sym_top = int(getattr(cls, 'sympathetic_max', 6))
            k.sym_nobend = int(bool(getattr(cls, 'bend_detents', False)))
            k.sym_per_mode = int(bool(getattr(cls, 'sympathetic_per_mode', False)))     # (by coincidence, per mode)
            k.sym_bw = float(getattr(cls, 'sympathetic_width_hz', 0.0) or 1.0)
            _st = getattr(cls, 'sympathetic_strings', ())
            if _st:
                _tn = int(getattr(cls, 'sympathetic_tonic', 60))
                _sdb = tuple(getattr(cls, 'sympathetic_string_db', ())) or (0.0,) * len(_st)
                _sct = tuple(getattr(cls, 'sympathetic_string_cents', ())) or (0.0,) * len(_st)
                if getattr(cls, 'sympathetic_mode', 'coincidence') == 'contact':
                    k.sym_kind, k.sym_n = 1, len(_st)
                    for _i, (_o, _db, _ct) in enumerate(zip(_st, _sdb, _sct)):
                        k.sym_pitch[_i] = _tn + int(_o)
                        k.sym_d[_i] = _sg * 10.0 ** (_db / 20.0)
                        k.sym_cents[_i] = float(_ct)
                else:                   # (by coincidence: the C's coupling, per strike)
                    k.sym_kind, k.sym_n, k.sym_tonic = 3, len(_st), _tn
                    k.sym_g = _sg
                    k.sym_wmin = float(getattr(cls, 'sympathetic_width_hz', 0.0) or 0.0)
                    for _i, (_o, _db, _ct) in enumerate(zip(_st, _sdb, _sct)):
                        k.sym_pitch[_i] = int(_o)
                        k.sym_d[_i] = 10.0 ** (_db / 20.0)
                        k.sym_cents[_i] = float(_ct)
            else:
                _rsp = _SYMP.responders(cls)
                if len(_rsp) > 32:
                    _NOTE[cls] = False
                    return None
                k.sym_kind, k.sym_n = 2, len(_rsp)
                for _i, _it in enumerate(_rsp):
                    k.sym_pitch[_i], k.sym_d[_i] = int(_it[0]), float(_it[1])
                    k.sym_cents[_i] = float(_it[2]) if len(_it) > 2 else 0.0
        # A STRUCK, PITCHED LAYER (struck_layer): its class's NoteClass, kept
        sl = getattr(cls, 'struck_layer', None)
        if sl:
            lcls = T.rank_spectrum(sl[0])
            lk = note_class(lcls)
            if lk is None or len(getattr(lcls, 'mode_ratios', None) or ()) > 64:
                _NOTE[cls] = False
                return None
            k.sl_on, k.sl_idx = 1, -1
            k.sl_nm = len(getattr(lcls, 'mode_ratios', None) or ()) or 8
            k.sl_db, k.sl_rise, k.sl_dbs = float(sl[1]), float(sl[2]), float(sl[3])
            k.sl_lo, k.sl_hi = (float(x) for x in getattr(cls, 'struck_layer_range', (73.42, 146.83)))
            k.sl = ctypes.addressof(lk)
            _SL_CLS[cls] = lcls
        if getattr(cls, 'detuned_pair', None) and len(cls.detuned_pair) != 2:
            _NOTE[cls] = False
            return None
        _osr = getattr(cls, 'open_string_ring', None)
        if _osr:                            # (a palm-muted open string: blockrender's _string_free)
            if len(_osr[0]) > 8 or list(_osr[0]) != sorted(_osr[0]):
                _NOTE[cls] = False
                return None
            k.osr_n, k.osr_cap = len(_osr[0]), float(_osr[1])
            k.osr_open[:k.osr_n] = [float(x) for x in _osr[0]]
        if breath_noise(cls):
            k.n_bn, k.bn_rows, k.bn_fade_s = (len(cls.breath_noise_db), int(getattr(cls, 'breath_noise_rows', 1)),
                                               float(cls.breath_noise_fade_s))
            k.bn_slur = int(bool(getattr(cls, 'breath_noise_slur', False)))
            k.bn_oct = float(getattr(cls, 'breath_noise_octave_db', 0.0) or 0.0)     # (the octave law)
            k.bn_ref = float(getattr(cls, 'breath_noise_ref_hz', 440.0))
            for i, (hz, db) in enumerate(cls.breath_noise_db):
                k.bn_hz[i], k.bn_db[i] = float(hz), float(db)
            if getattr(cls, 'breath_noise_low_db', None):
                k.bn_low_set = 1
                k.bn_low[:len(cls.breath_noise_low_db)] = [float(db) for _, db in cls.breath_noise_low_db]
                k.bn_low_hz[:] = [float(x) for x in cls.register_low_hz]
        elif getattr(cls, 'breath_noise_db', ()):
            _NOTE[cls] = False              # (a breath the engine cannot play -- BreathyTnr.'s octave law: Python's)
            return None
        if kit_drum(cls) == 3:
            k.shake, k.n_nb, k.noise_rows = 1, len(cls.noise_bands), int(cls.noise_rows)
            for i, (f, db) in enumerate(cls.noise_bands):
                k.nb_hz[i], k.nb_db[i] = float(f), float(db)
            for f in ('shake_min_s', 'shake_frac', 'shake_xfade_s', 'rise_s', 'settle_db', 'settle_s', 'noise_rel'):
                setattr(k, f, float(getattr(cls, f)))
        k.held_texture = int(bool(getattr(cls, 'held_texture', False)))
        k.sps = float(getattr(cls, 'strike_phase_spread', 0.0) or 0.0)
        k.one_shot = int(bool(getattr(cls, 'one_shot', False)))
        k.one_shot_hold = BR.ONE_SHOT_MIN_S
        k.tape_s = float(getattr(cls, 'tape_length_s', 0.0) or 0.0)     # (a Mellotron's tape runs out)
        k.os_floor_db, k.os_max_s = float(BR.ONE_SHOT_FLOOR_DB), float(BR.ONE_SHOT_MAX_S)
        k.damper_pedal = int(bool(getattr(cls, 'damper_pedal', True)) and not k.one_shot)
        k.detune_lo, k.detune_hi = getattr(cls, 'string_detune_range', (0.0, 0.0))
        k.detune_wheel = int(bool(getattr(cls, 'detune_wheel', False)))
        import register as _RG
        k.reg_gain = float(getattr(cls, 'register_gain', 0.0))
        k.reg_knock = float(getattr(cls, 'register_knock_gain', 0.0))
        k.reg_fall = float(getattr(cls, 'register_knock_falloff', 0.0))
        k.damper_top = int(getattr(cls, 'damper_top', 128))
        k.reg_floor = _RG.floor_of(cls)
        k.reg_release = float(getattr(cls, 'release_valve_time', 0.12) or 0.12)
        kb, pt, kp = (getattr(cls, 'key_bridge', None), getattr(cls, 'bridge_partner', None),
                      getattr(cls, 'register_knock_profile', None))
        if kb is not None or pt or kp or getattr(cls, 'register_knock_tilt', 0.0):
            # (register.Strings: a key's bridge, its partner, the knock's profile and tilt)
            k.reg_keyed = 1
            pr = v[2]
            k.reg_kb[:] = [int(kb(pr, q)) if kb is not None else -1 for q in range(128)]
            k.reg_partner[:] = [int((pt or {}).get(q, -1)) for q in range(128)]
            k.reg_cross = float(getattr(cls, 'cross_bridge_coupling', 1.0))
            k.reg_partner_k = float(getattr(cls, 'partner_coupling', 1.0))
            k.reg_ktilt = float(getattr(cls, 'register_knock_tilt', 0.0) or 0.0)
            k.reg_nkp = len(kp or ())
            for i, (x, db) in enumerate(kp or ()):
                k.reg_kp_x[i], k.reg_kp_db[i] = float(x), float(db)
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
                 finish=True, legato=(), strokes=None):
        """ccs, notes and total as blockrender's; the tuning: freq the file's
        128-key table, mts {channel: [(t, table)]}, btun {channel: ratio},
        otun {channel: 12 cents}; faders the channels whose fader is a row;
        trim(program) the program's trim on the channel volume; legato
        _legato_ticks' {(channel, key, k)}; strokes (stroke_pitch,
        inner_ridge) as _prep_strokes made them, for its notes."""
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
        _, kf0, kseat, kchoke = kits()[:4]
        d.nv_song_kits(self.p, kf0, kseat)
        d.nv_song_chokes(self.p, kchoke)
        for c, n, k in legato:
            d.nv_song_legato(self.p, int(c), int(n), int(k))
        if strokes is not None:
            sp, ir = strokes
            for i, e in enumerate(notes):
                key = (e[1], e[2])
                if key in sp or key in ir:
                    d.nv_song_note_stroke(self.p, i, float(sp.get(key, 1.0)), int(key in ir))
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
        """(f0, velocity, pan, channel volume, effort, seat) of the song's
        note at index (seat: a drum's in its set, else 0), or None"""
        o = (ctypes.c_double * 6)()
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

    def slur(self, index):
        """(slurred, a slur leaves it) of the song's note at index, or None"""
        o = (I * 2)()
        if index is None or not self.d.nv_song_slur(self.p, int(index), o):
            return None
        return bool(o[0]), bool(o[1])

    def choke(self, ch, note, on):
        """Where a later strike in its exclusive class stops this note, or None"""
        o = ctypes.c_double(0.0)
        return o.value if self.d.nv_song_choke(self.p, int(ch), int(note), float(on), ctypes.byref(o)) else None

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
                -6: 'an NRPN or MPE', -7: 'mono mode',
                -9: "MIDI 2.0 at its own resolution (a value MIDI 1.0 has no number for)",
                -10: 'MIDI 2.0 groups past the second'}


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
        self._p = d.nv_midi_read(b, len(b), ctypes.byref(e))
        self.error = e.value

    @property
    def p(self):
        # (a refused file has no reading: asking it for notes or events would
        # hand the engine a null pointer and crash the process)
        if not self._p:
            raise ValueError("native.Midi: the file was refused (%s)"
                             % MIDI_REFUSED.get(self.error, self.error))
        return self._p

    def __del__(self):
        if getattr(self, '_p', None):
            self.d.nv_midi_free(self._p)
            self._p = None

    def total(self):
        return self.d.nv_midi_total(self.p)

    def banked(self):
        """True where a program change selects a bank (or a note is on one):
        the file renderer's, not live's yet"""
        return bool(self.d.nv_midi_banked(self.p))

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

    def sysex(self, i):
        """Exclusive i (an event of type 6's a): its bytes between F0 and F7."""
        buf = (ctypes.c_uint8 * 65536)()
        n = self.d.nv_midi_sysex(self.p, int(i), buf, 65536)
        return bytes(buf[:n]) if n > 0 else b""

    def master(self):
        """A master message (1), a master volume under full (2), none (0)."""
        return self.d.nv_midi_master(self.p)

    def events(self):
        """[(t, type, channel, a, b)] in message order: 0 note-on (key,
        velocity), 1 note-off, 2 control (number, value), 3 the channel's
        aftertouch (value), 4 the pitch wheel
        (-8192..8191), 5 a program change, 6 an exclusive (a: sysex(a)), 7 a
        key's polytouch (key, value)"""
        I4 = ctypes.c_int * 4
        out = []
        for i in range(self.d.nv_midi_n_events(self.p)):
            iv, t = I4(), ctypes.c_double()
            self.d.nv_midi_event(self.p, i, iv, ctypes.byref(t))
            out.append((t.value, iv[0], iv[1], iv[2], iv[3]))
        return out

    def events_x(self):
        """Each event's MIDI 2.0 value, in events()'s order: a Note On's Pitch
        7.9 (semitones), a per-note message's (type 8: a the note, b the kind --
        0 Pitch 7.25, 1 per-note bend, 2 its range, 3 per-note management with
        its reset 16 and detach 32, 4 ignored); NaN none"""
        return [self.d.nv_midi_event_x(self.p, i) for i in range(self.d.nv_midi_n_events(self.p))]

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
        volume's trim; the tuning as Song's; a bank's variations, nvrender's
        tables (song_vars)."""
        s = Song({}, [], None, freq=freq, mts=mts, btun=btun, otun=otun, faders=faders, finish=False)
        tr = (ctypes.c_double * 256)(*([float(trim(p, False)) for p in range(128)]
                                       + [float(trim(p, True)) for p in range(128)]))
        if self.banked():
            song_vars(s.p, self.d.nv_midi_gs(self.p))
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
    K, keep = k_table(classes)
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
    if hasattr(cls, 'string_detune_range'):
        lo, hi = cls.string_detune_range
        if issubclass(cls, T.HonkyTonkProperties):
            lo, hi = lo * T.honky_detune, hi * T.honky_detune
        c.detune_lo, c.detune_hi = lo, hi
    c.fixed_touch = int(bool(T.FIXED_TOUCH))
    tab = (ctypes.c_double * 128)(*[float(table[k]) if k in table else 0.0 for k in range(128)])
    cap = 88 * 4 * 130
    out = (StringMode * cap)()
    tmp = (StringMode * cap)()
    og = organ(cls) if getattr(cls, 'string_choirs', None) else None     # (a harpsichord's choirs)
    n = lib().nv_strings_og(ctypes.byref(c), ctypes.byref(got[1]), ctypes.addressof(og) if og is not None else None,
                            tab, float(pan), float(chan_vol), float(sr), out, tmp, cap)
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


def xatan(x):
    """np.arctan of float64 values, libm's atan (numpy's is SVML)."""
    import numpy as np
    x = np.ascontiguousarray(x, np.float64)
    d = lib()
    if d is None:
        return np.arctan(x)
    out = np.empty_like(x)
    d.nv_atan_n(x.size, x.ctypes.data, out.ctypes.data)
    return out


def xlog10(x):
    import numpy as np
    x = np.ascontiguousarray(x, np.float64)
    d = lib()
    if d is None:
        return np.log10(x)
    out = np.empty_like(x)
    d.nv_log10_n(x.size, x.ctypes.data, out.ctypes.data)
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


TUNING_ERRORS = {-1: "no such tuner", -2: "no such key", -3: "a bad pitch",
                 -4: "@KEY or :A4 on a tuner with no table to move", -5: "a bad raga spec"}


def tuning_table(name, reference=None):
    """blockrender.tuning_table(name) from native/tuner.cpp: {midi: Hz}, at
    the reference (note, Hz) -- tunelib's in force when not given."""
    if reference is None:
        import tunelib as TL
        reference = TL.reference()
    out = (ctypes.c_double * 128)()
    have = (ctypes.c_int * 128)()
    r = lib().nv_tuning_table(name.encode(), -1 if reference is None else int(reference[0]),
                              0.0 if reference is None else float(reference[1]), out, have)
    if r:
        raise ValueError("tuner %r: %s" % (name, TUNING_ERRORS.get(r, r)))
    return {n: out[n] for n in range(128) if have[n]}


def xtanh(x):
    """np.tanh of float64 values, libm's tanh (numpy's SIMD differs in the last bit)."""
    import numpy as np
    x = np.ascontiguousarray(x, np.float64)
    d = lib()
    if d is None:
        return np.tanh(x)
    out = np.empty_like(x)
    d.nv_tanh_n(x.size, x.ctypes.data, out.ctypes.data)
    return out


def xtanhf(x):
    """np.tanh of float32 values, libm's tanhf."""
    import numpy as np
    x = np.ascontiguousarray(x, np.float32)
    d = lib()
    if d is None:
        return np.tanh(x)
    out = np.empty(x.shape, np.float32)
    d.nv_tanhf_n(x.size, x.ctypes.data, out.ctypes.data)
    return out


def xangle(z):
    """np.angle of complex values, libm's atan2(im, re)."""
    import numpy as np
    z = np.ascontiguousarray(z, np.complex128)
    d = lib()
    if d is None:
        return np.angle(z)
    out = np.empty(z.shape, np.float64)
    d.nv_cangle_n(z.size, z.ctypes.data, out.ctypes.data)
    return out


def xcexp(z):
    """exp of complex values as exp(re) * (cos im, sin im), libm's."""
    import numpy as np
    z = np.ascontiguousarray(z, np.complex128)
    d = lib()
    if d is None:
        return np.exp(z)
    out = np.empty_like(z)
    d.nv_cexp_n(z.size, z.ctypes.data, out.ctypes.data)
    return out


def efx_ir(kind, sr, *args):
    """efxbus's Reverb ('reverb': type, pre-delay ms, Time, HF damp Hz or
    None) or Gate Reverb ('gate': type, pre-delay ms, gate ms) response, an
    array per ear, from native/efxrev.c -- or None without the library."""
    import numpy as np
    d = lib()
    if d is None:
        return None
    cap = int(10.0 * sr) + 64
    hL, hR = np.empty(cap), np.empty(cap)
    if kind == 'reverb':
        rtype, pre_ms, time, damp = args
        n = d.nv_efx_reverb_ir(float(sr), int(rtype), float(pre_ms), int(time), float(damp or 0.0),
                               hL.ctypes.data, hR.ctypes.data, cap)
    else:
        gtype, pre_ms, gate_ms = args
        n = d.nv_efx_gate_ir(float(sr), int(gtype), float(pre_ms), float(gate_ms), hL.ctypes.data, hR.ctypes.data,
                             cap)
    if n <= 0:
        raise ValueError("efx_ir: %s's response past %d samples" % (kind, cap))
    return [hL[:n].copy(), hR[:n].copy()]


def efx_conv(x, h, k, m):
    """(x * h)[k:k + m], native/efxrev.c's overlap-add (efxbus's reverbs)."""
    import numpy as np
    x = np.ascontiguousarray(x, np.float64)
    h = np.ascontiguousarray(h, np.float64)
    out = np.empty(int(m))
    if lib().nv_efx_conv(x.ctypes.data, len(x), h.ctypes.data, len(h), int(k), int(m), out.ctypes.data):
        raise ValueError("efx_conv: no plan for a response of %d" % len(h))
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


def pulse_series(T, t0, period, fmax, taper):
    """tonelib.pulse_series as native/pocketfft.c's nv_pulse_series: numpy
    1.26.4's own rfft (pocketfft, vendored) of the sampled N-wave, each bin's
    magnitude and phase libm's hypot and atan2 -- the same on every machine
    and numpy (whose complex abs and arctan2 are its SIMD loops'). [(hz, amp,
    phase)], or None where there is no library."""
    d = lib()
    if d is None:
        return None
    cap = int(round(4 * fmax * period)) // 2 + 2
    out = (ctypes.c_double * (3 * cap))()
    k = d.nv_pulse_series(float(T), float(t0), float(period), float(fmax), float(taper), out, cap)
    if k < 0 or k > cap:
        return None
    return [(out[3 * i], out[3 * i + 1], out[3 * i + 2]) for i in range(k)]


def xrfft(x):
    """The real FFT of x (its length a power of two), np.fft.rfft's layout and
    scale: native/tubeamp.cpp's, the same on every machine (numpy's
    pocketfft is not across its versions); numpy's where there is no library."""
    import numpy as np
    x = np.ascontiguousarray(x, np.float64)
    d = lib()
    n = len(x)
    if d is None or n < 2 or n & (n - 1):
        return np.fft.rfft(x)
    out = np.empty(n // 2 + 1, np.complex128)
    d.nv_rfft(x.ctypes.data, n, out.ctypes.data)
    return out


def leslie_constants():
    """leslie.py's constants as native/leslie.cpp reads them (its L_*): the
    export's LESL section, and a template cache's and a live part's."""
    import leslie as LES
    les = [LES.CROSSOVER_HZ, LES.HORN_RADIUS, LES.DRUM_RADIUS, LES.SLOW_HZ, LES.FAST_HZ, LES.DRUM_RATIO,
           LES.C_SOUND, LES.XOVER_FLOOR, LES.HORN_FLOOR, LES.HORN_SHARPNESS, LES.DRUM_DEPTH, LES.DRUM_REF_HZ,
           LES.HORN_SPIN_UP, LES.HORN_SPIN_DOWN, LES.DRUM_SPIN_UP, LES.DRUM_SPIN_DOWN,
           float(bool(LES.SIDEBANDS and LES.KERNEL_LOBE)), len(LES.CABINET_DB)]
    return [float(x) for x in les + [x for pt in LES.CABINET_DB for x in pt]]


def scan_constants():
    """scanner.py's constants and its circuit's tables (scanner.table_d) as
    native/scanner.cpp reads them: the export's SCAN section, and a live part's."""
    import numpy as np
    import scanner as SCN
    scn = [SCN.SCAN_HZ, float(bool(SCN.SIDEBANDS)), SCN.SIDEBAND_DB, SCN.FLOOR_DB, float(SCN.MAX_SIDE)]
    scn += list(SCN.BAND_HZ) + [float(x) for d in (1, 2, 3) for x in SCN.TAPS[d]] + [float(x) for x in SCN.PLATES]
    for cho in (False, True):
        fg, lg, rm, rp, mag, ph = SCN.table_d(cho)
        scn += [float(len(fg))] + [float(x) for a in (fg, lg, rm, rp) for x in a]
        scn += [float(x) for x in np.ascontiguousarray(mag).ravel()] + [float(x) for x in np.ascontiguousarray(ph).ravel()]
    return [float(x) for x in scn]


def xgamma(x):
    """gamma(x) of a float, libm's tgamma (math.gamma is CPython's own)."""
    d = lib()
    if d is None:
        import math
        return math.gamma(x)
    a, o = (C * 1)(float(x)), (C * 1)()
    d.nv_tgamma_n(1, a, o)
    return o[0]


def reed_series(gate, edge, spread, points, max_harmonic, direct):
    """FreeReedProperties._reed_series' flow spectrum from native/reed.cpp (the
    same on every machine, and the engine's); None where there is no library."""
    d = lib()
    if d is None:
        return None
    top = min(int(max_harmonic), 4096)
    out = (C * (top + 1))()
    n = d.nv_reed_series(float(gate), float(edge), float(spread), int(points), int(max_harmonic), float(direct), out)
    return tuple(out[:n])


def ep_layers(kind, params, a0, rho, f0, op, harmonics, terms, max_hz, floor_db, control):
    """ElectricPianoProperties._pickup_layers from native/epiano.cpp (the same
    on every machine, and the engine's): ((k, n, w, phase), ...); None where
    there is no library. kind 1 the Rhodes' pickup, 2 the Wurlitzer's slot."""
    d = lib()
    if d is None:
        return None
    p = (C * 5)(*[float(x) for x in params])
    out = (C * (4 * 512))()
    n = d.nv_ep_layers_cached(int(kind), p, float(a0), float(rho), float(f0), float(op), int(harmonics), int(terms),
                              float(max_hz or 0.0), float(floor_db), int(bool(control)), out, 512)
    return tuple((int(out[4 * q]), out[4 * q + 1], out[4 * q + 2], out[4 * q + 3]) for q in range(min(n, 512)))


def xcos(x):
    """np.cos of x, libm's (native.xcexp of i x)."""
    import numpy as np
    x = np.asarray(x, np.float64)
    z = np.zeros(x.shape, np.complex128)
    z.imag = x
    return np.ascontiguousarray(xcexp(z).real)


def xfft(z, axis=-1):
    """np.fft.fft of z along its last axis (its length a power of two):
    native/tubeamp.cpp's (the same on every machine), row by row."""
    import numpy as np
    z = np.ascontiguousarray(z, np.complex128)
    d = lib()
    n = z.shape[-1]
    if d is None or n < 2 or n & (n - 1) or axis not in (-1, z.ndim - 1):
        return np.fft.fft(z, axis=axis)
    out = np.empty_like(z)
    zz, oo = z.reshape(-1, n), out.reshape(-1, n)
    for r in range(zz.shape[0]):
        d.nv_cfft(zz[r].ctypes.data, n, oo[r].ctypes.data)
    return out


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
    K, keep = k_table(classes)
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
             sym_rows=(int(out[3]), int(out[42])),
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
    bl = None if F.get('BL') is None else np.ascontiguousarray(F['BL'], np.float32)
    keep.append(bl)
    sh = (ctypes.c_float * 4)(*[float(x) for x in F['sh']])
    has = F.get('DM') is not None
    dm = [np.ascontiguousarray(F[k], t) for k, t in (('DM', np.float32), ('DMO', np.int64), ('DMB', np.int64),
                                                     ('DMN', np.int64))] if has else [None] * 4
    keep.extend([a for a in dm if a is not None])
    fn = lambda f: ctypes.cast(f, ctypes.c_void_p).value       # noqa: E731
    sv = fn(BR.ensure_lib().synth_voice)
    sx = fn(BR.ensure_xdec_lib().synth_voice_xdec)
    sd = fn(BR.ensure_damp_lib().synth_voice_damp)
    # a table with a Leslie: its plain rows through synth_voice_lobe, with their lobes
    lang = F.get('LANG')
    if lang is not None:
        lang = np.ascontiguousarray(lang, np.float32)
        lsr = np.ascontiguousarray(F['lsr'], np.int32)
        lob = [np.ascontiguousarray(F[k], np.float32) for k in ('lph', 'lfl', 'lsh', 'lnm')]
        keep.extend([lang, lsr] + lob)
        lobp = (ctypes.c_void_p * 4)(*[a.ctypes.data for a in lob])
        lo = (fn(BR.ensure_lobe_lib().synth_voice_lobe), lsr.ctypes.data, lobp, lang.ctypes.data, lang.shape[1])
    else:
        lo = (None, None, None, None, 0)
    d.nv_render(sv, sx, sd, n, BR.BLK, int(F['nblk']), int(F['P']), D, Fp, Lp, Ip, tabs[0].ctypes.data,
                tabs[1].ctypes.data, tabs[2].ctypes.data, tabs[3].ctypes.data,
                None if bl is None else bl.ctypes.data, BR._NO_ROWS.ctypes.data, sh,
                BR._chunk(), float(BR.XDEC_NEPERS), float(BR.SR), float(BR.T.master_gain),
                *[a.ctypes.data if a is not None else None for a in dm], L.ctypes.data, R.ctypes.data, *lo, None,
                None, None, None, None, 0, None, 1)
    return L, R


def build_nvlive():
    """native/nvlive (the live engine), built beside libnative.so when a source
    is newer: its path."""
    lib()
    src = os.path.join(HERE, 'native', 'nvlive.cpp')
    exe = os.path.join(HERE, 'nvlive')
    so = os.path.join(HERE, 'libnative.so')
    hdr = os.path.join(HERE, 'native', 'panel.h')
    hint = os.path.join(HERE, 'native', 'hostint.h')
    hlive = os.path.join(HERE, 'native', 'hostlive.h')
    if not os.path.exists(exe) or max(os.path.getmtime(src), os.path.getmtime(hdr), os.path.getmtime(hint), os.path.getmtime(hlive),
                                      os.path.getmtime(so)) > os.path.getmtime(exe):
        tmp = '%s.%d.tmp' % (exe, os.getpid())
        subprocess.check_call(['g++', '-std=c++17', '-O2', '-march=native', '-ffp-contract=off', '-fno-builtin',
                               src, '-o', tmp, '-L' + HERE, '-lnative', '-ldl', '-lpthread',
                               '-Wl,-rpath,$ORIGIN'])
        os.replace(tmp, exe)
    return exe


def build_nvrender():
    """native/nvrender (the standalone renderer), built beside libnative.so
    when a source is newer: its path."""
    lib()
    src = os.path.join(HERE, 'native', 'nvrender.cpp')
    exe = os.path.join(HERE, 'nvrender')
    so = os.path.join(HERE, 'libnative.so')       # (the tuners are in it: native/tuner.cpp)
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
    if k is None or k.organ:
        return None                         # (a registered organ: live stamps it rank by rank)
    K = (ctypes.c_void_p * (2 * 16384 + 256))()
    K[128 * program + note] = ctypes.addressof(k)
    _pk = note_class(BR.property_class_for_note(program, 60)) if note != 60 else k
    if _pk is not None:                         # (its program's class: the drones are the program's)
        K[128 * program + 60] = ctypes.addressof(_pk)
    for i, dcls in enumerate(DRONES[:256]):     # (its drones' classes: K's drone region)
        dk = note_class(dcls)
        if dk is not None:
            K[NV_K_DRONE + i] = ctypes.addressof(dk)
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
                      float(BR.SR), dm, None)       # (kit: none -- its C default is not ctypes')
    try:
        if n < 0:
            return None
        rows = np.ctypeslib.as_array(buf, shape=(n, NCOLS)).copy() if n else np.zeros((0, NCOLS))
    finally:
        d.nv_buf_free(buf)
    dt = {c: (np.float32 if c in BR._COL_F4 else np.int32 if c in BR._COL_I4 else np.float64)
          for c in BR.EMIT_COLS}
    P = {c: rows[:, j].astype(dt[c]) for j, c in enumerate(BR.EMIT_COLS)}
    P.update(N=int(out[0]), nblk=int(out[1]), P=int(out[2]), sym_rows=(int(out[3]), int(out[42])),
             room_q=[(out[4 + 3 * i], out[5 + 3 * i], out[6 + 3 * i]) for i in range(9)])
    return final(P)


LIVE_F8 = ("om", "p0", "p0R", "fmw", "fmp", "fmpR")
LIVE_F4 = ("aL", "aR", "nf", "fa", "re", "ch", "logr", "logrA", "aft", "sus", "cv", "cc", "crl", "sj", "csc",
           "cbw", "tbav", "tau", "tcut", "vd", "vr", "vp", "delL", "delR", "az", "rdl", "nfr")
LIVE_F4N = ("gb", "gt", "gc", "vdl")
LIVE_I4 = ("gr", "cr", "br", "pl", "fx", "mk")
SLAB_BOOK = ("sw", "aL0", "aR0", "sg", "sre", "hrel", "vbase", "vrbase", "vsc")


class Slab(object):
    """native/slab.cpp's slab: live.Slab's core -- stamp, release,
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
                                        (SLAB_BOOK, np.float32), (("dk", "slot_ch", "busy"), np.int32),
                                        (("aLp", "aRp"), np.float32), ((None, None, None, "dg"), np.float32),
                                        (("tr_dep", "tr_aL", "tr_aR", "tr_st", "tr_on", "hs_dep"), np.float32),
                                        (("ls_on", "ls_horn", "ls_am", "ls_sharp", "ls_norm", "ls_ph", "ls_aL",
                                          "ls_aR"), np.float32))):
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
    or, drums, a drum set's (the program its set: each key on GM's
    percussion channel) -- each key at every velocity bucket's centre and
    every wheel step, built once (warm) and looked up (get) -- its
    templates as live's dicts."""

    def __init__(self, program, tuner='hybrid', drums=False):
        import math
        import blockrender as BR
        import damper as DM
        import patch_map as PM
        import percussion_map as PCM
        import tonelib as T
        self.d = lib()
        self.program = program
        self.drums = drums
        if drums:
            K, self.keep = k_table(lambda p, k: None, programs=())
        else:
            self.keep = []
            K = (ctypes.c_void_p * (2 * 16384))()
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
        L = leslie_constants()
        self.d.nv_tcache_leslie(self.p, (ctypes.c_double * len(L))(*L), len(L))
        if drums:
            import live as LV
            _, f0, seat, choke, skind, spar = kits()
            self.d.nv_tcache_kits(self.p, f0, seat, choke, skind, spar, float(LV.ONESHOT_FLOOR_DB))

    def __del__(self):
        if getattr(self, 'p', None):
            self.d.nv_tcache_free(self.p)
            self.p = None

    def warm(self, lo, hi, nbuckets, speeds=(None,)):
        sp = (ctypes.c_int * len(speeds))(*[-1 if v is None else int(v) for v in speeds])
        return self.d.nv_tcache_warm(self.p, int(self.program), int(lo), int(hi), int(nbuckets), sp, len(speeds))

    def get(self, note, bucket, speed=None):
        """The template as live's dict (a piano's fields, a drum's one-shot,
        its rows' own ends and its strokes' offsets), or None."""
        import numpy as np
        o = (LL * 6)()
        t = self.d.nv_tcache_get(self.p, int(note), int(bucket), -1 if speed is None else int(speed), o)
        if not t:
            return None
        n = int(o[0])
        out = dict(P=n, dur=int(o[1]), vel=int(o[2]), oneshot=bool(o[3]), send=None,
                   scatter_ms=float(self.d.nv_tmpl_scatter(t)), FT=None, KN=None,
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
        if o[4]:
            out["rof"] = col(7, 0, ctypes.c_int64)
        if o[5]:
            out["sof"] = col(8, 0, ctypes.c_int64)
        out["sym"] = np.zeros(n, bool)
        out["ring"] = np.zeros(n, bool)
        _pp = self.d.nv_tmpl_col(t, 9, 0)
        out["push"] = (np.ctypeslib.as_array(ctypes.cast(_pp, ctypes.POINTER(ctypes.c_int8)), shape=(n,)).astype(bool)
                       if _pp and n else np.zeros(n, bool))
        out["lflip"] = np.zeros(n, bool)
        # AN ORGAN'S RANKS (t["ranks"]): {name: (its columns, P, hrel)}
        import blockrender as BR
        cls = BR.property_class_for_note(self.program, note) if not self.drums else None
        if cls is not None and getattr(cls, 'registerable', False):
            for ri, r in enumerate(cls.stop_ranks):
                rn = LL(0)
                rt = self.d.nv_tmpl_rank(t, ri, ctypes.byref(rn))
                if not rt:
                    continue
                m = int(rn.value)

                def rcol(g, i, dt, rt=rt, m=m):
                    p = self.d.nv_tmpl_col(rt, g, i)
                    return np.ctypeslib.as_array(ctypes.cast(p, ctypes.POINTER(dt)), shape=(m,)).copy()
                cols = {}
                for i, c in enumerate(LIVE_F8):
                    cols[c] = rcol(0, i, ctypes.c_double)
                for i, c in enumerate(LIVE_F4):
                    cols[c] = rcol(1, i, ctypes.c_float)
                for i, c in enumerate(LIVE_F4N):
                    cols[c] = rcol(2, i, ctypes.c_float)
                for i, c in enumerate(("non", "noff")):
                    cols[c] = rcol(3, i, ctypes.c_int64)
                for i, c in enumerate(LIVE_I4):
                    cols[c] = rcol(4, i, ctypes.c_int32)
                cols["lflip"] = np.zeros(m, bool)
                out["ranks"][r[0]] = (cols, m, rcol(5, 0, ctypes.c_float))
        return out


class LivePart(object):
    """native/slab.cpp's part, live (live.Part: any native voice): its template cache, its slab, and
    live.Live's events for it block by block. The slab reads back as a
    native.Slab's does."""

    def __init__(self, cache, pid, level_db, nbuckets, speed, damper_pedal, soft_drop, soft_top, rate,
                 capacity=16384, headroom=1.0, press_db=None, detune_wheel=False):
        import live as L
        import blockrender as BR
        tab = L.pan_table()
        pt = (ctypes.c_double * (128 * 3))(*[float(x) for row in tab for x in row])
        self.d = lib()
        self.cache = cache
        self.p = self.d.nv_part_new(cache.p, int(pid), float(level_db), int(nbuckets),
                                  -1 if speed is None else int(speed), int(bool(damper_pedal)), int(soft_drop),
                                  int(soft_top), float(rate), float(BR.RETRIGGER_FADE), int(capacity),
                                  float(headroom), pt, float(L._PAN_BETA))
        self.d.nv_part_program(self.p, int(cache.program))       # (its slurs' and glides' class)
        _kl = BR.ensure_lib()                                   # (the Moog's mod rows: the kernel's own)
        self.d.nv_part_moog_kernel(self.p, ctypes.cast(_kl.moog_pitch_cells, ctypes.c_void_p).value,
                                   ctypes.cast(_kl.moog_shape_rows, ctypes.c_void_p).value,
                                   ctypes.cast(_kl.moog_coeff_rows, ctypes.c_void_p).value)
        # (the Moog extensions' kernel: a note's loops, its contours' age, its filter contour's depth)
        self.d.nv_part_moogx(self.p, ctypes.cast(BR.ensure_moogx_lib().synth_voice_moogx, ctypes.c_void_p).value,
                             None, None, None)
        self.slab = Slab.__new__(Slab)
        self.slab.d, self.slab.cap, self.slab.p = self.d, capacity, self.d.nv_part_slab(self.p)
        import damper as DMP
        self.d.nv_part_damper(self.p, float(DMP.FULL_DB_S), float(DMP.RESIDUAL), float(DMP.KNEE_DB), float(DMP.BETA),
                            float(DMP.LN10_20))
        import tonelib as T
        self.d.nv_part_press_db(self.p, float(T.PRESS_DB if press_db is None else press_db))
        self.d.nv_part_detune_wheel(self.p, int(bool(detune_wheel)))
        L = leslie_constants()
        self.d.nv_part_leslie(self.p, (ctypes.c_double * len(L))(*L), len(L))
        X = scan_constants()
        self._scan = (ctypes.c_double * len(X))(*X)
        self.d.nv_part_scan(self.p, self._scan, len(X))

    def __del__(self):
        if getattr(self, 'p', None):
            self.slab.p = None              # the part owns its slab
            self.d.nv_part_free(self.p)
            self.p = None
        if getattr(self, '_cl', None):
            self.d.nv_cl_free(self._cl)
            self._cl = None

    def bend_rows(self, n):
        """The bend rows' tables (live's Slab.BR, BC, BL), their first n."""
        import numpy as np
        br, bc, bl = np.zeros(n, np.float32), np.zeros(n, np.float64), np.zeros(2 * n, np.float32)
        m = self.d.nv_part_bend_rows(self.p, br.ctypes.data, bc.ctypes.data, bl.ctypes.data, n)
        return br[:m], bc[:m], bl[:2 * m].reshape(m, 2)

    def swap(self, pi, cache, nbuckets, speed, damper_pedal, soft_drop, soft_top, detune_wheel, choke=None,
             reg_note=None, strings=None):
        """A PATCH CHANGE (live._swap_patch), posted -- done after the next
        block's events: patch pi on cache (a TemplateCache, warmed), its
        buckets, wheel step (None: none), dampers, una corda and detune wheel;
        a drum set's exclusive classes and the keys that answer the register
        (None: as they were). The cache is kept: notes struck from it may
        still be sounding."""
        self._caches = getattr(self, '_caches', [])
        self._caches.append(cache)
        ch = None
        if choke is not None:
            ch = (ctypes.c_ulonglong * len(choke))(*choke)
        rn = None if reg_note is None else (ctypes.c_int * 128)(*[int(bool(x)) for x in reg_note])
        if strings is not None:
            # ...ANOTHER VOICE's STRINGS (live._reg_forget): (its class at key 60
            # or None, its tuning table, the rate, the register's scale) -- its
            # bank as live's worker builds it, none for a voice without
            import damper as DMP
            cls, table, rate, scale = strings
            try:
                modes, M, k = live_bank(cls, table, rate, scale)
            except Exception:
                modes, M, k = (StringMode * 1)(), 0, (0.0, 0.0, 0.0, 0.0, 128, float(DMP.BETA))
            rel = float(getattr(cls, 'release_valve_time', 0.12) or 0.12) * rate if cls is not None else 0.12 * rate
            k6 = (ctypes.c_double * 6)(k[0], k[1], k[2], k[3], k[5], rel)
            nt = (ctypes.c_int * 128)(*[int(bool(x)) for x in (reg_note or [0] * 128)])
            chs = live_bank_choirs(cls) if (M and cls is not None) else None
            self._bank = (modes, chs)
            if chs is not None:
                self.d.nv_part_swap_bank(self.p, modes, M, k6, int(k[4]), int(bool(getattr(cls, 'damper_pedal', True))),
                                       nt, chs[0], chs[1], chs[2], chs[3], chs[4])
            else:
                self.d.nv_part_swap_bank(self.p, modes, M, k6, int(k[4]),
                                       int(bool(getattr(cls, 'damper_pedal', True))) if cls is not None else 0,
                                       nt, 0, None, 1.0, 0, None)
            kc = note_class(cls) if (M and cls is not None) else None
            if kc is not None and kc.reg_keyed:
                self._keyed = kc                # (a dulcimer's bridges by key: kept alive with the part)
                self.d.nv_part_swap_bank_keys(self.p, ctypes.byref(kc))
        self.d.nv_part_swap(self.p, int(pi), cache.p, int(cache.program), int(bool(cache.drums)), int(nbuckets),
                          -1 if speed is None else int(speed), int(bool(damper_pedal)), int(soft_drop),
                          int(soft_top), int(bool(detune_wheel)), ch, rn)

    def register(self, cls, table, rate, scale, reg_note):
        """The part's free strings, as live's register (live._reg_*) with a
        worker that answers each job as it is sent: cls the part's class at
        key 60 (its strings, dampers, release), table its tuning, scale
        blockrender.REGISTER_SCALE, reg_note which keys' classes answer."""
        import damper as DMP
        import blockrender as BR
        self._modes, M, k = live_bank(cls, table, rate, scale)
        rel = float(getattr(cls, 'release_valve_time', 0.12) or 0.12) * rate
        flags = (ctypes.c_int * 128)(*[int(bool(x)) for x in reg_note])
        self.d.nv_part_register(self.p, self._modes, M, *k, int(bool(getattr(cls, 'damper_pedal', True))), rel,
                              float(DMP.FULL_DB_S), float(DMP.RESIDUAL), float(DMP.LN10_20), int(BR.BLK), flags)
        ch = live_bank_choirs(cls)
        if ch is not None:
            self._choirs = ch
            self.d.nv_part_reg_choirs(self.p, *ch)
        kc = note_class(cls)
        if kc is not None and kc.reg_keyed:
            self._keyed = kc                    # (a dulcimer's bridges by key: kept alive with the part)
            self.d.nv_part_reg_keys(self.p, ctypes.byref(kc))

    def reg_dropped(self):
        return self.d.nv_part_reg_dropped(self.p)

    def gpu(self, backend="cl", gpu_min=1000, nthreads=4):
        """Render on the GPU, as live.GpuRenderer: the setup through
        blockrender's GPU builds, the samples on OpenCL ("cl", native/gpu.cpp)
        or the C reference ("c", voice_samples). A block with fewer than
        gpu_min busy slots stays on the CPU."""
        import blockrender as BR
        g, gd = BR.ensure_gpu_lib(), BR.ensure_gpu_damp_lib()
        fn = lambda f: ctypes.cast(f, ctypes.c_void_p).value       # noqa: E731
        cl = None
        if backend == "cl":
            sz = (ctypes.c_int * 3)()
            g.voice_sizes(sz)
            err = ctypes.create_string_buffer(512)
            cl = self.d.nv_cl_new(os.fsencode(HERE), sz, err, 512)
            if not cl:
                raise RuntimeError("native GPU: %s" % err.value.decode())
        self._cl = cl
        self._gl = (g, gd)
        self.d.nv_part_gpu(self.p, fn(g.voice_block), fn(gd.voice_block), fn(gd.voice_damp_set),
                         fn(g.voice_samples), fn(g.voice_sizes), cl, int(gpu_min), int(nthreads))
        gm = BR.ensure_gpu_moogx_lib()          # (the Moog extensions' build of the setup)
        self.d.nv_part_moogx(self.p, fn(BR.ensure_moogx_lib().synth_voice_moogx), fn(gm.voice_block),
                             fn(gm.voice_damp_set), fn(gm.voice_moogx_set))

    def on_gpu(self):
        return bool(self.d.nv_part_on_gpu(self.p))

    def room(self, ir, mir, frames):
        """live.RoomTail's late room from its IRs ((n, 2) float32; mir the
        modes', or None), through live's own convolver.c."""
        import numpy as np
        import live as L
        cd = L._conv_dll()
        self._ir = np.ascontiguousarray(ir, np.float32)
        self._mir = None if mir is None else np.ascontiguousarray(mir, np.float32)
        fn = lambda f: ctypes.cast(f, ctypes.c_void_p).value       # noqa: E731
        self.d.nv_part_room(self.p, fn(cd.conv_new), fn(cd.conv_process), fn(cd.conv_free), self._ir.ctypes.data,
                          len(self._ir), None if self._mir is None else self._mir.ctypes.data,
                          0 if self._mir is None else len(self._mir), int(frames))

    def amp_ahead(self, blocks, hold=True):
        """live.LIVE_AMP_LOOKAHEAD (blocks) and LIVE_AMP_HOLD, as a check sets them."""
        self.d.nv_part_amp_ahead(self.p, int(blocks), int(bool(hold)))

    def post(self, thresh=0.70, bend_range=2.0, mod_cents=35.0):
        """The limiter's knee (live.thresh), the pitch wheel's range and the
        mod wheel's (live.bend_range, live.mod_cents)."""
        self.d.nv_part_post(self.p, float(thresh), float(bend_range), float(mod_cents))

    def output(self, n0, frames):
        """live's callback after its step: the render, the room on the send,
        the limiter -- (L, R) float32."""
        import numpy as np
        import blockrender as BR
        L, R = np.empty(frames, np.float32), np.empty(frames, np.float32)
        fn = lambda f: ctypes.cast(f, ctypes.c_void_p).value       # noqa: E731
        self.d.nv_part_output(self.p, int(n0), int(frames), L.ctypes.data, R.ctypes.data,
                            fn(BR.ensure_lib().synth_voice), fn(BR.ensure_xdec_lib().synth_voice_xdec),
                            fn(BR.ensure_damp_lib().synth_voice_damp), BR.BLK, float(BR.T.master_gain))
        return L, R

    def shed(self, n, frac):
        """live.Slab.shed: the highest frac of the partials sounding at n end."""
        return self.d.nv_part_shed(self.p, int(n), float(frac))

    def govern(self, ms, budget_ms, n):
        """live's governor after a block of ms against budget_ms (the next at n)."""
        return self.d.nv_part_govern(self.p, float(ms), float(budget_ms), int(n))

    def dm(self):
        """The damper tracks' values (live.Slab.DM): two a track."""
        import numpy as np
        out = np.zeros(2 * 256, np.float32)
        self.d.nv_part_dm(self.p, out.ctypes.data)
        return out

    def event(self, msg):
        """A mido message for the next block (note-on, note-off, control change,
        channel aftertouch, the pitch wheel)."""
        if msg.type == "note_on" and msg.velocity > 0:
            self.d.nv_part_event(self.p, 0, msg.channel, msg.note, msg.velocity)
        elif msg.type in ("note_on", "note_off"):
            self.d.nv_part_event(self.p, 1, msg.channel, msg.note, 0)
        elif msg.type == "control_change":
            self.d.nv_part_event(self.p, 2, msg.channel, msg.control, msg.value)
        elif msg.type == "aftertouch":
            self.d.nv_part_event(self.p, 3, msg.channel, msg.value, 0)
        elif msg.type == "pitchwheel":
            self.d.nv_part_event(self.p, 4, msg.channel, msg.pitch, 0)

    def block(self, n0, blk):
        self.d.nv_part_block(self.p, int(n0), int(blk))

    def render(self, n0, frames, send=False):
        """Renderer.render's block: (L, R) float32, and with send the room's
        send pair -- (L, R, SL, SR)."""
        import numpy as np
        import blockrender as BR
        L, R = np.empty(frames, np.float32), np.empty(frames, np.float32)
        SL = np.empty(frames, np.float32) if send else None
        SR = np.empty(frames, np.float32) if send else None
        fn = lambda f: ctypes.cast(f, ctypes.c_void_p).value       # noqa: E731
        self.d.nv_part_render(self.p, int(n0), int(frames), L.ctypes.data, R.ctypes.data,
                            SL.ctypes.data if send else None, SR.ctypes.data if send else None,
                            fn(BR.ensure_lib().synth_voice), fn(BR.ensure_xdec_lib().synth_voice_xdec),
                            fn(BR.ensure_damp_lib().synth_voice_damp), BR.BLK,
                            float(BR.T.master_gain))
        return (L, R, SL, SR) if send else (L, R)


ROUTE_SRC = {"cc": 0, "bend": 1, "pressure": 2, "note": 3}
ROUTE_HALF = {"up": 0, "down": 1, "both": 2}
ROUTE_DST = {"bend": -1, "pressure": -2, "mono": -3}


def route_args(r):
    """A live.Route as nv_rt_add's (src, arg, dst, keep, channel, latch, press);
    a destination live's catalogue does not have stays one (-99: no output)."""
    kind = r.src[0]
    arg = (ROUTE_HALF.get(r.src[1] if len(r.src) > 1 else "up", 0) if kind == "bend"
           else int(r.src[1]) if kind in ("cc", "note") else 0)
    dst = ROUTE_DST.get(r.dst, -99) if isinstance(r.dst, str) else int(r.dst)
    return (ROUTE_SRC[kind], arg, dst, int(r.keep), -1 if r.channel is None else int(r.channel),
            int(r.latch), int(r.press))


class Router(object):
    """native/slab.cpp's routes (live.Route, Live.on_midi's pass): feed(msg)
    -> the messages it becomes, as on_midi hands them on."""

    def __init__(self, routes):
        self.d = lib()
        self.p = self.d.nv_rt_new()
        for r in routes:
            self.d.nv_rt_add(self.p, *route_args(r))

    def __del__(self):
        if getattr(self, 'p', None):
            self.d.nv_rt_free(self.p)
            self.p = None

    def feed(self, msg):
        import mido
        if msg.type == "aftertouch":
            m = (3, msg.channel, msg.value, 0)
        elif msg.type == "note_on" and msg.velocity > 0:
            m = (0, msg.channel, msg.note, msg.velocity)
        elif msg.type in ("note_on", "note_off"):
            m = (1, msg.channel, msg.note, 0)
        elif msg.type == "control_change":
            m = (2, msg.channel, msg.control, msg.value)
        elif msg.type == "pitchwheel":
            m = (4, msg.channel, msg.pitch, 0)
        else:
            return [msg]
        out = (ctypes.c_int * 64)()
        n = self.d.nv_rt_feed(self.p, *m, out, 16)
        got = []
        for q in range(n):
            t, ch, a, b = out[4 * q:4 * q + 4]
            if (t, ch, a, b) == m:
                got.append(msg)             # passed on as it came (a release's velocity too)
                continue
            got.append(mido.Message("note_on", channel=ch, note=a, velocity=b) if t == 0 else
                       mido.Message("note_off", channel=ch, note=a, velocity=0) if t == 1 else
                       mido.Message("control_change", channel=ch, control=a, value=b) if t == 2 else
                       mido.Message("aftertouch", channel=ch, value=a) if t == 3 else
                       mido.Message("pitchwheel", channel=ch, pitch=a))
        return got


class KeyPedal(Router):
    """A key held as the sustain pedal, pushed into to lower the dampers: the
    router of live.Route(("note", key), 64) alone."""

    def __init__(self, key):
        import live as L
        Router.__init__(self, [L.Route(("note", int(key)), 64)])


def live_bank_class(cls):
    """What nv_strings builds live's string bank for cls from, at any tuning:
    (VoiceInit, VoiceSnap) -- the class's, the honky-tonk's detune as the
    worker has it (1.0: a process of its own, where no file's channel has
    set tonelib.honky_detune). native_export.py writes both, so nvlive can
    build the bank again at a tuner of its own."""
    import tonelib as T
    got = _class(cls)
    if got is None:
        raise ValueError("%s is not the engine's" % cls.__name__)
    c = VoiceInit.from_buffer_copy(got[0])
    if hasattr(cls, 'string_detune_range'):
        c.detune_lo, c.detune_hi = cls.string_detune_range
    c.fixed_touch = int(bool(T.FIXED_TOUCH))
    return c, got[1]


def live_bank_choirs(cls):
    """A harpsichord's choirs as its live register couples them: (choir
    bridges, cross_bridge_coupling, buffs as (buffed, plain) pairs, flat),
    as ctypes arrays -- or None for one row of strings."""
    og = organ(cls) if getattr(cls, 'string_choirs', None) else None
    if og is None or not og.n_choir:
        return None
    br = (ctypes.c_long * og.n_choir)(*[og.choir_bridge[i] for i in range(og.n_choir)])
    bf = (ctypes.c_int * max(1, 2 * og.n_buff))(*[og.buff[q][e] for q in range(og.n_buff) for e in (0, 1)])
    return og.n_choir, br, float(og.cross), og.n_buff, bf


def live_bank(cls, table, sr, scale=1.0):
    """live's register worker's string bank for a piano class (register.Strings
    at pan 0, full volume) from native/strings.c, and its LiveChannel's
    constants: (modes, M, (kappa, knock, fall, floor, damper_top, BETA))."""
    import register as RG
    import damper as DMP
    c, snap = live_bank_class(cls)
    tab = (ctypes.c_double * 128)(*[float(table[k]) if k in table else 0.0 for k in range(128)])
    cap = 88 * 4 * 130
    modes = (StringMode * cap)()
    tmp = (StringMode * cap)()
    og = organ(cls) if getattr(cls, 'string_choirs', None) else None     # (a harpsichord's choirs)
    M = lib().nv_strings_og(ctypes.byref(c), ctypes.byref(snap), ctypes.addressof(og) if og is not None else None,
                            tab, 0.0, 1.0, float(sr), modes, tmp, cap)
    if M < 0:
        raise ValueError("too many modes")
    P = RG._isolated(cls, 261.63, 0.0, 1.0)         # live_worker's props
    return modes, M, (float(getattr(P, 'register_gain', 0.0)) * scale,
                      float(getattr(P, 'register_knock_gain', 0.0)) * scale,
                      float(getattr(P, 'register_knock_falloff', 0.0)),
                      float(RG.floor_of(P)), int(getattr(P, 'damper_top', 128)), float(DMP.BETA))


class LiveReg(object):
    """native/livereg.cpp: register.LiveChannel for a piano class, its jobs
    by the same names. Each answers as LiveChannel's does: (modes, z), and a
    strike's forced rows [(slot, weight, decay, value)] too; floor() the
    floor its last answer was made at."""

    LIVE_DRV = ("om", "p0", "delL", "aM", "non", "logr", "logrA", "aft", "sus", "tbav", "tau", "tcut")

    def __init__(self, cls, table, sr, scale=1.0):
        import numpy as np
        self.d = lib()
        self._modes, self.M, k = live_bank(cls, table, sr, scale)
        self.p = self.d.nv_lreg_new(self._modes, self.M, float(sr), *k)
        self._choirs = live_bank_choirs(cls)
        if self._choirs is not None:
            self.d.nv_lreg_choirs(self.p, *self._choirs)
        self._np = np

    def __del__(self):
        if getattr(self, 'p', None):
            self.d.nv_lreg_free(self.p)
            self.p = None

    def _keys(self, keys):
        return self._np.ascontiguousarray(list(keys), self._np.int32)

    def _answer(self, n):
        np = self._np
        idx = np.empty(max(n, 1), np.int64)
        z = np.empty(max(n, 1), np.complex128)
        fl = ctypes.c_double()
        nf = self.d.nv_lreg_answer(self.p, idx.ctypes.data, z.ctypes.data, ctypes.byref(fl))
        self.last_floor = fl.value
        return idx[:n], z[:n], nf

    def floor(self):
        return self.last_floor

    def strike(self, sid, key, at, drv, free_keys, plucked=None):
        np = self._np
        R = len(drv['om'])
        cols = np.ascontiguousarray(np.stack([np.asarray(drv[c], np.float64) for c in self.LIVE_DRV])
                                    if R else np.zeros((len(self.LIVE_DRV), 0)))
        slot = np.ascontiguousarray(drv['slot'], np.int64) if R else np.zeros(1, np.int64)
        fk = self._keys(free_keys)
        if plucked is not None or 'choir' in drv:
            pk = self._keys(plucked if plucked is not None else [0])
            chs = np.ascontiguousarray(drv['choir'], np.int64) if 'choir' in drv and R else None
            n = self.d.nv_lreg_pluck(self.p, int(sid), int(key), float(at), R, cols.ctypes.data, slot.ctypes.data,
                                     fk.ctypes.data, len(fk), pk.ctypes.data,
                                     len(plucked) if plucked is not None else -1,
                                     chs.ctypes.data if chs is not None else None)
        else:
            n = self.d.nv_lreg_strike(self.p, int(sid), int(key), float(at), R, cols.ctypes.data, slot.ctypes.data,
                                      fk.ctypes.data, len(fk))
        idx, z, nf = self._answer(n)
        sl = np.empty(max(nf, 1), np.int64)
        w, b = np.empty(max(nf, 1)), np.empty(max(nf, 1))
        v = np.empty(max(nf, 1), np.complex128)
        self.d.nv_lreg_forced(self.p, sl.ctypes.data, w.ctypes.data, b.ctypes.data, v.ctypes.data)
        forced = [(int(sl[q]), float(w[q]), float(b[q]), complex(v[q])) for q in range(nf)]
        return idx, z, forced

    def release(self, sid, at, free_keys):
        fk = self._keys(free_keys)
        n = self.d.nv_lreg_release(self.p, int(sid), float(at), fk.ctypes.data, len(fk))
        return self._answer(n)[:2]

    def damp(self, keys):
        k = self._keys(keys)
        self.d.nv_lreg_damp(self.p, k.ctypes.data, len(k))

    def felt(self, at, keys, rates):
        k = self._keys(keys)
        r = self._np.ascontiguousarray(rates, self._np.float64)
        n = self.d.nv_lreg_felt(self.p, float(at), k.ctypes.data, r.ctypes.data, len(k))
        return self._answer(n)[:2]


_SONG_VARS = {}


def song_vars(song_p, gs):
    """Bank select's tables into an engine song (nv_song_vars), as nvrender
    loads them from the export's VARS: each entry's layers, its trim (in a
    file that speaks GS or not), GS's and GM 2's tables. Made once a process."""
    import patch_map as PM
    key = bool(gs)
    if key not in _SONG_VARS:
        slots, entries, vgs, vgm2 = variation_tables()
        nls, ls, tr = [0], [], [1.0]
        for p, v, lys in entries[1:]:
            nls.append(len(lys))
            for x in lys:
                ls.extend(int(a) for a in x)
            tr.append(float(PM.program_trim(PM.VariationProgram(p, v), gs=key)))
        I_, D_ = ctypes.c_int, ctypes.c_double
        _SONG_VARS[key] = (len(nls), (I_ * len(nls))(*nls), (I_ * max(1, len(ls)))(*ls), (D_ * len(tr))(*tr),
                           (I_ * (5 * 128 * 128))(*[e for m in vgs for row in m for e in row]),
                           (I_ * (128 * 128))(*[e for row in vgm2 for e in row]))
    lib().nv_song_vars(song_p, *_SONG_VARS[key])
    # ...and each one-tone variation's organ, its slot's (nvrender's ent_organ)
    if 'organs' not in _SONG_VARS:
        slots, entries = variation_tables()[:2]
        so = (ctypes.c_void_p * max(1, len(slots)))()
        for p, v, lys in entries[1:]:
            pc = PM.property_class_for_program(PM.VariationProgram(p, v))
            o = organ(pc) if len(lys) == 1 and getattr(pc, 'registerable', False) else None
            if o is not None:
                so[lys[0][0]] = ctypes.addressof(o)
        _SONG_VARS['organs'] = (len(slots), so)
    lib().nv_song_slot_organs(song_p, *_SONG_VARS['organs'])


def sfx_prog_key(cls):
    """A melodic SFX class's kit key, as kits()' stroke tables index it: (the
    program whose kit it is, the key or -1 for the note's own), (-1, -1) none."""
    so = getattr(cls, 'sfx_strokes_of', None)
    if not so:
        return -1, -1
    import percussion_map as PM
    p = next((p for p in range(128) if PM.kit_for_program(p) == so[0]), None)
    if p is None and so[0] >= 128:
        # (a map's own set -- the Morse keyboard's: after the programs', in map_kits' order)
        ids = sorted(k for k in PM.KITS if k >= 128)
        p = 128 + ids.index(so[0]) if so[0] in ids else None
    return (-1, -1) if p is None else (p, -1 if so[1] is None else int(so[1]))


def sfx_strokes_ok(cls):
    """Whether the engine plays a melodic SFX class's strokes: none, or its
    kit key's table among kits()' (stroke_spec)."""
    if not sfx_strokes(cls):
        return True
    p, key = sfx_prog_key(cls)
    if p < 0:
        return False
    import percussion_map as PM
    so = cls.sfx_strokes_of
    skind, q0 = (kits()[4], 128 * p) if p < 128 else (map_kits()[5], 128 * (p - 128))
    keys = range(128) if key < 0 else (key,)
    return all(skind[q0 + k] for k in keys if PM.rasp_strokes(k, 0.0, 1.0, kit=so[0]) is not None)


def sfx_strokes(cls):
    """Whether a melodic SFX class's kit key has strokes (sfx_strokes_of,
    _prep_strokes' rasp_strokes: a dog's barks, the gallop's hooves): the
    engine's melodic notes have none yet."""
    so = getattr(cls, 'sfx_strokes_of', None)
    if not so:
        return False
    import percussion_map as PM
    keys = range(128) if so[1] is None else (so[1],)
    return any(PM.rasp_strokes(k, 0.0, 1.0, kit=so[0]) is not None for k in keys)


def variation_tables():
    """BANK SELECT for native/ (native_export's VARS): (slots, entries, gs, gm2).
    slots: [(program, variation key, layer or -1, [128 classes or None])] --
    a variation's class at each key (property_class_for_note), a layered
    one's layer's (layer_class), None where the engine does not play it;
    entries: [None] + [(program, variation, [(slot, semitones, lowest and
    highest velocity)])] -- what a program change selects, one slot or a
    layered set; gs[m][p][msb] the entry GS's bank msb selects for program p
    under map m (0: a CC32 naming no map, its bank read as is; 1-4 the Sound
    Canvas maps: patch_map.map_bank), gm2[p][lsb] GM 2's (MSB 121), 0 the
    capital tone. A variation the engine does not play whole -- an organ, a
    kit's strokes borrowed (sfx_strokes_of), a key it has no class for --
    has its slots None: its notes are refused, not played as the capital."""
    import patch_map as P
    import blockrender as B
    slots, entries, ent = [], [None], {}

    # (...and the note loop's own the engine has not: a tone's insertion
    # effect, a melodic note's sounding octaves)
    def ok(c):
        return (isinstance(c, type) and sfx_strokes_ok(c)
                and not (getattr(c, 'insertion_efx', None) and efx_chain(c) is None)
                and note_class(c) is not None)

    for (p, v) in sorted(P.VARIATIONS):
        vp = P.VariationProgram(p, v)
        lys = P.layers_of(vp)
        if lys:
            layer_slots, whole = [], True
            # (a layer's organ: the engine's where the variation's own class
            # is registered and the layer is of its family -- the part's
            # registration is that class's, its layers' notes ride it -- else Python's)
            vpc = P.property_class_for_program(vp)
            vfam = (B.organ_family(vpc) if isinstance(vpc, type) and getattr(vpc, 'registerable', False)
                    and organ(vpc) is not None else None)

            # (a layer of another family -- Technorg Hit's organ stab on the
            # orchestra hit -- its own registration on the channel, as
            # _prep_organ_rows keys them: (channel, organ_family))
            def reg_ok(c):
                return (not getattr(c, 'registerable', False) or (vfam is not None and B.organ_family(c) == vfam)
                        or organ(c) is not None)
            for lp, st, vlo, vhi in lys:
                cl = [P.layer_class(lp, k) for k in range(128)]
                whole = whole and all(ok(c) and reg_ok(c) for c in cl if c is not None)
                slots.append((p, v, int(lp.layer), cl))
                layer_slots.append((len(slots) - 1, int(st), int(vlo), int(vhi)))
            if not whole:
                for q, _, _, _ in layer_slots:
                    slots[q] = slots[q][:3] + ([None] * 128,)
        else:
            cl = [B.property_class_for_note(vp, k) for k in range(128)]
            if not all(ok(c) for c in cl if c is not None):
                cl = [None] * 128
            slots.append((p, v, -1, cl))
            layer_slots = [(len(slots) - 1, 0, 0, 127)]
        ent[(p, v)] = len(entries)
        entries.append((p, v, layer_slots))
    gs = [[[0] * 128 for _ in range(128)] for _ in range(5)]
    for m in range(5):
        for p in range(128):
            for msb in range(1, 128):
                vk = P.map_bank(p, msb, m if m else 0)
                gs[m][p][msb] = ent.get((p, vk), 0) if vk else 0
    gm2 = [[0] * 128 for _ in range(128)]
    for p in range(128):
        for lsb in range(1, 128):
            vk = P.gm2_bank(p, lsb)
            gm2[p][lsb] = ent.get((p, vk), 0) if vk else 0
    return slots, entries, gs, gm2
