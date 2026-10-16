#!/usr/bin/env python3
"""The Room (program 8) and Power (16) sets' LIVE ROOM, against GeneralUser GS.

    python3 examples/roomset_fit.py              # score the room as it stands
    python3 examples/roomset_fit.py --search     # ...and at other sizes

Roland's Room set changes only the six toms (SC-55 p.70) and Power uses them
too. GeneralUser GS's are its Standard toms layered with "Room Tom" takes, so
what a Room tom adds over a Standard one is its ROOM's early sound; ours are
Standard's fitted toms in a small live room of their own (tonelib.LiveRoom).

THE MEASURE, per tom, as each set's tom differs from the Standard tom on the
same key, averaged over 41, 45 and 50:
  early   the energy 8-80 ms after the strike against its first 8 ms, dB:
          the early reflections against the direct sound
  top     2-8 kHz against 60-500 Hz over the first 300 ms, dB
GeneralUser's Room toms: +5.4 dB and +2.2 dB over its Standard toms.

WHAT DID NOT WORK, so it is not tried again: the hall's drum placed further
back (+1 dB at most: a tom's own ring fills its first 80 ms), and aimed at
the back wall (directivity_axis_deg 180: 6-7 dB darker, its direct sound
off axis). The live room's hard walls are what make it both roomier and
brighter.

Ours renders WITH THE ROOM -- its reflections are the point -- so this must
not run where TUNING_REFLECT=0 has been set (the fits elsewhere set it).
"""
import os
import sys
import tempfile
import warnings

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")

GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
TOMS = (41, 45, 50)
DIMS = ("room_left", "room_right", "room_front", "room_back", "room_ceiling")


def early(x, sr):
    x = np.asarray(x, float)
    if x.ndim > 1:
        x = x.mean(1)
    a = int(np.argmax(np.abs(x) > np.abs(x).max() * 0.02))
    e = lambda t0, t1: float(np.sum(x[a + int(t0 * sr):a + int(t1 * sr)] ** 2)) + 1e-20  # noqa: E731
    X = np.abs(np.fft.rfft(x[a:a + int(0.3 * sr)])) ** 2
    f = np.fft.rfftfreq(int(0.3 * sr), 1.0 / sr)
    return np.array([10 * np.log10(e(0.008, 0.08) / e(0.0, 0.008)),
                     10 * np.log10(X[(f > 2000) & (f < 8000)].sum() / X[(f > 60) & (f < 500)].sum())])


def gu_gain(d):
    import elkit_fit as E
    out = []
    for n in TOMS:
        E.KIT = 0
        a = early(*E.theirs(GU, n, d))
        E.KIT = 8
        out.append(early(*E.theirs(GU, n, d)) - a)
    return np.mean(out, 0)


def ours_gain(base):
    import blockrender as B
    import percussion_map as P
    from drumset_check import note_file
    P._RING_CLASSES.clear()
    out = []
    for n in TOMS:
        L, R = B.render(note_file(8, n, vel=100, hold=1.0))[:2]
        out.append(early(0.5 * (np.asarray(L, float) + np.asarray(R, float)), B.SR) - base[n])
    return np.mean(out, 0)


def main(argv):
    assert os.environ.get("TUNING_REFLECT", "1") != "0", "the room must be on"
    import blockrender as B
    import tonelib as T
    from drumset_check import note_file
    base = {}
    for n in TOMS:
        L, R = B.render(note_file(0, n, vel=100, hold=1.0))[:2]
        base[n] = early(0.5 * (np.asarray(L, float) + np.asarray(R, float)), B.SR)
    with tempfile.TemporaryDirectory() as d:
        target = gu_gain(d)
    print("GeneralUser's Room toms over its Standard: early %+.1f dB, top %+.1f dB" % tuple(target))
    g = ours_gain(base)
    print("ours, the live room as it stands:          early %+.1f dB, top %+.1f dB  (miss %.1f dB)"
          % (g[0], g[1], float(np.sqrt(np.mean((g - target) ** 2)))))
    if "--search" in argv:
        dims0 = {k: getattr(T.LiveRoom, k) for k in DIMS}
        for scale in (0.8, 0.9, 1.1, 1.2, 1.4):
            for k, v in dims0.items():
                setattr(T.LiveRoom, k, v * scale)
            g = ours_gain(base)
            print("   at %.1fx its size: early %+.1f dB, top %+.1f dB  (miss %.1f dB)"
                  % (scale, g[0], g[1], float(np.sqrt(np.mean((g - target) ** 2)))), flush=True)
        for k, v in dims0.items():
            setattr(T.LiveRoom, k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
