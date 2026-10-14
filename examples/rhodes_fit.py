#!/usr/bin/env python3
"""Measure GM 4's Rhodes against Jeff Learman's 1977 Mark I Stage 73
("jRhodes3d", samples CC BY-NC, measured only; sources.md), and ours the
same way.

    python3 -I examples/rhodes_fit.py measure [--ours]
    python3 -I examples/rhodes_fit.py fit [--params=a,b] [--maxfev=N]
    python3 -I examples/rhodes_fit.py ab OUT.wav [--note-s=3]   take, then ours, note by note

THE HARP CONNECTOR, THROUGH HIS EQ. The takes are the pickups' own output,
no amp and no speaker -- what tonelib.RhodesProperties makes with the
cabinet out -- but recorded through Learman's EQ (a treble boost and a
low-mid scoop, curve not given) and denoised. A fixed EQ is a fixed gain
per Hz, so it cancels from anything compared at the same Hz:
  * each partial's DECAY (dB/s) -- the EQ moves a level, never a slope;
  * a note's spectrum at one velocity AGAINST another (dB, layer re the
    softest) -- the growl the hammer adds, which is the tine's swing;
  * a partial's level LATE against EARLY -- the bark fading into the bell;
and not from the ladder itself (dB re h1), which carries the EQ's tilt.

Fifteen notes, F1-C7, every fourth white key; five layers in the bass and
three at the top. The files are numbered 1 (hardest) to 5 (softest), and
the set's own map gives each a velocity band (_jRhodes3d-mono-no-xfade
-flac.sfz): 5 1-47, 4 48-72, 3 73-95, 2 96-111, 1 112-127. Played here at
each band's middle. The layers were set to peak 3 dB apart, so their
levels say nothing; their spectra do.
"""
import glob
import os
import sys

import numpy as np

os.environ.setdefault("TUNING_CABINET", "0")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U
import wurli_fit as W

REFS = os.path.expanduser("~/Documents/refs/rhodes/jrhodes3d_wav")    # sox-decoded jRhodes3d-mono
PROGRAM = 4
VEL = {1: 120, 2: 104, 3: 84, 4: 60, 5: 30}


def recordings():
    """{(layer, key): path}: A_029__F1_5.wav is key 29, layer 5."""
    out = {}
    for p in glob.glob(os.path.join(REFS, "A_*.wav")):
        b = os.path.basename(p)[:-4].split("_")
        out[(int(b[-1]), int(b[1]))] = p
    return out


def f0_of(x, sr, k):
    """The pitch by harmonic sum around the label's, cents re the label --
    a check the labels mean what they say (the BaltiWurli's did not)."""
    t0 = U.onset(x, sr)
    X, f = U.spectrum(x, sr, t0, 0.2, 1.2, 1 << 18)
    best = None
    for c in np.arange(-1250, 1250, 2.0):
        g = W.hz(k) * 2 ** (c / 1200)
        s = 0.0
        for m in range(1, 6):
            w = (f > m * g * 0.998) & (f < m * g * 1.002)
            if w.any():
                s += np.log(X[w].max() + 1e-30)
        if best is None or s > best[0]:
            best = (s, c)
    return best[1]


def h1_peak(x, sr, k):
    """When the fundamental is loudest, s after the onset (20 ms frames)."""
    from scipy.signal import butter, sosfiltfilt
    t0 = U.onset(x, sr)
    f0 = W.hz(k)
    bw = max(4.0, 0.04 * f0)
    y = sosfiltfilt(butter(2, [f0 - bw, f0 + bw], btype="band", fs=sr, output="sos"), x[t0:])
    w = int(0.02 * sr)
    e = np.array([np.mean(y[i:i + w] ** 2) for i in range(0, min(len(y), 4 * sr) - w, w)])
    return 0.02 * int(np.argmax(e))


def source(ours):
    """(layer, key) -> (x, sr): the take, or ours at the layer's velocity
    (cabinet out, no CC1), 4.5 s -- long enough for the bass's h1 to peak."""
    rs = recordings()
    memo = {}

    def get(L, k):
        if (L, k) not in memo:
            memo[(L, k)] = U.render(PROGRAM, k, VEL[L], 4.5) if ours else U.load(rs[(L, k)])
        return memo[(L, k)]
    return rs, get


def measure_all(ours=False):
    rs, get = source(ours)
    keys = sorted({k for _, k in rs})
    print("  [%s]" % ("OURS" if ours else "jRhodes3d"))
    if not ours:
        print("  pitch, cents re the label (layer 3, else 2):")
        for k in keys:
            x, sr = get(3 if (3, k) in rs else 2, k)
            print("   %3d %+5.0f" % (k, f0_of(x, sr, k)), end="")
        print("\n  %d takes" % len(rs))
    print("\n  DECAY h1-h6, dB/s (layer 2):")
    for k in keys:
        print("   %3d " % k + " ".join("%6.1f" % v for v in W.decays(*get(2, k), k)))
    print("\n  GROWL: h2-h6 at each layer, dB re the softest layer's (each re its own h1)")
    for k in keys:
        lays = sorted(L for L, kk in rs if kk == k)
        soft = W.ladder(*get(lays[-1], k), k, n=6)
        for L in lays[:-1]:
            ld = W.ladder(*get(L, k), k, n=6)
            print("   %3d L%d " % (k, L) + " ".join("%+6.1f" % v for v in (ld - soft)[1:]))
    print("\n  BARK INTO BELL: h2-h6 at 0.6-1.0 s re 0.03-0.23 s, dB (each re h1; layer 2)")
    for k in keys:
        x, sr = get(2, k)
        e, l = W.ladder(x, sr, k, n=6), W.ladder(x, sr, k, n=6, a=0.6, b=1.0)
        print("   %3d " % k + " ".join("%+6.1f" % v for v in (l - e)[1:])
              + "    h1 peaks %.2f s" % h1_peak(x, sr, k))


# THE FIT (`fit`): the pickup and the tine's decay together, since the
# layers tie them -- a harmonic's envelope is its swing's power series, so
# how fast the bark fades IS the decay. Only what Learman's EQ cancels:
#   growl   h2-h6 and the bands past them (BANDS) at each layer re the
#           softest (each re its own h1), dB; both ladders floored at -60
#           dB, under which the denoiser works
#   bark    h2-h4 late (0.6-1.0 s) re early, re h1, dB (layer 2)
#   attack  the same for the hardest layer over 0-50 ms (the strike)
#   decay   h1-h3, dB/s, as 10 log10 of ours over the take's (layer 2;
#           where the take's falls at 0.5-100 dB/s -- a building h1 is the
#           next target's)
#   build   when h1 peaks, below D3: 10 log10 of the ratio, the 0.1 s
#           frame floor under both (layer 2)
FIT = ("pickup_offset,pickup_deflection,pickup_deflection_max,deflection_register_slope,"
       "deflection_velocity_power,harmonic_decay_db,decay_register_slope,"
       "pickup_gap,pickup_side,pickup_side_depth,tine_arc")
STEPS = {"pickup_offset": 0.1, "pickup_deflection": 0.15, "pickup_deflection_max": 0.4,
         "deflection_register_slope": 0.15, "deflection_velocity_power": 0.4,
         "harmonic_decay_db": 2.0, "decay_register_slope": 0.2,
         "pickup_gap": 0.2, "pickup_side": 0.5, "pickup_side_depth": 0.5, "tine_arc": 15.0}


# ...and up the series: the bass's buzz is h17-h48 (B1's hard layer holds
# them at -2 to +10 dB re h1), so past h6 the growl is read as each band's
# loudest harmonic -- h7-12, h13-20, h21-32, h33-48 -- floored the same.
BUZZ_N = 48
BANDS = ((7, 12), (13, 20), (21, 32), (33, 48))


def bands(ld):
    ld = np.maximum(ld, -60)
    return np.concatenate((ld[1:6], [np.nanmax(ld[a - 1:b]) if np.isfinite(ld[a - 1:b]).any()
                                     else np.nan for a, b in BANDS]))


def targets(get, rs):
    out = {}
    keys = sorted({k for _, k in rs})
    for k in keys:
        lays = sorted(L for L, kk in rs if kk == k)
        soft = bands(W.ladder(*get(lays[-1], k), k, n=BUZZ_N))
        for L in (lays[0], lays[len(lays) // 2]):
            out[("growl", L, k)] = bands(W.ladder(*get(L, k), k, n=BUZZ_N)) - soft
        # ...and the hard layer's ATTACK, 0-50 ms, where Ben hears it short
        out[("attack", k)] = (bands(W.ladder(*get(lays[0], k), k, n=BUZZ_N, a=0.0, b=0.05))
                              - bands(W.ladder(*get(lays[-1], k), k, n=BUZZ_N, a=0.0, b=0.05)))
        x, sr = get(2, k)
        e = np.maximum(W.ladder(x, sr, k, n=4), -60)
        l = np.maximum(W.ladder(x, sr, k, n=4, a=0.6, b=1.0), -60)
        out[("bark", k)] = (l - e)[1:]
        out[("decay", k)] = W.decays(x, sr, k, n=3)
        if k < 50:
            out[("build", k)] = h1_peak(x, sr, k)
    return out


def error(rec, ours, detail=False):
    E, parts = [], {}
    for key, r in rec.items():
        o = ours[key]
        if key[0] in ("growl", "bark", "attack"):
            ok = np.isfinite(r) & np.isfinite(o)
            e = list((o - r)[ok])
        elif key[0] == "decay":
            e = [10 * np.log10(b / a) for a, b in zip(r, o)
                 if np.isfinite(a) and np.isfinite(b) and 0.5 < a < 100 and b > 0.5]
        else:
            e = [10 * np.log10(max(o, 0.1) / max(r, 0.1))]
        E += e
        parts.setdefault(key[0], []).extend(e)
    if detail:
        for n, e in parts.items():
            print("    %-6s rms %5.1f dB over %d" % (n, np.sqrt(np.mean(np.square(e))), len(e)))
    return float(np.sqrt(np.mean(np.square(E))))


def fit(opts):
    import tonelib as T
    import dulcimer_fit as D
    cls = T.RhodesProperties
    rs, get = source(False)
    rec = targets(get, rs)
    names = opts.get("--params", FIT).split(",")

    def err():
        T._EP_PICKUP_CACHE.clear()
        _, mine = source(True)
        return error(rec, targets(mine, rs))
    print("  start:")
    T._EP_PICKUP_CACHE.clear()
    error(rec, targets(source(True)[1], rs), detail=True)
    D.nelder(cls, names, err, STEPS, int(opts.get("--maxfev", 120)), "rms")
    T._EP_PICKUP_CACHE.clear()
    error(rec, targets(source(True)[1], rs), detail=True)


def ab(out, note_s):
    """Each take, then ours at its layer's velocity (cabinet out, no CC1),
    then a rest -- softest, middle, hardest a note at a time, low to high;
    each peak-normalised alike (harpsi_ab.fit_note). His EQ is on the takes
    and not on ours: a tilt between them is the EQ's, not the tine's."""
    import harpsi_ab as A
    from roomtail import write_wav
    A.NOTE_S = note_s
    rs = recordings()
    gap, rest = np.zeros(int(A.GAP_S * A.SR)), np.zeros(int(0.6 * A.SR))
    parts = []
    for k in sorted({k for _, k in rs}):
        lays = sorted(L for L, kk in rs if kk == k)
        for L in (lays[-1], lays[len(lays) // 2], lays[0]):
            y, sr = U.render(PROGRAM, k, VEL[L], note_s + 0.5)
            parts += [A.fit_note(*U.load(rs[(L, k)])), gap, A.fit_note(y, sr), rest]
    x = np.concatenate(parts)
    write_wav(out, np.stack([x, x], 1), A.SR)


def main(argv):
    if argv[:1] == ["measure"]:
        measure_all("--ours" in argv)
    elif argv[:1] == ["ab"]:
        ab(argv[1], float(dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
                          .get("--note-s", 3.0)))
    elif argv[:1] == ["fit"]:
        fit(dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
