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

A REGISTERED ORGAN is stamped rank by rank, so its key is compared as live
holds it: live.Patch._raw_template (every stop drawn, the table sliced by
each rank's gate row: t["ranks"]) against native.TemplateCache's (live.cpp's
slices) -- at each velocity bucket's centre and each rotor speed the patch
builds, every rank's columns, count and hrel. --vels is not used for them.
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
    if getattr(B.property_class_for_program(prog), 'drone_wheel', False):
        # (live._raw_template's: a drone-wheel program's drones corked -- live sounds them itself)
        tr.append(mido.Message("control_change", channel=0, control=1, value=0, time=0))
    tr.append(mido.Message("note_on", channel=0, note=note, velocity=vel, time=0))
    tr.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=480))
    tr.append(mido.MetaMessage("end_of_track", time=480))
    was = B.REGISTER
    import tubeamp as TA
    wasa, TA.ENABLED = TA.ENABLED, False    # (live's _raw_template: the valve waits for the chord)
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
        TA.ENABLED = wasa


def _organ(B, N, prog):
    """Whether a program's notes are a registered organ's (stamped by rank)."""
    for key in range(21, 109):
        cls = B.property_class_for_note(prog, key)
        k = N.note_class(cls) if cls is not None else None
        if k is not None and k.organ:
            return True
    return False


def organ_check(B, N, prog, k0, k1, tuner):
    """A registered organ's keys, rank by rank: live's slices against the
    native cache's. (same, differ, skipped), a template a (key, bucket, speed)."""
    import numpy as np
    import live as L
    pt = L.Patch(prog, False, tuner, 0)
    tc = N.TemplateCache(prog, tuner)
    same = differ = skipped = 0
    for key in range(k0, k1 + 1):
        cls = B.property_class_for_note(prog, key)
        k = N.note_class(cls) if cls is not None else None
        if k is None or not k.organ:
            skipped += pt.nbuckets * len(pt.speeds)
            continue
        tc.warm(key, key, pt.nbuckets, pt.speeds)
        for b in range(pt.nbuckets):
            for sp in pt.speeds:
                with contextlib.redirect_stdout(io.StringIO()):
                    P = pt._raw_template(key, pt.bucket_vel(b), sp)
                Q = tc.get(key, b, sp)
                if P is None or Q is None:
                    bad = [] if P is None and Q is None else ["missing"]
                else:
                    bad = [k_ for k_ in ("P",) if P[k_] != Q[k_]]
                    pr, qr = P.get("ranks") or {}, Q.get("ranks") or {}
                    if set(pr) != set(qr):
                        bad.append("ranks %s vs %s" % (sorted(pr), sorted(qr)))
                    for nm in sorted(set(pr) & set(qr)):
                        (pc, pn, ph), (qc, qn, qh) = pr[nm], qr[nm]
                        if pn != qn or not np.array_equal(np.asarray(ph, np.float32), np.asarray(qh, np.float32)):
                            bad.append("%s: count/hrel" % nm)
                            continue
                        for c in L.ALL_COLS:
                            if c in pc and c in qc:
                                x, y = np.asarray(pc[c]), np.asarray(qc[c])
                                if x.dtype != y.dtype or not np.array_equal(x, y):
                                    bad.append("%s: %s" % (nm, c))
                if bad:
                    differ += 1
                    if differ <= 10:
                        print("  program %d key %d bucket %d speed %s DIFFERS: %s" % (prog, key, b, sp,
                                                                                     " ".join(bad[:8])))
                else:
                    same += 1
    return same, differ, skipped


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
    organs = [p for p in progs if _organ(B, N, p)]
    progs = [p for p in progs if p not in organs]
    for prog in organs:
        a, b, k = organ_check(B, N, prog, k0, k1, tuner)
        same, differ, skipped = same + a, differ + b, skipped + k
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
                    # (br: live stamps -1 over it -- it bends through retune, never a
                    # row -- so the template's own, a breath's rows, never reaches it)
                    if c not in P or c == "br":
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
