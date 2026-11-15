#!/usr/bin/env python3
"""Tuning through the host library (host.h: nv_host_tuners, nv_host_tuner,
nv_host_set_tuner, nv_host_eastern, nv_host_set_eastern -- the app's Tuning):
python3 tests/live/tuning_check.py

The host on the piano at the export's tuner (live's hybrid, A=415): the list
of tuners whole (the panel's), the tuner in force read back; an A4 held and
its pitch measured; hybrid440 asked for, built -- read back, and the same A4
up by 440/415 (+101 cents); an Eastern tuning set, built, read back; off.
Exits 1 if any check fails.
"""
import ctypes
import math
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))


def main():
    import nvlive_check as NC
    import native as N
    tmp = tempfile.mkdtemp(prefix="tuning")
    nvx = NC.live_export(tmp, "hall")
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_building", [vp]), ("nv_host_tuners", [cp, ci]),
                 ("nv_host_tuner", [vp, cp, ci]), ("nv_host_set_tuner", [vp, cp]),
                 ("nv_host_eastern", [vp, cp, ci]), ("nv_host_set_eastern", [vp, cp])):
        getattr(d, f).argtypes = a
    d.nv_raga_system_name.restype = cp
    d.nv_raga_system_name.argtypes = [ci]
    av = [b"nvlive", nvx.encode(), b"--program=0", b"--cpu", b"--no-pipeline", b"--no-register",
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

    def settle(seconds=180.0):
        # rendered until the builder has been idle 100 blocks running -- bounded
        # by the clock, not a count of blocks: blocks render far faster than
        # real time, and a tuner rebuilds every patch (on the M3 past 12000)
        import time
        quiet, i, t0 = 0, 0, time.monotonic()
        while time.monotonic() - t0 < seconds:
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
            i += 1
            quiet = 0 if d.nv_host_building(h) else quiet + 1
            if quiet >= 100:
                return i
        return -1

    def text(fn, *a):
        b = ctypes.create_string_buffer(65536)
        fn(*(a + (b, 65536)))
        return b.value.decode()

    def pitch():
        # A4 held, its frequency from 0.5 s of it (the spectrum's peak near 400-470 Hz)
        for _ in range(300):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
        d.nv_host_midi(h, bytes([0x90, 69, 90]), 3)
        x = []
        for i in range(380):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
            if i >= 190:
                x.append(L.copy())
        d.nv_host_midi(h, bytes([0x80, 69, 0]), 3)
        y = np.concatenate(x) * np.hanning(len(x) * blk)
        n = 1 << 18
        sp = np.abs(np.fft.rfft(y, n))
        fr = np.fft.rfftfreq(n, 1.0 / 48000)
        band = (fr > 380) & (fr < 480)
        k = np.argmax(sp * band)
        a, b, c = sp[k - 1], sp[k], sp[k + 1]
        return fr[k] + 0.5 * (a - c) / (a - 2 * b + c) * (fr[1] - fr[0])

    settle()
    tl = text(d.nv_host_tuners).split("\n")
    names = [t.split("\t")[0] for t in tl]
    check("the tuners listed (%d), hybrid440 and hybrid among them" % len(names),
          len(names) > 20 and "hybrid440" in names and "hybrid" in names)
    now = text(d.nv_host_tuner, h)
    f0 = pitch()
    check("the tuner in force: %s, an A4 at %.2f Hz" % (now, f0), now == "hybrid" and 400 < f0 < 430)
    d.nv_host_set_tuner(h, b"hybrid440")
    n = settle()
    now2 = text(d.nv_host_tuner, h)
    f1 = pitch()
    c = 1200 * math.log2(f1 / f0)
    check("hybrid440 asked, built in %d blocks: read back %s" % (n, now2), n >= 0 and now2 == "hybrid440")
    check("...the A4 up by 440/415 (+101.2 cents)", abs(c - 1200 * math.log2(440 / 415)) < 3,
          "%.2f Hz, %+.1f cents" % (f1, c))
    sysn = d.nv_raga_system_name(0)
    check("the Eastern tuning's systems listed (first: %s)" % (sysn.decode() if sysn else None), bool(sysn))
    d.nv_host_set_eastern(h, b"raga:et@c#")
    n = settle()
    check("an Eastern tuning set, built (%d blocks): read back" % n, n >= 0 and text(d.nv_host_eastern, h) == "raga:et@c#",
          text(d.nv_host_eastern, h))
    d.nv_host_set_eastern(h, b"")
    settle()
    check("...and off", text(d.nv_host_eastern, h) == "")
    print("tuning: %d failed" % bad)
    sys.stdout.flush()
    shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    os._exit(1 if bad else 0)


if __name__ == "__main__":
    main()
