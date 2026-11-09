#!/usr/bin/env python3
"""Does native/nvlive play a MIDI file as live.Live does?

    python3 examples/nvlive_check.py FILE.mid [SECONDS] [--program=N [--drums]] [--register] [--pedal-key=N]
                                     [--gpu=cl|c] [--gpu-min=N] [--room=NAME] [--tuner=NAME] [--eastern=SPEC] [--programs]

The first SECONDS (default 20) of FILE, cut as bitident cuts, its notes and
controllers (the native reader's, in message order) each applied at the
start of the 128-sample block its time falls in: once through nvlive --test
(the native live engine, from a live export: examples/native_export.py
--live), once through live.Live(program, 48 kHz, 128 a block, on the CPU)
by on_midi and its own callback -- its patch warmed first, its governor off
-- each block's whole output (its callback's: the render, the room, the
limiter). Both in ROOM (default the hall; not the session's: the export
is made --fresh), live's templates and the native ones built in it. Every
sample of the two compared with ==. The file's programs are not followed: the part plays
PROGRAM throughout, as a keyboard would -- unless --programs: then each side
follows them as a keyboard's program changes (live's builder in step,
examples/patchsync.py: the patch posted for the next block, warmed whole;
nvlive --programs builds and posts at the same place). --register: the free strings too,
each side's register worker answering in step (examples/regsync.py; nvlive
with its export's LREG); without, nvlive --no-register. --pedal-key=N: the
file's key N is the sustain pedal on both sides (live.Route(("note", N), 64);
nvlive --pedal-key). --gpu: both on live.GpuRenderer's path (the samples on
OpenCL, or "c" the C reference), from GPU-MIN busy slots (live's GPU_MIN).
--tuner: live at that tuner, and nvlive computing it (native/tuner.cpp) in
place of the export's, its free strings' bank built again at it.
--eastern: a secondary tuning (a raga spec) for the Indian instruments, on
both sides (live.Live(eastern=), nvlive --eastern).
--drums: the part a drum part, PROGRAM its drum set (live.Live(drums=True),
nvlive --drums): the file's notes struck on its kit, whatever their channel.
--beside: the drum set (Standard) on channel 10 beside the piano, which
plays the file's channel 1 (live: a part on each; nvlive's default, its
piano on every channel but 10). --split=N [--split-transpose=T]: on channel
1, keys under N the drum set's, moved by T (live: a drum part over 0..N-1
transposed, the piano over N..127; nvlive --split). Without either, nvlive
--no-drums.
--pipeline (with --gpu): both a block late, the next block's setup while the
GPU renders this one (live's TUNING_GPU_PIPELINE=1; nvlive's default on
OpenCL). Both slabs at --slots=N (default live's 65536); on the CPU unless --gpu.
"""
import atexit
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


def live_export(tmp, room):
    """the live export at ROOM (--fresh), its path. With NV_EXPORT_CACHE set:
    made once in that directory for this tree's sources, ROOM and the TUNING_*
    environment, and the same file handed to every later check (a batch's
    checks share one export; a perturbed tree's sources make another);
    without, made in TMP"""
    cmd = [sys.executable, os.path.join(HERE, "examples", "native_export.py"), None, "--live", "--fresh",
           "--room=" + room]
    cache = os.environ.get("NV_EXPORT_CACHE")
    if not cache:
        cmd[2] = os.path.join(tmp, "live.nvx")
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
        return cmd[2]
    import glob
    import hashlib
    h = hashlib.sha256()
    pin = dict(x.split("=", 1) for x in os.environ.get("NV_EXPORT_KEY_PIN", "").split() if "=" in x)
    for d, pats in (("", ("*.py",)), ("examples", ("*.py",)), ("native", ("*.c", "*.cpp", "*.h", "*.cl"))):
        for p in sorted(f for pat in pats for f in glob.glob(os.path.join(HERE, d, pat))):
            rel = os.path.relpath(p, HERE)
            h.update(rel.encode() + b"\0")
            if rel in pin:                              # (a change the export never runs: the clean file's)
                h.update(bytes.fromhex(pin[rel]))
            else:
                with open(p, "rb") as f:
                    h.update(hashlib.sha256(f.read()).digest())
    for k in sorted(k for k in os.environ if k.startswith("TUNING_")):
        h.update(("%s=%s\0" % (k, os.environ[k])).encode())
    h.update(HERE.encode() + b"\0" + room.encode())   # (the export names the tree's libraries)
    os.makedirs(cache, exist_ok=True)
    out = os.path.join(cache, "live-%s.nvx" % h.hexdigest()[:20])
    if not os.path.exists(out):
        cmd[2] = out + ".part"
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
        os.replace(out + ".part", out)                  # (a killed export never handed on)
    return out


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import mido
    import numpy as np
    import bitident as BI
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L
    import native as N
    prog = int(opt.get("program", 0))
    secs = float(args[1]) if len(args) > 1 else 20.0
    tmp = tempfile.mkdtemp(prefix="nvlivecheck")
    atexit.register(shutil.rmtree, tmp, True)       # (an export and WAVs a run: they filled the disk)
    mid = os.path.join(tmp, "in.mid")
    BI.excerpt(args[0], secs).save(mid)
    room = opt.get("room") or "hall"
    nvx = live_export(tmp, room)
    exe = N.build_nvlive()
    m = N.Midi(mid)
    if m.error or (m.banked() and "programs" not in opt):
        print("refused: %s" % (N.MIDI_REFUSED.get(m.error, m.error) if m.error else "a bank (with --programs only)"))
        return 2
    total = m.total() + 3.0
    out = os.path.join(tmp, "nv.wav")
    reg = "register" in opt
    gmin = int(opt.get("gpu-min", L.GPU_MIN))
    drums = "drums" in opt
    beside = "beside" in opt
    split = int(opt.get("split") or 0)
    stp = int(opt.get("split-transpose") or 0)
    slots = int(opt.get("slots") or 65536)
    pipe = "pipeline" in opt and "gpu" in opt and (opt["gpu"] or "cl") == "cl"
    if pipe:
        os.environ["TUNING_GPU_PIPELINE"] = "1"
    subprocess.check_call([exe, nvx, "--test", mid, out, "--program=%d" % prog, "--seconds=%r" % total,
                           "--slots=%d" % slots] + ([] if "gpu" in opt else ["--cpu"]) + ([] if pipe else ["--no-pipeline"])
                          + ([] if reg else ["--no-register"]) + (["--drums"] if drums else [])
                          + ([] if (beside or drums) else ["--no-drums"])
                          + (["--split=%d" % split, "--split-transpose=%d" % stp] if split else [])
                          + (["--pedal-key=" + opt["pedal-key"]] if "pedal-key" in opt else [])
                          + (["--messenger" + ("=pre-1.0.7" if opt["messenger"] == "pre-1.0.7" else "")]
                             if "messenger" in opt else [])
                          + (["--messenger-log=" + os.path.join(tmp, "msgr.log")] if "messenger-out" in opt else [])
                          + (["--gpu=" + (opt["gpu"] or "cl"), "--gpu-min=%d" % gmin] if "gpu" in opt else [])
                          + (["--tuner=" + opt["tuner"]] if opt.get("tuner") else [])
                          + (["--eastern=" + opt["eastern"]] if opt.get("eastern") else [])
                          + (["--programs"] if "programs" in opt else [])
                          + (["--bank=" + opt["bank"]] if opt.get("bank") else [])
                          + (["--room-at=" + opt["room-at"]] if opt.get("room-at") else []),
                          stderr=subprocess.DEVNULL)
    raw = open(out, "rb").read()          # float32 stereo after a 44-byte header
    nv = np.frombuffer(raw[44:], np.float32).reshape(-1, 2)
    # live.Live, fed the same events on the same blocks
    # (--bank=V: the part a variation, live.Patch's: map x 128 + bank)
    vparts = ([L.Part(L.patch_for(prog, False, opt.get("tuner") or "hybrid", variation=int(opt["bank"])))]
              if opt.get("bank") else None)
    lv = L.Live(program=prog, rate=48000, frames=128, capacity=slots, verbose=False, threads=1, gpu=False,
                tuner=opt.get("tuner") or "hybrid", drums=drums, eastern=opt.get("eastern") or None, parts=vparts)
    lv.enable_room(room)
    lv.parts[0].patch.warm()
    from livepart_check import instant_scan
    instant_scan(lv, lv.parts[0].patch)         # (the scanner's builder, instant: nvlive's works at the press)
    import ampsync
    ampsync.sync(lv)                            # (the valve in step, as nvlive --test answers it)
    if beside or split:
        # the piano on channel 1 (keys from the split), the drum set beside it
        pp = lv.parts[0].patch
        dp = L.Patch(0, True, opt.get("tuner") or "hybrid", 0)
        dp.warm()
        parts = [L.Part(pp, channel=0 if beside else None, lo=split)]
        if beside:
            parts.append(L.Part(dp, channel=9))
        if split:
            parts.append(L.Part(dp, channel=0, lo=0, hi=split - 1, transpose=stp))
        lv.set_parts(parts)
    lv.slab.shed = lambda n, frac: 0
    if "gpu" in opt:
        send = lv.renderer.send
        lv.renderer = L.GpuRenderer(lv.slab, 128, 1, backend=opt["gpu"] or "cl", gpu_min=gmin)
        lv.renderer.send = send
    if "pedal-key" in opt:
        lv.set_routes([L.Route(("note", int(opt["pedal-key"])), 64)])
    if "messenger" in opt:
        # every part reading a Messenger's chart (--messenger=pre-1.0.7: that firmware's)
        for _p in lv.parts:
            _p.cc_map = "messenger"
        lv.messenger_firmware = "pre-1.0.7" if opt["messenger"] == "pre-1.0.7" else "1.0.7+"
    if reg:
        import regsync
        regsync.sync(lv, lv.parts[0])
    progs = "programs" in opt
    # --room-at=S:NAME[,S:NAME...]: live.set_room at the block S falls in,
    # before its events -- its builder in step (_room_switch, then the parts'
    # patches built in the new room and their swaps posted: patchsync's)
    room_at = {}
    for it in (opt.get("room-at") or "").split(","):
        if ":" in it:
            s_, nm = it.split(":", 1)
            room_at[int(float(s_) * 48000) // 128] = nm
    # the builder in step always: a reset (GS Reset, GM System On) asks every
    # part for program 0, as a program change does
    import patchsync
    patchsync.sync(lv)
    # --messenger-out: a Messenger set as live.open_messenger would, its queue
    # kept with each message's block, against nvlive's --messenger-log
    sent, blk = [], [0]
    if "messenger-out" in opt:
        class _Q:
            def put(self, msg):
                sent.append((blk[0],) + tuple(msg.bytes()))
        lv.messenger_q = _Q()
        for _p in lv.parts:
            lv.messenger_sync(_p)
    dry = []
    evs = m.events()
    nb = int(total * 48000) // 128
    e = 0
    M = mido.Message
    for b in range(nb):
        blk[0] = b
        if b in room_at:
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
            elif ty == 5:
                if progs:
                    lv.on_midi(M("program_change", channel=ch, program=a))
            elif ty == 6:
                lv.on_midi(M("sysex", data=list(m.sysex(a))))
            else:
                lv.on_midi(M("control_change", channel=ch, control=a, value=v))
            e += 1
        lv.slab.tap_cap = lv.slab.tap_ucap         # (the copies' governor off too: live._callback's
                                                   # cut on a slow block; nvlive cuts none in --test)
        dry.append(np.frombuffer(lv.callback(None, 128, None, 0)[0], np.float32).reshape(-1, 2))
        if progs:
            for _part, _p in patchsync.build(lv):
                instant_scan(lv, _p)
        else:
            lv.patch_reqs.clear()       # (a reset's program 0: nvlive follows none without --programs)
    py = np.concatenate(dry) if dry else np.zeros((0, 2), np.float32)
    if py.shape != nv.shape:
        print("%s: length %r vs %r" % (os.path.basename(args[0]), py.shape, nv.shape))
        return 1
    if "messenger-out" in opt:
        got = [tuple(int(x) for x in ln.split()) for ln in open(os.path.join(tmp, "msgr.log"))]
        if got != sent:
            k = next((i for i in range(min(len(got), len(sent))) if got[i] != sent[i]), min(len(got), len(sent)))
            print("the Messenger's messages differ: %d vs %d, from #%d (nvlive %s, live %s)"
                  % (len(got), len(sent), k, got[k:k + 3], sent[k:k + 3]))
            return 1
        print("the Messenger's %d messages identical" % len(sent))
    d = np.flatnonzero(np.any(py != nv, 1))
    # (its peak: two silences are identical too)
    print("%s (%g s, program %d%s, %s): %d blocks, peak %.3g, %s" % (
        os.path.basename(args[0]), secs, prog, ", register" if reg else "", room, nb,
        float(np.max(np.abs(py))) if py.size else 0.0,
        "identical" if not len(d) else "%d frames differ from block %d (max %g)"
        % (len(d), d[0] // 128, float(np.max(np.abs(py.astype(np.float64) - nv))))))
    return 1 if len(d) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
