#!/usr/bin/env python3
"""The effects through the host library (host.h: nv_host_efx_tables,
nv_host_efx_state, nv_host_efx_send, nv_host_sysfx, nv_host_sysfx_send --
the app's Effects): python3 tests/live/efx_check.py

The host on the piano: the insertion effect's tables whole (Roland's types,
families, parameters); an overdrive (or distortion) chosen and channel 1 put
on it -- read back, and a held chord brighter for it (the spectrum's
centroid up); a parameter set, read back; off again, the chord as before.
The system effects: the reverb's level and the EQ's low gain set as a
sequencer's GS messages, read back. Exits 1 if any check fails.
"""
import ctypes
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))


class Efx(ctypes.Structure):
    _fields_ = [("has", ctypes.c_int), ("msb", ctypes.c_int), ("lsb", ctypes.c_int), ("p", ctypes.c_int * 21),
                ("send", ctypes.c_int * 3), ("ctl", ctypes.c_int * 4), ("nparts", ctypes.c_int),
                ("parts", ctypes.c_int * 32), ("status", ctypes.c_int), ("why", ctypes.c_char * 128)]


class Sysfx(ctypes.Structure):
    _fields_ = [("rev_macro", ctypes.c_int), ("rev_level", ctypes.c_int), ("rev_time", ctypes.c_int),
                ("rev_fb", ctypes.c_int), ("room", ctypes.c_char * 64), ("gs", ctypes.c_int),
                ("cho", ctypes.c_int * 7), ("dly", ctypes.c_int * 11), ("eq", ctypes.c_int * 4)]


def main():
    import nvlive_check as NC
    import native as N
    tmp = tempfile.mkdtemp(prefix="efx")
    nvx = NC.live_export(tmp, "hall")
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_efx_tables", [vp, cp, ci]),
                 ("nv_host_efx_state", [vp, vp]), ("nv_host_efx_send", [vp, ci, ci, ci]),
                 ("nv_host_sysfx", [vp, vp]), ("nv_host_sysfx_send", [vp, ci, ci, ci])):
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

    def state():
        s = Efx()
        d.nv_host_efx_state(h, ctypes.byref(s))
        return s

    def centroid():
        # a chord held a second, the spectrum's centroid of its last half
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

    run(200)
    b = ctypes.create_string_buffer(1 << 20)
    d.nv_host_efx_tables(h, b, 1 << 20)
    lines = b.value.decode("utf-8", "replace").split("\n")
    types = [ln.split("\t") for ln in lines if ln.startswith("T\t")]
    params = [ln for ln in lines if ln.startswith("P\t")]
    check("the tables: %d types, %d families, %d parameters" % (
        len(types), sum(ln.startswith("C\t") for ln in lines), len(params)), len(types) > 60 and len(params) > 300)
    od = next((t for t in types if "Overdrive" in t[4]), None) or next(t for t in types if "Distortion" in t[4])
    base = centroid()
    d.nv_host_efx_send(h, ord("t"), int(od[2]), int(od[3]))
    d.nv_host_efx_send(h, ord("c"), 0, 1)
    run(20)
    s = state()
    check("'%s' chosen, channel 1 on it: read back" % od[4],
          s.has and (s.msb, s.lsb) == (int(od[2]), int(od[3])) and 0 in list(s.parts)[:s.nparts],
          "type %d/%d, parts %s%s" % (s.msb, s.lsb, list(s.parts)[:s.nparts], (" -- " + s.why.decode()) if s.why else ""))
    on = centroid()
    check("...a held chord brighter for it (the centroid up)", on > 1.05 * base, "%.0f -> %.0f Hz" % (base, on))
    d.nv_host_efx_send(h, ord("p"), 1, 100)
    run(20)
    check("its parameter 1 set to 100: read back", state().p[1] == 100, "%d" % state().p[1])
    d.nv_host_efx_send(h, ord("c"), 0, 0)
    run(20)
    off = centroid()
    check("channel 1 off it: the chord as before", abs(off / base - 1) < 0.03, "%.0f Hz" % off)
    def sysfx():
        # (read between two blocks, as the app's window reads it: from
        # another thread while this one renders)
        import threading
        sx = Sysfx()
        t = threading.Thread(target=lambda: d.nv_host_sysfx(h, ctypes.byref(sx)))
        t.start()
        while t.is_alive():
            run(1)
        return sx
    lv0 = sysfx().rev_level
    d.nv_host_sysfx_send(h, 1, 0x33, 100)
    d.nv_host_sysfx_send(h, 2, 1, 0x48)
    run(20)
    sx = sysfx()
    check("the reverb's level %d -> 100, the EQ's low gain +8 dB: read back" % lv0,
          sx.rev_level == 100 and sx.eq[1] == 0x48, "level %d, low gain %d" % (sx.rev_level, sx.eq[1]))
    print("effects: %d failed" % bad)
    sys.stdout.flush()
    shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    os._exit(1 if bad else 0)


if __name__ == "__main__":
    main()
