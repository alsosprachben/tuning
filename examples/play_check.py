#!/usr/bin/env python3
"""Does the native engine play a piano file's notes as blockrender does?

    python3 examples/play_check.py FILE.mid [SECONDS] [--tuner=NAME] [--register] [--prepare]

The engine on its own from the file's bytes: native/midi.cpp reads it,
native/channel.cpp keeps its channels, and nv_play plays every note in the
note loop's order (nv_song_play: the voice, its times, knock, tone,
phantoms, the room's images), the global random stream carried from
_prepare's seed. Against blockrender.prepare all in Python
(TUNING_NATIVE_TONE=off): the table's first rows -- the notes' -- column by
column, with ==, cast to the table's column types.

Still the Python's, as inputs: the tuning table (the tuner), each channel's
bend or fader row number (from the table: the bend rows are a pass not
ported), and the emitter's constants. A file with a note the engine does not
play (not a native piano class, a drum) is refused. Notes only: the
register's rows and the rest of the table after them are not compared.
"""
import contextlib
import io
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"        # the reference: all Python...
    if "prepare" in opt:
        opt["register"] = ""
    if "register" in opt:
        os.environ["TUNING_REGISTER_C"] = "1"       # ...its register on its C core
    import numpy as np
    import bitident as BI
    import blockrender as B
    import native as N
    import tonelib as T
    path = args[0]
    src = BI.excerpt(path, float(args[1])) if len(args) > 1 else path
    tuner = opt.get("tuner") or "hybrid440"
    m = N.Midi(src)
    if m.error:
        print("refused: %s" % N.MIDI_REFUSED.get(m.error, m.error))
        return 2
    with contextlib.redirect_stdout(io.StringIO()):
        P = B.prepare(src, tuner=tuner)
    # each channel's bend (or fader) row, as the table has it
    br = {}
    for c, r in zip(np.asarray(P["mch"]), np.asarray(P["br"])):
        br.setdefault(int(c), int(r))
    freq = B.tuning_table(tuner)
    song = m.song(m.total(), lambda p, d: B.program_trim(B.DrumProgram(p) if d else p, d, gs=B._GS_FILE[0]),
                  freq=freq, faders=set(P.get("fader_rows") or ()))
    t = N.NoteIn()
    t.sr, t.retrigger_fade, t.nyq_om = B.SR, B.RETRIGGER_FADE, 0.98 * math.pi
    t.sv[:] = [0.0, 1.0]
    t.sound_vib_depth_cents, t.vibrato_delay = T.SOUND_VIB_DEPTH_CENTS, 0.0
    t.gl[:] = [0.0, 0.05, 0.0]
    t.fx, t.mk, t.fm_omega, t.fm_phase = -1.0, 0.0, 0.0, 0.0
    t.room_bands[:] = [63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0]
    t.reflect = int(os.environ.get("TUNING_REFLECT", "1") not in ("0", "off", ""))
    t.fixed_touch = int(bool(T.FIXED_TOUCH))

    def classes(prog, key):
        return B.property_class_for_note(prog, key)

    nn = len(m.notes())
    scale = float(os.environ.get("TUNING_REGISTER", "1") or 1)
    extra = []
    if "prepare" in opt:
        Q = N.prepare(song, classes, t, br, m.total(), scale=scale)
        if isinstance(Q, tuple):
            got = Q
        else:
            got = (np.stack([Q[c].astype(np.float64) for c in B.EMIT_COLS], 1),)
            for k in ("dk", "dg", "DM", "DMO", "DMB", "DMN"):
                # a half-pedalled song's damper tracks
                if (k in P) != (k in Q):
                    extra.append("%s %s" % (k, "missing" if k in P else "extra"))
                elif k in P and not (np.asarray(P[k]).dtype == np.asarray(Q[k]).dtype
                                     and np.array_equal(np.asarray(P[k]), np.asarray(Q[k]))):
                    extra.append("%s differs" % k)
            for k in ("N", "nblk", "P", "total", "sym_rows", "room_q"):
                a, b = P[k], Q[k]
                if k == "room_q":
                    a, b = [tuple(float(x) for x in q) for q in a], [tuple(float(x) for x in q) for q in b]
                if a != b:
                    extra.append("%s (%r vs %r)" % (k, a, b))
    else:
        got = N.play(song, classes, t, br, 600 * max(nn, 1), register="register" in opt, scale=scale)
    if got[0] is None:
        print("not the engine's: note %d %r" % (got[1], m.notes()[got[1]]))
        return 2
    rows = got[0]
    n = len(rows)
    bad, skipped = list(extra), []
    for j, c in enumerate(B.EMIT_COLS):
        if c not in P:
            skipped.append(c)       # used by the passes after the notes, not returned ('dr')
            continue
        py = np.asarray(P[c])
        if len(py) < n:
            bad.append("%s (table has %d rows)" % (c, len(py)))
            continue
        a = py[:n]
        b = rows[:, j].astype(a.dtype)
        if not np.array_equal(a, b):
            k = int(np.nonzero(a != b)[0][0])
            bad.append("%s from row %d (%r vs %r)" % (c, k, a[k], b[k]))
    print("native play: %d notes, %d rows; the table %d rows; %s%s"
          % (nn, n, len(np.asarray(P["om"])), "identical" if not bad else "DIFFER: " + "; ".join(bad[:6]),
             " (not returned, not compared: %s)" % " ".join(skipped) if skipped else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
