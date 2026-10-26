#!/usr/bin/env python3
"""Fit an Asia-set voice to recordings of the instrument: its COLOUR (octave
bands over the first 50 ms, re the strongest) and its LENGTH (the time to
fall 40 dB) -- a class on a set's key, refitted until ours reads as the
takes do.

    asia_fit.py VOICE            the takes against ours
    asia_fit.py VOICE --fit      the class's band_trim_db (and its ring) toward them

VOICE (the key it is fitted on; the takes, sources.md):
  naobo   Asia 87 Nao Bo -- the Beijing opera cymbals (Beijing Opera Percussion
          Instrument Dataset, CC BY 4.0, measured only): our china cymbal
          refitted (tonelib.RfxNaoboProperties), its ring percussion_gs.RING
  bangu   Asia 77 Ban Gu -- the opera's small high drum, the same dataset: a
          TR-808 drum patch (tonelib.RfxBanguProperties); its length the
          patch's own, so only its colour is fitted

The colour fit is SHAPE only (the octaves' mean removed: the level is the
set's); the ring bisected on the -40 dB time.
"""
import glob
import os
import re
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

JINGJU = os.path.expanduser("~/Documents/refs/jingju_perc/raw/beijing_opera_percussion_instrument_1.0")
OCT = (125, 250, 500, 1000, 2000, 4000, 8000, 16000)
# voice: (takes glob, class, kit (program), key, the ring's name in RING or None)
VOICES = {
    "naobo": (os.path.join(JINGJU, "*__naobo-*.wav"), "RfxNaoboProperties", 52, 87, "Nao Bo"),
    "bangu": (os.path.join(JINGJU, "*__bangu-*.wav"), "RfxBanguProperties", 52, 77, None),
}


def measure(x, sr):
    k = int(np.argmax(np.abs(x)))
    y = x[k:]
    seg = y[:int(0.05 * sr)]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 15)) ** 2
    f = np.fft.rfftfreq(1 << 15, 1.0 / sr)
    c = np.array([10 * np.log10(S[(f >= lo) & (f < hi)].sum() + 1e-20) for lo, hi in zip(OCT[:-1], OCT[1:])])
    w = int(0.01 * sr)
    env = np.array([np.sqrt(np.mean(y[i:i + w] ** 2)) for i in range(0, len(y) - w, w)])
    db = 20 * np.log10(env / env.max() + 1e-12)
    a = np.flatnonzero(db < -40)
    return c - c.max(), (a[0] * 0.01 if len(a) else len(y) / sr)


def takes(v):
    from scipy.io import wavfile
    out = []
    for f in sorted(glob.glob(VOICES[v][0])):
        sr, x = wavfile.read(f)
        x = x.astype(np.float64)
        out.append(measure(x.mean(1) if x.ndim > 1 else x, sr))
    return np.median([o[0] for o in out], 0), float(np.median([o[1] for o in out]))


def ours(v):
    import mido
    import blockrender as B
    import percussion_map as P
    P._RING_CLASSES.clear()
    _g, _c, kit, key, _r = VOICES[v]
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    t.append(mido.Message("program_change", channel=9, program=kit, time=0))
    t.append(mido.Message("note_on", channel=9, note=key, velocity=100, time=240))
    t.append(mido.Message("note_off", channel=9, note=key, velocity=0, time=240))
    t.append(mido.MetaMessage("end_of_track", time=960 * 10))
    L, R = B.render(m)[:2]
    return measure(0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR)


def show(label, c, t40):
    print("  %-8s %s   -40 dB at %.2f s" % (label, " ".join("%d:%+5.1f" % (o, v) for o, v in zip(OCT, c)), t40))


def fit(v, passes=4):
    import percussion_gs as G
    import percussion_map as P
    import tonelib
    _g, cname, kit, key, ringname = VOICES[v]
    cls = getattr(tonelib, cname)
    want, wt = takes(v)
    show("takes", want, wt)
    cen = [np.sqrt(a * b) for a, b in zip(OCT[:-1], OCT[1:])]
    for n in range(passes + 1):
        c, t40 = ours(v)
        err = (want - c) - np.mean(want - c)
        print("  pass %d: colour rms %.1f dB" % (n, np.sqrt(np.mean(err ** 2))), end="")
        show("", c, t40)
        if n == passes:
            break
        bt = getattr(cls, 'band_trim_db', ()) or ()
        base = [np.interp(np.log(h), np.log([p[0] for p in bt]), [p[1] for p in bt]) if bt else 0.0
                for h in cen]
        cls.band_trim_db = tuple((int(round(h)), round(float(b + e), 1)) for h, b, e in zip(cen, base, err))
        if ringname:
            r = G.RING[ringname] * (wt / t40) ** 0.8
            G.RING[ringname] = round(r, 3)
            P.KIT_RING[kit][key] = G.RING[ringname]
    path = os.path.join(HERE, "tonelib.py")
    body = open(path).read()
    i = body.index("class %s(" % cname)
    j = i + re.search(r"\n(?=\S)", body[i + 10:]).start() + 10
    blk = body[i:j]
    line = "    band_trim_db = %s" % (cls.band_trim_db,)
    blk = (re.sub(r"(?m)^    band_trim_db = .*$", lambda _: line, blk) if "band_trim_db" in blk
           else blk.rstrip("\n") + "\n" + line + "\n\n")
    open(path, "w").write(body[:i] + blk + body[j:])
    print(line)
    if ringname:
        p = os.path.join(HERE, "percussion_gs.py")
        s = open(p).read()
        s = re.sub(r"(?m)^RING\['%s'\] = .*$" % re.escape(ringname), "RING['%s'] = %r" % (ringname, G.RING[ringname]), s)
        open(p, "w").write(s)
        print("    RING['%s'] = %r" % (ringname, G.RING[ringname]))


def main(argv):
    v = argv[1]
    if "--fit" in argv:
        fit(v)
        return 0
    show("takes", *takes(v))
    show("ours", *ours(v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
