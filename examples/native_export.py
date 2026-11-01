#!/usr/bin/env python3
"""Export what the native renderer needs from the Python, once: OUT.nvx

    python3 examples/native_export.py OUT.nvx [--tuner=NAME] [--live]

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
  the voices               each native piano class's NoteClass (native.py),
                           and which class each (program, key) plays (-1:
                           not the engine's)
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
"""
import ctypes
import math
import os
import struct
import sys

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
    if "live" in opt:
        B.set_sample_rate(48000)
        B.BLK = 128
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
    room = os.fsencode(T.ROOM_NAME[0] or "")
    with open(args[0], "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<iii", len(consts), ctypes.sizeof(N.NoteClass), len(classes)))
        f.write(struct.pack("<%dd" % len(consts), *consts))
        f.write(struct.pack("<128d", *[float(freq[k]) if k in freq else 0.0 for k in range(128)]))
        f.write(struct.pack("<512d", *trims))
        for c in classes:
            f.write(c)
        f.write(struct.pack("<16384i", *cmap))
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
            f.write(struct.pack("<dd", float(L._PAN_BETA), 10.0 ** (-4.0 / 20.0)))
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
    print("native export: %d piano class(es), tuner %s, room %s -> %s" % (len(classes), tuner,
                                                                          room.decode() or "-", args[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
