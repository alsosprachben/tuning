#!/usr/bin/env python3
"""On-screen controls, routes, scenes and the GS Reset through the host
library (host.h: nv_host_control_*, nv_host_route_*, nv_host_learn_key,
nv_host_scene_*, nv_host_gs_reset -- the app's Controls tab):
python3 tests/live/controls_routes_check.py

  controls  the kinds listed; a sustain control added (every channel), sent
            127: the pedal down (its switch read on); 0: up; a hotkey kept
  routes    key 36 routed to the sustain pedal (held, replacing it): key 36
            down puts the pedal down; the route removed, key 36 does not;
            learning a key: the next note-on's channel and note
  scenes    channel 1's reverb send 100 saved as a scene, set 0, recalled: 100
  reset     a GS Reset: the reverb send back to its power-on 40

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


class Ctl(ctypes.Structure):
    _fields_ = [("key", ctypes.c_int), ("channel", ctypes.c_int), ("value", ctypes.c_int),
                ("hotkey", ctypes.c_int), ("on", ctypes.c_int)]


def main():
    import nvlive_check as NC
    import native as N
    tmp = tempfile.mkdtemp(prefix="ctlroutes")
    nvx = NC.live_export(tmp, "hall")
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_set_session_path", [vp, cp]),
                 ("nv_host_control_kinds", [cp, ci]), ("nv_host_controls", [vp, vp, ci]),
                 ("nv_host_control_add", [vp, ci, ci]), ("nv_host_control_set", [vp, ci, ci]),
                 ("nv_host_control_hotkey", [vp, ci, ci]), ("nv_host_routes", [vp, vp, ci]),
                 ("nv_host_route_text", [vp, cp, ci]), ("nv_host_route_add", [vp, vp]),
                 ("nv_host_route_remove", [vp, ci]), ("nv_host_learn_key", [vp, ci]),
                 ("nv_host_learnt_key", [vp, vp, vp]), ("nv_host_scene_save", [vp, cp, cp, ci]),
                 ("nv_host_scene_recall", [vp, cp, cp, ci]), ("nv_host_chan_cc", [vp, ci, ci]),
                 ("nv_host_chan_cc_send", [vp, ci, ci, ci]), ("nv_host_gs_reset", [vp])):
        getattr(d, f).argtypes = a
    av = [b"nvlive", nvx.encode(), b"--program=0", b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-drums", b"--reg-sync", b"--no-governor", b"--messenger-out=none"]
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the host refused"
    d.nv_host_start(h)
    d.nv_host_set_session_path(h, os.path.join(tmp, "session.json").encode())
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
        # (between two blocks, as the app calls it: from another thread while this one renders)
        import threading
        out = []
        t = threading.Thread(target=lambda: out.append(fn()))
        t.start()
        while t.is_alive():
            run(1)
        return out[0]

    def ctls():
        n = d.nv_host_controls(h, None, 0)
        a = (Ctl * max(n, 1))()
        d.nv_host_controls(h, a, n)
        return list(a)[:n]

    run(200)
    b = ctypes.create_string_buffer(8192)
    d.nv_host_control_kinds(b, 8192)
    kinds = [ln.split("\t") for ln in b.value.decode().split("\n") if ln]
    check("the controls one may add: %d" % len(kinds), len(kinds) > 20 and any(k[0] == "64" and k[2] == "switch" for k in kinds))
    i = d.nv_host_control_add(h, 64, -1)
    d.nv_host_control_set(h, i, 127)
    run(10)
    down = ctls()[i].on
    d.nv_host_control_set(h, i, 0)
    run(10)
    up = ctls()[i].on
    d.nv_host_control_hotkey(h, i, ord("z"))
    c = ctls()[i]
    check("a sustain control: 127 the pedal down, 0 up; hotkey 'z' kept", down == 1 and up == 0 and c.hotkey == ord("z"),
          "on %d then %d, value %d" % (down, up, c.value))

    r = (ci * 7)(3, 36, 64, 0, -1, 0, 1)
    d.nv_host_route_add(h, r)
    run(10)
    t = ctypes.create_string_buffer(128)
    d.nv_host_route_text(r, t, 128)
    n = d.nv_host_routes(h, None, 0)
    d.nv_host_midi(h, bytes([0x90, 36, 100]), 3)
    run(10)
    held = ctls()[i].on
    d.nv_host_midi(h, bytes([0x80, 36, 0]), 3)
    run(10)
    rel = ctls()[i].on
    check("route %s: key 36 holds the pedal" % t.value.decode(), n == 1 and held == 1 and rel == 0,
          "%d route(s), down %d, released %d" % (n, held, rel))
    d.nv_host_route_remove(h, 0)
    run(10)
    d.nv_host_midi(h, bytes([0x90, 36, 100]), 3)
    run(10)
    after = ctls()[i].on
    d.nv_host_midi(h, bytes([0x80, 36, 0]), 3)
    run(10)
    check("the route removed: key 36 plays, the pedal stays up", d.nv_host_routes(h, None, 0) == 0 and after == 0)
    d.nv_host_learn_key(h, 1)
    run(5)
    d.nv_host_midi(h, bytes([0x92, 50, 90]), 3)
    run(5)
    lc, ln = ci(-1), ci(-1)
    got = d.nv_host_learnt_key(h, ctypes.byref(lc), ctypes.byref(ln))
    d.nv_host_midi(h, bytes([0x82, 50, 0]), 3)
    check("a key learnt: the next note-on's channel and note", got == 1 and (lc.value, ln.value) == (2, 50),
          "channel %d, note %d" % (lc.value + 1, ln.value))

    msg = ctypes.create_string_buffer(256)
    d.nv_host_chan_cc_send(h, 0, 91, 100)
    run(10)
    sv = aside(lambda: d.nv_host_scene_save(h, b"check", msg, 256))
    sm = msg.value.decode()
    d.nv_host_chan_cc_send(h, 0, 91, 0)
    run(10)
    mid = d.nv_host_chan_cc(h, 0, 91)
    aside(lambda: d.nv_host_scene_recall(h, b"check", msg, 256))
    run(20)
    check("a scene (%s): reverb send 100 saved, set 0, recalled" % sm, sv == 0 and mid == 0 and d.nv_host_chan_cc(h, 0, 91) == 100,
          "%d -> %d -> %d" % (100, mid, d.nv_host_chan_cc(h, 0, 91)))
    d.nv_host_gs_reset(h)
    run(40)
    check("a GS Reset: the reverb send back to 40", d.nv_host_chan_cc(h, 0, 91) == 40, "%d" % d.nv_host_chan_cc(h, 0, 91))
    print("controls and routes: %d failed" % bad)
    sys.stdout.flush()
    shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    os._exit(1 if bad else 0)


if __name__ == "__main__":
    main()
