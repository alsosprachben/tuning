#!/usr/bin/env python3
"""The SFX set's electronic clicks (39 High Q, 44 Square Click) fitted to
GeneralUser GS's samples of them, on the TR-808 engine.

    python3 -I examples/sfx808_fit.py                  score each against its sample
    python3 -I examples/sfx808_fit.py --fit=highq[,square] [--write]

The High Q's sweep is fitted to GU's own track (fit_sweep): 4.5 octaves in
45 ms outruns the 808 fit's 20 ms pitch windows, which settled it at 436 Hz.

These are Roland's own synthesized sounds, so there is no recording of an
instrument to find: the reference is the sample itself, and the instrument
a synth voice. The 808's resonator with its bend IS a filter snapping shut
(a sine swept down exponentially in pitch); its click alone is a square
pulse. The fit and its score are examples/tr808_fit.py's (a time-frequency
picture, the hit's balance, the resonator's pitch track), pointed at the SFX
set and at GU's samples: the High Q as timidity plays it on its key (it
plays this one right), the Square Click read from the SF2 (130 samples, no
key tracking).
"""
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

import tr808_fit as F          # noqa: E402  (sets elkit_fit's KIT to 25: re-set below)
import elkit_fit as E          # noqa: E402

F.KIT = E.KIT = 56
GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
F.KNOBS = {
    "highq": (39, "SfxHighQProperties", (
        ("decay_s", True, 0.3), ("bend_oct", False, 0.5), ("bend_ms", True, 0.3),
        ("h2_db", False, 6.0), ("h3_db", False, 6.0), ("click_db", False, 6.0),
        ("click_dbs", True, 0.4))),
    "square": (44, "SfxSquareClickProperties", (
        ("click_db", False, 6.0), ("click_dbs", True, 0.4), ("click_tilt", False, 2.0),
        ("click_hp_hz", True, 0.4), ("click_lp_hz", True, 0.4))),
}
F.HITS = {39: "GU39", 44: "GU44"}


def sf2_sample(name):
    """A sample's frames from GU's SF2 (shdr/smpl), as floats."""
    import struct
    d = open(GU, "rb").read()
    top, o = {}, 12
    while o < len(d):
        cid, n = d[o:o + 4], struct.unpack("<I", d[o + 4:o + 8])[0]
        if cid == b"LIST":
            p = o + 12
            while p < o + 8 + n:
                c2, n2 = d[p:p + 4], struct.unpack("<I", d[p + 4:p + 8])[0]
                top[c2] = (p + 8, n2)
                p += 8 + n2 + (n2 & 1)
        o += 8 + n + (n & 1)
    so, ho, hn = top[b"smpl"][0], *top[b"shdr"]
    for i in range(hn // 46):
        nm, s0, s1 = struct.unpack("<20sII", d[ho + 46 * i:ho + 46 * i + 28])
        if nm.split(b"\0")[0].decode(errors="replace") == name:
            return np.frombuffer(d[so + 2 * s0:so + 2 * s1], "<i2").astype(np.float64) / 32768.0
    raise KeyError(name)


_HIT = {}


def hit(name):
    if name not in _HIT:
        if name == "GU44":
            x = sf2_sample("Square Click")
            _HIT[name] = (np.concatenate((np.zeros(441), x, np.zeros(44100))), 44100)
        else:
            with tempfile.TemporaryDirectory() as d:
                x, sr = E.theirs(GU, int(name[2:]), d)
            _HIT[name] = (np.asarray(x, np.float64), sr)
    return _HIT[name]


F.hit = hit
# the High Q's track reaches its start, 3.2 kHz (the 808's ceiling is 1.5 kHz)
_fmax = F.fmax
F.fmax = lambda cls: 5000.0 if cls.__name__.startswith("SfxHighQ") else _fmax(cls)


def sweep_track(x, sr, span=0.045):
    """ln Hz every 1.45 ms over the first SPAN from the onset (128-sample
    frames, peak bin), and the level (dB rms): a fast sweep's track, which
    the 808 fit's 20 ms windows cannot follow."""
    x = np.asarray(x, np.float64)
    x = x[int(np.argmax(np.abs(x) > np.abs(x).max() * 0.05)):]
    f = np.fft.rfftfreq(8192, 1.0 / sr)
    out = []
    for i in range(0, int(span * sr), 64):
        seg = x[i:i + 128]
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 8192))
        out.append((np.log(max(f[np.argmax(X)], 20.0)), 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)))
    return np.array(out)


def fit_sweep(d, maxfev=60):
    """THE HIGH Q'S SWEEP, fitted to GU's track directly: its depth and time
    (the bend as the kernel plays it -- a mean frequency a 512-sample block,
    from the note's own start), the ring's decay against the level."""
    from scipy.optimize import minimize
    import tonelib as T
    import percussion_map as P
    cls = T.SfxHighQProperties
    y, sr = hit("GU39")
    ref = sweep_track(y, sr)

    def f(v):
        cls.tr808 = dict(cls.tr808, bend_oct=float(v[0]), bend_ms=float(np.exp(v[1])),
                         decay_s=float(np.exp(v[2])))
        T.tr808_refresh(cls)
        P._RING_CLASSES.clear()
        got = sweep_track(E.ours(39, d)[0], sr)
        n = min(len(got), len(ref))
        e = (np.sqrt(np.mean(((got[:n, 0] - ref[:n, 0]) * 1200 / np.log(2) / 100) ** 2))
             + 0.5 * np.sqrt(np.mean(((got[:n, 1] - got[:n, 1].max()) - (ref[:n, 1] - ref[:n, 1].max())) ** 2)))
        return e
    p = cls.tr808_patch
    x0 = np.array([p["bend_oct"], np.log(p["bend_ms"]), np.log(p["decay_s"])])
    s0 = f(x0)
    r = minimize(f, x0, method="Nelder-Mead", options=dict(maxfev=maxfev, xatol=0.01, fatol=0.05,
                 initial_simplex=np.vstack([x0, x0 + [0.7, 0, 0], x0 + [0, 0.4, 0], x0 + [0, 0, 0.4]])))
    f(r.x)
    print("FITTED the High Q's sweep: %.2f -> %.2f (semitones rms + level/2)" % (s0, r.fun))
    F.fit.done.append(("SfxHighQProperties", dict(cls.tr808)))


def main(argv):
    with tempfile.TemporaryDirectory() as d:
        fits = next((a.split("=")[1].split(",") for a in argv if a.startswith("--fit=")), None)
        for v in fits or ():
            if v == "highq":
                fit_sweep(d)
            else:
                F.fit(v, d)
        if fits and "--write" in argv:
            for cls_name, patch in F.fit.done:
                F.write(cls_name, patch)
        F.report(d, notes=[39, 44])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
