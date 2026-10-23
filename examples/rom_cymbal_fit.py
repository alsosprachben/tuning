#!/usr/bin/env python3
"""The drum machines' SAMPLED metal -- a real cymbal or hat in ROM -- fitted
on our acoustic cymbals to the machine's own take.

    python3 -I examples/rom_cymbal_fit.py [--model]          each take's grid beside ours
    python3 -I examples/rom_cymbal_fit.py --fit[=NAME,...] [--maxfev=N] [--write]

The 909's crash, ride and open hat and the 707's hats are recordings of
real cymbals, 6-bit, played once through a VCA (the 909's crash and ride
by TUNE's clock). A circuit patch on them (tr808.py's noise layers) scored
well and sounded synthetic (Ben: the 909's "sound almost real" on the high
end, ours not): a real plate is hundreds of modes, the high ones dying
fastest. So each is a subclass of our crash, ride or hat -- before the fit,
exactly ours -- and examples/crash_fit.py's grid (octave bands x windows to
4 s, a closed-form band trim) fits its shape to the ONE take, at the
velocity the set plays an accent (127: Baker's "levels at max"). Cells past
the take's end weigh nothing (crash_fit's weights), so a ROM's cut ring is
not a ring to match.

THE ROM ON TOP: its 6-bit steps are a noise of fixed size under a ring that
decays in the data, so the grit rises through the tail -- a flat noise
layer (rom_db re the plate, falling rom_dbs) fitted with the rest; the
clock's capped top is the band trim's.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

import crash_fit as C   # noqa: E402
import elkit_fit as E   # noqa: E402

REFS = os.path.expanduser("~/Documents/refs")
# name: (set, note, class, take)
ROM = {
    "909crash": (30, 49, "TR909CrashProperties", "tr909_hyperreal/all/CSHD4.WAV"),
    "909ride": (30, 51, "TR909RideProperties", "tr909_hyperreal/all/RIDED4.WAV"),
    "909openhat": (30, 46, "TR909OpenHatProperties", "tr909_hyperreal/all/HHOD4.WAV"),
    "707closedhat": (29, 42, "TR707ClosedHatProperties", "tr707_hyperreal/all/HhC.wav"),
    "707openhat": (29, 46, "TR707OpenHatProperties", "tr707_hyperreal/all/HhO.wav"),
}
VEL = 127
ROM_PARAMS = ("rom_db", "rom_dbs")
THIRDS = tuple(round(100.0 * 2 ** (k / 3.0)) for k in range(22))      # 100 Hz - 12.7 kHz


def rom_layer(cls):
    """The 6-bit grit: flat third octaves at rom_db, falling rom_dbs."""
    if cls.rom_db <= -90.0:
        return ()
    return ((tuple((hz, round(cls.rom_db, 2)) for hz in THIRDS), 0.0005, cls.rom_dbs, 2.0),)


def take(path):
    x, sr = E.read(os.path.join(REFS, path))
    return [np.asarray(x, float)], sr


def grid_of(name):
    chs, sr = take(ROM[name][3])
    return C.norm(C.grid(chs, sr))


def ours(name):
    kit, note, _, _ = ROM[name]
    C.KIT = kit
    return C.norm(C.grid(*C.render(note, VEL)))


def fit(name, maxfev):
    from scipy.optimize import minimize
    import tonelib as T
    kit, note, cls_name, _ = ROM[name]
    C.KIT = kit
    cls = getattr(T, cls_name)
    cls.band_trim_db = ()
    rec = [grid_of(name)]
    # ...those the class uses (a hat has no chiff_width: None)
    params = tuple(k for k in C.PARAMS if getattr(cls, k, None) is not None) + ROM_PARAMS
    n = len(params) - len(ROM_PARAMS)
    x0 = np.array([max(float(getattr(cls, k)), C.FLOOR.get(k, 1e-3)) if k not in ROM_PARAMS
                   else float(getattr(cls, k)) for k in params])
    best = [1e9, None, None]

    def setx(z):
        vals = np.array(x0, float)
        vals[:n] = np.exp(z[:n]) * x0[:n]
        vals[n:] = x0[n:] + z[n:] * np.array([10.0, 10.0])      # dB, dB/s: additive
        for k, v in zip(params, vals):
            setattr(cls, k, float(v))
        cls.strike_noise_layers = rom_layer(cls)
        return vals

    def f(z):
        vals = setx(z)
        e, trim = C.score([ours(name)], rec)
        if e < best[0]:
            best[:] = [e, vals, trim]
            print("   %6.3f dB  %s  trim %s" % (e, " ".join("%s=%.4g" % (k[:12], v) for k, v in zip(params, vals)),
                                                " ".join("%+.1f" % t for t in trim)), flush=True)
        return e
    m = len(params)
    simplex = np.vstack([np.zeros(m)] + [0.47 * np.eye(m)[i] * (1 if i % 2 else -1) for i in range(m)])
    minimize(f, np.zeros(m), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02,
                      "adaptive": True})
    e, vals, trim = best
    for k, v in zip(params, vals):
        setattr(cls, k, float(v))
    cls.band_trim_db = tuple((round(c), round(float(t), 1)) for c, t in zip(C.CENTRES, trim))
    cls.strike_noise_layers = rom_layer(cls)
    print("FITTED %s to %s: %.3f dB" % (name, ROM[name][3], e), flush=True)
    return cls_name, dict(zip(params, vals)), cls.band_trim_db


def write(cls_name, vals, trim):
    """Rewrite the class's FITTED block (between its markers) in tonelib.py."""
    path = os.path.join(HERE, "tonelib.py")
    s = open(path).read()
    i = s.index("class %s(" % cls_name)
    a = s.index("    # FITTED (examples/rom_cymbal_fit.py)\n", i)
    b = s.index("    # /FITTED\n", a)
    lines = ["    # FITTED (examples/rom_cymbal_fit.py)"]
    lines += ["    %s = %s" % (k, "%.6g" % v) for k, v in vals.items()]
    lines.append("    band_trim_db = (%s)" % ", ".join("(%d, %.1f)" % t for t in trim))
    s = s[:a] + "\n".join(lines) + "\n" + s[b:]
    open(path, "w").write(s)
    print("   wrote %s" % cls_name)


def main(argv):
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    args = dict(a.split("=", 1) if "=" in a else (a, "") for a in argv[1:])
    names = args.get("--fit") or ",".join(ROM)
    names = names.split(",")
    if "--fit" in args:
        for n in names:                  # each written as it is done
            d = fit(n, int(args.get("--maxfev", 300)))
            if "--write" in args:
                write(*d)
        return 0
    for n in names:
        rec = grid_of(n)
        C.show("%s take (%s)" % (n, ROM[n][3]), rec - rec.max())
        if "--model" in args:
            m = ours(n)
            e, _ = C.score([m], [rec])
            C.show("ours minus take (score %.2f dB)" % e, m - rec)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
