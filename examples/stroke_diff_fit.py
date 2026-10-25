#!/usr/bin/env python3
"""Fit a STROKE as a difference from one we have, to DRSKit's two strokes
of one instrument (CC-BY 4.0, measured only; ~/Documents/refs/drums,
sources.md), matched in level -- applied to our voice, not DRSKit's absolute
colour:

  edge    the ride's shank on the edge against its tip on the bow
          (tonelib.RideEdgeProperties; Cymbal & Claps 84-86 against 81-83,
          our ride Iowa's stick on the bow)
  brush   the crash with brushes against the stick's shank
          (tonelib.BrushCrashProperties; Cymbal & Claps 64 against 61, our
          Crash 1 fitted to that very crash)

    stroke_diff_fit.py VARIANT           the difference, DRSKit's and ours
    stroke_diff_fit.py VARIANT --fit     the class's band_trim_db toward it

THE COLOUR: octave bands at the variant's moment after the peak, on its
microphone; DRSKit's strokes paired across the two by level (within 2 dB).
The trim reaches the modes, not the wash, so it is refitted on our render,
the octaves' mean removed.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

REFS = os.path.expanduser("~/Documents/refs/drums")
OCT = (250, 500, 1000, 2000, 4000, 8000, 16000)
# variant: (DRSKit's stroke we have, the new one (globs under REFS), its
# microphones (DRSKit's 13 channels), the moment s, our class, kit, our
# note for each)
VARIANTS = {
    "edge": ("drskit_more/*-Ride_tip.wav", "drskit_more/*-Ride_shank.wav", (7,), 0.03,
             "RideEdgeProperties", 53, 82, 85),
    "brush": ("drskit/Crash_left_shank/*.wav", "drskit_more/*-Crash_left_whisker.wav", (5, 6), 0.05,
              "BrushCrashProperties", 53, 61, 64),
}
V = None


def colour(h, sr):
    from scipy.signal import butter, sosfilt
    t = V[3]
    k = int(np.argmax(np.abs(h)))
    c = []
    for lo, hi in zip(OCT[:-1], OCT[1:]):
        b = sosfilt(butter(4, [lo, min(hi, 0.45 * sr)], "bp", fs=sr, output="sos"), h)
        w = int(0.02 * sr)
        e = 10 * np.log10(np.convolve(b * b, np.ones(w) / w, "same") + 1e-20)
        c.append(e[k + int(t * sr)])
    return np.array(c)


def drskit():
    from scipy.io import wavfile

    def strokes(pat):
        out = []
        for f in glob.glob(os.path.join(REFS, pat)):
            sr, x = wavfile.read(f)
            h = x[:, list(V[2])].sum(1).astype(np.float64)
            k = int(np.argmax(np.abs(h)))
            out.append((10 * np.log10(np.mean(h[k:k + int(0.05 * sr)] ** 2)), colour(h, sr)))
        return out
    T, S = strokes(V[0]), strokes(V[1])
    d = []
    for ls, cs in S:
        lt, ct = min(T, key=lambda t: abs(t[0] - ls))
        if abs(lt - ls) < 2.0:
            d.append(cs - ct)
    d = np.mean(d, 0)
    return d - d.mean()


def ours():
    import mido
    import blockrender as B
    import percussion_map as P
    P._RING_CLASSES.clear()
    c = {}
    for note in (V[6], V[7]):
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
        t.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
        t.append(mido.Message("program_change", channel=9, program=V[5], time=0))
        t.append(mido.Message("note_on", channel=9, note=note, velocity=100, time=240))
        t.append(mido.Message("note_off", channel=9, note=note, velocity=0, time=960))
        L, R = B.render(m)[:2]
        c[note] = colour(0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR)
    d = c[V[7]] - c[V[6]]
    return d - d.mean()


def show(label, d):
    print("  %-8s " % label + " ".join("%d:%+5.1f" % (o, v) for o, v in zip(OCT, d)))


def fit(passes=4):
    import tonelib
    cls = getattr(tonelib, V[4])
    want = drskit()
    show("DRSKit", want)
    for n in range(passes + 1):
        got = ours()
        err = want - got
        print("  pass %d: rms %.1f dB" % (n, np.sqrt(np.mean(err ** 2))), flush=True)
        show("ours", got)
        if n == passes:
            break
        cen = [np.sqrt(a * b) for a, b in zip(OCT[:-1], OCT[1:])]
        cur = dict(cls.band_trim_db)
        pts = []
        for hz, e in zip(cen, err):
            base = np.interp(np.log(hz), np.log([p[0] for p in cls.band_trim_db]), [p[1] for p in cls.band_trim_db])
            pts.append((int(round(hz)), round(float(base + e), 1)))
        cls.band_trim_db = tuple(pts)
    path = os.path.join(HERE, "tonelib.py")
    body = open(path).read()
    i = body.index("class %s(" % V[4])
    j = i + re.search(r"\n(?=\S)", body[i + 10:]).start() + 10
    blk = re.sub(r"(?m)^    band_trim_db = \(.*\)$", lambda _: "    band_trim_db = %s" % (cls.band_trim_db,), body[i:j])
    open(path, "w").write(body[:i] + blk + body[j:])
    print("    band_trim_db = %s" % (cls.band_trim_db,))


def main(argv):
    global V
    V = VARIANTS[argv[1]]
    if "--fit" in argv:
        fit()
        return 0
    show("DRSKit", drskit())
    show("ours", ours())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
