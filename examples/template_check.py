#!/usr/bin/env python3
"""Does the native engine make live's templates as live does?

    python3 examples/template_check.py [--programs=0,1,2,3] [--vels=1,40,64,100,127] [--keys=21-108] [--live]

live.Voice._raw_template: blockrender.prepare of a one-note file (tempo one
beat a second, the program, CC7 and CC11 at 127, the key down at 0, up at
1 s, the end a second later) with fixed touch on, the register off, the Moog
panel and the scanner neutral. native.template: the same file's bytes made in
native/live.cpp and run through the engine. Per (program, key, velocity) the
table's columns in prepare's final types, its length (N, nblk, P) and room
(room_q), compared with ==. A key no native class plays is skipped. --live:
at live's rate and block (48 kHz, 128 samples: Live sets them before it
builds a template).
"""
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def python_template(B, T, prog, note, vel, tuner):
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=1000000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=prog, time=0))
    for cc in (7, 11):
        tr.append(mido.Message("control_change", channel=0, control=cc, value=127, time=0))
    tr.append(mido.Message("note_on", channel=0, note=note, velocity=vel, time=0))
    tr.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=480))
    tr.append(mido.MetaMessage("end_of_track", time=480))
    was = B.REGISTER
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            B.MOOG_NEUTRAL = True
            B.SCANNER_OFF = True
            T.FIXED_TOUCH = True
            B.REGISTER = False
            return B.prepare(m, tuner)
    finally:
        B.MOOG_NEUTRAL = False
        B.SCANNER_OFF = False
        T.FIXED_TOUCH = False
        B.REGISTER = was


def main(argv):
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import numpy as np
    import blockrender as B
    import native as N
    import tonelib as T
    if "live" in opt:
        B.set_sample_rate(48000)
        B.BLK = 128
    progs = [int(x) for x in (opt.get("programs") or "0,1,2,3").split(",")]
    vels = [int(x) for x in (opt.get("vels") or "1,40,64,100,127").split(",")]
    k0, k1 = (int(x) for x in (opt.get("keys") or "21-108").split("-"))
    tuner = opt.get("tuner") or "hybrid440"
    same = differ = skipped = 0
    for prog in progs:
        for key in range(k0, k1 + 1):
            for vel in vels:
                Q = N.template(prog, key, vel, tuner)
                if Q is None:
                    skipped += 1
                    continue
                P = python_template(B, T, prog, key, vel, tuner)
                bad = [k for k in ("N", "nblk", "P", "sym_rows") if P[k] != Q[k]]
                if [tuple(map(float, q)) for q in P["room_q"]] != [tuple(map(float, q)) for q in Q["room_q"]]:
                    bad.append("room_q")
                for c in B.EMIT_COLS:
                    if c not in P:
                        continue
                    a, b = np.asarray(P[c]), np.asarray(Q[c])
                    if a.dtype != b.dtype or not np.array_equal(a, b):
                        bad.append(c)
                if bad:
                    differ += 1
                    if differ <= 10:
                        print("  program %d key %d velocity %d DIFFERS: %s" % (prog, key, vel, " ".join(bad[:8])))
                else:
                    same += 1
    print("templates: %d identical, %d differ, %d keys not the engine's" % (same, differ, skipped))
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
