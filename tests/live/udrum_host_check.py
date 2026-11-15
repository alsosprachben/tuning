#!/usr/bin/env python3
"""The user drum sets through the host library (host.h: nv_host_udrum_* --
the app's Drums tab): python3 tests/live/udrum_host_check.py

The host with its part on user set 1 (drum program 64, GS's 65): the sets
and key names (the export's DKEY); key 36 read, unset (silent struck); given
set 25's key 36 (an 808 kick), read back, and struck it sounds; given level
40, struck quieter; receive note on off, struck silent. Exits 1 if any check
fails.
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


def main():
    import nvlive_check as NC
    import native as N
    tmp = tempfile.mkdtemp(prefix="udrumhost")
    nvx = NC.live_export(tmp, "hall")
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_building", [vp]), ("nv_host_udrum_tables", [vp, cp, ci]),
                 ("nv_host_udrum_state", [vp, ci, vp]), ("nv_host_udrum_send", [vp, ci, ci, ci, ci])):
        getattr(d, f).argtypes = a
    av = [b"nvlive", nvx.encode(), b"--drums", b"--program=64", b"--cpu", b"--no-pipeline", b"--no-register",
          b"--reg-sync", b"--no-governor", b"--messenger-out=none"]
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

    def settle():
        quiet = 0
        for _ in range(8000):
            run(1)
            quiet = 0 if d.nv_host_building(h) else quiet + 1
            if quiet >= 100:
                return

    def state():
        # (read between two blocks: from another thread while this one renders)
        out = (ci * (128 * 16))()
        r = []
        t = threading.Thread(target=lambda: r.append(d.nv_host_udrum_state(h, 0, out)))
        t.start()
        while t.is_alive():
            run(1)
        return list(out) if r and r[0] == 0 else None

    def strike(key, rest=300):
        run(rest)                       # (rest: the last strike's room tail gone -- 2.56 s)
        d.nv_host_midi(h, bytes([0x99, key, 100]), 3)
        pk = 0.0
        for _ in range(100):
            run(1)
            pk = max(pk, float(np.abs(L).max()), float(np.abs(R).max()))
        d.nv_host_midi(h, bytes([0x89, key, 0]), 3)
        return pk

    settle()
    b = ctypes.create_string_buffer(1 << 20)
    d.nv_host_udrum_tables(h, b, 1 << 20)
    lines = b.value.decode("utf-8", "replace").split("\n")
    sets = [ln.split("\t") for ln in lines if ln.startswith("S\t")]
    keys = {(int(f[1]), int(f[2])): f[3] for f in (ln.split("\t") for ln in lines if ln.startswith("K\t"))}
    check("the tables: %d sets, %d key names" % (len(sets), len(keys)),
          len(sets) > 5 and (25, 36) in keys, "set 25 key 36: %s" % keys.get((25, 36)))
    u = state()
    p0 = strike(36, rest=1600)
    check("user set 1 key 36 read: unset, struck silent", u is not None and u[36 * 16 + 0x0C] < 0 and p0 < 1e-4,
          "peak %.2g" % p0)
    d.nv_host_udrum_send(h, 0, 36, 0x0B, 25)
    d.nv_host_udrum_send(h, 0, 36, 0x0C, 36)
    run(30)
    u = state()
    p1 = strike(36)
    check("given set 25's key 36: read back, struck it sounds",
          u[36 * 16 + 0x0B] == 25 and u[36 * 16 + 0x0C] == 36 and p1 > 1e-2, "peak %.3g" % p1)
    d.nv_host_udrum_send(h, 0, 36, 0x02, 40)
    run(30)
    p2 = strike(36)
    check("its level 40: read back, struck quieter", state()[36 * 16 + 0x02] == 40 and p2 < 0.7 * p1, "peak %.3g" % p2)
    d.nv_host_udrum_send(h, 0, 36, 0x08, 0)
    run(30)
    p3 = strike(36, rest=1600)
    check("receive note on off: struck silent", state()[36 * 16 + 0x08] == 0 and p3 < 1e-4, "peak %.2g" % p3)
    print("user drum sets: %d failed" % bad)
    sys.stdout.flush()
    shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    os._exit(1 if bad else 0)


if __name__ == "__main__":
    main()
