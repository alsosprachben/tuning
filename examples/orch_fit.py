#!/usr/bin/env python3
"""The Orchestra set (program 48 on the drum channel) against real orchestral
percussion.

    python3 -I examples/orch_fit.py --select        level one: which VCSL hit each note plays
    python3 -I examples/orch_fit.py --bd            the concert bass drum, read as drum_fit reads a kick
    python3 -I examples/orch_fit.py --bd --model    ...and ours, played from the set
    python3 -I examples/orch_fit.py --fit=bd        fit it to its hit (time x band grid, tr808_fit.score)

THE SET (SC-55 owner's manual p.70, "49:Orchestra Set"): 27-29 the hi-hats as
one exclusive group (EXC1), 30 a ride, 35 and 36 two concert bass drums, 38
and 40 a concert snare, 39 castanets, 41-53 timpani chromatically F to f
(F2-F3: FluidR3's 41 rings at 87.3 Hz, its 47, 50 and 53 at 1.51 x B2, d3, f3
-- the timpano's fifth-above mode), 57 and 59 two concert cymbals, 88
applause. Every other note is Standard's.

TWO LEVELS, as the Electronic and TR-808 sets were. VCSL (CC0; ~/Documents/
refs/vcsl, sources.md) holds concert percussion; GeneralUser GS's Orchestra
sample on each note picks the closest hit (examples/tr808_fit.score, its
pitch left out), and the voice is fitted to THAT. FluidR3 agrees on all but
59, where it would take the other clash pair.
"""
import glob
import os
import sys
import tempfile
import warnings

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")

KIT = 48
VCSL = os.path.expanduser("~/Documents/refs/vcsl")
CAND = {35: ("bassdrum1", "bassdrum2"), 36: ("bassdrum1", "bassdrum2"),
        38: ("snare_rope", "snare_legacy"), 40: ("snare_rope", "snare_legacy"),
        57: ("clash1", "clash2"), 59: ("clash1", "clash2")}
# LEVEL ONE's answer (--select, GeneralUser GS choosing)
HITS = {36: "bassdrum1/BDrumNew_hit_v7_rr1_Sum.wav", 35: "bassdrum1/BDrumNew_hit_v5_rr1_Sum.wav",
        38: "snare_legacy/drum1_snare1_mp_rr1.wav", 40: "snare_legacy/drum1_snare1_mp_rr1.wav",
        57: "clash2/cymbal_crash2_fff2.wav", 59: "clash1/cymbal_crash1_ff2.wav"}


def load(p, mono=True):
    import elkit_fit as E
    from drum_fit import read
    if mono:
        x, sr = E.read(p)
    else:
        a, sr = read(p)
        x = a
    if sr != 44100:
        from scipy.signal import resample_poly
        x = resample_poly(x, 44100, sr, axis=0)
        sr = 44100
    return x, sr


def select(d):
    import elkit_fit as E
    import tr808_fit as F
    from gm_release import SETS
    E.KIT = KIT
    sets = dict(SETS.items() if isinstance(SETS, dict) else SETS)
    for n, dirs in sorted(CAND.items()):
        for gm in ("GeneralUser", "FluidR3"):
            sf = [p for k, p in sets.items() if k.startswith(gm)][0]
            g, sr = E.theirs(sf, n, d)
            res = sorted((F.score(load(f)[0], g, sr, pitch=False), dd + "/" + os.path.basename(f))
                         for dd in dirs for f in sorted(glob.glob(os.path.join(VCSL, dd, "*.wav"))))
            print("%d %-11s -> %s" % (n, gm, "   ".join("%s %.1f" % (m, s) for s, m in res[:3])))


def bd_strokes():
    """VCSL's Bass Drum 1: eight hits in four layers, a stereo pair -- the two
    sides as drum_fit's two close microphones, summed in power."""
    import re
    out = []
    for p in sorted(glob.glob(os.path.join(VCSL, "bassdrum1", "*.wav"))):
        m = re.search(r"_v(\d+)_rr(\d+)", p)
        a, sr = load(p, mono=False)
        out.append((10 * int(m.group(1)) + int(m.group(2)), [a[:, 0], a[:, -1]], sr))
    return out


# THE CONCERT BASS DRUM'S KNOBS, over the measured table (--bd): the click's
# calibration and fall, every mode's rate scaled, the levels tilted by
# octaves of ratio, the remainder, and the head's stretch
BD_OCT = (60.0, 120.0, 240.0, 480.0, 960.0)     # the modes' octaves: under 60 Hz, ... over 960
BD_KNOBS = (("click_cal_db", False, 6.0), ("click_dbs", True, 0.4),
            ("slow_share", False, 0.05), ("slow_dbs", True, 0.4), ("tension_bend", False, 0.03)) \
    + tuple(("trim%d" % i, False, 4.0) for i in range(len(BD_OCT) + 1)) \
    + tuple(("rate%d" % i, True, 0.3) for i in range(len(BD_OCT) + 1))


def _oct(hz):
    return int(np.searchsorted(BD_OCT, hz))


def bd_fit(d, maxfev=300, write=False):
    """Fit the concert bass drum, played at 36, to its hit (HITS[36])."""
    from scipy.optimize import minimize
    import elkit_fit as E
    import tr808_fit as F
    import tonelib as T
    import percussion_map as P
    E.KIT = KIT
    cls = T.ConcertBassDrumProperties
    base = tuple(cls.DRUM_MODES)
    y, sr = load(os.path.join(VCSL, HITS[36]))
    f0 = P.KITS[KIT][36][2]
    state = dict(click_cal_db=cls.click_cal_db, click_dbs=cls.click_dbs,
                 slow_share=max(cls.slow_share, 0.05), slow_dbs=max(cls.slow_dbs, 15.0),
                 tension_bend=cls.tension_bend)
    state.update({"trim%d" % i: 0.0 for i in range(len(BD_OCT) + 1)})
    state.update({"rate%d" % i: 1.0 for i in range(len(BD_OCT) + 1)})

    def setx(x):
        for (k, lg, _), v in zip(BD_KNOBS, x):
            state[k] = float(np.exp(v)) if lg else float(v)
        cls.DRUM_MODES = tuple((r, l + state["trim%d" % _oct(r * f0)], dbs * state["rate%d" % _oct(r * f0)])
                               for r, l, dbs in base)
        for k in ("click_cal_db", "click_dbs", "slow_share", "slow_dbs", "tension_bend"):
            setattr(cls, k, state[k])
        cls.tension_bend_max = max(cls.tension_bend_max, abs(state["tension_bend"]))
        P._RING_CLASSES.clear()
    best = [1e9]

    def f(x):
        setx(x)
        # NO PITCH TERM: a big drum's strongest partial wanders among its
        # modes (87 -> 62 Hz over 100 ms on the hit), and the track scored that
        s = F.score(E.ours(36, d)[0], y, sr, False)
        if s < best[0]:
            best[0] = s
            print("   %.2f  %s" % (s, " ".join("%.3f" % v for v in x)), flush=True)
        return s
    x0 = np.array([np.log(state[k]) if lg else state[k] for k, lg, _ in BD_KNOBS])
    step = np.array([st for _, _, st in BD_KNOBS])
    s0 = f(x0)
    r = minimize(f, x0, method="Nelder-Mead",
                 options=dict(initial_simplex=np.vstack([x0] + [x0 + np.eye(len(x0))[i] * step[i]
                                                                 for i in range(len(x0))]),
                              maxfev=maxfev, xatol=0.005, fatol=0.02))
    setx(r.x)
    print("FITTED concert BD to %s: %.2f -> %.2f" % (HITS[36], s0, r.fun))
    print("    DRUM_MODES = (\n%s\n    )" % "\n".join("        (%.3f, %.1f, %.1f)," % m for m in cls.DRUM_MODES))
    for k in ("click_cal_db", "click_dbs", "slow_share", "slow_dbs", "tension_bend"):
        print("    %s = %.4g" % (k, state[k]))
    if write:
        write_class("ConcertBassDrumProperties", cls.DRUM_MODES,
                    {k: state[k] for k in ("click_cal_db", "click_dbs", "slow_share", "slow_dbs",
                                           "tension_bend")})


def write_class(name, modes, params):
    """Rewrite a class's DRUM_MODES and set its fitted knobs in tonelib.py."""
    import re
    path = os.path.join(HERE, "tonelib.py")
    s = open(path).read()
    i = s.index("class %s(" % name)
    end = s.index("\nclass ", i + 1)
    body = s[i:end]
    j = body.index("    DRUM_MODES = (")
    k = body.index("\n    )\n", j) + 6
    body = body[:j] + "    DRUM_MODES = (\n%s\n    )\n" % "\n".join(
        "        (%.3f, %.1f, %.1f)," % m for m in modes) + body[k:]
    for key, v in params.items():
        line = "    %s = %.6g" % (key, v)
        if re.search(r"^    %s = .*$" % key, body, re.M):
            body = re.sub(r"^    %s = .*$" % key, line, body, count=1, flags=re.M)
        else:
            body = body.rstrip("\n") + "\n" + line + "\n\n\n"
    s = s[:i] + body + s[end:]
    open(path, "w").write(s)
    print("   wrote %s" % name)


def bd_modes(ss):
    """The concert bass drum's modes: its SETTLED ones (0.15-0.6 s) to -45 dB
    and 1 kHz, as drum_fit reads a kick -- and, because a big head's upper
    modes are gone before 0.15 s, its EARLY ones (5-60 ms, 500 Hz - 3 kHz, to
    -40 dB), as snare_fit reads a snare: a mode within 2% of one already
    found is that one."""
    import drum_fit as D
    sr = ss[0][2]
    top = [c for _, c, _ in ss[len(ss) // 2:]]
    found = [fq for fq, _ in D.find_modes(top, sr, lo=30.0, hi=1000.0, floor_db=-45.0)]
    acc = None
    for chs in top:
        t0 = D.strike(chs, sr)
        a, b = t0 + int(0.005 * sr), t0 + int(0.060 * sr)
        P = sum(np.abs(np.fft.rfft(c[a:b] * np.hanning(b - a), 1 << 16)) ** 2 for c in chs)
        acc = P if acc is None else acc + P
    f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    A = np.sqrt(acc)
    b = (f > 500.0) & (f < 3000.0)
    fb, Ab = f[b], A[b]
    pk = [i for i in np.flatnonzero((Ab[1:-1] > Ab[:-2]) & (Ab[1:-1] >= Ab[2:])) + 1
          if Ab[i] >= Ab[np.abs(fb - fb[i]) < 0.025 * fb[i]].max()]
    ref = Ab[pk].max() if pk else 1.0
    for i in pk:
        if Ab[i] > ref * 10 ** (-40 / 20.0) and all(abs(fb[i] / m - 1) > 0.02 for m in found):
            found.append(float(fb[i]))
    return sorted(found)


def main(argv):
    with tempfile.TemporaryDirectory() as d:
        if "--select" in argv:
            select(d)
        if "--fit=bd" in argv:
            bd_fit(d, int(next((a.split("=")[1] for a in argv if a.startswith("--maxfev=")), 300)),
                   "--write" in argv)
        if "--bd" in argv:
            import drum_fit as D
            ss = bd_strokes()
            D.analyse(ss, "VCSL Bass Drum 1", modes=bd_modes(ss))
            if "--model" in argv:
                os.environ.setdefault("TUNING_REFLECT", "0")
                import blockrender as B
                import percussion_map as PM
                from drumset_check import note_file
                for note in (36, 35):
                    strokes = []
                    for v in (36, 64, 100, 127):
                        L, R = B.render(note_file(KIT, note, vel=v, hold=2.5))[:2]
                        strokes.append((v, [np.asarray(L, np.float64) + np.asarray(R, np.float64)], B.SR))
                    cls, f0 = PM.KITS[KIT][note][1], PM.KITS[KIT][note][2]
                    D.analyse(strokes, "ours, Orchestra %d" % note,
                              modes=[f0 * r[0] for r in cls.DRUM_MODES])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
