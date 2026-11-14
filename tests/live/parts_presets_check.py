#!/usr/bin/env python3
"""Parts and presets through the host library (host.h: nv_host_parts,
nv_host_part_*, nv_host_preset_*): python3 tests/live/parts_presets_check.py

The app's parts and presets are the library's (native/hostsession.cpp: the
session, scenes and presets moved there from nvlive.cpp, the same
presets.json nvlive and live.py keep). Two hosts, each in a process of its own:

  A  the piano layered and put on channel 1; the layer set to channel 2, keys 60-96, an octave
     up, -6 dB, and given the strings (48), built; its parts read; the
     setup saved as a preset
  B  a fresh host loads that preset: the same parts, field by field; and
     it sounds so -- a note on channel 2 in the layer's keys sounds, one
     under them on channel 2 does not, a note on channel 1 sounds (the piano)

Exits 1 if any check fails.
"""
import ctypes
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))

FIELDS = ("program", "variation", "drums", "channel", "lo", "hi", "transpose", "level_db", "muted")


class Part(ctypes.Structure):
    _fields_ = [("row", ctypes.c_int), ("program", ctypes.c_int), ("variation", ctypes.c_int),
                ("drums", ctypes.c_int), ("channel", ctypes.c_int), ("lo", ctypes.c_int), ("hi", ctypes.c_int),
                ("transpose", ctypes.c_int), ("level_db", ctypes.c_double), ("muted", ctypes.c_int),
                ("solo", ctypes.c_int), ("touch_fixed", ctypes.c_int), ("name", ctypes.c_char * 64)]


class Patch(ctypes.Structure):
    _fields_ = [("program", ctypes.c_int), ("variation", ctypes.c_int), ("drums", ctypes.c_int),
                ("native", ctypes.c_int), ("pick", ctypes.c_int), ("name", ctypes.c_char * 64)]


def child(nvx, case, sess, outp):
    import native as N
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_building", [vp]),
                 ("nv_host_render", [vp, vp, vp, ci]), ("nv_host_midi", [vp, cp, ci]),
                 ("nv_host_patches", [vp, vp, ci]), ("nv_host_parts", [vp, vp, ci]),
                 ("nv_host_part_set", [vp, ci, ci, ci, ci, ci, ctypes.c_double, ci]),
                 ("nv_host_part_pick", [vp, ci, ci]), ("nv_host_part_layer", [vp, ci]),
                 ("nv_host_set_session_path", [vp, cp]),
                 ("nv_host_preset_save", [vp, cp, cp, ci]), ("nv_host_preset_load", [vp, cp, cp, ci])):
        getattr(d, f).argtypes = a
    av = [b"nvlive", nvx.encode(), b"--program=0", b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-drums", b"--reg-sync", b"--no-governor", b"--messenger-out=none"]
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the host refused"
    d.nv_host_start(h)
    d.nv_host_set_session_path(h, sess.encode())
    blk = d.nv_host_block(h)
    L = np.zeros(blk, np.float32)
    R = np.zeros(blk, np.float32)
    msg = ctypes.create_string_buffer(256)

    def settle(most=8000, until=None):
        # rendered until the builder has been idle 100 blocks running (a
        # swap lands a block or two after it says it is done) -- and, given
        # `until`, until that holds of the parts
        quiet = 0
        for i in range(most):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
            quiet = 0 if d.nv_host_building(h) else quiet + 1
            if quiet >= 100 and (until is None or until()):
                return i
        return -1

    def parts():
        n = d.nv_host_parts(h, None, 0)
        buf = (Part * n)()
        d.nv_host_parts(h, buf, n)
        return [dict({f: getattr(p, f) for f in FIELDS}, name=p.name.decode()) for p in buf]

    out = {}
    if case == "A":
        settle()
        out["before"] = parts()
        assert d.nv_host_part_layer(h, 0) == 0, "no layer"
        settle()
        d.nv_host_part_set(h, 0, 0, 0, 127, 0, 0.0, 0)      # (the piano on channel 1 alone)
        d.nv_host_part_set(h, 1, 1, 60, 96, 12, -6.0, 0)
        n = d.nv_host_patches(h, None, 0)
        pt = (Patch * n)()
        d.nv_host_patches(h, pt, n)
        pk = [x.pick for x in pt if x.program == 48 and not x.drums and x.variation == 0 and x.native]
        d.nv_host_part_pick(h, 1, pk[0])
        out["settled"] = settle(until=lambda: len(parts()) > 1 and parts()[1]["program"] == 48)
        out["parts"] = parts()
        out["saved"] = d.nv_host_preset_save(h, b"check", msg, 256)
        out["msg"] = msg.value.decode()
    else:
        settle()
        out["loaded"] = d.nv_host_preset_load(h, b"check", msg, 256)
        out["msg"] = msg.value.decode()
        out["settled"] = settle()
        out["parts"] = parts()

        def note(ch, key):
            # a note held a quarter second, the peak of what it played
            # (after a silence for the last one's release)
            for _ in range(200):
                d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
            d.nv_host_midi(h, bytes([0x90 | ch, key, 100]), 3)
            pk = 0.0
            for i in range(94):
                d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
                pk = max(pk, float(np.abs(L).max()), float(np.abs(R).max()))
            d.nv_host_midi(h, bytes([0x80 | ch, key, 0]), 3)
            return pk
        # (the note outside the layer's keys first: nothing ringing yet)
        out["peaks"] = {"ch2 key 48": note(1, 48), "ch2 key 72": note(1, 72), "ch1 key 60": note(0, 60)}
    json.dump(out, open(outp, "w"))
    sys.stdout.flush()
    os._exit(0)


def main(argv):
    if argv and argv[0] == "--child":
        return child(*argv[1:5])
    import nvlive_check as NC
    tmp = tempfile.mkdtemp(prefix="partspresets")
    nvx = NC.live_export(tmp, "hall")
    sess = os.path.join(tmp, "session.json")
    got = {}
    for case in ("A", "B"):
        outp = os.path.join(tmp, case + ".json")
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", nvx, case, sess, outp],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(outp):
            print("  host %s failed\n%s" % (case, r.stderr[-1500:]))
            return 1
        got[case] = json.load(open(outp))
    bad = 0

    def check(what, ok, detail=""):
        nonlocal bad
        bad += not ok
        print("  %-62s %s  %s" % (what, "ok" if ok else "FAILED", detail), flush=True)

    A, B = got["A"], got["B"]
    lay = A["parts"][1] if len(A["parts"]) > 1 else {}
    check("A: the piano layered, the layer set and given the strings (built)",
          len(A["parts"]) == len(A["before"]) + 1 and lay.get("program") == 48 and lay.get("channel") == 1
          and (lay.get("lo"), lay.get("hi"), lay.get("transpose"), lay.get("level_db")) == (60, 96, 12, -6.0)
          and A["settled"] >= 0, "%s (built in %s blocks)" % (lay, A["settled"]))
    check("A: saved as a preset (%s)" % A["msg"], A["saved"] == 0)
    pre = json.load(open(os.path.join(tmp, "presets.json"))).get("check", {})
    pp = pre.get("parts", [])
    check("presets.json: the preset's parts as live.py writes them (%d)" % len(pp),
          len(pp) == len(A["parts"]) and any(p.get("program") == 48 and p.get("transpose") == 12 for p in pp),
          "%s" % [{k: p.get(k) for k in ("program", "channel", "lo", "hi", "transpose")} for p in pp])
    check("B: loaded (%s), built" % B["msg"], B["loaded"] == 0 and B["settled"] >= 0, "in %s blocks" % B["settled"])
    same = [{f: p[f] for f in FIELDS} for p in A["parts"]] == [{f: p[f] for f in FIELDS} for p in B["parts"]]
    check("B: the same parts as A, field by field", same, "" if same else "%s / %s" % (A["parts"], B["parts"]))
    pk = B["peaks"]
    check("B sounds so: ch2 in the layer's keys plays, under them silent, ch1 plays",
          pk["ch2 key 72"] > 1e-3 and pk["ch1 key 60"] > 1e-3 and pk["ch2 key 48"] < 1e-5,
          "  ".join("%s %.2g" % kv for kv in pk.items()))
    print("parts and presets: %d failed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
