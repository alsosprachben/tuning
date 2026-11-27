"""THE SEQUENCER's TIMING (native/eucseq.h, slab.cpp's seq_tick), through the
host library (ctypes, in step: no device, the blocks as fast as they go):

- STRAIGHT: one lane, E(4,16) at 120 bpm, sixteenths -- its notes 0.5 s
  apart to the sample (24000 at 48 kHz: not a whole number of 128-sample
  blocks, so a note placed at its block's start would show 23936/24064);
- SWING: every step struck, swing 66 -- each pair's second step late by
  (2*0.66 - 1) of a step, the gaps alternating 1.32 and 0.68 of a step;
- E(3,8): the lane's notes where Bjorklund puts them (steps 0, 3, 6);
- THE METRONOME's CLOCK: clicking alone, then the sequencer started (empty
  lanes: its clock the click's), then stopped -- every click a beat apart
  throughout, no beat lost or doubled at either change (a click is a noise
  burst: placed to ~25 samples, as the metronome alone measures).

Onsets are read from the output: the first sample over a threshold after a
quiet stretch. A piano (program 0) plays the lanes: its attack is sharp, and
each note is let go at the lane's next step.

    python3 examples/seq_check.py EXPORT.nvx
"""
import ctypes
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

LEAD = 1200


def onsets(x, mingap):
    """the notes' starts: coarse from the envelope's rises (hop 32), then each
    placed to the sample by its attack's correlation with the first's (the
    same note struck the same way: the same waveform, so the lag is exact)"""
    hop, win = 32, 128
    n = (len(x) - win) // hop
    env = np.array([np.sqrt(np.mean(x[i * hop:i * hop + win] ** 2)) for i in range(n)])
    rise = np.zeros(n)
    rise[4:] = env[4:] - env[:-4]
    thr = 0.3 * rise.max()
    coarse, last = [], -10 ** 9
    for i in range(n):
        if rise[i] > thr and i * hop - last > mingap and rise[i] >= rise[max(0, i - 8):i + 9].max():
            coarse.append(i * hop)
            last = i * hop
    if not coarse:
        return []
    T0 = coarse[0] - 512
    tpl = x[max(0, T0):T0 + 2048]
    out = []
    for c in coarse:
        best, at = -1e30, c
        for lag in range(-700, 701):
            s0 = c - 512 + lag
            if s0 < 0 or s0 + len(tpl) > len(x):
                continue
            v = float(np.dot(x[s0:s0 + len(tpl)], tpl))
            if v > best:
                best, at = v, s0 + 512
        out.append(at)
    return out


def clicks(x):
    """the metronome's clicks: where each leaves the floor the last one's tail left"""
    a = np.abs(x)
    out, last = [], -10 ** 9
    for j in np.flatnonzero(a > 0.02):
        if j - last > 12000:
            fl = np.sqrt(np.mean(x[max(0, j - 3000):max(1, j - 800)] ** 2)) + 1e-9
            w = np.flatnonzero(a[max(0, j - 400):j + 1] > 8 * fl)
            out.append(max(0, j - 400) + int(w[0]) if len(w) else int(j))
        last = j
    return out


def main(argv):
    nvx = argv[1]
    import native as N
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    for f, a in (("nv_host_start", [vp]), ("nv_host_block", [vp]), ("nv_host_rate", [vp]),
                 ("nv_host_render", [vp, vp, vp, ci]), ("nv_host_set_global", [vp, ci, ctypes.c_double])):
        getattr(d, f).argtypes = a
    d.nv_ui_watch_new.restype = vp
    d.nv_ui_call.restype = ctypes.c_void_p
    d.nv_ui_call.argtypes = [vp, vp, cp]
    d.nv_ui_free.argtypes = [vp]
    av = [b"nvlive", nvx.encode(), b"--program=0", b"--cpu", b"--no-pipeline", b"--no-register",
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
        for _ in range(int(sec * sr) // blk):
            d.nv_host_render(h, L.ctypes.data, R.ctypes.data, blk)
            out.append(L + R)
        return np.concatenate(out)

    def lanes(*spec):          # (lane: key, steps, hits, rot; the rest emptied)
        for i in range(8):
            k, n, kk, r = spec[i] if i < len(spec) else (-1, 16, 0, 0)
            for f, v in (("key", k), ("steps", n), ("hits", kk), ("rot", r), ("mute", 0), ("accent", 0), ("vel", 100)):
                call({"call": "seq_set", "lane": i, "f": f, "v": v})

    render(LEAD * blk / sr)
    bad = 0
    step = sr * 60.0 / (120 * 4)
    print("rate %d, block %d, a step %.1f samples" % (sr, blk, step))

    def case(name, want_gaps, sec, tol=2):
        nonlocal bad
        r0 = call({"call": "seq_run", "on": 1, "ch": 0})
        x = render(sec)
        r1 = call({"call": "seq_run", "on": 0})
        if os.environ.get("SEQ_DEBUG"):
            print(name, "peak %.4f" % np.abs(x).max(), "run:", json.dumps(r0)[:300], "pos then:", r1.get("seq_pos"))
        render(1.5)
        on = onsets(x, int(0.6 * min(want_gaps)))
        g = np.diff(on)
        n = min(len(g), 3 * len(want_gaps))
        want = np.array([want_gaps[i % len(want_gaps)] for i in range(n)])
        err = np.abs(g[:n] - want) if n else np.array([1e9])
        ok = n >= len(want_gaps) and err.max() <= tol
        bad += not ok
        print("%-9s gaps %s  want %s  worst %.1f samples  %s" % (
            name, list(g[:n]), [round(v, 1) for v in want_gaps], err.max(), "ok" if ok else "WRONG"))

    call({"call": "seq_set", "lane": -1, "f": "bpm", "v": 120})
    call({"call": "seq_set", "lane": -1, "f": "spb", "v": 4})
    call({"call": "seq_set", "lane": -1, "f": "swing", "v": 50})
    lanes((60, 16, 4, 0))
    case("straight", [4 * step], 3.2)
    # (swing: one lane on the beats -- even steps, straight -- one a step after them, odd: late)
    lanes((60, 16, 4, 0), (60, 16, 4, 1))
    call({"call": "seq_set", "lane": -1, "f": "bpm", "v": 60})
    step = sr * 60.0 / (60 * 4)
    call({"call": "seq_set", "lane": -1, "f": "swing", "v": 66})
    sw = (2 * 0.66 - 1) * step
    case("swing", [step + sw, 3 * step - sw], 4.2)
    call({"call": "seq_set", "lane": -1, "f": "swing", "v": 50})
    lanes((60, 8, 3, 0))
    case("E(3,8)", [3 * step, 3 * step, 2 * step], 6.2)

    # THE METRONOME: built, then clicking alone for 2 s, on the sequencer's clock (empty lanes)
    # for 2 s, alone again for 2 s -- a click every beat throughout, none lost or doubled at
    # either change. (Its click is a noise burst: placed to within ~25 samples, here as alone.)
    lanes()
    call({"call": "seq_set", "lane": -1, "f": "bpm", "v": 120})
    d.nv_host_set_global(h, 10, 120.0)
    for _ in range(60):                                             # (until its part is built and clicking)
        if np.abs(render(0.5)).max() > 0.01:
            break
    x = [render(2.0)]
    call({"call": "seq_run", "on": 1, "ch": 0})
    x.append(render(2.0))
    call({"call": "seq_run", "on": 0})
    x.append(render(2.0))
    x = np.concatenate(x)
    on = clicks(x)
    g = np.diff(on)
    beat = sr * 60.0 / 120
    err = np.abs(g - beat)
    ok = len(on) == 12 and err.max() <= 40
    bad += not ok
    print("metronome %d clicks in 6 s, gaps %s  want %.0f +-40  %s" % (len(on), list(g), beat, "ok" if ok else "WRONG"))
    print("FAILED %d" % bad if bad else "all ok")
    sys.stdout.flush()
    os._exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv)
