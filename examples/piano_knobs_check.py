#!/usr/bin/env python3
"""Do the pianos' (and electric guitars') knobs move the native voice as the
Python reference does?

    python3 examples/piano_knobs_check.py

For each piano voice (GM 0-3 and the variations whose classes are their
own) and each knob it has (piano_knobs.knobs_of), at three settings across
the knob's range: the class made by piano_knobs.piano_class, exported as
the engine exports a class (A), against the plain class exported and moved
in place by the engine's nv_voicing_apply (B) -- the knobs the engine says
the class has the same as Python's, and for notes across the keyboard and
the velocities, the note's setup (nv_voice_init: VoiceSnap and VoiceNote)
byte for byte the same, and each harmonic's volume the same. Then what the
knob does: the spectrum's centroid against the plain class's (brightness,
averaged over the notes), or the unison strings' spread. Exit status: the
count of failures.
"""
import ctypes
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import native as N          # noqa: E402
import patch_map as PM      # noqa: E402
import piano_knobs as PK    # noqa: E402

RANGE = {PK.HAMMER: (-1.0, 0.0, 1.0), PK.WEAR: (0.3, 1.0, 2.5), PK.STRIKE: (0.1, None, 0.18),
         PK.UNISON: (0.0, 0.5, 2.5), PK.LID: (-6.0, None, 2.5), PK.BOARD: (0.5, 0.8, 1.8),
         PK.PICKUP: (0.6, 1.3, 1.8), PK.TINE: (0.0, 0.3, 1.2), PK.GAP: (0.5, 1.5, 2.5),
         PK.SWING: (0.4, 1.4, 2.2), PK.TONEBAR: (0.2, 2.0, 3.5), PK.REED: (0.0, 0.25, 1.0),
         PK.PICK: (0.05, None, 0.3), PK.STRINGS: (0.4, 2.0, 5.0), PK.TONE: (0.004, 0.1, 0.5),
         PK.PLUCK: (0.05, None, 0.2), PK.DAMPER: (0.3, 2.0, 5.0)}


def settings(i, v0):
    """Three settings of knob i around v0 (absolute values)."""
    out = []
    for x in RANGE[i]:
        if x is None:
            continue
        if i == PK.HAMMER:
            out.append(v0 + x + 0.25)
        elif i in (PK.STRIKE, PK.LID, PK.TINE, PK.REED, PK.PICK, PK.PLUCK):
            out.append(x)
        else:
            out.append(v0 * x)
    return out


def main():
    d = N.lib()
    if d is None:
        print("native: no library")
        return 1
    NC = None
    D7 = ctypes.c_double * PK.N_KNOBS
    d.nv_voicing_knobs.restype = ctypes.c_int
    d.nv_voicing_knobs.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    d.nv_voicing_apply.restype = None
    d.nv_voicing_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    d.nv_noteclass_size.restype = ctypes.c_size_t
    d.nv_harmonic_decay.restype = ctypes.c_double
    d.nv_harmonic_decay.argtypes = [ctypes.c_void_p, ctypes.c_int]
    d.nv_voicing_apply_organ.restype = None
    d.nv_voicing_apply_organ.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    # (the pianos and electric pianos, GM 0-5; the electric guitars and basses, 26-37)
    voices = [(p, PM.property_class_for_note(p, 60)) for p in list(range(7)) + list(range(26, 38))]
    voices = [(p, c) for p, c in voices if PK.knobs_of(c)]
    # (the variations with classes of their own: Honky-tonk 2 and the like)
    seen = {c for _, c in voices}
    for (p, v), _ in sorted(PM.VARIATIONS.items(), key=lambda kv: kv[0]) if hasattr(PM, 'VARIATIONS') else ():
        if not (p <= 6 or 26 <= p <= 37) or v >= 4096:
            continue
        try:
            c = PM.variation_class(p, v)
        except Exception:
            continue
        c = c(60) if callable(c) and not isinstance(c, type) else c
        if isinstance(c, type) and c not in seen and PK.knobs_of(c):
            seen.add(c)
            voices.append(((p, v), c))
    bad, asked = 0, 0
    # (the VOICE card's millimetres for the Rhodes' GAP: uiapi's RHODES_POLE_MM, the class's unit)
    import re
    import tonelib as T
    src = open(os.path.join(HERE, "native", "uiapi.cpp")).read()
    mm = float(re.search(r"RHODES_POLE_MM = ([0-9.]+);", src).group(1))
    if abs(mm - T.RhodesProperties.pole_halfwidth_mm) > 1e-9:
        print("uiapi RHODES_POLE_MM %g, the class's %g" % (mm, T.RhodesProperties.pole_halfwidth_mm))
        bad += 1
    notes = [(33, 40), (33, 110), (60, 64), (72, 100), (88, 30), (100, 120)]
    for who, base in voices:
        have = PK.knobs_of(base)
        nb = N.note_class(base)
        if nb is None:
            print(who, base.__name__, "not the engine's")
            bad += 1
            continue
        if NC is None:
            NC = type(nb)
            if ctypes.sizeof(NC) != d.nv_noteclass_size():
                print("NoteClass size: ctypes %d, engine %d" % (ctypes.sizeof(NC), d.nv_noteclass_size()))
                return 1
        v0 = D7()
        m = d.nv_voicing_knobs(ctypes.byref(nb), v0)
        mp = sum(1 << i for i in have)
        if m != mp or any(abs(v0[i] - have[i]) > 1e-12 for i in have):
            print(who, base.__name__, "knobs: engine %s %s, Python %s %s" % (bin(m), list(v0), bin(mp), have))
            bad += 1
        line = []
        for i in sorted(have):
            for val in settings(i, have[i]):
                t, mask = PK.transforms(base, {i: val})
                sub = PK.piano_class(base, t, mask)
                na = N.note_class(sub)
                nbm = NC.from_buffer_copy(nb)
                d.nv_voicing_apply(ctypes.byref(nbm), D7(*t), mask)
                moved, bright = 0.0, []
                if PK._harpsi(base):
                    # (a harpsichord's other ranks: the organ's pipes, moved on a
                    # copy as nv_voice_variant moves them, against Python's)
                    OS = type(N.organ(base))
                    oc = OS.from_buffer_copy(OS.from_address(nb.organ))
                    d.nv_voicing_apply_organ(ctypes.byref(oc), D7(*t), mask & (1 << PK.PLUCK | 1 << PK.DAMPER))
                    oa = OS.from_buffer_copy(OS.from_address(na.organ))
                    # (not compared: the organ's family, the plain one's in the
                    # engine -- the same instrument's wind and grouping -- and
                    # each pipe's cached bore_norm, which nv_voice_init makes
                    # again from the pipe's own values: its notes compared below)
                    oa.family = oc.family
                    for j in range(oc.n_pipe):
                        oa.pipe[j].tmpl.bore_norm = oc.pipe[j].tmpl.bore_norm
                    for j in range(oc.n_pipe):
                        for key, vel in notes:
                            f = 440.0 * 2 ** ((key - 69) / 12.0)
                            got = []
                            for o_ in (oc, OS.from_address(na.organ)):
                                s_, n_ = N.VoiceSnap(), N.VoiceNote()
                                c_ = N.VoiceInit.from_buffer_copy(o_.pipe[j].init)
                                tm_ = N.VoiceSnap.from_buffer_copy(o_.pipe[j].tmpl)
                                d.nv_voice_init(ctypes.byref(c_), ctypes.byref(tm_), f, 0.0, vel / 127.0, 1.0, 0.0,
                                                None, ctypes.byref(s_), ctypes.byref(n_))
                                got.append((bytes(s_), bytes(n_)))
                            asked += 1
                            if got[0] != got[1]:
                                bad += 1
                                print(who, base.__name__, PK.NAMES[i], "%.4g" % val, "rank pipe", j, "key", key,
                                      "differs")
                    asked += 1
                    if bytes(oc) != bytes(oa):
                        bad += 1
                        bc_, ba_ = bytes(oc), bytes(oa)
                        diff = [f for f, _ in OS._fields_
                                if bc_[getattr(OS, f).offset:getattr(OS, f).offset + getattr(OS, f).size]
                                != ba_[getattr(OS, f).offset:getattr(OS, f).offset + getattr(OS, f).size]]
                        print(who, base.__name__, PK.NAMES[i], "%.4g" % val, "the ranks' organ differs:", diff,
                              [(oc.pipe[j].tmpl.strike_point, oa.pipe[j].tmpl.strike_point) for j in range(oc.n_pipe)])
                    if i == PK.DAMPER:
                        line.append("damper %.4g: ranks' release %s s" % (val, ", ".join(
                            "%.4g" % oc.pipe[j].release_valve_time for j in range(oc.n_pipe))))
                for key, vel in notes:
                    f = 440.0 * 2 ** ((key - 69) / 12.0)
                    out = []
                    for k in (na, nbm, nb):
                        s, o = N.VoiceSnap(), N.VoiceNote()
                        c = N.VoiceInit.from_buffer_copy(k.init)
                        c.detune_lo, c.detune_hi = k.detune_lo, k.detune_hi
                        tm = N.VoiceSnap.from_buffer_copy(k.tmpl)
                        d.nv_voice_init(ctypes.byref(c), ctypes.byref(tm), f, 0.0, vel / 127.0, 1.0, 0.0, None,
                                        ctypes.byref(s), ctypes.byref(o))
                        vols = [d.nv_harmonic_volume(ctypes.byref(s), h) for h in range(1, 41)]
                        out.append((bytes(s), bytes(o), vols))
                    asked += 1
                    if out[0][0] != out[1][0] or out[0][1] != out[1][1] or out[0][2] != out[1][2]:
                        bad += 1
                        print(who, base.__name__, PK.NAMES[i], "%.4g" % val, "key", key, "vel", vel,
                              "differs:", "snap" if out[0][0] != out[1][0] else "",
                              "note" if out[0][1] != out[1][1] else "",
                              "volumes" if out[0][2] != out[1][2] else "")
                    def cent(v):        # (the spectrum's centroid, in harmonics, power-weighted)
                        e = sum(x * x for x in v)
                        return sum((h + 1) * x * x for h, x in enumerate(v)) / e if e > 0 else 0.0
                    ca, cb = cent(out[0][2]), cent(out[2][2])
                    if i == PK.STRINGS:     # (the strings' loss: harmonic 8's decay rate against the plain's)
                        sa, sb = (N.VoiceSnap.from_buffer_copy(out[j][0]) for j in (0, 2))
                        ra, rb = d.nv_harmonic_decay(ctypes.byref(sa), 8), d.nv_harmonic_decay(ctypes.byref(sb), 8)
                        if rb > 0:
                            bright.append(100.0 * (ra / rb - 1.0))
                    elif cb > 0:
                        bright.append(100.0 * (ca / cb - 1.0))
                    if i == PK.UNISON:      # (the spread is the strings' draws, not the volumes)
                        sa = N.VoiceSnap.from_buffer_copy(out[0][0])
                        moved = max(moved, abs(sa.note_detune_cents[1] - sa.note_detune_cents[0]))
                if i == PK.UNISON:
                    line.append("%s %.3g: strings up to %.2f c apart" % (PK.NAMES[i], val, moved))
                else:
                    line.append("%s %.4g: %s %+.0f%%" % (PK.NAMES[i], val, "h8 decay" if i == PK.STRINGS else "brightness",
                                                      sum(bright) / max(1, len(bright))))
        print(who, base.__name__, "|", "; ".join(line))
    print("%d notes compared, %d failed" % (asked, bad))
    return bad


if __name__ == '__main__':
    sys.exit(main())
