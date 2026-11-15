#!/usr/bin/env python3
"""A Moog part's knobs, an organ's drive and the globals through the host
library (host.h: nv_host_synth_*, nv_host_drive, nv_host_global -- the app's
Synth tab and Globals): python3 tests/live/synth_globals_check.py

  synth   the host on program 81 (a Moog): the panel's knob table whole;
          the part read (a Moog, its knobs); the cutoff turned down -- read
          back as turned, a held chord darker for it (the centroid down), its
          words ("Hz"); back to the patch's -- the chord as before
  organ   the host on program 16: an organ, its drive read; set, read back
  globals every global counted; the bend range and the metronome's tempo set,
          read back; a part's reverb send and velocity sense set on every
          channel, its pan hard left -- read back; panned left then right,
          the far side quieter each way

Exits 1 if any check fails.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))
NK = 51


def child(nvx, case):
    import native as N
    d = N.lib()
    vp, cp, ci, cd = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_double
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    d.nv_host_global.restype = cd
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_building", [vp]), ("nv_host_synth_knobs", [cp, ci]),
                 ("nv_host_synth_get", [vp, ci, ci, vp, vp]), ("nv_host_synth_set", [vp, ci, ci, ci, cd]),
                 ("nv_host_synth_forget", [vp, ci, ci, ci]), ("nv_host_synth_fmt", [cp, cd, vp, cp, ci]),
                 ("nv_host_drive", [vp, ci, vp]), ("nv_host_set_drive", [vp, ci, cd]),
                 ("nv_host_global", [vp, ci]), ("nv_host_set_global", [vp, ci, cd]),
                 ("nv_host_chan_cc", [vp, ci, ci]), ("nv_host_chan_cc_send", [vp, ci, ci, ci])):
        getattr(d, f).argtypes = a
    prog = {"synth": 81, "organ": 16, "globals": 0}[case]
    av = [b"nvlive", nvx.encode(), b"--program=%d" % prog, b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-drums", b"--reg-sync", b"--no-governor", b"--messenger-out=none"]
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the host refused"
    d.nv_host_start(h)
    blk = d.nv_host_block(h)
    L = np.zeros(blk, np.float32)
    R = np.zeros(blk, np.float32)
    bad = 0

    def check(what, ok, detail=""):
        nonlocal bad
        bad += not ok
        print("  %-62s %s  %s" % (what, "ok" if ok else "FAILED", detail), flush=True)

    def run(n):
        for _ in range(n):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)

    def aside(fn):
        # (read between two blocks, as the app reads it: from another thread while this one renders)
        out = []
        t = threading.Thread(target=lambda: out.append(fn()))
        t.start()
        while t.is_alive():
            run(1)
        return out[0]

    def settle():
        quiet = 0
        for _ in range(8000):
            run(1)
            quiet = 0 if d.nv_host_building(h) else quiet + 1
            if quiet >= 100:
                return

    def centroid():
        run(400)
        for k in (48, 55, 60, 64):
            d.nv_host_midi(h, bytes([0x90, k, 100]), 3)
        x = []
        for i in range(375):
            run(1)
            if i >= 190:
                x.append(L.copy())
        for k in (48, 55, 60, 64):
            d.nv_host_midi(h, bytes([0x80, k, 0]), 3)
        y = np.concatenate(x)
        sp = np.abs(np.fft.rfft(y * np.hanning(len(y))))
        fr = np.fft.rfftfreq(len(y), 1.0 / 48000)
        return float((sp * fr).sum() / sp.sum())

    settle()
    if case == "synth":
        b = ctypes.create_string_buffer(16384)
        d.nv_host_synth_knobs(b, 16384)
        knobs = [ln.split("\t") for ln in b.value.decode().split("\n") if ln]
        idx = {k[3] + ":" + k[2]: int(k[1]) for k in knobs}
        check("the knob table: %d knobs, %d sections" % (len(knobs), len({k[0] for k in knobs})),
              len(knobs) >= 50 and all(0 <= int(k[1]) < NK for k in knobs))
        pn = (cd * NK)()
        own = (ctypes.c_char * NK)()
        n = aside(lambda: d.nv_host_synth_get(h, 0, 0, pn, own))
        cut = idx["hz:cutoff"]
        c0 = pn[cut]
        check("part 1 read: a Moog", n >= 1, "%d layer(s), cutoff %.3f" % (n, c0))
        base = centroid()
        d.nv_host_synth_set(h, 0, 0, cut, 0.25)
        run(20)
        n = aside(lambda: d.nv_host_synth_get(h, 0, 0, pn, own))
        check("its cutoff turned to 0.25: read back, marked turned", abs(pn[cut] - 0.25) < 1e-9 and own[cut] == b"\x01",
              "%.3f, own %d" % (pn[cut], own[cut][0]))
        w = ctypes.create_string_buffer(64)
        d.nv_host_synth_fmt(b"hz", pn[cut], pn, w, 64)
        check("...in the panel's words", w.value.decode().endswith("Hz"), w.value.decode())
        dark = centroid()
        check("...a held chord darker for it (the centroid down)", dark < 0.8 * base, "%.0f -> %.0f Hz" % (base, dark))
        d.nv_host_synth_forget(h, 0, 0, cut)
        run(20)
        aside(lambda: d.nv_host_synth_get(h, 0, 0, pn, own))
        back = centroid()
        check("back to the patch's: read back, the chord as before (10%)",
              abs(pn[cut] - c0) < 1e-9 and own[cut] == b"\x00" and abs(back / base - 1) < 0.10,   # (a Moog's oscillators run free: untouched takes differ ~7%)

              "cutoff %.3f, %.0f Hz" % (pn[cut], back))
    elif case == "organ":
        pn = (cd * NK)()
        own = (ctypes.c_char * NK)()
        n = aside(lambda: d.nv_host_synth_get(h, 0, 0, pn, own))
        dv = (cd * 3)()
        r = aside(lambda: d.nv_host_drive(h, 0, dv))
        check("program 16: not a Moog, an organ with a drive", n == 0 and r == 1, "drive %.2f (the voice's %.2f)" % (dv[0], dv[1]))
        d.nv_host_set_drive(h, 0, 1.5)
        run(20)
        aside(lambda: d.nv_host_drive(h, 0, dv))
        check("its drive set to 1.5: read back", abs(dv[0] - 1.5) < 1e-9 and abs(dv[2] - 1.5) < 1e-9, "%.2f" % dv[0])
    else:
        cnt = d.nv_host_global_count()
        check("the globals counted", cnt == 14, "%d" % cnt)
        d.nv_host_set_global(h, 3, 12.0)
        d.nv_host_set_global(h, 10, 96.0)
        run(40)
        check("the bend range 12, the metronome 96 bpm: read back",
              d.nv_host_global(h, 3) == 12.0 and d.nv_host_global(h, 10) == 96.0,
              "%.1f st, %.0f bpm" % (d.nv_host_global(h, 3), d.nv_host_global(h, 10)))
        d.nv_host_set_global(h, 10, 0.0)

        # A PART's PAN AND SENDS: set on every channel, read back; panned hard left, its right side quiet
        def lr():
            run(400)
            d.nv_host_midi(h, bytes([0x90, 60, 100]), 3)
            l = r = 0.0
            for i in range(150):
                run(1)
                if i >= 40:
                    l += float((L ** 2).sum())
                    r += float((R ** 2).sum())
            d.nv_host_midi(h, bytes([0x80, 60, 0]), 3)
            return l, r
        d.nv_host_chan_cc_send(h, -1, 91, 0)
        run(30)
        l0, r0 = lr()
        d.nv_host_chan_cc_send(h, -1, 91, 100)
        d.nv_host_chan_cc_send(h, -1, 1000, 90)
        d.nv_host_chan_cc_send(h, 0, 10, 0)
        run(30)
        got = [d.nv_host_chan_cc(h, 0, 91), d.nv_host_chan_cc(h, 5, 91), d.nv_host_chan_cc(h, 0, 1000), d.nv_host_chan_cc(h, 0, 10)]
        check("reverb send 100 and vel sense 90 on every channel, pan 0: read back", got == [100, 100, 90, 0], "%s" % got)
        d.nv_host_chan_cc_send(h, -1, 91, 0)       # (the pan heard dry: the room's return is both sides)
        run(30)
        l1, r1 = lr()
        d.nv_host_chan_cc_send(h, 0, 10, 127)
        run(30)
        l2, r2 = lr()
        # (the engine's pan is a head's shadow, not a level law: the far ear
        # loses the highs, so a piano's C4 moves its energy ~20%, each way)
        check("...pan 0 / 127: the far side quieter, each way (right/left)",
              r1 / l1 < 0.9 * (r0 / l0) and r2 / l2 > 1.1 * (r0 / l0),
              "centre %.2f, left %.2f, right %.2f" % (r0 / l0, r1 / l1, r2 / l2))
    sys.stdout.flush()
    os._exit(1 if bad else 0)


def main(argv):
    if argv and argv[0] == "--child":
        return child(argv[1], argv[2])
    import nvlive_check as NC
    tmp = tempfile.mkdtemp(prefix="synthglob")
    nvx = NC.live_export(tmp, "hall")
    bad = 0
    for case in ("synth", "organ", "globals"):
        r = subprocess.run([sys.executable, "-u", os.path.abspath(__file__), "--child", nvx, case],
                           capture_output=True, text=True)
        sys.stdout.write("".join(ln + "\n" for ln in r.stdout.splitlines() if ln.startswith("  ")))
        if r.returncode:
            bad += 1
            if "FAILED" not in r.stdout:
                print("  %s: the host failed\n%s" % (case, r.stderr[-1500:]))
    print("synth and globals: %d failed" % bad)
    shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
