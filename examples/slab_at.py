#!/usr/bin/env python3
"""Where does nvlive's slab first part from live's? For a file nvlive_check
finds differing: the native host (host.h, through ctypes, as host_check plays
it) and live.Live (as nvlive_check sets it up) fed the same file block by
block, and at each block asked for, every slab column the native part can hand
out (native.Slab.col) compared with live's -- the columns that differ, how
many slots, the first few slots' values on both sides.

    python3 examples/slab_at.py FILE.mid SECONDS --program=P --at=B[,B,...] [--room=NAME]

(The native host in a child process of its own, the slabs saved at those
blocks; live in this one after it: one engine's memory at a time.)
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


def names():
    import native as N
    return (list(N.LIVE_F8) + list(N.LIVE_F4) + list(N.LIVE_F4N) + ["non", "noff"] + list(N.LIVE_I4)
            + list(N.SLAB_BOOK) + ["dk", "slot_ch", "busy", "aLp", "aRp", "dg", "tr_dep", "tr_aL", "tr_aR",
                                   "tr_st", "tr_on", "hs_dep", "ls_on", "ls_horn", "ls_am", "ls_sharp", "ls_norm",
                                   "ls_ph", "ls_aL", "ls_aR"])


def child(nvx, mid, prog, at, outdir, bank=None, room_at=None):
    """the native host: its slab at each block in `at`, to outdir/B.npz"""
    import native as N
    from host_check import encode
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    d.nv_host_set_room.argtypes = [vp, cp]
    d.nv_host_building.argtypes = [vp]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_rate", [vp]), ("nv_host_part", [vp]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_render", [vp, vp, vp, ci])):
        getattr(d, f).argtypes = a
    d.nv_host_part.restype = vp
    d.nv_midi_read.restype = vp
    d.nv_midi_read.argtypes = [cp, ctypes.c_longlong, ctypes.POINTER(ci)]
    d.nv_midi_n_events.argtypes = [vp]
    d.nv_midi_event.argtypes = [vp, ci, ctypes.POINTER(ci), ctypes.POINTER(ctypes.c_double)]
    d.nv_midi_sysex.argtypes = [vp, ci, cp, ci]
    raw = open(mid, "rb").read()
    err = ci(0)
    m = d.nv_midi_read(raw, len(raw), ctypes.byref(err))
    av = [b"nvlive", nvx.encode(), b"--program=%d" % prog, b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-drums", b"--reg-sync", b"--no-governor"] + ([b"--bank=%d" % int(bank)] if bank else [])
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the host refused"
    d.nv_host_start(h)
    blk, sr = d.nv_host_block(h), d.nv_host_rate(h)
    S = N.Slab.__new__(N.Slab)
    S.d, S.cap, S.p = d, 65536, d.nv_part_slab(d.nv_host_part(h))
    L = np.zeros(blk, np.float32)
    R = np.zeros(blk, np.float32)
    ne, e = d.nv_midi_n_events(m), 0
    iv = (ci * 4)()
    t = ctypes.c_double()
    xb = ctypes.create_string_buffer(65536)
    want = sorted(at)
    import time
    for b in range(want[-1] + 1):
        if room_at and b in room_at:            # (the switch asked, its builder waited for: in step)
            d.nv_host_set_room(h, room_at[b].encode())
            time.sleep(25.0)                    # (built by then: the next block takes the swap)
        while e < ne:
            d.nv_midi_event(m, e, iv, ctypes.byref(t))
            if int(t.value * sr) // blk > b:
                break
            sx = b""
            if iv[0] == 6:
                xn = d.nv_midi_sysex(m, iv[2], xb, 65536)     # (filled first: then read)
                sx = xb.raw[:xn]
            by = encode(list(iv), sx)
            if os.environ.get("SLAB_PROBE") and e < 8:
                print("event %d at block %d: iv %s bytes %s" % (e, b, list(iv), by.hex(" ")))
            d.nv_host_midi(h, by, len(by))
            e += 1
        d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
        if b in want:
            st = (ci * 64)()
            why = cp()
            d.nv_part_efx_state.argtypes = [vp, ctypes.POINTER(ci), ci, ctypes.POINTER(cp)]
            d.nv_part_efx_state.restype = ci
            n_ = d.nv_part_efx_state(d.nv_host_part(h), st, 64, ctypes.byref(why))
            print("native at block %d: the effect's state %d %s, why %r" % (b, n_, list(st)[:max(0, min(n_, 64))],
                                                                             why.value))
            cols = {}
            for c in names():
                try:
                    cols[c] = S.col(c)
                except Exception:
                    pass
            np.savez(os.path.join(outdir, "%d.npz" % b), **cols)
    sys.stdout.flush()
    os._exit(0)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    if "child" in opt:
        ra = {}
        for it in (opt.get("room-at") or "").split(","):
            if ":" in it:
                ra[int(float(it.split(":")[0]) * 48000) // 128] = it.split(":", 1)[1]
        child(args[0], args[1], int(opt["program"]), [int(x) for x in opt["at"].split(",")], opt["child"],
              opt.get("bank"), ra)
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import mido
    import bitident as BI
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L
    import native as N
    from nvlive_check import live_export
    from livepart_check import instant_scan
    prog = int(opt.get("program", 0))
    secs = float(args[1])
    at = sorted(int(x) for x in opt["at"].split(","))
    room = opt.get("room") or "hall"
    tmp = tempfile.mkdtemp(prefix="slabat")
    try:
        mid = os.path.join(tmp, "in.mid")
        BI.excerpt(args[0], secs).save(mid)
        nvx = live_export(tmp, room)
        N.build_nvlive()
        r = subprocess.run([sys.executable, os.path.abspath(__file__), nvx, mid, "--child=" + tmp,
                            "--program=%d" % prog, "--at=" + ",".join(map(str, at))]
                           + (["--bank=" + opt["bank"]] if opt.get("bank") else [])
                           + (["--room-at=" + opt["room-at"]] if opt.get("room-at") else []),
                           capture_output=True, text=True)
        if r.returncode:
            print("the native child failed: %s" % r.stderr.strip()[-400:])
            return 1
        print(r.stdout.strip())
        vparts = ([L.Part(L.patch_for(prog, False, "hybrid", variation=int(opt["bank"])))]
                  if opt.get("bank") else None)
        lv = L.Live(program=prog, rate=48000, frames=128, capacity=65536, verbose=False, threads=1, gpu=False,
                    tuner="hybrid", drums=False, eastern=None, parts=vparts)
        lv.enable_room(room)
        lv.parts[0].patch.warm()
        instant_scan(lv, lv.parts[0].patch)
        import ampsync
        ampsync.sync(lv)
        lv.slab.shed = lambda n, frac: 0
        import patchsync
        patchsync.sync(lv)                      # (a reset's program 0, in step: nvlive_check's)
        m = N.Midi(mid)
        evs = m.events()
        M = mido.Message
        e = 0
        room_at = {}
        for it in (opt.get("room-at") or "").split(","):
            if ":" in it:
                room_at[int(float(it.split(":")[0]) * 48000) // 128] = it.split(":", 1)[1]
        for b in range(at[-1] + 1):
            if b in room_at:                    # (nvlive_check's switch: live's builder in step)
                lv.set_room(room_at[b])
                lv._room_switch()
                for _part, _p in patchsync.build(lv):
                    instant_scan(lv, _p)
            while e < len(evs) and int(evs[e][0] * 48000) // 128 <= b:
                t, ty, ch, a, v = evs[e]
                if ty == 0:
                    lv.on_midi(M("note_on", channel=ch, note=a, velocity=v))
                elif ty == 1:
                    lv.on_midi(M("note_off", channel=ch, note=a, velocity=0))
                elif ty == 3:
                    lv.on_midi(M("aftertouch", channel=ch, value=a))
                elif ty == 4:
                    lv.on_midi(M("pitchwheel", channel=ch, pitch=a))
                elif ty == 6:
                    lv.on_midi(M("sysex", data=list(m.sysex(a))))
                elif ty != 5:
                    lv.on_midi(M("control_change", channel=ch, control=a, value=v))
                e += 1
            lv.slab.tap_cap = lv.slab.tap_ucap
            lv.callback(None, 128, None, 0)
            lv.patch_reqs.clear()           # (a reset's program 0: nvlive_check's, without --programs)
            if b not in at:
                continue
            nat = np.load(os.path.join(tmp, "%d.npz" % b))
            S = lv.slab
            busy = np.flatnonzero(np.asarray(S.busy, bool))
            bad = []
            for c in nat.files:
                x = nat[c]
                try:
                    a_ = np.asarray(S.a[c])
                except (KeyError, ValueError, IndexError, TypeError):
                    a_ = getattr(S, c, None)
                    if a_ is None:
                        continue
                    a_ = np.asarray(a_)
                if a_.shape != x.shape:
                    bad.append("%s: shape %s vs %s" % (c, a_.shape, x.shape))
                    continue
                a_ = a_.astype(x.dtype)
                diff = np.flatnonzero(a_ != x)
                diff = diff[~(np.isnan(a_[diff]) & np.isnan(x[diff]))] if a_.dtype.kind == "f" else diff
                if len(diff):
                    bs = np.intersect1d(diff, busy)
                    s0 = bs[:4] if len(bs) else diff[:4]
                    bad.append("%-8s %6d slots (%d busy); slots %s live %s native %s" % (
                        c, len(diff), len(bs), s0.tolist(), a_[s0].tolist(), x[s0].tolist()))
            print("== block %d: %d busy slots (live), %d columns differ" % (b, len(busy), len(bad)))
            for ln in bad:
                print("   " + ln)
            if opt.get("non"):                  # --non=LO:HI: the slots whose onset is in it, each side
                lo, hi = (int(x) for x in opt["non"].split(":"))
                for side, get in (("live", lambda c: np.asarray(S.a[c])), ("nat", lambda c: nat[c])):
                    nn_ = get("non")
                    ix = np.flatnonzero((nn_ >= lo) & (nn_ < hi))
                    print("   %s: %d slots with onset in [%d, %d): slots %s.. onsets %s" % (
                        side, len(ix), lo, hi, ix[:6].tolist(), sorted(set(nn_[ix].tolist()))[:8]))
                    try:
                        _rd = np.asarray(get("rdl"))[ix]
                        print("      rdl distinct %d: %s" % (len(set(_rd.tolist())), sorted(set(_rd.astype(int).tolist()))[:14]))
                    except Exception as _e:
                        print("      rdl: %s" % _e)
                    for c in ("nf", "fx", "mk", "aL", "fa", "logr", "crl", "slot_ch"):
                        try:
                            v = get(c)
                        except Exception:
                            v = np.asarray(getattr(S, c)) if side == "live" else None
                        if v is not None:
                            print("      %-7s %s" % (c, np.round(np.asarray(v)[ix[:10]].astype(np.float64), 4).tolist()))
            if opt.get("slots"):                # --slots=A:B: every column there, both sides
                a0, a1 = (int(x) for x in opt["slots"].split(":"))
                for c in nat.files:
                    try:
                        lvv = np.asarray(S.a[c])
                    except (KeyError, ValueError, IndexError, TypeError):
                        lvv = getattr(S, c, None)
                        if lvv is None:
                            continue
                        lvv = np.asarray(lvv)
                    if lvv.shape == nat[c].shape:
                        print("   %-8s live %s\n   %-8s nat  %s" % (c, np.round(lvv[a0:a1].astype(np.float64), 4).tolist(),
                                                                 "", np.round(nat[c][a0:a1].astype(np.float64), 4).tolist()))
    finally:
        shutil.rmtree(tmp, True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
