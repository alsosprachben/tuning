#!/usr/bin/env python3
"""Export what the native renderer needs from the Python, once: OUT.nvx

    python3 examples/native_export.py OUT.nvx [--tuner=NAME] [--room=NAME] [--live [--fresh]]

native/nvrender renders a General MIDI piano file to the dry WAV and room
sidecar blockrender writes, with no Python at runtime. What it cannot work out
itself is written here, from the classes it was checked against:

  the render's constants   SR, BLK, the kernel's chunk, the master gain, the
                           ring's floor and limit, the fast-burst threshold,
                           the register's scale, the felt's law (damper.py),
                           the emitter's rest state, the room's bands, the
                           shutter, the room's name (for the sidecar)
  the tuning               the tuner's 128-key table (0 where it has no key)
  the trims                patch_map.program_trim for each program, melodic
                           and drum set, in a GM file and in a GS one
  the voices               each native class's NoteClass (native.py),
                           and which class each (program, key) plays (-1:
                           not the engine's), then each drum set's (drum
                           program, key)
  the drum sets            each drum program's keys' pitch and seat (0
                           where the set has none: native.kits), and the
                           keys a strike on each stops (two 64-bit words),
                           and its gesture's strokes (native.stroke_spec:
                           a kind, native.SPAR numbers)
  the columns              each EMIT_COLS column's type in the table (_COL_F4,
                           _COL_I4) and in prepare's result (FINAL_DTYPES)

The kernel libraries are blockrender's (built here if they are not yet):
their paths go in too. Binary, little-endian, for this machine.

--room: the voices packed in that room, a file's (a GS file's reverb macro
chose it: nvrender refuses one the export's room is not).

--live: for native/nvlive, at live's rate and block (48 kHz, 128 a block,
live's tuner, hybrid, unless --tuner says), and after the rest a LIVE
section: live's pan table (CC10 -> shadow alphas, half the ears' delay) and
the head's beta, the slab's headroom (live's 4 dB), and each native
program's part as live.Patch makes it -- its velocity buckets, wheel steps
and default step, dampers, una corda's strings and the instrument's top.
Then an LREG section, each program's free strings as live's register
builds them (native.live_bank: the string bank at the part's tuning, its
LiveChannel's constants), its dampers and release, damper.py's felt, which
keys' classes answer (live._reg_voice), and what the bank is built from
(native.live_bank_class), for nvlive at another tuner -- an M of 0 where
none.
Then LGPU (live's GPU renderer's builds), LROOM (live's convolver library
and the room's late tail, live.room_irs: the diffuse tail's and the modes'
impulse responses, stereo; none in a room without one) and LROUTE (the
session's routes, native.route_args each).

--live TAKES THE LAST SESSION, as live starts (live.load_session; --fresh:
not): its room (--room says otherwise; else TUNING_ROOM, else the hall),
which the voices are packed in and the tail is drawn for, its master level,
the slab's headroom, the pressure's lift, the limiter's knee, the wheel's
range and its routes.
"""
import ctypes
import math
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

MAGIC = b"NVX1"

# VARIATIONS NOT LIVE YET: nvlive refuses them (a 0 VLIV record) -- 117:24,
# Jngl SD Roll: its velocity probe (live.Patch._vel_dependent) rolls about
# 80 bounces a second, each a whole snare stroke (21,924 rows), past 2.5 GB
# on its own; refused until the roll is cheaper (bounces sharing a ring, or
# quiet bounces with fewer partials -- Ben's call)
# (125:10, the Morse keyboard, played since: a melodic cache whose class
# borrows a kit key's strokes gives its template's song the sets' tables,
# nv_tcache_stroke_kits)
LIVE_REFUSED = {(117, 24)}


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    if not args:
        print(__doc__)
        return 2
    import blockrender as B
    sess = {}
    if "live" in opt:
        B.set_sample_rate(48000)
        B.BLK = 128
        import live as L
        sess = ({} if "fresh" in opt else L.load_session()) or {}
        room_name = opt.get("room") or sess.get("room") or os.environ.get("TUNING_ROOM") or "hall"
        # live.Live._apply_room: the room every voice is built in, before they are packed
        if room_name == "dry":
            os.environ["TUNING_REFLECT"] = "0"
        else:
            os.environ.pop("TUNING_REFLECT", None)
            import tonelib as _T
            _T.set_room(room_name)
        if "master_db" in sess:
            import tonelib as _T
            _T.master_gain = 10.0 ** (float(sess["master_db"]) / 20.0)
    elif opt.get("room"):
        # A FILE'S ROOM (blockrender.prepare: a GS file's reverb macro chose it)
        import tonelib as _T
        _T.set_room(opt["room"])
    import damper as DM
    import native as N
    import patch_map as PM
    import percussion_map as PCM
    import tonelib as T
    tuner = opt.get("tuner") or ("hybrid" if "live" in opt else "hybrid440")
    freq = B.tuning_table(tuner)
    classes, idx, cmap = [], {}, []
    for prog in range(128):
        for key in range(128):
            cls = B.property_class_for_note(prog, key)
            k = N.note_class(cls) if cls is not None else None
            if k is None:
                cmap.append(-1)
                continue
            if cls not in idx:
                idx[cls] = len(classes)
                classes.append(bytes(k))
            cmap.append(idx[cls])
    # ...and each drum set's keys the engine plays (native.kits), after them
    kcls, kf0, kseat, kchoke, kskind, kspar = N.kits()
    for cls in kcls:
        k = N.note_class(cls) if cls is not None else None
        if k is None:
            cmap.append(-1)
            continue
        if cls not in idx:
            idx[cls] = len(classes)
            classes.append(bytes(k))
        cmap.append(idx[cls])
    # ...and THE MAPS' OWN DRUM SETS (native.map_kits: SC-88's, SC-88 Pro's),
    # their keys' classes among the rest (MKIT, below)
    mk_ids, mk_cls, mk_f0, mk_seat, mk_choke, mk_skind, mk_spar = N.map_kits()
    mk_map = []
    for cls in mk_cls:
        k = N.note_class(cls) if cls is not None else None
        if k is None:
            mk_map.append(-1)
            continue
        if cls not in idx:
            idx[cls] = len(classes)
            classes.append(bytes(k))
        mk_map.append(idx[cls])
    # ...and THE VARIATIONS (bank select: native.variation_tables), each slot's
    # keys after them
    vslots, ventries, vgs, vgm2 = N.variation_tables()
    import patch_map as PM_
    vmap = []
    for _p, _v, _l, cl in vslots:
        for cls in cl:
            k = N.note_class(cls) if cls is not None else None
            if k is None:
                vmap.append(-1)
                continue
            if cls not in idx:
                idx[cls] = len(classes)
                classes.append(bytes(k))
            vmap.append(idx[cls])
    vpcls = {}
    for _p, _v, _ls in ventries[1:]:
        cls = PM_.property_class_for_program(PM_.VariationProgram(_p, _v))
        k = N.note_class(cls) if isinstance(cls, type) else None
        if k is None:
            vpcls[(_p, _v)] = -2 if any(getattr(cls, a, 0.0) > 0.0 for a in (
                'breath_wobble_db', 'breath_noise_wobble_db', 'breath_pitch_cents')) else -1
            continue
        if cls not in idx:
            idx[cls] = len(classes)
            classes.append(bytes(k))
        vpcls[(_p, _v)] = idx[cls]
    # ...and THE DRONES' CLASSES (native.DRONES: a bagpipe's)
    for cls in list(N.DRONES):
        k = N.note_class(cls)
        if k is not None and cls not in idx:
            idx[cls] = len(classes)
            classes.append(bytes(k))
    # A STRUCK LAYER's CLASS (an orchestra hit's timpani): among the classes,
    # and its index in the class that strikes it (NoteClass.sl_idx)
    for cls in list(idx):
        lcls = N._SL_CLS.get(cls)
        if lcls is None:
            continue
        if lcls not in idx:
            idx[lcls] = len(classes)
            classes.append(bytes(N.note_class(lcls)))
        k = N.NoteClass.from_buffer_copy(classes[idx[cls]])
        k.sl_idx = idx[lcls]
        classes[idx[cls]] = bytes(k)
    # THE REGISTERED ORGANS (native.organ): each organ class's table, and each
    # program's organ (property_class_for_program's: -1 none, -2 an organ the
    # engine does not play)
    ocls = {c: i for c, i in idx.items()}
    organs, oidx = [], {}
    cls_organ = [-1] * len(classes)
    for c, i in ocls.items():
        if getattr(c, 'registerable', False) and N.organ(c) is not None:
            oidx[c] = len(organs)
            organs.append(bytes(N.organ(c)))
            cls_organ[i] = oidx[c]
    prog_organ = []
    for prog in range(128):
        pc = B.property_class_for_program(prog)
        if not getattr(pc, 'registerable', False):
            prog_organ.append(-1)
        elif N.organ(pc) is None or N.note_class(pc) is None:
            prog_organ.append(-2)
        else:
            if pc not in oidx:
                oidx[pc] = len(organs)
                organs.append(bytes(N.organ(pc)))
            prog_organ.append(oidx[pc])
    # (live's Moogs: knob-neutral templates the slab weighs from the panel,
    # one stamp a layer, a unison's voices each a stamp of its own, an
    # MF-104M's repeats their own keys, SYNC locked under a held note -- all
    # but a class with no native panel)
    def _moog_later(c):
        import moog as MG
        sp = N.moog_spec(c)
        return sp is None
    _moogs = {i for c, i in idx.items() if N.kit_drum(c) == 6 and _moog_later(c)}
    cmap_live = [-1 if x in _moogs else x for x in cmap]
    trims = []
    for gs in (False, True):
        trims += [float(PM.program_trim(p, False, gs=gs)) for p in range(128)]
        trims += [float(PM.program_trim(PCM.DrumProgram(p), True, gs=gs)) for p in range(128)]
    libs = [os.fsencode(getattr(B, f)()._name) for f in ("ensure_lib", "ensure_xdec_lib", "ensure_damp_lib")]
    # (and the Moog extensions' builds beside them: nvlive finds them by name)
    B.ensure_moogx_lib()
    B.ensure_gpu_moogx_lib()
    sh = (0.06, 1.6, 3.5, 1500.0)
    consts = [float(B.SR), float(B.BLK), float(B._chunk()), float(T.master_gain), float(B.RING_FLOOR),
              float(B.RING_MAX), float(B.XDEC_NEPERS), float(os.environ.get("TUNING_REGISTER", "1") or 1),
              float(DM.FULL_DB_S), float(DM.RESIDUAL), float(DM.BETA), float(DM.KNEE_DB), float(DM.LN10_20),
              float(B.RETRIGGER_FADE), 0.98 * math.pi, float(T.SOUND_VIB_DEPTH_CENTS),
              float(bool(T.FIXED_TOUCH)), float(os.environ.get("TUNING_REFLECT", "1") not in ("0", "off", ""))]
    consts += [63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0] + list(sh)
    # live's pressure at full aftertouch, the limiter's knee, the wheel's range (nvlive)
    consts += [float(sess.get("press_db", T.PRESS_DB)), float(sess.get("thresh", 0.70)),
               float(sess.get("bend_range", 2.0))]
    # the bend passes' (nvrender: native/bend.cpp): the fader's glide, its tail,
    # the stamped channel's test, GM's bend range and power-on levels
    consts += [float(B.TAU), float(B.FADER_TAIL), float(B.STAMP_S), float(B.STAMPED_SHARE),
               float(T.BEND_RANGE_SEMITONES), float(T.GM_DEFAULT_VOLUME), float(T.GM_DEFAULT_EXPRESSION)]
    # (K_GSPLACE, below) and then THE MAPS' OWN DRUM SETS (percussion_map.KITS
    # past 127, kit_in_map's): how many, then 32 slots
    _mk = sorted(k for k in PCM.KITS if k >= 128)
    if len(_mk) > 32:
        raise SystemExit("native_export: %d maps' drum sets, room for 32" % len(_mk))
    _mapkits = [float(len(_mk))] + [float(k) for k in _mk] + [0.0] * (32 - len(_mk))
    # a GS file's chorus device's outputs (blockrender.gsd_place's head): its
    # beta, then the left, right and centre outputs' gains and delays (samples)
    import gsdelay as _GSDX
    _q = T.StoppedPipeProperties(261.6, 0, 1, 1)
    consts += [float(_q.hrtf_beta)]
    for _sd in ("l", "r", "c"):
        _li, _ri, _ld, _rd = _q.hrtf_at(_GSDX.OUTPUT_X[_sd], 0.0, _q.listener_distance)
        consts += [float(_li), float(_ri), float(_ld * B.SR), float(_rd * B.SR)]
    consts += _mapkits
    # A FILE'S INSERTION EFFECT (gsefx.chain, as nvrender builds it): the
    # built types' codes (msb * 128 + lsb: how many, then 128 slots); the
    # types built natively (how many, EFX_KEYS's length, a record's width,
    # then 96 records (every type's room): the code, the kind -- 1 Overdrive, 2 Distortion, 3 a
    # multi, 4 3D Manual, 5 the Compressor, 6 3D Auto, 7 Reverb, 8 Gate Reverb, 9 2 Pitch Shifter, 10 Fb
    # P.Shifter, 11 Space D, 12 Stereo Chorus, 13 Hexa Chorus, 14 Tremolo Chorus, 15 3D Chorus, 16 Stereo
    # Flanger, 17 Tremolo, 18 Auto Pan, 19 Stereo-EQ, 20 Spectrum, 21 Stereo Delay, 22 Mod Delay, 23 3 Tap
    # Delay, 24 4 Tap Delay, 25 Tm Ctrl Delay, 26 3D Delay, 27 Phaser, 28 Auto Wah, 29 Step Flanger, 30
    # Humanizer, 31 Lo-Fi 1, 32 Limiter, 33 Enhancer -- a bass's cabinet, each of
    # EFX_KEYS's parameter numbers, 0 none, the type's defaults 1-20, -1
    # none, and the parameters its controllers move, + then # (0 none),
    # each's range lo, hi -- -1, -1 a choice of codes); gsefx's laws (OD_DB, DS_DB, OD_MAKEUP_DB, CMP_ATTACK_MS,
    # PEDAL_AMP_DRIVE, EFX_DEPTH_SCALE, EQ_Q, EQ_FREQS: 30); the two
    # cabinets a chain names (guitar12, bass410: 33 each, NoteClass's cab_*);
    # and the value tables *6 (a rate, Hz), *13 (an azimuth, degrees), *1 and *8: 128 each
    import gsefx as _GSX
    import cabinet as _CABX
    _codes = sorted(k[0] * 128 + k[1] for k, v in _GSX.TYPES.items() if v in _GSX.BUILT)
    if len(_codes) > 128:
        raise SystemExit("native_export: %d built EFX types, room for 128" % len(_codes))
    consts += [float(len(_codes))] + [float(c) for c in _codes] + [0.0] * (128 - len(_codes))
    _nat = [("Overdrive", 1), ("Distortion", 2), ("Bass Multi", 3), ("Clean Gt Multi 1", 3),
            ("GTR Multi 1", 3), ("GTR Multi 2", 3), ("3D Manual", 4), ("3D Auto", 6), ("Compressor", 5),
            ("Reverb", 7), ("Gate Reverb", 8), ("2 Pitch Shifter", 9), ("Fb P.Shifter", 10),
            ("GTR Multi 3", 3), ("Space D", 11), ("Stereo Chorus", 12), ("Hexa Chorus", 13),
            ("Tremolo Chorus", 14), ("3D Chorus", 15), ("Stereo Flanger", 16), ("Tremolo", 17), ("Auto Pan", 18),
            ("Stereo-EQ", 19), ("Spectrum", 20), ("Stereo Delay", 21), ("Mod Delay", 22), ("3 Tap Delay", 23),
            ("4 Tap Delay", 24), ("Tm Ctrl Delay", 25), ("3D Delay", 26), ("Phaser", 27), ("Auto Wah", 28),
            ("Step Flanger", 29), ("Humanizer", 30), ("Lo-Fi 1", 31), ("Limiter", 32), ("Enhancer", 33),
            ("Clean Gt Multi 2", 3), ("Rhodes Multi", 3), ("Rotary", 34), ("Rotary Multi", 35),
            ("Keyboard Multi", 3), ("Lo-Fi 2", 36)] + [(_s, 37) for _s in _GSX.SERIES_TYPES]
    _nat += [(_s, 38) for _s in _GSX.PARALLEL_TYPES]
    # (a record a code: a type printed at two, the Rotary Multi's, has both)
    _nat = [(_k, _nm, _kd) for _nm, _kd in _nat for _k in sorted(k for k, v in _GSX.TYPES.items() if v == _nm)]
    if len(_nat) > 96:
        raise SystemExit("native_export: %d native EFX records, room for 96" % len(_nat))
    _NATW = 3 + len(N.EFX_KEYS) + 20 + 8
    consts += [float(len(_nat)), float(len(N.EFX_KEYS)), float(_NATW)]
    for _k, _nm, _kd in _nat:
        _pn = _GSX.param_numbers(_nm)
        _df = _GSX.DEFAULTS.get(_nm, {})
        consts += [float(_k[0] * 128 + _k[1]), float(_kd), float(_nm == "Bass Multi")]
        consts += [float(_pn.get(x, 0)) for x in N.EFX_KEYS]
        consts += [float(_df.get(n, -1)) for n in range(1, 21)]
        _mk = _GSX.marks(_nm)
        consts += [float(_mk.get('+', 0)), float(_mk.get('#', 0))]
        _ch = []
        for _m in ('+', '#'):
            _rg = _GSX.param_range(_nm, _mk[_m]) if _m in _mk else (0, 127)
            consts += [float(min(_rg)), float(max(_rg))]
            # (a choice of codes, gsefx.controlled's nearest: 1 every code
            # lo..hi, 2 the two ends)
            if not isinstance(_rg, list):
                _ch.append(0.0)
            elif _rg == list(range(min(_rg), max(_rg) + 1)):
                _ch.append(1.0)
            elif _rg == [min(_rg), max(_rg)]:
                _ch.append(2.0)
            else:
                raise SystemExit("native_export: %s's choice %r is not the engine's" % (_nm, _rg))
        consts += _ch
    consts += [0.0] * (_NATW * (96 - len(_nat)))
    _laws = (list(_GSX.OD_DB) + list(_GSX.DS_DB) + [_GSX.OD_MAKEUP_DB, _GSX.CMP_ATTACK_MS, _GSX.PEDAL_AMP_DRIVE,
             _GSX.EFX_DEPTH_SCALE] + list(_GSX.EQ_Q) + list(_GSX.EQ_FREQS))
    consts += [float(x) for x in _laws] + [0.0] * (30 - len(_laws))
    for _cn in ("guitar12", "bass410"):
        _cb = _CABX.get(_cn)
        if len(_cb.formants) > 4 or len(_cb.antiformants) > 4 or _cb.body_trim_db:
            raise SystemExit("native_export: the %s cabinet is not the engine's" % _cn)
        _fm = [float(x) for row in _cb.formants for x in row]
        _af = [float(x) for row in _cb.antiformants for x in row]
        consts += [1.0, float(len(_cb.formants)), float(len(_cb.antiformants)), float(_cb.formant_floor)]
        consts += _fm + [0.0] * (12 - len(_fm)) + _af + [0.0] * (12 - len(_af))
        consts += [float(_cb.bore_corner_hz), float(_cb.bore_order), float(_cb.bell_cutoff_hz or 0.0),
                   float(_cb.bell_order), float(_cb._ref)]
    consts += [float(_GSX.table_value(6, v)) for v in range(128)]
    consts += [float(_GSX.azimuth(v)) for v in range(128)]
    # ...and *1 (a pre-delay, ms) and *8 (a damping corner, Hz: NaN Bypass)
    for _tk in (1, 8):
        consts += [float('nan') if _GSX.table_value(_tk, v) is None else float(_GSX.table_value(_tk, v))
                   for v in range(128)]
    # ...and a tap at a pan between the outputs (gsd_place's: a pitch shifter's
    # EFX Pan, (v - 64) / 63 at the pan law's angle): each v's incidences and
    # delays (samples), 128 x 4
    for v in range(128):
        _x = _q.listener_distance * math.tan(T.stage_angle((v - 64) / 63.0))
        _li, _ri, _ld, _rd = _q.hrtf_at(_x, 0.0, _q.listener_distance)
        consts += [float(_li), float(_ri), float(_ld * B.SR), float(_rd * B.SR)]
    # ...and *9 (a pre-filter's cutoff, Hz: NaN Bypass); the tremolo's waves
    # (gsefx.WAVES: each's count, then 6 (harmonic, coefficient, phase));
    # the Hexa Chorus's voices placed (gsd_place of a pan: each Pan Dev
    # 0-127's six -- the pan itself, its memo's key, then incidences and
    # delays, samples); the 3D types' sides at -60 and 60 degrees (key 1000 + a)
    consts += [float('nan') if _GSX.table_value(9, v) is None else float(_GSX.table_value(9, v))
               for v in range(128)]
    for _w in _GSX.WAVES:
        if len(_w) > 6:
            raise SystemExit("native_export: a tremolo wave of %d harmonics, room for 6" % len(_w))
        consts += [float(len(_w))] + [float(x) for h in _w for x in h] + [0.0] * (3 * (6 - len(_w)))

    def _side_place(_x):
        _li, _ri, _ld, _rd = _q.hrtf_at(_x, 0.0, _q.listener_distance)
        return [float(_li), float(_ri), float(_ld * B.SR), float(_rd * B.SR)]
    for v in range(128):
        _pd = v / 20.0
        for k in range(6):
            _pan = _pd * (2.0 * k / 5.0 - 1.0)
            consts += [float(_pan)] + _side_place(_q.listener_distance * math.tan(T.stage_angle(float(_pan))))
    for _a in (-60.0, 60.0):
        consts += [1000.0 + _a] + _side_place(_q.listener_distance
                                              * math.tan(math.radians(max(-80.0, min(80.0, _a)))))
    # ...and the delay types' times, *2, *3, *4 (ms: NaN none); a phaser's
    # Manual *12 (Hz), the Humanizer's Accel *14; Lo-Fi 2's noises' LPFs *11
    for _tk in (2, 3, 4, 12, 14, 11):
        consts += [float('nan') if _GSX.table_value(_tk, v) is None else float(_GSX.table_value(_tk, v))
                   for v in range(128)]
    # ...and its Butterworths (efxbus.butter: scipy's own coefficients, at this
    # rate): the filter after at each Cutoff (*9, else 630 Hz), a low pass then
    # a high pass, b then a (3 each); the radio's band (300-3000 Hz, first order)
    import efxbus as _EFB
    for v in range(128):
        _hz = _GSX.table_value(9, v) or 630.0
        for _kd in ('low', 'high'):
            _f = _EFB.butter(_kd, _hz, B.SR)
            if len(_f.b) != 3 or len(_f.a) != 3:
                raise SystemExit("native_export: a Butterworth not of three taps")
            consts += [float(x) for x in _f.b] + [float(x) for x in _f.a]
    _f = _EFB.butter('band', (300.0, 3000.0), B.SR, 1)
    if len(_f.b) != 3 or len(_f.a) != 3:
        raise SystemExit("native_export: the radio's band not of three taps")
    consts += [float(x) for x in _f.b] + [float(x) for x in _f.a]
    room = os.fsencode(T.ROOM_NAME[0] or "")
    with open(args[0], "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<iii", len(consts), ctypes.sizeof(N.NoteClass), len(classes)))
        f.write(struct.pack("<%dd" % len(consts), *consts))
        f.write(struct.pack("<128d", *[float(freq[k]) if k in freq else 0.0 for k in range(128)]))
        f.write(struct.pack("<512d", *trims))
        for c in classes:
            f.write(c)
        f.write(struct.pack("<32768i", *cmap))
        f.write(bytes(kf0) + bytes(kseat) + bytes(kchoke) + bytes(kskind) + bytes(kspar))
        fin = dict(B.FINAL_DTYPES)
        f.write(struct.pack("<50i", *[1 if c in B._COL_F4 else 2 if c in B._COL_I4 else 0 for c in B.EMIT_COLS]))
        f.write(struct.pack("<50i", *[{'f8': 0, 'f4': 1, 'i8': 2, 'i4': 3}.get(fin.get(c), -1)
                                      for c in B.EMIT_COLS]))
        for s in [room] + libs:
            f.write(struct.pack("<i", len(s)) + s)
        # ORGA: the organs' tables, padded to their alignment (the pad's count
        # said) -- nvrender maps them from the file, as it maps the classes
        f.write(b"ORGA")
        f.write(struct.pack("<ii", len(organs), ctypes.sizeof(N.OrganSpec)))
        pad = -(f.tell() + 4) % ctypes.alignment(N.OrganSpec)
        f.write(struct.pack("<i", pad) + bytes(pad))
        for o in organs:
            f.write(o)
        f.write(struct.pack("<%di" % len(classes), *cls_organ))
        f.write(struct.pack("<128i", *prog_organ))
        # LESL: the rotating speaker's constants (native/leslie.cpp's L_*) and the lobe's kernel
        les = N.leslie_constants()
        # SCAN: the scanner's constants and its circuit's tables (native/scanner.cpp's)
        scn = N.scan_constants()
        lobe = os.fsencode(B.ensure_lobe_lib()._name)
        f.write(b"LESL" + struct.pack("<i", len(les)) + struct.pack("<%dd" % len(les), *[float(x) for x in les])
                + struct.pack("<i", len(lobe)) + lobe)
        f.write(b"SCAN" + struct.pack("<i", len(scn)) + struct.pack("<%dd" % len(scn), *scn))
        # VBOD: the voice parts a track's name declares (tonelib.VOICE_BODIES,
        # VOICE_CLUSTER, _NOT_A_VOICE: nv_voice_bodies_set's)
        vbn = list(T.VOICE_BODIES)
        blob = b"".join(os.fsencode(x) + b"\0" for x in vbn + list(T._NOT_A_VOICE))
        f.write(b"VBOD" + struct.pack("<iii", len(vbn), len(T._NOT_A_VOICE), len(blob)) + blob
                + struct.pack("<%dd" % len(vbn), *[float(T.VOICE_BODIES[x]) for x in vbn])
                + struct.pack("<%dd" % len(vbn), *[float(T.VOICE_CLUSTER.get(x, 1.0)) for x in vbn]))
        # VARS: bank select -- the slots (program, variation, layer), their
        # classes at each key, the entries (a slot, or a layered set: each
        # layer's slot, semitones and velocities), GS's and GM 2's tables;
        # its length first, so a reader that does not know it steps over it
        vb = struct.pack("<i", len(vslots)) + b"".join(struct.pack("<iii", p, v, l) for p, v, l, _ in vslots)
        vb += struct.pack("<%di" % len(vmap), *vmap)
        vb += struct.pack("<i", len(ventries) - 1)
        for _p, _v, ls in ventries[1:]:
            vb += struct.pack("<iii", _p, _v, len(ls)) + b"".join(struct.pack("<iiii", *x) for x in ls)
        vb += struct.pack("<%di" % (5 * 128 * 128), *[e for m in vgs for row in m for e in row])
        vb += struct.pack("<%di" % (128 * 128), *[e for row in vgm2 for e in row])
        # ...and each entry's trim (patch_map.program_trim: VARIATION_TRIM_DB),
        # in a file that speaks GS and not
        import patch_map as PM
        for _p, _v, _ls in ventries[1:]:
            vp = PM.VariationProgram(_p, _v)
            vb += struct.pack("<dd", PM.program_trim(vp), PM.program_trim(vp, gs=True))
        # ...and each entry's program class (property_class_for_program, as
        # _prep_breath reads it): its class, -1 none the engine has and no
        # breath, -2 one that breathes
        for _p, _v, _ls in ventries[1:]:
            vb += struct.pack("<i", vpcls[(_p, _v)])
        f.write(b"VARS" + struct.pack("<i", len(vb)) + vb)
        # DRON: the drone classes (native.DRONES, registered as the bagpipes'
        # classes were made), K's drone region
        dmap = []
        for cls in N.DRONES[:256]:
            k = N.note_class(cls)
            if k is None:
                dmap.append(-1)
                continue
            if cls not in idx:
                raise SystemExit("native_export: drone class %s met after the classes were written" % cls.__name__)
            dmap.append(idx[cls])
        dmap += [-1] * (256 - len(dmap))
        f.write(b"DRON" + struct.pack("<i", 4 * 256) + struct.pack("<256i", *dmap))
        # MKIT: the maps' own drum sets -- how many, their ids, each key's
        # class, pitch, seat, chokes, gesture and layers (kits()'s, set j's
        # key at 128 j + key)
        mb = struct.pack("<i", len(mk_ids)) + struct.pack("<%di" % len(mk_ids), *mk_ids)
        mb += struct.pack("<%di" % len(mk_map), *mk_map)
        mb += bytes(mk_f0) + bytes(mk_seat) + bytes(mk_choke) + bytes(mk_skind) + bytes(mk_spar)
        f.write(b"MKIT" + struct.pack("<i", len(mb)) + mb)
        # MKNM: their names (percussion_map.drum_set_name), for nvlive's panel
        _nb = b"".join(struct.pack("<i", len(_s)) + _s
                       for _s in (PCM.drum_set_name(_k).encode("utf-8") for _k in mk_ids))
        f.write(b"MKNM" + struct.pack("<i", len(_nb)) + _nb)
        # VNAM: the variations a picker offers (livetui's: GS's own tones and the
        # maps' -- not the MT-32 set's, bank 127), each its program, its key
        # (map x 128 + bank) and its name (a map's own with its map, gm_label's)
        vn = []
        for (_p, _v) in sorted(PM.VARIATIONS):
            if _v == 127 or (_p, _v) not in PM.VARIATION_NAMES:
                continue
            _nm = PM.VARIATION_NAMES[(_p, _v)] + (" (%s)" % PM.MAP_LABELS[_v >> 7]
                                                    if _v >> 7 in PM.MAP_LABELS else "")
            _b = _nm.encode("utf-8")
            vn.append(struct.pack("<iii", _p, _v, len(_b)) + _b)
        vb2 = struct.pack("<i", len(vn)) + b"".join(vn)
        f.write(b"VNAM" + struct.pack("<i", len(vb2)) + vb2)
        if "live" in opt:
            # VLIV: each of VNAM's variations' live.Patch record, as LIVE's
            # program's (its buckets, rotor speeds, Leslie default, damper and
            # soft pedal), 0s where its program is not live's
            import live as _LV
            vl = []
            for (_p, _v) in sorted(PM.VARIATIONS):
                if _v == 127 or (_p, _v) not in PM.VARIATION_NAMES:
                    continue
                rec = [0] * 10
                _vc = PM.VARIATIONS[(_p, _v)]
                _vc = _vc if isinstance(_vc, type) else _vc(60)     # (a picker: its key 60's)
                if (_p, _v) in LIVE_REFUSED or (N.kit_drum(_vc) == 6 and _moog_later(_vc)):
                    pass                # (refused: nvlive's "not native" -- a Moog with no native panel)
                elif any(cmap_live[128 * _p + k] >= 0 for k in range(128)):
                    # (one variation at a time: its probe notes' per-class
                    # memos let go after it -- N.memo_scope -- or the walk
                    # held every variation's, 0.85 MB each)
                    with N.memo_scope():
                        pt = _LV.Patch(_p, False, tuner, _v)
                    sp = [(-1 if x is None else int(x)) for x in pt.speeds][:3]
                    rec = ([1, pt.nbuckets, len(sp)] + sp + [-1] * (3 - len(sp))
                           + [int(pt.leslie_default if pt.detune_wheel else -1)]
                           + [int(bool(pt.damper_pedal)), int(pt.soft_pedal_strings), int(pt.soft_pedal_top)])
                vl.append(struct.pack("<10i", *(rec + [0] * (10 - len(rec)))[:10]))
            vb3 = struct.pack("<i", len(vl)) + b"".join(vl)
            f.write(b"VLIV" + struct.pack("<i", len(vb3)) + vb3)
            # VDRN: a voice's own drone patch's live record, its variation
            # one no picker names (the pungi's drone, Patch.drone_note_var):
            # program, variation, then the record as VLIV's
            vd = []
            for (_p, _v) in sorted(PM.VARIATIONS):
                if _v == 127 or (_p, _v) not in PM.VARIATION_NAMES or (_p, _v) in LIVE_REFUSED:
                    continue
                _dc = PM.VARIATIONS[(_p, _v)]
                _dv = int(getattr(_dc, 'drone_note_variation', 0)) if getattr(_dc, 'drone_note_wheel', False) else 0
                if not _dv or (_p, _dv) in PM.VARIATION_NAMES:
                    continue
                with N.memo_scope():
                    pt = _LV.Patch(_p, False, tuner, _dv)
                sp = [(-1 if x is None else int(x)) for x in pt.speeds][:3]
                rec = ([1, pt.nbuckets, len(sp)] + sp + [-1] * (3 - len(sp))
                       + [int(pt.leslie_default if pt.detune_wheel else -1)]
                       + [int(bool(pt.damper_pedal)), int(pt.soft_pedal_strings), int(pt.soft_pedal_top)])
                vd.append(struct.pack("<12i", _p, _dv, *(rec + [0] * (10 - len(rec)))[:10]))
            vb4 = struct.pack("<i", len(vd)) + b"".join(vd)
            f.write(b"VDRN" + struct.pack("<i", len(vb4)) + vb4)
            # MTAB: moog.py's spectra by knob position and its laws' constants
            # (native.moog_tables), what a knob turned live is built from
            mt = N.moog_tables().astype("<f8").tobytes()
            f.write(b"MTAB" + struct.pack("<i", len(mt)) + mt)
            # EFXU: the panel's insertion effect (livetui.pick_efx): Roland's
            # numbered types and families, each type's parameters -- name,
            # its controller's mark, whether the model reads it, the value in
            # effect where none is set (gsefx.in_effect), its raw values and
            # each printed as his panel shows it -- as tab-separated lines
            import gsefx as _GSX
            ul = ["T\t%d\t%d\t%d\t%s" % (_n, _k[0], _k[1], _nm) for _n, _k, _nm in _GSX.numbered()]
            ul += ["C\t%d\t%d\t%s" % (_a, _b, _c) for _c, _a, _b in _GSX.CATEGORIES]
            for _n, _k, _nm in _GSX.numbered():
                # (the model reads some only in some states -- a chorus's
                # Cutoff with its Pre Filter on: the type fresh, then each
                # parameter alone through its ends and middle, what it reads
                # of those left unset)
                _eff = {}
                _sts = [_GSX.tone_state(_k)]
                for _q, _pn, _rg, _d in _GSX.params(_nm):
                    _r = _GSX.param_range(_nm, _q)
                    _sts += [_GSX.tone_state(_k, {_q: _v}) for _v in
                             (_r if isinstance(_r, list) else sorted({_r[0], _r[0] + 1, (_r[0] + _r[1]) // 2, _r[1]}))]
                for _st in _sts:
                    _GSX._USED.clear()
                    _GSX.chain(_st)
                    for _q, _v in _GSX._USED.items():
                        if _q not in _st['p']:
                            _eff.setdefault(_q, _v)
                _mk = {v: m for m, v in _GSX.marks(_nm).items()}
                for _q, _pn, _rg, _d in _GSX.params(_nm):
                    _r = _GSX.param_range(_nm, _q)
                    _vs = list(_r) if isinstance(_r, list) else list(range(_r[0], _r[1] + 1))
                    ul.append("P\t%d\t%d\t%d\t%s\t%s\t%d\t%d\t%s\t%s" % (
                        _k[0], _k[1], _q, _pn, _mk.get(_q, "-"), int(_q in _eff),
                        int(_eff.get(_q, _d if _d is not None else 0)), ",".join(str(x) for x in _vs),
                        "\x1f".join(_GSX.printed_value(_nm, _q, x) for x in _vs)))
            ub = "\n".join(ul).encode("utf-8")
            f.write(b"EFXU" + struct.pack("<i", len(ub)) + ub)
        if "live" in opt:
            import live as L
            tab = L.pan_table()
            f.write(b"LIVE")
            f.write(struct.pack("<384d", *[float(x) for row in tab for x in row]))
            f.write(struct.pack("<dd", float(L._PAN_BETA), 10.0 ** (-float(sess.get("headroom_db", 4.0)) / 20.0)))
            for prog in range(128):
                rec = [0] * 9
                if any(cmap_live[128 * prog + k] >= 0 for k in range(128)):
                    pt = L.Patch(prog, False, tuner, 0)
                    sp = [(-1 if v is None else int(v)) for v in pt.speeds][:3]
                    rec = ([1, pt.nbuckets, len(sp)] + sp + [-1] * (3 - len(sp))
                           + [int(pt.leslie_default if pt.detune_wheel else -1)])
                    rec += [int(bool(pt.damper_pedal)), int(pt.soft_pedal_strings), int(pt.soft_pedal_top)]
                    rec = rec[:7] + rec[7:]
                f.write(struct.pack("<10i", *(rec + [0] * (10 - len(rec)))[:10]))
            f.write(b"LREG")
            for prog in range(128):
                pc = None
                if any(cmap_live[128 * prog + k] >= 0 for k in range(128)):
                    pt = L.Patch(prog, False, tuner, 0)
                    pc = pt._voice_class(60)
                    if not B.REGISTER or pc is None or not (getattr(pc, 'register_gain', 0.0) > 0.0
                                                            or getattr(pc, 'register_knock_gain', 0.0) > 0.0):
                        pc = None
                if pc is None:
                    f.write(struct.pack("<i", 0))
                    continue
                modes, M, kk = N.live_bank(pc, B.tuning_table(pt.tuner), float(B.SR),
                                           getattr(B, 'REGISTER_SCALE', 1.0))
                f.write(struct.pack("<i", M))
                f.write(bytes(modes)[:M * ctypes.sizeof(N.StringMode)])
                kappa, knock, fall, fl, top, beta = kk
                f.write(struct.pack("<9d", kappa, knock, fall, fl, beta,
                                    float(getattr(pc, 'release_valve_time', 0.12) or 0.12) * B.SR,
                                    float(DM.FULL_DB_S), float(DM.RESIDUAL), float(DM.LN10_20)))
                f.write(struct.pack("<3i", int(top), int(bool(getattr(pc, 'damper_pedal', True))), int(B.BLK)))
                # live._reg_voice, key by key
                ok = []
                for k in range(128):
                    kc = pt._voice_class(k)
                    ok.append(int(kc is not None and (getattr(kc, 'register_gain', 0.0) > 0.0
                                                      or getattr(kc, 'register_knock_gain', 0.0) > 0.0)))
                f.write(struct.pack("<128i", *ok))
                # ...and what the bank is built from, so nvlive can build it at
                # a tuner of its own (native.live_bank_class: nv_strings' inputs)
                bc, bs = N.live_bank_class(pc)
                for x in (bytes(bc), bytes(bs)):
                    f.write(struct.pack("<i", len(x)) + x)
            # LGPU: live's GPU renderer -- the setup's two builds (gpurender's,
            # and the damper's), the directory gpukernel.cl and voicedesc.h are in,
            # and live's GPU_MIN
            f.write(b"LGPU")
            for s in (os.fsencode(B.ensure_gpu_lib()._name), os.fsencode(B.ensure_gpu_damp_lib()._name),
                      os.fsencode(HERE)):
                f.write(struct.pack("<i", len(s)) + s)
            f.write(struct.pack("<ii", int(L.GPU_MIN), int(L.GPU_MIN_SMALL)))
            # LROOM: live's convolver, and the room's late tail as live draws it
            # at its start (no rig measured yet: band_q None)
            f.write(b"LROOM")
            cv = os.fsencode(L._conv_dll()._name)
            f.write(struct.pack("<i", len(cv)) + cv)
            irs = None if room_name == "dry" else L.room_irs(48000)
            for a in ((None, None) if irs is None else irs):
                if a is None:
                    f.write(struct.pack("<i", 0))
                else:
                    a = np.ascontiguousarray(a, np.float32)
                    f.write(struct.pack("<i", len(a)) + a.tobytes())
            # LROOMS: EVERY ROOM live can switch to (live.set_room, ROOM_NAMES):
            # the byte ranges of a class record the room sets (its walls and
            # their order; its voice snapshot's room, band corners, absorption,
            # scattering and the listener's distance), the class count, the device tails' filters
            # (roomtail.device_spec), then each room's name, whether it
            # reflects (dry: off, the classes as they were), its tail's spec
            # (roomtail.tail_spec: what does not depend on the stage) and, where
            # it reflects, every class's ranges in it -- the export's own room
            # last set again, as the rest of the export expects
            import roomtail as _RTL
            import tonelib as _T
            _was = _T.ROOM_NAME[0]
            _VS = N.VoiceSnap
            _t0 = N.NoteClass.tmpl.offset
            rng = [(N.NoteClass.room_planes.offset, N.NoteClass.room_planes.size),
                   (N.NoteClass.room_order.offset, N.NoteClass.room_order.size)]
            rng += [(_t0 + getattr(_VS, _f).offset, getattr(_VS, _f).size)
                    for _f in ("room", "ahz", "alpha", "scat", "radiation_distance")]
            ordered = sorted(idx.items(), key=lambda kv: kv[1])
            rb = struct.pack("<i", len(rng)) + b"".join(struct.pack("<ii", o, z) for o, z in rng)
            rb += struct.pack("<i", len(classes))
            dsp = _RTL.device_spec(48000)
            rb += struct.pack("<i", len(dsp)) + struct.pack("<%dd" % len(dsp), *dsp)
            rb += struct.pack("<i", len(L.ROOM_NAMES))
            for _rn in L.ROOM_NAMES:
                _nb = _rn.encode()
                rb += struct.pack("<i", len(_nb)) + _nb
                if _rn == "dry":
                    rb += struct.pack("<ii", 0, 0)
                    continue
                _T.set_room(_rn)
                tsp = _RTL.tail_spec(_T.StoppedPipeProperties(261.6, 0, 1, 1))
                rb += struct.pack("<ii", 1, len(tsp)) + struct.pack("<%dd" % len(tsp), *tsp)
                for _cls, _i in ordered:
                    _kb = bytes(N.note_class(_cls))
                    rb += b"".join(_kb[o:o + z] for o, z in rng)
            if _was:
                _T.set_room(_was)
            f.write(b"LROOMS" + struct.pack("<q", len(rb)) + rb)
            # LROUTE: the session's routes (live.Route), each as nv_rt_add takes it
            routes = [L.Route.from_dict(r) for r in sess.get("routes", [])]
            f.write(b"LROUTE" + struct.pack("<i", len(routes)))
            for r in routes:
                f.write(struct.pack("<7i", *N.route_args(r)))
            # LSTOP: each organ program's stops as live's panel lays them out
            # (Patch.stop_rows: row 0 on the digits, row 1 shifted, 2 and 3
            # after the prefix) -- its ranks' names, and each row's ranks, -1
            # where the voice breaks the line (a "|" in Patch.stop_row_lines:
            # livetui.stops_grid's groups; not a stop, no key)
            orgs = [p for p in range(128) if prog_organ[p] >= 0]
            f.write(b"LSTOP" + struct.pack("<i", len(orgs)))
            for p in orgs:
                pt = L.Patch(p, False, tuner, 0)
                f.write(struct.pack("<ii", p, len(pt.rank_names)))
                for nm in pt.rank_names:
                    b = nm.encode()
                    f.write(struct.pack("<i", len(b)) + b)
                f.write(struct.pack("<i", len(pt.stop_row_lines)))
                for row in pt.stop_row_lines:
                    f.write(struct.pack("<i", len(row)) + struct.pack(
                        "<%di" % len(row), *[-1 if n == "|" else pt.rank_names.index(n) for n in row]))
            # LPROG: what a PROGRAM CHANGE needs, each program's -- its strings'
            # identity (its class at key 60, as live compares them to forget
            # the register's, -1 for no part), a harpsichord's choirs for its
            # register (native.live_bank_choirs: bridges, cross, buffs; 0
            # none), and what the panel calls it, as a program and as a set ("" not a set)
            import livetui as LT
            import percussion_map as PM
            f.write(b"LPROG")
            sids = []
            for prog in range(128):
                sid, chs = -1, None
                if any(cmap_live[128 * prog + k] >= 0 for k in range(128)):
                    pc = L.Patch(prog, False, tuner, 0)._voice_class(60)
                    if pc not in sids:
                        sids.append(pc)
                    sid = sids.index(pc)
                    if B.REGISTER and pc is not None:
                        chs = N.live_bank_choirs(pc)
                f.write(struct.pack("<i", sid))
                if chs is None:
                    f.write(struct.pack("<i", 0))
                else:
                    nc, br, cross, nb, bf = chs
                    f.write(struct.pack("<i%dqdi%di" % (nc, 2 * nb), nc, *list(br), cross, nb,
                                        *list(bf)[:2 * nb]))
                for nm in (LT.GM[prog], PM.drum_set_name(prog) if prog in PM.DRUM_SETS else ""):
                    b = nm.encode()
                    f.write(struct.pack("<i", len(b)) + b)
            # LP3D: live.pan_at's head (a 3D type's place, Live._efx_place3d): the
            # stopped pipe's height and distance, the head's radius, the speed of sound
            _q3 = T.StoppedPipeProperties(261.63, 0.0, 1.0, 1.0)
            f.write(b"LP3D" + struct.pack("<4d", float(_q3.position_z), float(_q3.listener_distance),
                                           float(_q3.head_radius), float(_q3.sound_speed)))
    print("native export: %d piano class(es), tuner %s, room %s -> %s" % (len(classes), tuner,
                                                                          room.decode() or "-", args[0]))
    if sess:
        print("  from the last session: room %s, master %s dB, headroom %s dB, press %s dB, knee %s, %d route(s)"
              % (sess.get("room"), sess.get("master_db"), sess.get("headroom_db"), sess.get("press_db"),
                 sess.get("thresh"), len(sess.get("routes", []))))
    return 0


def write_deps(path):
    """NV_EXPORT_DEPS: the repository's Python files this export loaded (the
    modules in sys.modules, this script among them), one path per line,
    relative -- what nvlive_check.live_export keys a cached export on"""
    here = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    got = set()
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if not f or not f.endswith(".py"):
            continue
        f = os.path.realpath(f)
        if f.startswith(here + os.sep):
            got.add(os.path.relpath(f, here))
    got.add(os.path.relpath(os.path.realpath(os.path.abspath(__file__)), here))
    with open(path, "w") as fh:
        fh.write("".join(r + "\n" for r in sorted(got)))


if __name__ == "__main__":
    _r = main(sys.argv)
    if os.environ.get("NV_EXPORT_DEPS"):
        write_deps(os.environ["NV_EXPORT_DEPS"])
    sys.exit(_r)
