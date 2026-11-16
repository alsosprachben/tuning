#!/usr/bin/env python3
"""An organ's stops through the host library (host.h: nv_host_stop_names,
nv_host_stop_rows, nv_host_drawn, nv_host_toggle_stop -- the app's Stops):
python3 tests/live/stops_check.py

The host opened on the church organ (19): its ranks named, the panel's rows
covering every rank once; a stop not drawn drawn by nv_host_toggle_stop --
read back drawn, and a held note's level moved by it (a rank more sounding);
retired again -- read back so, and the level back where it was. Then a
second part layered on it (another church organ): its stops its own
(nv_host_part_set_drawn on it leaves the first's as they were), and with
the first muted, a stop drawn on the second moves what is heard.
Exits 1 if any check fails.
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


def main():
    import nvlive_check as NC
    import native as N
    tmp = tempfile.mkdtemp(prefix="stops")
    nvx = NC.live_export(tmp, "hall")
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_stop_names", [vp, ci, cp, ci]),
                 ("nv_host_stop_rows", [vp, ci, vp, ci]), ("nv_host_drawn", [vp, cp, ci]),
                 ("nv_host_toggle_stop", [vp, ci]), ("nv_host_part_drawn", [vp, ci, cp, ci]),
                 ("nv_host_part_set_drawn", [vp, ci, cp, ci]), ("nv_host_part_layer", [vp, ci]),
                 ("nv_host_parts", [vp, vp, ci]),
                 ("nv_host_part_set", [vp, ci, ci, ci, ci, ci, ctypes.c_double, ci])):
        getattr(d, f).argtypes = a
    av = [b"nvlive", nvx.encode(), b"--program=19", b"--cpu", b"--no-pipeline", b"--no-register",
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

    def drawn(n):
        b = ctypes.create_string_buffer(n)
        k = d.nv_host_drawn(h, b, n)
        return [b.raw[i] != 0 for i in range(min(k, n))]

    def level():
        # a chord held two seconds, its last half second's RMS, after a silence
        run(800)
        for k in (48, 55, 60, 64):
            d.nv_host_midi(h, bytes([0x90, k, 100]), 3)
        x = []
        for i in range(750):
            run(1)
            if i >= 560:
                x.append(L.copy())
        for k in (48, 55, 60, 64):
            d.nv_host_midi(h, bytes([0x80, k, 0]), 3)
        return float(np.sqrt(np.mean(np.concatenate(x) ** 2)))

    run(200)
    nb = ctypes.create_string_buffer(16384)
    n = d.nv_host_stop_names(h, 19, nb, 16384)
    names = nb.value.decode().split("\n") if n else []
    k = d.nv_host_stop_rows(h, 19, None, 0)
    rows = (ci * k)()
    d.nv_host_stop_rows(h, 19, rows, k)
    ranks = [x for x in rows if x >= 0]
    check("the church organ's ranks named (%d), the rows cover each once" % n,
          n > 4 and len(names) == n and sorted(ranks) == sorted(set(ranks)) and set(ranks) <= set(range(n)),
          "%d in the rows" % len(set(ranks)))
    dr = drawn(n)
    off = [r for r in ranks if r < len(dr) and not dr[r]]
    check("some drawn at the start, some not", any(dr) and bool(off), "%d drawn" % sum(dr))
    # (a sounding rank -- one with a footage, "principal 8" -- not the
    # tremulant, which moves the sound without adding to it)
    sounding = [x for x in off if any(ch.isdigit() for ch in names[x]) and "trem" not in names[x].lower()]
    r = (sounding or off)[len(sounding or off) // 2]
    base = level()
    d.nv_host_toggle_stop(h, r)
    run(4)
    check("'%s' drawn: read back drawn" % names[r], drawn(n)[r])
    more = level()
    check("...a held chord's level moved by it", abs(20 * np.log10(more / base)) > 0.3,
          "%+.2f dB" % (20 * np.log10(more / base)))
    d.nv_host_toggle_stop(h, r)
    run(4)
    check("retired: read back not drawn", not drawn(n)[r])
    back = level()
    check("...and the level back where it was", abs(20 * np.log10(back / base)) < 0.1,
          "%+.3f dB" % (20 * np.log10(back / base)))

    # A SECOND PART's ORGAN: its own stops
    def pdrawn(row):
        b = ctypes.create_string_buffer(n)
        k = d.nv_host_part_drawn(h, row, b, n)
        return [b.raw[i] != 0 for i in range(min(k, n))]

    d.nv_host_part_layer(h, 0)
    for _ in range(3000):                       # (built on the builder: added between two blocks)
        run(10)
        if d.nv_host_parts(h, None, 0) >= 2 and len(pdrawn(1)) == n:
            break
    check("a second church organ layered on the first", d.nv_host_parts(h, None, 0) >= 2 and len(pdrawn(1)) == n)
    first = pdrawn(0)
    want = [0] * n
    for x in (sounding or off)[:2]:
        want[x] = 1
    d.nv_host_part_set_drawn(h, 1, bytes(want), n)
    run(4)
    check("the second's stops set: read back so", pdrawn(1) == [bool(w) for w in want],
          "%d drawn" % sum(pdrawn(1)))
    check("...the first's as they were", pdrawn(0) == first)
    d.nv_host_part_set(h, 0, -1, 0, 127, 0, 0.0, 1)    # (the first muted: the second heard alone)
    one = [1 if x else 0 for x in first]       # (the first's registration, then that and one more, as above)
    d.nv_host_part_set_drawn(h, 1, bytes(one), n)
    run(4)
    alone = level()
    want2 = list(one)
    want2[r] = 1
    d.nv_host_part_set_drawn(h, 1, bytes(want2), n)
    run(4)
    more2 = level()
    check("a stop drawn on the second moves what is heard", abs(20 * np.log10(more2 / alone)) > 0.3,
          "%+.2f dB" % (20 * np.log10(more2 / alone)))
    check("...and the first's still as they were", pdrawn(0) == first)
    print("stops: %d failed" % bad)
    sys.stdout.flush()
    shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    os._exit(1 if bad else 0)


if __name__ == "__main__":
    main()
