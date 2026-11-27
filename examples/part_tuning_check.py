"""A PART'S TUNING, LIVE (live.tuner_for; the host's tuning_of, set_part_tuner,
set_natural): through the host library in step (ctypes, no device), on a
live export (the rig's tuner its own, gm2) --

- the church organ (19) plays its natural tuning, the hybrid mean at the
  rig's A4: the TUNING card's THIS PART says so (part: plays, natural), and
  C7 sounds where that table puts it against the rig's -- A4 the same;
- the part set to the rig's (part_tuner_set "rig"): C7 back on the rig's;
  set to `even`: it plays even; a program change: its own choice gone, the
  instrument's again;
- the fortepiano (0.40) plays the pleyel, its C7 the table's against the rig's;
- natural tunings off (natural_set): the organ on the rig's tuner;
- a preset saved and loaded: the part's own tuning and the switch kept.

A pitch is the strongest peak within 30 cents of the note's table pitch,
over 1 s of the held note (a 2^20 FFT, parabolic peak); compared as the
interval between two settings, against the interval their tables give
(within half a cent; a cent below 200 Hz, where the peak reads coarser).

    python3 examples/part_tuning_check.py LIVE.nvx
"""
import ctypes
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv):
    nvx = argv[1]
    import native as N
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_rate", [vp]), ("nv_host_building", [vp]),
                 ("nv_host_render", [vp, vp, vp, ci]), ("nv_host_midi", [vp, ctypes.c_char_p, ci])):
        getattr(d, f).argtypes = a
    d.nv_ui_watch_new.restype = vp
    d.nv_ui_call.restype = ctypes.c_void_p
    d.nv_ui_call.argtypes = [vp, vp, cp]
    d.nv_ui_free.argtypes = [vp]
    av = [b"nvlive", nvx.encode(), b"--program=19", b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-drums", b"--reg-sync", b"--no-governor"]
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the host refused"
    d.nv_host_start(h)
    w = d.nv_ui_watch_new()
    blk, sr = d.nv_host_block(h), d.nv_host_rate(h)
    L = np.zeros(blk, np.float32)
    R = np.zeros(blk, np.float32)

    def call(o):
        p = d.nv_ui_call(h, w, json.dumps(o).encode())
        r = json.loads(ctypes.string_at(p).decode())
        d.nv_ui_free(p)
        return r

    def render(sec):
        out = []
        for _ in range(max(1, int(sec * sr) // blk)):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
            out.append(L + R)
        return np.concatenate(out)

    def midi(*b):
        d.nv_host_midi(h, bytes(b), len(b))

    def settle(want=None):
        """until nothing is building (and the part plays WANT, where given): its
        THIS PART then"""
        t0 = time.time()
        p = {}
        while time.time() - t0 < 90:
            render(0.05)
            p = call({"call": "tuning", "row": 0})["tuning"].get("part", {})
            # (the host's whole count: a natural tunings switch builds no part's ask)
            if not d.nv_host_building(h) and (want is None or p.get("plays") == want) and time.time() - t0 > 0.5:
                render(0.2)     # (the patch built is handed to the audio a block or two after)
                return p
        return p

    def pitch(key, near):
        """the held key's pitch (Hz) near NEAR, and its level (dB re full scale)"""
        midi(0x90, key, 100)
        render(0.4)
        x = render(1.0)
        midi(0x80, key, 0)
        render(1.5)
        lv = 10 * math.log10(max(1e-30, float(np.mean(x.astype(np.float64) ** 2))))
        n = 1 << 20
        X = np.abs(np.fft.rfft(x * np.hanning(len(x)), n))
        f = np.fft.rfftfreq(n, 1.0 / sr)
        m = (f > near * 2 ** (-30 / 1200)) & (f < near * 2 ** (30 / 1200))
        i = int(np.argmax(np.where(m, X, 0)))
        a, b, c = np.log(X[i - 1:i + 2] + 1e-30)
        return (f[i] + 0.5 * (a - c) / (a - 2 * b + c) * (f[1] - f[0])), lv

    def cents(a, b):
        return 1200.0 * math.log2(a / b)

    RIG = N.tuning_table("gm2")
    bad = 0
    notes = 0

    def table_of(plays):
        return RIG if not plays else N.tuning_table("%s~%r" % (plays, RIG[69]))

    def compare(name, key, p_a, p_b, tol):
        """the key under setting A against B: their interval as measured and as
        their tables give it"""
        nonlocal bad, notes
        ta, tb = table_of(p_a), table_of(p_b)
        fa, la = pitch(key, ta[key]) if key not in meas.get(p_a or "rig", {}) else meas[p_a or "rig"][key]
        meas.setdefault(p_a or "rig", {})[key] = (fa, la)
        fb, lb = meas[p_b or "rig"][key]
        heard, want = cents(fa, fb), cents(ta[key], tb[key])
        tol_ = tol * (2.0 if ta[key] < 200.0 else 1.0)    # (a low note: its peak a coarser read)
        ok = abs(heard - want) < tol_ and la > -80 and lb > -80
        notes += 2
        print("  %-28s key %3d: %+.2f c heard, %+.2f c in the tables  %s" % (name, key, heard, want,
                                                                          "ok" if ok else "WRONG"))
        bad += not ok

    render(1.0)
    # THE ORGAN: its natural tuning
    p = settle("hybridmean")
    ok = p.get("plays") == "hybridmean" and p.get("natural") == "hybridmean" and p.get("own") == ""
    print("church organ: plays %r, its voice's %r, its own %r  %s" % (p.get("plays"), p.get("natural"),
                                                                      p.get("own"), "ok" if ok else "WRONG"))
    bad += not ok
    meas = {}
    for key in (69, 96, 36):
        meas.setdefault("hybridmean", {})[key] = pitch(key, table_of("hybridmean")[key])
    call({"call": "part_tuner_set", "row": 0, "name": "rig"})
    p = settle("")
    ok = p.get("own") == "rig" and p.get("plays") == ""
    print("set to the rig's: plays %r, its own %r  %s" % (p.get("plays"), p.get("own"), "ok" if ok else "WRONG"))
    bad += not ok
    for key in (69, 96, 36):
        meas.setdefault("rig", {})[key] = pitch(key, RIG[key])
    for key in (69, 96, 36):
        compare("organ natural vs the rig's", key, "hybridmean", "", 0.5)
    # ITS OWN CHOICE: even
    call({"call": "part_tuner_set", "row": 0, "name": "even"})
    p = settle("even")
    ok = p.get("own") == "even" and p.get("plays") == "even"
    print("set to even: plays %r  %s" % (p.get("plays"), "ok" if ok else "WRONG"))
    bad += not ok
    compare("organ even vs the rig's", 96, "even", "", 0.5)
    # A PROGRAM CHANGE: its own choice gone
    midi(0xC0, 19)
    render(0.2)
    p = settle("hybridmean")
    ok = p.get("own") == "" and p.get("plays") == "hybridmean"
    print("program change: its own %r, plays %r  %s" % (p.get("own"), p.get("plays"), "ok" if ok else "WRONG"))
    bad += not ok
    # NATURAL TUNINGS OFF
    call({"call": "natural_set", "on": 0})
    p = settle("")
    t = call({"call": "tuning", "row": 0})["tuning"]
    ok = p.get("plays") == "" and t.get("natural") is False
    fo, _ = pitch(96, RIG[96])
    ok = ok and abs(cents(fo, meas["rig"][96][0])) < 0.5
    print("natural tunings off: plays %r, C7 %+.2f c from the rig's  %s" % (p.get("plays"), cents(fo, meas["rig"][96][0]),
                                                                          "ok" if ok else "WRONG"))
    bad += not ok
    notes += 1
    call({"call": "natural_set", "on": 1})
    settle("hybridmean")
    # THE FORTEPIANO (0.40): the pleyel
    midi(0xB0, 0, 40)
    midi(0xB0, 32, 0)
    midi(0xC0, 0)
    render(0.2)
    p = settle("pleyel")
    ok = p.get("plays") == "pleyel" and p.get("natural") == "pleyel"
    print("fortepiano: plays %r, its voice's %r  %s" % (p.get("plays"), p.get("natural"), "ok" if ok else "WRONG"))
    bad += not ok
    meas = {"pleyel": {k: pitch(k, table_of("pleyel")[k]) for k in (69, 96)}}
    call({"call": "part_tuner_set", "row": 0, "name": "rig"})
    settle("")
    meas["rig"] = {k: pitch(k, RIG[k]) for k in (69, 96)}
    for key in (69, 96):
        compare("fortepiano natural vs rig's", key, "pleyel", "", 1.5)
    # A PRESET keeps a part's own tuning and natural tunings off (saved by
    # name: own_tuner, natural_tunings), and brings them back
    d.nv_host_preset_save.argtypes = d.nv_host_preset_load.argtypes = [vp, cp, cp, ci]
    msg = ctypes.create_string_buffer(256)
    import tempfile
    sdir = tempfile.mkdtemp(prefix="part_tuning_")       # (a session path of the check's own: its presets.json there)
    d.nv_host_set_session_path.argtypes = [vp, cp]
    d.nv_host_set_session_path(h, os.path.join(sdir, "session.json").encode())
    call({"call": "part_tuner_set", "row": 0, "name": "hybridharm"})
    settle("hybridharm")
    call({"call": "natural_set", "on": 0})
    settle()
    if d.nv_host_preset_save(h, b"part tuning check", msg, 256):
        print("preset not saved: %s" % msg.value.decode())
    call({"call": "part_tuner_set", "row": 0, "name": ""})
    call({"call": "natural_set", "on": 1})
    settle("pleyel")
    d.nv_host_preset_load(h, b"part tuning check", msg, 256)
    render(0.5)
    p = settle("hybridharm")
    t = call({"call": "tuning", "row": 0})["tuning"]
    ok = p.get("own") == "hybridharm" and p.get("plays") == "hybridharm" and t.get("natural") is False
    print("a preset: its own %r, plays %r, natural tunings %s  %s" % (p.get("own"), p.get("plays"), t.get("natural"),
                                                                       "ok" if ok else "WRONG"))
    bad += not ok
    print("%d notes heard, %d wrong" % (notes, bad))
    sys.stdout.flush()
    os._exit(1 if bad else 0)


if __name__ == '__main__':
    main(sys.argv)
