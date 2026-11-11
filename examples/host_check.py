"""THE HOST AS A LIBRARY against nvlive: a file played through host.h's C API
(nv_host_open_args, nv_host_start, nv_host_midi, nv_host_render) in this
process, through ctypes, and through nvlive --test -- bit for bit.

Each block's events are read with the engine's own reader (nv_midi_*, as
nvlive --test reads them) and handed to nv_host_midi as the bytes a keyboard
would send, before that block renders: the library's parser, queue and
render_block, live's own path, where --test goes in step. The register in
step (--reg-sync), the CPU, no drums beside, as nvlive_check's defaults.
A file that changes program or room is not this check's (the builder runs
on its own thread here).

    python3 examples/host_check.py FILE.mid [SECONDS] [--program=N]
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


def encode(iv, sysex):
    """a reader's event as the bytes a keyboard sends"""
    t, ch, a, b = iv
    if t == 0:
        return bytes([0x90 | ch, a, b])
    if t == 1:
        return bytes([0x80 | ch, a, 0])
    if t == 2:
        return bytes([0xB0 | ch, a, b])
    if t == 3:
        return bytes([0xD0 | ch, a])
    if t == 4:
        v = a + 8192
        return bytes([0xE0 | ch, v & 127, v >> 7])
    if t == 5:
        return bytes([0xC0 | ch, a])
    if t == 7:
        return bytes([0xA0 | ch, a, b])
    if t == 6:
        return b"\xF0" + sysex + b"\xF7"
    return b""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = dict((a[2:].split("=") + [""])[:2] for a in sys.argv[1:] if a.startswith("--"))
    import bitident as BI
    import native as N
    prog = int(opt.get("program", 0))
    secs = float(args[1]) if len(args) > 1 else 10.0
    tmp = tempfile.mkdtemp(prefix="hostcheck")
    try:
        mid = os.path.join(tmp, "in.mid")
        BI.excerpt(args[0], secs).save(mid)
        from nvlive_check import live_export
        nvx = live_export(tmp, "hall")
        exe = N.build_nvlive()
        d = N.lib()
        d.nv_midi_read.restype = ctypes.c_void_p
        d.nv_midi_read.argtypes = [ctypes.c_char_p, ctypes.c_longlong, ctypes.POINTER(ctypes.c_int)]
        d.nv_midi_total.restype = ctypes.c_double
        d.nv_midi_total.argtypes = [ctypes.c_void_p]
        d.nv_midi_n_events.argtypes = [ctypes.c_void_p]
        d.nv_midi_event.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int),
                                    ctypes.POINTER(ctypes.c_double)]
        d.nv_midi_sysex.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        d.nv_midi_banked.argtypes = [ctypes.c_void_p]
        raw = open(mid, "rb").read()
        err = ctypes.c_int(0)
        m = d.nv_midi_read(raw, len(raw), ctypes.byref(err))
        if not m:
            print("refused: the reader (%d)" % err.value)
            return 2
        total = d.nv_midi_total(m) + 3.0
        common = ["--program=%d" % prog, "--cpu", "--no-pipeline", "--no-register", "--no-drums"]
        # ---- nvlive --test
        out = os.path.join(tmp, "nv.wav")
        subprocess.check_call([exe, nvx, "--test", mid, out, "--seconds=%r" % total] + common,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(out, "rb") as f:
            want = np.frombuffer(f.read()[44:], dtype=np.float32)
        # ---- the library, in this process
        d.nv_host_open_args.restype = ctypes.c_void_p
        d.nv_host_open_args.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_int]
        for f_ in ("nv_host_start", "nv_host_close"):
            getattr(d, f_).argtypes = [ctypes.c_void_p]
        d.nv_host_block.argtypes = [ctypes.c_void_p]
        d.nv_host_rate.argtypes = [ctypes.c_void_p]
        d.nv_host_render.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        d.nv_host_midi.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        # (the governor off, as --test runs: a block driven from here is slow)
        av = [b"nvlive", nvx.encode()] + [a.encode() for a in common + ["--reg-sync", "--no-governor"]]
        argv = (ctypes.c_char_p * len(av))(*av)
        eb = ctypes.create_string_buffer(256)
        h = d.nv_host_open_args(len(av), argv, eb, 256)
        if not h:
            print("the host refused: %s" % eb.value.decode())
            return 1
        d.nv_host_start(h)
        blk, sr = d.nv_host_block(h), d.nv_host_rate(h)
        nb = int(total * sr) // blk
        L = np.zeros(blk, np.float32)
        R = np.zeros(blk, np.float32)
        got = np.zeros(2 * blk * nb, np.float32)
        ne, e = d.nv_midi_n_events(m), 0
        iv = (ctypes.c_int * 4)()
        t = ctypes.c_double()
        xb = ctypes.create_string_buffer(65536)
        sent = 0
        for b in range(nb):
            while e < ne:
                d.nv_midi_event(m, e, iv, ctypes.byref(t))
                if int(t.value * sr) // blk > b:
                    break
                sx = b""
                if iv[0] == 6:
                    xn = d.nv_midi_sysex(m, iv[2], xb, 65536)
                    sx = xb.raw[:xn] if 0 < xn <= 65536 else None
                if sx is not None:
                    by = encode(list(iv), sx)
                    d.nv_host_midi(h, by, len(by))
                    sent += 1
                e += 1
            if d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk):
                print("nv_host_render refused the block")
                return 1
            got[2 * blk * b:2 * blk * (b + 1):2] = L
            got[2 * blk * b + 1:2 * blk * (b + 1):2] = R
        d.nv_host_close(h)
        n = min(len(want), len(got))
        diff = np.nonzero(want[:n].view(np.uint32) != got[:n].view(np.uint32))[0]
        name = os.path.basename(args[0])
        if len(want) == len(got) and not len(diff):
            print("%s (%g s, program %d): %d blocks, %d events through nv_host_midi, peak %.4f, identical"
                  % (name, secs, prog, nb, sent, float(np.abs(got).max())))
            return 0
        first = diff[0] // (2 * blk) if len(diff) else -1
        print("%s: %d vs %d samples, %d differ from block %d (max %.3g)"
              % (name, len(want), len(got), len(diff), first,
                 float(np.abs(want[:n] - got[:n]).max()) if len(diff) else 0.0))
        return 1
    finally:
        shutil.rmtree(tmp, True)


if __name__ == "__main__":
    sys.exit(main())
