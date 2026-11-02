#!/usr/bin/env python3
"""Export what the native renderer needs from the Python, once: OUT.nvx

    python3 examples/native_export.py OUT.nvx [--tuner=NAME] [--live [--room=NAME] [--fresh]]

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
                           a kind, 24 numbers)
  the columns              each EMIT_COLS column's type in the table (_COL_F4,
                           _COL_I4) and in prepare's result (FINAL_DTYPES)

The kernel libraries are blockrender's (built here if they are not yet):
their paths go in too. Binary, little-endian, for this machine.

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
    trims = []
    for gs in (False, True):
        trims += [float(PM.program_trim(p, False, gs=gs)) for p in range(128)]
        trims += [float(PM.program_trim(PCM.DrumProgram(p), True, gs=gs)) for p in range(128)]
    libs = [os.fsencode(getattr(B, f)()._name) for f in ("ensure_lib", "ensure_xdec_lib", "ensure_damp_lib")]
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
        if "live" in opt:
            import live as L
            tab = L.pan_table()
            f.write(b"LIVE")
            f.write(struct.pack("<384d", *[float(x) for row in tab for x in row]))
            f.write(struct.pack("<dd", float(L._PAN_BETA), 10.0 ** (-float(sess.get("headroom_db", 4.0)) / 20.0)))
            for prog in range(128):
                rec = [0] * 9
                if any(cmap[128 * prog + k] >= 0 for k in range(128)):
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
                if any(cmap[128 * prog + k] >= 0 for k in range(128)):
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
            # LROUTE: the session's routes (live.Route), each as nv_rt_add takes it
            routes = [L.Route.from_dict(r) for r in sess.get("routes", [])]
            f.write(b"LROUTE" + struct.pack("<i", len(routes)))
            for r in routes:
                f.write(struct.pack("<7i", *N.route_args(r)))
    print("native export: %d piano class(es), tuner %s, room %s -> %s" % (len(classes), tuner,
                                                                          room.decode() or "-", args[0]))
    if sess:
        print("  from the last session: room %s, master %s dB, headroom %s dB, press %s dB, knee %s, %d route(s)"
              % (sess.get("room"), sess.get("master_db"), sess.get("headroom_db"), sess.get("press_db"),
                 sess.get("thresh"), len(sess.get("routes", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
