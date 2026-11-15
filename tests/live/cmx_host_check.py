#!/usr/bin/env python3
"""The controller matrix through the host library (host.h: nv_host_cmx_* --
the app's Matrix tab): python3 tests/live/cmx_host_check.py

The host on the piano: channel 1's matrix read -- a reset's (the mod wheel
47 cents of LFO1 pitch, the bend 2 semitones, CC1 16, CC2 17); the mod wheel
given -50% amplitude, read back in its unit; a held note with the wheel up
quieter for it than with the wheel down; CC1 assigned 20 on every channel
(-1), read back on channels 1 and 6; the byte laws (a byte's depth, the byte
nearest it). Exits 1 if any check fails.
"""
import ctypes
import os
import shutil
import sys
import tempfile
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))


class Gm2(ctypes.Structure):
    _fields_ = [("cc", ctypes.c_int), ("dest", ctypes.c_int), ("depth", ctypes.c_double)]


class Cmx(ctypes.Structure):
    _fields_ = [("cc1", ctypes.c_int), ("cc2", ctypes.c_int), ("depth", (ctypes.c_double * 11) * 6),
                ("ngm2", ctypes.c_int), ("gm2", Gm2 * 32)]


def main():
    import nvlive_check as NC
    import native as N
    tmp = tempfile.mkdtemp(prefix="cmxhost")
    nvx = NC.live_export(tmp, "hall")
    d = N.lib()
    vp, cp, ci, cd = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_double
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    d.nv_host_cmx_depth.restype = cd
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_cmx_state", [vp, ci, vp]),
                 ("nv_host_cmx_cell", [vp, ci, ci, ci, ci]), ("nv_host_cmx_assign", [vp, ci, ci, ci]),
                 ("nv_host_cmx_depth", [ci, ci]), ("nv_host_cmx_raw", [ci, cd]),
                 ("nv_host_cmx_printed", [ci, cd, cp, ci])):
        getattr(d, f).argtypes = a
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

    def run(n):
        for _ in range(n):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)

    def state(ch):
        # (read between two blocks: from another thread while this one renders)
        m = Cmx()
        out = []
        t = threading.Thread(target=lambda: out.append(d.nv_host_cmx_state(h, ch, ctypes.byref(m))))
        t.start()
        while t.is_alive():
            run(1)
        return m if out and out[0] == 0 else None

    def printed(dest, dep):
        b = ctypes.create_string_buffer(48)
        d.nv_host_cmx_printed(dest, dep, b, 48)
        return b.value.decode()

    def rms(wheel):
        # a held note's level, the mod wheel at `wheel` before it
        run(300)
        d.nv_host_midi(h, bytes([0xB0, 1, wheel]), 3)
        run(5)
        d.nv_host_midi(h, bytes([0x90, 60, 100]), 3)
        x = []
        for i in range(150):
            run(1)
            if i >= 40:
                x.append(L.copy())
        d.nv_host_midi(h, bytes([0x80, 60, 0]), 3)
        return float(np.sqrt(np.mean(np.concatenate(x) ** 2)))

    run(200)
    m = state(0)
    check("channel 1 read: a reset's", m is not None and m.cc1 == 16 and m.cc2 == 17
          and abs(m.depth[0][4] - 47.24) < 0.1 and m.depth[1][0] == 2.0,
          m and "mod -> LFO1 pitch %s, bend -> pitch %s" % (printed(4, m.depth[0][4]), printed(0, m.depth[1][0])))
    quiet0 = rms(127)
    raw = d.nv_host_cmx_raw(2, -0.5)
    d.nv_host_cmx_cell(h, 0, 0, 2, raw)
    run(20)
    m = state(0)
    check("the mod wheel given -50%% amplitude (byte %d): read back" % raw, m and abs(m.depth[0][2] + 0.5) < 0.01,
          m and printed(2, m.depth[0][2]))
    down, up = rms(0), rms(127)
    check("...a held note quieter with the wheel up", up < 0.7 * down and abs(quiet0 / down - 1) < 0.1,
          "rms %.4f down, %.4f up (before: %.4f up)" % (down, up, quiet0))
    d.nv_host_cmx_assign(h, -1, 4, 20)
    run(20)
    a, b = state(0), state(5)
    check("CC1 assigned 20 on every channel: read on channels 1 and 6", a and b and a.cc1 == 20 and b.cc1 == 20,
          a and b and "%d, %d" % (a.cc1, b.cc1))
    laws = all(d.nv_host_cmx_raw(c, d.nv_host_cmx_depth(c, v)) == v for c in range(11)
               for v in range(0x28 if c == 0 else 0, (0x58 if c == 0 else 127) + 1))
    check("the byte laws: every byte's depth back to the byte", laws)
    print("controller matrix: %d failed" % bad)
    sys.stdout.flush()
    shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    os._exit(1 if bad else 0)


if __name__ == "__main__":
    main()
