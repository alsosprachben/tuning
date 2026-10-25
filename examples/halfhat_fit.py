#!/usr/bin/env python3
"""Fit the half-open hats (Cymbal & Claps 49-50; percussion_gs.RING) to
DRSKit's semi-open hat (CC-BY 4.0, measured only; ~/Documents/refs/drums/
drskit_more, sources.md) AGAINST ITS OWN OPEN HAT -- the difference, applied
to ours (fitted to Iowa), not DRSKit's absolute ring.

    halfhat_fit.py           DRSKit's and our hats' falls, and the rings fitted
    halfhat_fit.py --write   ...into percussion_gs.RING

THE FALL: dB/s over 0.05-0.8 s after the peak, at 4 and 8 kHz (the hats'
top, where they speak), on the hat's close microphone; DRSKit's strokes in
the middle of each instrument's range by level. The semi-open falls about
twice as fast as the open hat (4 kHz: 27 dB down by 0.8 s against 12).
HALF-OPEN 1 is DRSKit's semi-open; Roland's 2 more open, halfway (in log)
to the open hat. Each ring bisected until our half-open's fall over our open
hat's is the target ratio.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

REFS = os.path.expanduser("~/Documents/refs/drums/drskit_more")
BANDS = ((4000, 8000), (8000, 16000))
T0, T1 = 0.05, 0.8


def fall(h, sr):
    from scipy.signal import butter, sosfilt
    k = int(np.argmax(np.abs(h)))
    r = []
    for lo, hi in BANDS:
        b = sosfilt(butter(4, [lo, min(hi, 0.45 * sr)], "bp", fs=sr, output="sos"), h)
        w = int(0.01 * sr)
        e = 10 * np.log10(np.convolve(b * b, np.ones(w) / w, "same") + 1e-20)
        r.append((e[k + int(T0 * sr)] - e[k + int(T1 * sr)]) / (T1 - T0))
    return float(np.mean(r))


def drskit(inst):
    from scipy.io import wavfile
    P = []
    for f in glob.glob(os.path.join(REFS, "*-%s.wav" % inst)):
        sr, x = wavfile.read(f)
        h = x[:, 2].astype(np.float64)          # the hi-hat's close microphone
        k = int(np.argmax(np.abs(h)))
        P.append((10 * np.log10(np.mean(h[k:k + int(0.05 * sr)] ** 2)), fall(h, sr)))
    P.sort()
    mid = P[len(P) // 2 - 2:len(P) // 2 + 2]
    return float(np.mean([p[1] for p in mid]))


def ours(kit, note):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    t.append(mido.Message("program_change", channel=9, program=kit, time=0))
    t.append(mido.Message("note_on", channel=9, note=note, velocity=100, time=240))
    t.append(mido.Message("note_off", channel=9, note=note, velocity=0, time=1920))
    L, R = B.render(m)[:2]
    return fall(0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR)


def with_ring(name, ring):
    import percussion_gs as G
    import percussion_map as P
    G.RING[name] = ring
    key = {"Half-Open Hi-Hat 1": 49, "Half-Open Hi-Hat 2": 50}[name]
    P.KIT_RING[53][key] = ring
    P._RING_CLASSES.clear()
    return ours(53, key)


def main(argv):
    semi, opn = drskit("Hihat_semi_open"), drskit("Hihat_open")
    print("  DRSKit: semi-open falls %.1f dB/s, open %.1f (ratio %.2f)" % (semi, opn, semi / opn))
    o46 = ours(0, 46)
    print("  ours: open hat falls %.1f dB/s" % o46)
    fit = {}
    for name, ratio in (("Half-Open Hi-Hat 1", semi / opn), ("Half-Open Hi-Hat 2", (semi / opn) ** 0.5)):
        want = o46 * ratio
        lo, hi = 0.01, 0.23 * 4
        for _ in range(12):
            mid = (lo * hi) ** 0.5
            f = with_ring(name, mid)
            lo, hi = (lo, mid) if f < want else (mid, hi)
        fit[name] = round((lo * hi) ** 0.5, 4)
        print("  %s: want %.1f dB/s (x%.2f), ring %.4f -> %.1f" % (name, want, ratio, fit[name], with_ring(name, fit[name])))
    if "--write" in argv:
        p = os.path.join(HERE, "percussion_gs.py")
        s = open(p).read()
        s = re.sub(r"(?m)^RING = \{'Half-Open.*\}$", "RING = %r" % (fit,), s)
        open(p, "w").write(s)
        print("  wrote percussion_gs.RING")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
