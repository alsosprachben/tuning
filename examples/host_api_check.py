"""host.h's calls past the render (host step 2g), through ctypes:

- THE PICK, bit for bit: the host opened on program 0, program P picked
  (nv_host_pick: built on the builder, swapped in between two blocks), then
  a fixed silence (LEAD blocks, nothing building by its end) and a file --
  against the same host given P as a MIDI program change at the same block
  (--programs: the path nvlive_check --programs holds to live's), the same
  silence, the same file. (Not against a host OPENED on P: a program change
  keeps the part's state, as live's does.)
- the patches (nv_host_patches): every program, set and variation, named,
  P among them and native; what sounds now (nv_host_patch_now);
- the globals (nv_host_set_global, nv_host_global): each read back as set;
  the master (an absolute level, dB: T.master_gain's) 6 dB under where it
  stood, the output's peak half (the limiter's knee past it: by its ratio,
  not the bit);
- panic (nv_host_panic): as live's, every note released -- each with its own
  release, the room ringing on -- so a block after it no slot sounds
  unreleased (the slab's note-offs, through nv_host_part).

    python3 examples/host_api_check.py FILE.mid [--program=P]

(each host in a process of its own: a host holds the export, ~1 GB, and is
not freed -- its threads run to the end)
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
from host_check import encode                           # noqa: E402


class Patch(ctypes.Structure):
    _fields_ = [("program", ctypes.c_int), ("variation", ctypes.c_int), ("drums", ctypes.c_int),
                ("native", ctypes.c_int), ("pick", ctypes.c_int), ("name", ctypes.c_char * 64)]


LEAD = 1200          # (blocks of silence for the build: a Moog's took under 300)


def child(nvx, mid, case, prog, nsil, outp):
    """one host, one case: its output to outp (.npy), what it found to stdout"""
    import native as N
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_rate", [vp]),
                 ("nv_host_building", [vp]), ("nv_host_panic", [vp]), ("nv_host_pick", [vp, ci]),
                 ("nv_host_midi", [vp, cp, ci]), ("nv_host_render", [vp, vp, vp, ci]),
                 ("nv_host_patches", [vp, vp, ci]), ("nv_host_patch_now", [vp, vp, vp, vp]),
                 ("nv_host_set_global", [vp, ci, ctypes.c_double]), ("nv_host_global", [vp, ci])):
        getattr(d, f).argtypes = a
    d.nv_host_global.restype = ctypes.c_double
    d.nv_midi_read.restype = vp
    d.nv_midi_read.argtypes = [cp, ctypes.c_longlong, ctypes.POINTER(ci)]
    d.nv_midi_n_events.argtypes = [vp]
    d.nv_midi_event.argtypes = [vp, ci, ctypes.POINTER(ci), ctypes.POINTER(ctypes.c_double)]
    d.nv_midi_sysex.argtypes = [vp, ci, cp, ci]
    raw = open(mid, "rb").read()
    err = ci(0)
    m = d.nv_midi_read(raw, len(raw), ctypes.byref(err))
    p0 = 0 if case in ("pick", "progchg") else prog
    av = [b"nvlive", nvx.encode(), b"--program=%d" % p0, b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-drums", b"--reg-sync", b"--no-governor"]      # (the governor off: as --test runs)
    if case == "progchg":
        av.append(b"--programs")
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), ctypes.create_string_buffer(256), 256)
    assert h, "the host refused"
    d.nv_host_start(h)
    blk, sr = d.nv_host_block(h), d.nv_host_rate(h)
    L = np.zeros(blk, np.float32)
    R = np.zeros(blk, np.float32)
    bad = 0
    if case == "pick":
        n = d.nv_host_patches(h, None, 0)
        pt = (Patch * n)()
        d.nv_host_patches(h, pt, n)
        pk = [x for x in pt if x.program == prog and not x.drums and x.variation == 0]
        named = sum(1 for x in pt if x.name)
        print("patches: %d (%d named, %d native, %d variations); program %d %s" % (
            n, named, sum(x.native for x in pt), sum(1 for x in pt if x.variation),
            prog, ("native: %s" % pk[0].name.decode()) if pk and pk[0].native else "NOT NATIVE"))
        bad += not (pk and pk[0].native and named > 128)
        d.nv_host_pick(h, pk[0].pick)
        for nsil in range(1, LEAD + 1):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
        if d.nv_host_building(h):
            print("the pick still building after %d blocks" % LEAD)
            bad += 1
        pn, pv, pd = ci(), ci(), ci()
        d.nv_host_patch_now(h, ctypes.byref(pn), ctypes.byref(pv), ctypes.byref(pd))
        print("picked: %d silent blocks to build and swap; now program %d.%d%s" % (
            nsil, pn.value, pv.value, " (drums)" if pd.value else ""))
        print("NSIL %d" % nsil)
        bad += pn.value != prog
    elif case == "progchg":
        by = bytes([0xC0, prog])                # (channel 1's program change, as a keyboard sends it)
        d.nv_host_midi(h, by, len(by))
        for _ in range(LEAD):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
        if d.nv_host_building(h):
            print("the program change still building after %d blocks" % LEAD)
            bad += 1
    else:
        for _ in range(nsil):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
    if case == "globals":
        for g, v in ((1, 6.0), (2, 0.6), (3, 12.0), (4, 20.0), (5, 6.0)):
            d.nv_host_set_global(h, g, v)
            got = d.nv_host_global(h, g)
            if got != v:
                print("   global %d: set %g, read %g" % (g, v, got))
                bad += 1
        print("globals: %s" % ("read back as set" if not bad else "NOT AS SET"))
    if case == "master":
        was = d.nv_host_global(h, 0)
        d.nv_host_set_global(h, 0, was - 6.0)
        print("master: %g dB -> %g dB" % (was, was - 6.0))
    nfile = int(6.0 * 48000) // 128
    panic_at = int(3.0 * sr) // blk if case == "panic" else None     # (under the note held 2.5-4.5 s)
    ne, e = d.nv_midi_n_events(m), 0
    iv = (ci * 4)()
    t = ctypes.c_double()
    xb = ctypes.create_string_buffer(65536)
    out = np.zeros((nfile * blk, 2), np.float32)
    for b in range(nfile):
        while e < ne:
            d.nv_midi_event(m, e, iv, ctypes.byref(t))
            if int(t.value * sr) // blk > b:
                break
            sx = b""
            if iv[0] == 6:
                xn = d.nv_midi_sysex(m, iv[2], xb, 65536)
                sx = xb.raw[:xn]
            by = encode(list(iv), sx)
            d.nv_host_midi(h, by, len(by))
            e += 1
        if panic_at is not None and b == panic_at:
            d.nv_host_panic(h)
        if panic_at is not None and b == panic_at + 2:
            d.nv_host_part.restype = vp
            d.nv_host_part.argtypes = [vp]
            S_ = N.Slab.__new__(N.Slab)
            S_.d, S_.cap, S_.p = d, 65536, d.nv_part_slab(d.nv_host_part(h))
            busy_, noff_, non_ = S_.col("busy"), S_.col("noff"), S_.col("non")
            # (released: its key-up set -- n0 + its own release delay, which may
            # be past this block; unreleased: still IDLE) -- of the notes begun
            # before it (the file strikes on: lv000 has a chord at 2.0 s, the
            # panic's own block)
            n_panic = (nsil + panic_at) * blk
            held_ = int(((busy_ != 0) & (noff_ >= (1 << 62)) & (non_ < n_panic)).sum())
            print("panic: %d slots sounding, %d unreleased a block after it" % (int((busy_ != 0).sum()), held_))
            bad += held_ != 0
        d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
        out[b * blk:(b + 1) * blk, 0] = L
        out[b * blk:(b + 1) * blk, 1] = R
    np.save(outp, out)
    print("BAD %d" % bad)
    sys.stdout.flush()
    os._exit(0)                 # (the host's threads run to the end: not joined)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = dict((a[2:].split("=") + [""])[:2] for a in sys.argv[1:] if a.startswith("--"))
    if "child" in opt:
        child(args[0], args[1], opt["child"], int(opt["program"]), int(opt.get("nsil", 0)), args[2])
    import bitident as BI
    import native as N
    prog = int(opt.get("program", 81))
    tmp = tempfile.mkdtemp(prefix="hostapi")
    bad = 0
    try:
        mid = os.path.join(tmp, "in.mid")
        BI.excerpt(args[0], 6.0).save(mid)
        from nvlive_check import live_export
        nvx = live_export(tmp, "hall")
        N.lib()
        N.build_nvlive()

        def run(case, nsil=0):
            o = os.path.join(tmp, case + ".npy")
            r = subprocess.run([sys.executable, os.path.abspath(__file__), nvx, mid, o, "--child=" + case,
                                "--program=%d" % prog, "--nsil=%d" % nsil], capture_output=True, text=True)
            lines = r.stdout.splitlines()
            for ln in lines:
                if not ln.startswith(("NSIL", "BAD")):
                    print(ln)
            info = dict(ln.split(" ", 1) for ln in lines if ln.startswith(("NSIL", "BAD")))
            if r.returncode or "BAD" not in info:
                print("%s: the child failed (%d): %s" % (case, r.returncode, r.stderr.strip().splitlines()[-1:]))
                return None, 1, 0
            return np.load(o), int(info["BAD"]), int(info.get("NSIL", nsil))

        a, b1, nsil = run("pick")
        start, b2, _ = run("start", nsil)
        pc, b6, _ = run("progchg")
        bad += b1 + b2 + b6
        if a is not None and pc is not None:
            dd = np.flatnonzero(np.any(a != pc, 1))
            print("the pick against a program change: %s" % ("identical" if not len(dd) else
                  "%d frames differ from block %d" % (len(dd), int(dd[0]) // 128)))
            bad += len(dd) > 0
        if a is not None and start is not None:
            same = a.tobytes() == start.tobytes()
            dd = np.flatnonzero(np.any(a != start, 1))
            print("the pick against the start: peak %.4f, %s" % (float(np.abs(a).max()), "identical" if same else
                  "%d samples differ from block %d (max %.3g)" % (int((a != start).sum()), int(dd[0]) // 128,
                                                                 float(np.abs(a - start).max()))))
        _, b3, _ = run("globals", nsil)
        bad += b3
        c, b4, _ = run("master", nsil)
        bad += b4
        if c is not None and start is not None:
            r = float(np.abs(c).max()) / max(float(np.abs(start).max()), 1e-12)
            print("the master -6 dB: the peak x%.3f (10^(-6/20) = 0.501)" % r)
            bad += not (0.45 < r < 0.53)
        p, b5, _ = run("panic", nsil)
        bad += b5
    finally:
        shutil.rmtree(tmp, True)
    print("%d failed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
