#!/usr/bin/env python3
"""Does the native piano part play live MIDI as live.Live does?

    python3 examples/livepiano_check.py [BLOCKS] [--program=N] [--seed=N] [--every=N] [--render] [--register]
                                        [--half] [--pedal-key=N] [--pressure]
                                        [--gpu=c|cl] [--gpu-min=N] [--shed=N] [--wheels]
                                        [--room=NAME] [--cc91] [--thresh=X] [--rpn] [--modes]
                                        [--routes] [--porta] [--stops] [--scan]

live.Live(program, 48 kHz, 128 a block, on the CPU: no register) and the
native piano part (native/slab.cpp: its template cache, its slab, live's
events for it) are fed the same random MIDI block by block -- presses and
key-ups across the keyboard, the sustain pedal as a switch, CC7, CC11, CC10,
CC67 -- through on_midi and live's own callback on one side and the native
part's block on the other. Every EVERY blocks (default 1) the two slabs are
compared with ==: every slot column, the bookkeeping, the free queue's
order. The first block that differs is reported with its events. Live's
governor (Slab.shed, by the wall-clock render time) is off: a host policy,
not arithmetic to match. --render: each block's dry render too -- live's
Renderer.render (and its room send, when on) against the native part's.
--register: the free strings too (live's register, on the CPU here), its
worker answering each job as it is sent on both sides -- live's through
register.LiveWorker in step with its callback, the native part's in
native/livereg.cpp -- so a reply is placed at the first pump after its job.
--half: the pedal at values through damper.py's band as well (ondine.mid's
0/24/40/.../127; --half=all: any value), so half-pedalled keys take damper
tracks (live._damp_block):
the slabs' dk compared as which slots are on a track and that track's two
values (DM), as a track's number is handed out in a set's order, and dg.
--pedal-key=N: key N held as the sustain pedal and pushed into (channel
aftertouch while it is held) -- live.Route(("note", N), 64) through on_midi
on one side, native.KeyPedal before the part's events on the other.
--pressure: channel aftertouch among the controls (live's Slab.press).
--stops: an organ's stops drawn and put in as the panel does (livetui's
toggle_stop; the native part's nv_lp_toggle_stop), the Tremulant among them.
On a tonewheel (16-18) the Leslie's state is compared too (ls_*: its rotor
slots, lobes and baselines), the pitch wheel its half-moon under --wheels;
--scan: the scanner's selector (CC94) among the controls.
--programs=A,B,...: program changes among these (melodic) programs, on
either channel -- live's builder in step (examples/patchsync.py): the swap
posted on both sides after the block that asked for it, done after the next
block's events, the new patch warmed whole.
On a harmonium (program 20) its stop word too (CC43-45), the mod wheel
(its tremolo) and the sound controllers it answers (CC72/73, and by GS's
NRPNs); the tremolo's state (tr_on, its depth, baselines and sides)
compared with the slab.
--gpu: each side renders as live.GpuRenderer -- the setup on the CPU
(voice_block), the samples on the OpenCL GPU ("cl": live's through pyopencl,
the native part's through native/gpu.cpp) or the C reference ("c",
voice_samples) -- for a block with GPU-MIN busy slots or more (default
live's GPU_MIN); the blocks each side took to the GPU are counted.
--room=NAME: both in that room -- live.enable_room before its patch is
warmed, the native templates packed after -- and every block's whole output
compared (live's callback: the render, the master, the room's tail on the
send, the limiter; the native part's output) in place of --render's dry
blocks. --cc91: the channels' reverb sends among the controls, so the send
runs as the kernel's second output while they differ. --thresh: the soft
limiter's knee (live's 0.70), low to make it work.
--rpn: RPNs (bend range, fine and coarse tuning, the mod range, MTS's
selects, the null; data entry and increment), NRPN selects, CC121 and the
sostenuto pedal among the controls.
--routes: a random set of routes (live.Route) on both sides -- through
on_midi on live's, native.Router on the native part's -- onto what the
native piano plays: the pedals, CC1, 7, 10, 11, the wheel, pressure, mono.
--porta: portamento among the controls -- CC65 on and off, CC5's time,
CC84's source -- which a piano ignores in live as natively: no piano class
has a glide mechanism (live._glide). With --modes, in mono too.
--modes: All Sound Off (CC120), All Notes Off (CC123) and the channel-mode
messages that send them (124-127: MONO on and off among them, so the
channels play in mono mode for stretches -- a voice handed over, and back).

--wheels: the pitch wheel (live._repitch, the notes sounding moved and a
note struck under it joining) and the mod wheel (a honky-tonk's detune).
--shed=N: every N blocks the governor's last resort on both sides at the
next block's start (live's Slab.shed, a tenth of what sounds), as a block
over budget would -- the governor itself goes by the wall clock, so it is
asked here instead.
"""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


def instant_scan(lv, pt):
    """THE SCANNER'S DATA (live._scan_prep, by the builder thread) made as the
    press asks for it, as if the builder were instant: the native part works
    it out at the press. pt's templates (warmed) are the ranks it knows."""
    class _ScanG(dict):
        def get(self, k, d=None):
            if k not in self and k[0] in _ScanG.cols:
                cols, n, hrel = _ScanG.cols[k[0]]
                lv._scan_prep(cols, n, hrel, k[1], k[2])
            return dict.get(self, k, d)
    _ScanG.cols = {}
    for _t in pt.templates.values():
        for _rk, (_c, _n, _h) in (_t.get("ranks") or {}).items():
            _ScanG.cols[id(_c)] = (_c, _n, _h)
    lv._scan_g = _ScanG(lv._scan_g)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import mido
    import numpy as np
    import blockrender as B
    import live as L
    import native as N
    blocks = int(args[0]) if args else 2000
    prog = int(opt.get("program", 0))
    every = int(opt.get("every", 1))
    rng = random.Random(int(opt.get("seed", 1)))
    lv = L.Live(program=prog, rate=48000, frames=128, verbose=False, threads=1, gpu=False)
    if opt.get("room"):
        lv.enable_room(opt["room"])
    part = lv.parts[0]
    pt = part.patch
    pt.warm()           # live warms off the audio thread; here, before the first press
    instant_scan(lv, pt)
    import ampsync
    ampsync.sync(lv)                # the valve in step (the native part's, its worker off)
    lv.slab.shed = lambda n, frac: 0    # the governor sheds by wall-clock render time: not a reference
    lo, hi = pt.range
    cache = N.TemplateCache(prog, pt.tuner)
    cache.warm(lo, hi, pt.nbuckets, pt.speeds)
    speed = None if pt.speeds == (None,) else (lv.detune_step.get(part.pid, pt.leslie_default)
                                               if pt.detune_wheel else pt.leslie_default)
    nv = N.LivePiano(cache, part.pid, part.level_db, pt.nbuckets, speed, pt.damper_pedal, pt.soft_pedal_strings,
                     pt.soft_pedal_top, 48000, capacity=lv.slab.cap, headroom=lv.slab.headroom,
                     detune_wheel=pt.detune_wheel)
    ngpu = [0, 0]
    if "gpu" in opt:
        gmin = int(opt.get("gpu-min", L.GPU_MIN))
        send = lv.renderer.send
        lv.renderer = L.GpuRenderer(lv.slab, 128, 1, backend=opt["gpu"] or "cl", gpu_min=gmin)
        lv.renderer.send = send
        nv.gpu(opt["gpu"] or "cl", gmin)
    nv.post(lv.thresh, lv.bend_range, lv.mod_cents)
    if opt.get("room"):
        lv.thresh = float(opt.get("thresh", lv.thresh))
        if lv.room is not None:
            nv.room(lv.room.ir, lv.room.mir, 128)
        nv.post(lv.thresh, lv.bend_range, lv.mod_cents)
    if "register" in opt:
        import blockrender as BR
        import regsync
        regsync.sync(lv, part)
        nv.register(pt._voice_class(60), BR.tuning_table(pt.tuner), 48000.0, getattr(BR, 'REGISTER_SCALE', 1.0),
                    [lv._reg_voice(part, n) for n in range(128)])
    held = set()
    ntr = dmb = nshed = nlim = ntune = nsost = nmode = nmono = 0
    pk = int(opt["pedal-key"]) if "pedal-key" in opt else None
    kp = None
    routes = [L.Route(("note", pk), 64)] if pk is not None else []
    if "routes" in opt:
        for _ in range(rng.randint(1, 3)):
            kind = rng.choice(("cc", "bend", "pressure", "note"))
            src = (("cc", rng.choice((2, 4, 11))) if kind == "cc"
                   else ("bend", rng.choice(("up", "down", "both"))) if kind == "bend"
                   else ("pressure",) if kind == "pressure" else ("note", rng.choice((lo, hi))))
            routes.append(L.Route(src, rng.choice((64, 66, 67, 1, 7, 10, 11, "bend", "pressure", "mono")),
                                  keep=rng.random() < 0.3, latch=rng.random() < 0.3))
        print("  routes: %s" % "; ".join(r.describe() for r in routes))
    if routes:
        lv.set_routes(routes)
        kp = N.Router(routes)
    pk_down = set()
    progs = [int(x) for x in opt["programs"].split(",")] if opt.get("programs") else []
    pcaches = {}            # live's Patch -> its native cache: one tone, one identity (live._PATCHES')
    if progs:
        import patchsync
        patchsync.sync(lv)
    nswap = 0
    harm = bool(lv.parts[0].organ) and lv.parts[0].patch.stop_word_ccs[0] == 43
    pedal = ((0, 24, 40, 56, 72, 88, 104, 127) if opt.get("half") != "all" else tuple(range(128))) \
        if "half" in opt else (0, 127)
    M = mido.Message
    dry = []
    if "render" in opt:
        _rend = lv.renderer.render

        def _cap(n0, frames):
            oL, oR = _rend(n0, frames)
            r = lv.renderer
            dry.append((n0, frames, oL.copy(), oR.copy(), bool(r.send),
                        r.SL[:frames].copy() if r.send else None, r.SR[:frames].copy() if r.send else None))
            return oL, oR
        lv.renderer.render = _cap
    rbad = []
    bad, log = [], []

    def compare(b):
        S = lv.slab
        for c in L.ALL_COLS + ("sw",):
            a, x = np.asarray(S.a[c]), nv.slab.col(c)
            if a.dtype != x.dtype or not np.array_equal(a, x):
                bad.append(c)
        for c in ("aL0", "aR0", "sg", "sre", "hrel", "vbase", "vrbase", "vsc"):
            a = np.asarray(getattr(S, c))
            if not np.array_equal(a, nv.slab.col(c).astype(a.dtype)):
                bad.append(c)
        for c in ("tr_dep", "tr_aL", "tr_aR", "tr_st", "tr_on", "hs_dep", "ls_on", "ls_horn", "ls_am", "ls_sharp",
                  "ls_norm", "ls_ph", "ls_aL", "ls_aR"):
            if not np.array_equal(np.asarray(getattr(S, c), np.float32), nv.slab.col(c)):
                bad.append(c)
        if not np.array_equal(np.asarray(S.busy, np.int32), nv.slab.col("busy")):
            bad.append("busy")
        if list(S.free) != nv.slab.free_list():
            bad.append("the free queue")
        dk, xk = np.asarray(S.a['dk']), nv.slab.col("dk")
        if not np.array_equal(dk >= 0, xk >= 0):
            bad.append("dk")
        else:
            on = np.flatnonzero((dk >= 0) & np.asarray(S.busy, bool))
            ndm = nv.dm()
            if not (np.array_equal(S.DM[2 * dk[on]], ndm[2 * xk[on]])
                    and np.array_equal(S.DM[2 * dk[on] + 1], ndm[2 * xk[on] + 1])):
                bad.append("DM")
        if not np.array_equal(np.asarray(S.a['dg']), nv.slab.col("dg")):
            bad.append("dg")
        # the chest's state (wind.Wind's), where each side has one
        _ws = (ctypes.c_double * 8)()
        _has = nv.d.nv_lp_wind_state(nv.p, _ws)
        if bool(_has) != bool(lv.wind_st):
            bad.append("wind chest")
        elif _has:
            _w = next(iter(lv.wind_st.values()))["wind"]
            if [float(getattr(_w, a)) for a in ("w1", "w2", "s1", "s2", "d1", "r1", "te", "tph")] != list(_ws):
                bad.append("wind state")
        # the bend rows (the organs' wind): their tables
        _br, _bc, _bl = nv.bend_rows(S.BR.shape[0])
        _m = len(_br)
        if not (np.array_equal(S.BR[:_m, 0], _br) and np.array_equal(S.BC[:_m, 0], _bc)
                and np.array_equal(S.BL[:_m], _bl)):
            bad.append("bend rows")
        return bad

    for b in range(blocks):
        msgs = []
        for _ in range(rng.choice((0, 0, 0, 1, 1, 2, 3))):
            r = rng.random()
            ch = rng.choice((0, 0, 0, 1))
            if r < 0.4 or not held:
                note = rng.randint(lo, hi)
                if note == pk:
                    continue            # the pedal key plays no note
                msgs.append(M("note_on", channel=ch, note=note, velocity=rng.randint(1, 127)))
                held.add((ch, note))
            elif r < 0.8:
                ch, note = rng.choice(sorted(held))
                held.discard((ch, note))
                msgs.append(M("note_off", channel=ch, note=note, velocity=0))
            elif pk is not None and r < 0.9:
                # the pedal key: pressed, let go, or pushed into while down
                if ch in pk_down and rng.random() < 0.7:
                    msgs.append(M("aftertouch", channel=ch, value=rng.randint(0, 127)))
                elif ch in pk_down:
                    pk_down.discard(ch)
                    msgs.append(M("note_off", channel=ch, note=pk, velocity=0))
                else:
                    pk_down.add(ch)
                    msgs.append(M("note_on", channel=ch, note=pk, velocity=rng.randint(1, 127)))
            elif r < 0.9:
                msgs.append(M("control_change", channel=ch, control=64, value=rng.choice(pedal)))
            elif "wheels" in opt and rng.random() < 0.4:
                if rng.random() < 0.7:
                    msgs.append(M("pitchwheel", channel=ch, pitch=rng.choice((0, rng.randint(-8192, 8191)))))
                else:
                    msgs.append(M("control_change", channel=ch, control=1, value=rng.randint(0, 127)))
            elif "porta" in opt and rng.random() < 0.3:
                c = rng.choice((5, 65, 65, 84))
                msgs.append(M("control_change", channel=ch, control=c,
                              value=rng.randint(0, 127) if c != 65 else rng.choice((0, 127))))
            elif "routes" in opt and rng.random() < 0.4:
                y = rng.random()
                if y < 0.3:
                    msgs.append(M("control_change", channel=ch, control=rng.choice((2, 4, 11)),
                                  value=rng.randint(0, 127)))
                elif y < 0.55:
                    msgs.append(M("pitchwheel", channel=ch, pitch=rng.randint(-8192, 8191)))
                elif y < 0.75:
                    msgs.append(M("aftertouch", channel=ch, value=rng.randint(0, 127)))
                else:
                    nt = rng.choice((lo, hi))
                    msgs.append(M("note_on", channel=ch, note=nt, velocity=rng.randint(1, 127))
                                if rng.random() < 0.5 else M("note_off", channel=ch, note=nt, velocity=0))
            elif "pressure" in opt and rng.random() < 0.4:
                msgs.append(M("aftertouch", channel=ch, value=rng.choice((0, rng.randint(0, 127)))))
            elif "rpn" in opt and rng.random() < 0.5:
                x = rng.random()
                if x < 0.3:                                 # select: an RPN, the null, or an NRPN
                    sel = rng.choice(((0, 0), (0, 0), (0, 1), (0, 2), (0, 5), (0, 3), (127, 127), "n"))
                    if sel == "n":
                        msgs.append(M("control_change", channel=ch, control=99, value=1))
                    else:
                        msgs.append(M("control_change", channel=ch, control=101, value=sel[0]))
                        msgs.append(M("control_change", channel=ch, control=100, value=sel[1]))
                elif x < 0.6:
                    msgs.append(M("control_change", channel=ch, control=6, value=rng.choice((0, 1, 2, 12, 64, 70,
                                                                                            rng.randint(0, 127)))))
                elif x < 0.7:
                    msgs.append(M("control_change", channel=ch, control=38, value=rng.randint(0, 127)))
                elif x < 0.8:
                    msgs.append(M("control_change", channel=ch, control=rng.choice((96, 97)), value=0))
                elif x < 0.85:
                    msgs.append(M("control_change", channel=ch, control=121, value=0))
                else:
                    msgs.append(M("control_change", channel=ch, control=66, value=rng.choice((0, 127))))
            elif "modes" in opt and rng.random() < 0.25:
                msgs.append(M("control_change", channel=ch,
                              control=rng.choice((120, 123, 123, 124, 125, 126, 126, 127)), value=0))
                nmode += 1
            elif "stops" in opt and harm and rng.random() < 0.4:
                c = rng.choice((43, 43, 44, 45, 1, 72, 73, 75, "n"))
                if c == "n":                # the same by GS's sound NRPNs (release, attack)
                    msgs += [M("control_change", channel=ch, control=99, value=1),
                             M("control_change", channel=ch, control=98, value=rng.choice((0x66, 0x63, 0x20))),
                             M("control_change", channel=ch, control=rng.choice((6, 6, 38)),
                               value=rng.randint(0, 127))]
                else:
                    msgs.append(M("control_change", channel=ch, control=c, value=rng.randint(0, 127)))
            elif "scan" in opt and rng.random() < 0.3:
                # the scanner's selector: off, V1-V3, C1-C3
                msgs.append(M("control_change", channel=ch, control=94,
                              value=rng.choice((0, 20, 40, 60, 80, 100, 120))))
            elif "cc91" in opt and rng.random() < 0.3:
                msgs.append(M("control_change", channel=ch, control=91, value=rng.randint(0, 127)))
            else:
                cc = rng.choice((7, 11, 10, 67))
                msgs.append(M("control_change", channel=ch, control=cc, value=rng.randint(0, 127)))
        if progs and rng.random() < 0.04:
            msgs.append(M("program_change", channel=rng.choice((0, 0, 0, 1)), program=rng.choice(progs)))
        n0 = lv.n
        for m in msgs:
            lv.on_midi(m)
            for x in (kp.feed(m) if kp is not None else [m]):
                nv.event(x)
        if "stops" in opt and lv.parts[0].organ and rng.random() < 0.15:
            # A STOP DRAWN OR PUT IN FROM THE PANEL (livetui's toggle_stop):
            # posted on both sides, done after the block's events
            _pt = lv.parts[0]
            _ri = rng.randrange(len(_pt.patch.rank_names))
            lv.request_stops(_pt, set(_pt.drawn) ^ {_pt.patch.rank_names[_ri]})
            nv.d.nv_lp_toggle_stop(nv.p, _ri, n0)
            msgs = msgs + ["stop %s" % _pt.patch.rank_names[_ri]]
        got_py = lv.callback(None, 128, None, 0)[0]
        nv.block(n0, 128)
        if progs:
            # A PROGRAM CHANGE (live's builder, in step): the patch it asked
            # for, posted on both sides for the next block
            for _part, _p in patchsync.build(lv):
                _c = pcaches.get(id(_p), (None, None))[1]
                if _c is None:
                    _c = N.TemplateCache(_p.program, _p.tuner)
                    _c.warm(_p.range[0], _p.range[1], _p.nbuckets, _p.speeds)
                    pcaches[id(_p)] = (_p, _c)
                instant_scan(lv, _p)
                _sp = None if _p.speeds == (None,) else _p.leslie_default
                _rn, _str = None, None
                if "register" in opt:
                    # its keys that answer, and ITS STRINGS where they are another voice's (live._reg_forget)
                    import types
                    import blockrender as BR
                    _as = types.SimpleNamespace(drums=_p.drums, patch=_p, organ=_p.organ)
                    _rn = [lv._reg_voice(_as, n) for n in range(128)]
                    _sg = lambda q: None if q.drums else (q._voice_class(60), q.tuner)     # noqa: E731
                    if _sg(_part.patch) != _sg(_p):
                        _str = (None if _p.drums else _p._voice_class(60), BR.tuning_table(_p.tuner), 48000.0,
                                getattr(BR, 'REGISTER_SCALE', 1.0))
                nv.swap(0, _c, _p.nbuckets, _sp, _p.damper_pedal, _p.soft_pedal_strings, _p.soft_pedal_top,
                        _p.detune_wheel, reg_note=_rn, strings=_str)
                nswap += 1
                msgs = msgs + ["program %d" % _p.program]
                if "debug" in opt:
                    print("    (block %d: program %d posted)" % (b, _p.program))
        if opt.get("room"):
            oL, oR = nv.output(n0, 128)
            st = np.empty(256, np.float32)
            st[0::2] = oL
            st[1::2] = oR
            nlim += int(np.max(np.abs(st)) > lv.thresh * 0.9)
            if "gpu" in opt:
                ngpu[0] += lv.renderer.on_gpu
                ngpu[1] += nv.on_gpu()
            if st.tobytes() != got_py:
                rbad.append(b)
                bad.append("output")
            dry.clear()
        while dry:
            rn0, fr, dL, dR, snd, sL, sR = dry.pop(0)
            got = nv.render(rn0, fr, send=snd)
            if "gpu" in opt:
                ngpu[0] += lv.renderer.on_gpu
                ngpu[1] += nv.on_gpu()
            ok = np.array_equal(dL, got[0]) and np.array_equal(dR, got[1]) and (
                not snd or (np.array_equal(sL, got[2]) and np.array_equal(sR, got[3])))
            if not ok:
                rbad.append(b)
                bad.append("render")
        if "shed" in opt and b % int(opt["shed"]) == int(opt["shed"]) - 1:
            k0, k1 = L.Slab.shed(lv.slab, lv.n, 0.1), nv.shed(lv.n, 0.1)     # (lv.slab.shed is stubbed: the governor)
            nshed += k0
            if k0 != k1:
                bad.append("shed %d vs %d" % (k0, k1))
        log.append((b, n0, msgs))
        ntr = max(ntr, len(lv.damp_tracks))
        ntune += any(v not in (None, 2.0) for v in lv.brange.values()) or any(lv.fine.values()) \
            or any(lv.coarse.values())
        nsost += any(lv.sost.values())
        nmono += bool(lv.mono)
        dmb += bool(lv.damp_tracks)
        if b % every == every - 1 or b == blocks - 1:
            if compare(b):
                print("  block %d (sample %d) DIFFERS: %s" % (b, n0, " ".join(bad[:8])))
                if "debug" in opt and bad and bad[0].startswith("tr_"):
                    x, y = np.asarray(getattr(lv.slab, bad[0]), np.float32), nv.slab.col(bad[0])
                    dd = np.flatnonzero(x != y)
                    own = {int(q): k for k, v in lv.slab.live.items() for q in v}
                    print("    %s at %d slots, e.g. %s: live %s native %s; owners %s" % (
                        bad[0], len(dd), dd[:4].tolist(), x[dd[:4]].tolist(), y[dd[:4]].tolist(),
                        [own.get(int(q)) for q in dd[:4]]))
                    print("    trem_depth %s" % dict(lv.trem_depth))
                if "debug" in opt and "wind state" in bad:
                    _ws = (ctypes.c_double * 8)()
                    nv.d.nv_lp_wind_state(nv.p, _ws)
                    _w = next(iter(lv.wind_st.values()))["wind"]
                    print("    wind: live %s" % [float(getattr(_w, a)) for a in ("w1", "w2", "s1", "s2", "d1", "r1", "te", "tph")])
                    print("    wind: nati %s" % list(_ws))
                    _kk = (ctypes.c_longlong * 4096)()
                    _nm = ctypes.create_string_buffer(65536)
                    _nk = nv.d.nv_lp_live_keys(nv.p, _kk, 1024, _nm, 65536)
                    _names = _nm.value.decode().split("\n")
                    _nat = [(int(_kk[4 * i + 1]), int(_kk[4 * i + 2]), _names[i] or int(_kk[4 * i + 3]))
                            for i in range(_nk)]
                    _liv = [(k[1], k[2], k[3]) for k in lv.slab.live]
                    print("    live keys %d native %d; first difference at %s" % (
                        len(_liv), len(_nat), next((i for i, (a, b) in enumerate(zip(_liv, _nat)) if a != b), None)))
                    _i0 = next((i for i, (a, b) in enumerate(zip(_liv, _nat)) if a != b), None)
                    if _i0 is not None:
                        print("    live %s\n    nati %s" % (_liv[_i0:_i0 + 6], _nat[_i0:_i0 + 6]))
                    _st = next(iter(lv.wind_st.values()))
                    print("    live's drawing keys: %s" % [(k, getattr(lv.key_tone.get((k[0], k[1], k[2])), 'program', None))
                                                       for k in lv.slab.live if len(k) == 4 and k[3] in _st["ratios"]])
                if "debug" in opt and "bend rows" in bad:
                    _br, _bc, _bl = nv.bend_rows(lv.slab.BR.shape[0])
                    for _r in range(len(_br)):
                        if (lv.slab.BR[_r, 0] != _br[_r] or lv.slab.BC[_r, 0] != _bc[_r]
                                or not np.array_equal(lv.slab.BL[_r], _bl[_r])):
                            print("    row %d: live %s %s %s native %s %s %s" % (
                                _r, lv.slab.BR[_r, 0], lv.slab.BC[_r, 0], lv.slab.BL[_r].tolist(), _br[_r], _bc[_r],
                                _bl[_r].tolist()))
                    _wi = (ctypes.c_longlong * 256)()
                    _nw = nv.d.nv_lp_wind_info(nv.p, _wi, 256)
                    print("    native: %s" % list(_wi[:_nw]))
                    print("    live: wind_next %d spent %s free %s chests %s" % (
                        lv.wind_next, lv.wind_spent, list(lv.wind_free),
                        {k: dict(v["rows"]) for k, v in lv.wind_st.items()}))
                if "debug" in opt:
                    for c in bad[:2]:
                        if c in L.ALL_COLS:
                            x, y = np.asarray(lv.slab.a[c]), nv.slab.col(c)
                            dd = np.flatnonzero(x != y)
                            print("    %s at %d slots, e.g. %s: live %s native %s" % (
                                c, len(dd), dd[:6].tolist(), x[dd[:6]].tolist(), y[dd[:6]].tolist()))
                    own = {int(q): k for k, v in lv.slab.live.items() for q in v}
                    print("    owners:", [own.get(int(q), "reg/retiring") for q in dd[:6]])
                    print("    live's valve: busy %s, dirty %s, jid %s, oneshot %s, retired %s" % (
                        lv.amp_busy, sorted(lv.amp_dirty), dict(lv.amp_jid),
                        [str(k) for k in lv.slab.oneshot if k[1] < 0], list(lv.amp_retired)))
                    print("    busy: live %d, native %d; live's keys %s" % (
                        int(np.asarray(lv.slab.busy).sum()), int(nv.slab.col("busy").sum()),
                        sorted(((str(k), len(v)) for k, v in lv.slab.live.items()), key=str)[:12]))
                for x in log[-4:]:
                    print("    block %d at %d: %s" % (x[0], x[1], "; ".join(str(m) for m in x[2]) or "-"))
                break
    sounding = sum(len(v) for v in lv.slab.live.values())
    if "register" in opt:
        print("  register: %d rows placed, %d dropped (native %d); live's errors: %d %s" % (
            int(np.sum(lv.slab.busy)) - sounding, lv.reg_dropped, nv.reg_dropped(), lv.errors,
            lv.last_error or ""))
    if "porta" in opt:
        print("  portamento: live glided %d notes (a piano has no glide mechanism)" % getattr(lv, "glides", 0))
    if "modes" in opt:
        print("  modes: %d All Sound/Notes Off and mode messages; %d blocks in mono" % (nmode, nmono))
    if "rpn" in opt:
        print("  RPNs: %d blocks with a range or tuning off GM's, %d with sostenuto holding keys" % (ntune, nsost))
    if opt.get("room"):
        print("  room %s: %d blocks reaching the limiter's knee (%.2f)" % (opt["room"], nlim, lv.thresh))
    if "shed" in opt:
        print("  shed: %d partials" % nshed)
    if progs:
        print("  programs: %d changes among %s" % (nswap, ",".join(str(x) for x in progs)))
    if "gpu" in opt:
        print("  GPU (%s): live took %d blocks to it, native %d" % (opt["gpu"] or "cl", ngpu[0], ngpu[1]))
    if "half" in opt:
        print("  dampers: up to %d tracks at once, %d blocks with one" % (ntr, dmb))
    print("live piano: %d blocks, program %d, %s%s (%d slots sounding at the end)"
          % (b + 1, prog, "identical" if not bad else "differs",
             ", every block's render too" if "render" in opt and not rbad else "", sounding))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
