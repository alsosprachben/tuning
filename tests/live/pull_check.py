#!/usr/bin/env python3
"""An app's audio callback on the host library (host.h's nv_host_pull,
nv_host_midi_at): python3 tests/live/pull_check.py [FILE.mid] [SECONDS]

An app's audio comes from the system's callback -- AVAudioEngine's source
node, an Audio Unit -- asking for whatever its buffer holds (256, 512, 471
frames ...), and its MIDI arrives stamped with a time. The host renders
128-frame blocks; nv_host_pull fills any size from them, nv_host_midi_at puts
a message in the block its sample falls in. Four hosts, each in a process of
its own (a host holds the export and is not freed), on FILE's first SECONDS:

  blocks   each block's events by nv_host_midi just before it is rendered
           (host_api_check's way: the reference)
  timed    every event up front by nv_host_midi_at (its sample), then
           rendered block by block
  pull     the same up front, pulled in random sizes from 1 to 4100 frames
  late     (the control) the same pull, every stamp a block late
  rt       blocks with the real-time mode on (nv_host_set_realtime: an app's
           -- the room's body convolved on the audio thread, not its worker)

blocks, timed, pull and rt must be the same samples, every one; late must not
be (the stamps are what places the events), and the file must sound (its
events delivered: their count and the peak shown). Exits 1 if not.
"""
import ctypes
import os
import random
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))


def child(nvx, mid, case, secs, outp):
    from host_check import encode
    import native as N
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_rate", [vp]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_pull", [vp, vp, vp, ci]),
                 ("nv_host_midi_at", [vp, cp, ci, ctypes.c_longlong]), ("nv_host_set_realtime", [vp, ci])):
        getattr(d, f).argtypes = a
    d.nv_midi_read.restype = vp
    d.nv_midi_read.argtypes = [cp, ctypes.c_longlong, ctypes.POINTER(ci)]
    d.nv_midi_n_events.argtypes = [vp]
    d.nv_midi_event.argtypes = [vp, ci, ctypes.POINTER(ci), ctypes.POINTER(ctypes.c_double)]
    d.nv_midi_sysex.argtypes = [vp, ci, cp, ci]
    raw = open(mid, "rb").read()
    err = ci(0)
    m = d.nv_midi_read(raw, len(raw), ctypes.byref(err))
    av = [b"nvlive", nvx.encode(), b"--program=0", b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-drums", b"--reg-sync", b"--no-governor"]
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the host refused"
    d.nv_host_start(h)
    if case == "rt":
        d.nv_host_set_realtime(h, 1)
    blk, sr = d.nv_host_block(h), d.nv_host_rate(h)
    nblk = int(secs * sr) // blk
    total = nblk * blk
    iv = (ci * 4)()
    t = ctypes.c_double()
    xb = ctypes.create_string_buffer(65536)
    evs = []
    for e in range(d.nv_midi_n_events(m)):
        d.nv_midi_event(m, e, iv, ctypes.byref(t))
        sx = b""
        if iv[0] == 6:
            sx = xb.raw[:d.nv_midi_sysex(m, iv[2], xb, 65536)]
        by = encode(list(iv), sx)
        if by and int(t.value * sr) < total:
            evs.append((int(t.value * sr), by))
    out = np.zeros((total, 2), np.float32)
    if case in ("blocks", "rt"):
        L = np.zeros(blk, np.float32)
        R = np.zeros(blk, np.float32)
        e = 0
        for b in range(nblk):
            while e < len(evs) and evs[e][0] // blk <= b:
                d.nv_host_midi(h, evs[e][1], len(evs[e][1]))
                e += 1
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
            out[b * blk:(b + 1) * blk, 0] = L
            out[b * blk:(b + 1) * blk, 1] = R
    else:
        shift = blk if case == "late" else 0
        for fr, by in evs:
            d.nv_host_midi_at(h, by, len(by), fr + shift)
        if case == "timed":
            L = np.zeros(blk, np.float32)
            R = np.zeros(blk, np.float32)
            for b in range(nblk):
                d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
                out[b * blk:(b + 1) * blk, 0] = L
                out[b * blk:(b + 1) * blk, 1] = R
        else:
            rng = random.Random(11)
            L = np.zeros(4200, np.float32)
            R = np.zeros(4200, np.float32)
            at, sizes = 0, []
            while at < total:
                n = min(total - at, rng.choice([rng.randint(1, 4100), 256, 512, 471, 1024, 127, 129]))
                d.nv_host_pull(h, L.ctypes.data, R.ctypes.data, n)
                out[at:at + n, 0] = L[:n]
                out[at:at + n, 1] = R[:n]
                at += n
                sizes.append(n)
            print("SIZES %d calls, %d to %d frames" % (len(sizes), min(sizes), max(sizes)))
    print("EVENTS %d" % len(evs))
    np.save(outp, out)
    sys.stdout.flush()
    os._exit(0)                         # (the host's threads run to the end: not waited for)


def main(argv):
    if argv and argv[0] == "--child":
        return child(*argv[1:4], float(argv[4]), argv[5])
    mid = argv[0] if argv else os.path.join(HERE, "midi", "chords3.mid")
    secs = float(argv[1]) if len(argv) > 1 else 5.0
    import nvlive_check as NC
    tmp = tempfile.mkdtemp(prefix="pullcheck")
    nvx = NC.live_export(tmp, "hall")
    got, info = {}, {}
    for case in ("blocks", "timed", "pull", "late", "rt"):
        outp = os.path.join(tmp, case + ".npy")
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", nvx, mid, case, str(secs), outp],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(outp):
            print("  %s: the host failed\n%s" % (case, r.stderr[-1500:]))
            return 1
        got[case] = np.load(outp)
        info[case] = " ".join(ln for ln in r.stdout.splitlines() if ln.startswith(("EVENTS", "SIZES")))
    bad = 0

    def check(what, ok, detail=""):
        nonlocal bad
        bad += not ok
        print("  %-62s %s  %s" % (what, "ok" if ok else "FAILED", detail), flush=True)

    ref = got["blocks"]
    peak = float(np.abs(ref).max())
    check("blocks: the file sounds (%s)" % info["blocks"], peak > 1e-3, "peak %.3g" % peak)
    for case in ("timed", "pull", "rt"):
        a = got[case]
        n = int((a != ref).sum())
        check("%s: the same samples as blocks (%s)" % (case, info[case]), n == 0,
              "%d of %d differ, max %.3g" % (n, a.size, float(np.abs(a - ref).max())))
    n = int((got["late"] != ref).sum())
    check("late (the control): every stamp a block late differs", n > 0, "%d of %d differ" % (n, ref.size))
    print("pull: %d failed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
