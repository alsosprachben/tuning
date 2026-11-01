#!/usr/bin/env python3
"""Does native/nvlive play a MIDI file as live.Live does?

    python3 examples/nvlive_check.py FILE.mid [SECONDS] [--program=N] [--register]

The first SECONDS (default 20) of FILE, cut as bitident cuts, its notes and
controllers (the native reader's, in message order) each applied at the
start of the 128-sample block its time falls in: once through nvlive --test
(the native live piano, from a live export: examples/native_export.py
--live), once through live.Live(program, 48 kHz, 128 a block, on the CPU)
by on_midi and its own callback -- its patch warmed first, its governor off
-- capturing each block's dry render (Renderer.render). Every sample of the
two compared with ==. The file's programs are not followed: the part plays
PROGRAM throughout, as a keyboard would. --register: the free strings too,
each side's register worker answering in step (examples/regsync.py; nvlive
with its export's LREG); without, nvlive --no-register.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import mido
    import numpy as np
    import bitident as BI
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L
    import native as N
    prog = int(opt.get("program", 0))
    secs = float(args[1]) if len(args) > 1 else 20.0
    tmp = tempfile.mkdtemp(prefix="nvlivecheck")
    mid = os.path.join(tmp, "in.mid")
    BI.excerpt(args[0], secs).save(mid)
    nvx = os.path.join(tmp, "live.nvx")
    subprocess.check_call([sys.executable, os.path.join(HERE, "examples", "native_export.py"), nvx, "--live"],
                          stdout=subprocess.DEVNULL)
    exe = N.build_nvlive()
    m = N.Midi(mid)
    if m.error:
        print("refused: %s" % N.MIDI_REFUSED.get(m.error, m.error))
        return 2
    total = m.total() + 3.0
    out = os.path.join(tmp, "nv.wav")
    reg = "register" in opt
    subprocess.check_call([exe, nvx, "--test", mid, out, "--program=%d" % prog, "--seconds=%r" % total]
                          + ([] if reg else ["--no-register"]), stderr=subprocess.DEVNULL)
    raw = open(out, "rb").read()          # float32 stereo after a 44-byte header
    nv = np.frombuffer(raw[44:], np.float32).reshape(-1, 2)
    # live.Live, fed the same events on the same blocks
    lv = L.Live(program=prog, rate=48000, frames=128, verbose=False, threads=1, gpu=False)
    lv.parts[0].patch.warm()
    lv.slab.shed = lambda n, frac: 0
    if reg:
        import regsync
        regsync.sync(lv, lv.parts[0])
    dry = []
    _rend = lv.renderer.render

    def cap(n0, frames):
        a, b = _rend(n0, frames)
        dry.append(np.stack([a.copy(), b.copy()], 1))
        return a, b
    lv.renderer.render = cap
    evs = m.events()
    nb = int(total * 48000) // 128
    e = 0
    M = mido.Message
    for b in range(nb):
        while e < len(evs) and int(evs[e][0] * 48000) // 128 <= b:
            t, ty, ch, a, v = evs[e]
            if ty == 0:
                lv.on_midi(M("note_on", channel=ch, note=a, velocity=v))
            elif ty == 1:
                lv.on_midi(M("note_off", channel=ch, note=a, velocity=0))
            else:
                lv.on_midi(M("control_change", channel=ch, control=a, value=v))
            e += 1
        lv.callback(None, 128, None, 0)
    py = np.concatenate(dry) if dry else np.zeros((0, 2), np.float32)
    if py.shape != nv.shape:
        print("%s: length %r vs %r" % (os.path.basename(args[0]), py.shape, nv.shape))
        return 1
    d = np.flatnonzero(np.any(py != nv, 1))
    print("%s (%g s, program %d%s): %d blocks, %s" % (
        os.path.basename(args[0]), secs, prog, ", register" if reg else "", nb,
        "identical" if not len(d) else "%d frames differ from block %d (max %g)"
        % (len(d), d[0] // 128, float(np.max(np.abs(py.astype(np.float64) - nv))))))
    return 1 if len(d) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
