#!/usr/bin/env python3
"""Does the native engine render a piano file as blockrender does?

    python3 examples/render_check.py FILE.mid [SECONDS] [--tuner=NAME] [--wav=OUT]

Three renders of the same excerpt, on the CPU, compared sample for sample:

  python   blockrender.prepare all in Python (the register on its C core),
           then synth_window(prep, 0, N) -- the dry render bitident compares
  render   the same table through native/render.cpp (nv_render): the kernel's
           three entries routed as synth_partials routes them, the master
           gain, the clip
  native   the engine end to end: the file read by native/midi.cpp, its
           table by nv_prepare (notes, register, length, damper tracks), the
           render by nv_render

"render" equal to "python" proves the render loop; "native" equal to it, the
whole engine for the file. Still Python's: the tuning table and each channel's
bend row (as play_check's). --wav writes the native render (16-bit).
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
    os.environ["TUNING_NATIVE_TONE"] = "off"
    os.environ["TUNING_REGISTER_C"] = "1"
    os.environ["TUNING_GPU"] = ""
    import numpy as np
    import bitident as BI
    import blockrender as B
    import native as N
    import tonelib as T
    src = BI.excerpt(args[0], float(args[1])) if len(args) > 1 else args[0]
    tuner = opt.get("tuner") or "hybrid440"
    m = N.Midi(src)
    if m.error:
        print("refused: %s" % N.MIDI_REFUSED.get(m.error, m.error))
        return 2
    with contextlib.redirect_stdout(io.StringIO()):
        P = B.prepare(src, tuner=tuner)
    pL, pR = B.synth_window(P, 0, P['N'])
    rL, rR = N.render(P)
    br = {}
    for c, r in zip(np.asarray(P["mch"]), np.asarray(P["br"])):
        br.setdefault(int(c), int(r))
    song = m.song(m.total(), lambda p, d: B.program_trim(B.DrumProgram(p) if d else p, d, gs=B._GS_FILE[0]),
                  freq=B.tuning_table(tuner), faders=set(P.get("fader_rows") or ()))
    t = N.NoteIn()
    t.sr, t.retrigger_fade, t.nyq_om = B.SR, B.RETRIGGER_FADE, 0.98 * math.pi
    t.sv[:] = [0.0, 1.0]
    t.sound_vib_depth_cents, t.vibrato_delay = T.SOUND_VIB_DEPTH_CENTS, 0.0
    t.gl[:] = [0.0, 0.05, 0.0]
    t.fx, t.mk, t.fm_omega, t.fm_phase = -1.0, 0.0, 0.0, 0.0
    t.room_bands[:] = [63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0]
    t.reflect = int(os.environ.get("TUNING_REFLECT", "1") not in ("0", "off", ""))
    t.fixed_touch = int(bool(T.FIXED_TOUCH))
    Q = N.prepare(song, lambda p, k: B.property_class_for_note(p, k), t, br, m.total())
    if isinstance(Q, tuple):
        print("not the engine's: note %d" % Q[1])
        return 2
    nL, nR = N.render(N.final(Q))

    def cmp(a, b):
        if len(a) != len(b):
            return "length %d vs %d" % (len(a), len(b))
        d = np.flatnonzero(a != b)
        return "identical" if not len(d) else "%d samples differ from %d (max %g)" % (
            len(d), d[0], float(np.max(np.abs(a.astype(np.float64) - b))))
    print("%s: %d samples; render vs python: L %s, R %s; native vs python: L %s, R %s"
          % (os.path.basename(args[0]), len(pL), cmp(rL, pL), cmp(rR, pR), cmp(nL, pL), cmp(nR, pR)))
    if opt.get("wav"):
        B.write_wav(opt["wav"], nL, nR)
        print("wrote %s" % opt["wav"])
    same = all(np.array_equal(x, y) for x, y in ((rL, pL), (rR, pR), (nL, pL), (nR, pR)))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
