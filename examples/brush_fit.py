#!/usr/bin/env python3
"""The Brush set's SWIRL (program 40, note 40, SC-55 p.70) fitted on two levels.

    python3 -I examples/brush_fit.py               score it
    python3 -I examples/brush_fit.py --fit [--write]

The taps and slaps are strokes, fitted as snares are (examples/snare_fit.py
--brush=tap|slap). The swirl is not a stroke. Karoryfer's Swirly Drums (CC0;
~/Documents/refs/swirly_drums_karoryfer) recorded the brush STIRRING the head
for 6-13 s at a time -- material its own player shapes into a stir of any
length; none of the takes falls 20 dB -- while a GS swirl is ONE swish:
GeneralUser GS's peaks at 0.37 s and is gone by ~0.8.

So the two levels split along that line:
  TEXTURE  the real brush: our swirl's third-octave balance while it sounds
           against the stir's while it stirs (1-5 s of the FASTEST PLAIN stir,
           stir_dl4_rr4: see STIR), as tr808_fit.balance reads
  GESTURE  the GS sample: our 20 ms envelope against GeneralUser's, dB re
           each one's peak, over its first 1.2 s, floor -50
The score is their sum.

THE MODEL. A brush stirring a head is friction noise across the whole
spectrum with the head's resonances in it. The class keeps its head --
modes excited by noise (sustain_jitter), swelling over attack_time and
dying at decay_db -- and gains a NOISE LAYER (strike_noise_layers: a band
table, a linear rise, a fall, a length), the friction: the table's shape is
fitted in five octave trims, its level, rise, fall and length beside them.
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

import tr808_fit  # noqa: E402,F401  -- FIRST: importing it sets elkit_fit.KIT = 25,
                  # and a later import mid-fit sent every render to the 808 set
KIT, NOTE = 40, 40
# THE FASTEST PLAIN STIR. A GS swirl is one quick swish, and the plain takes
# carry the wires' sizzle the "skin" takes do not: the one fitted first
# (stir_dl3_skin, the take GeneralUser's swirl had scored closest to) read a
# 1.75 kHz centroid and -36 dB at 12.7 kHz, the fastest plain 3.2 kHz and -17,
# GeneralUser's own swirl 4.5 kHz -- Ben: "the swirl seems to need more
# harmonics or high-end"
STIR = os.path.expanduser("~/Documents/refs/swirly_drums_karoryfer/snare_stir/stir_dl4_rr4.wav")
GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
BANDS = tuple(100.0 * 2 ** (k / 3.0) for k in range(23))         # 100 Hz - 16 kHz
OCT = (250.0, 500.0, 1000.0, 2000.0, 3200.0, 5000.0, 8000.0, 12700.0)   # trim points: finer at the top
KNOBS = (("attack_time", True, 0.4), ("decay_db", True, 0.4), ("chiff_volume", True, 0.5),
         ("noise_db", False, 10.0), ("rise_s", True, 0.4), ("fall_dbs", True, 0.4),
         ("len_s", True, 0.3)) + tuple(("trim%d" % i, False, 4.0) for i in range(len(OCT)))


def envelope(x, sr):
    x = np.asarray(x, float)
    w = int(0.02 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same")) + 1e-12
    a = int(np.argmax(e > e.max() * 0.01))
    e = e[a:a + int(1.2 * sr)]
    e = np.pad(e, (0, int(1.2 * sr) - len(e)), constant_values=1e-12)
    db = 20 * np.log10(e / e.max())
    return np.maximum(db[::int(0.01 * sr)], -50.0)


def texture(x, sr, t0=None, t1=None):
    import tr808_fit as F
    x = np.asarray(x, float)
    if t0 is not None:
        x = x[int(t0 * sr):int(t1 * sr)]
    return F.balance(x, sr, F.sounding(x, sr))


def targets(d):
    import elkit_fit as E
    E.KIT = KIT
    g, sr = E.theirs(GU, NOTE, d)
    s, _ = E.read(STIR)
    return envelope(g, sr), np.maximum(texture(s, sr, 1.0, 5.0), -60.0)


def score(x, sr, tg):
    env, tex = tg
    a = envelope(x, sr)
    t = np.maximum(texture(x, sr), -60.0)
    live = (t > -60) | (tex > -60)
    return float(np.sqrt(np.mean((a - env) ** 2))) + float(np.sqrt(np.mean((t[live] - tex[live]) ** 2)))


def apply(cls, st):
    for k in ("attack_time", "decay_db", "chiff_volume"):
        setattr(cls, k, st[k])
    trims = [st["trim%d" % i] for i in range(len(OCT))]
    table = tuple((round(hz), round(st["noise_db"] + float(np.interp(np.log2(hz), np.log2(OCT), trims)), 2))
                  for hz in BANDS)
    cls.strike_noise_layers = ((table, st["rise_s"], st["fall_dbs"], st["len_s"]),)
    if not getattr(cls, "strike_noise_db", None):
        # the layers ride the strike's path: a silent strike beside them
        cls.strike_noise_db = tuple((round(hz), -120.0) for hz in BANDS)
        cls.strike_noise_dbs = 600.0
        cls.strike_noise_len_s = 0.05
        cls.strike_noise_fade_s = 0.001


def main(argv):
    from scipy.optimize import minimize
    import elkit_fit as E
    import tonelib as T
    import percussion_map as P
    E.KIT = KIT
    cls = T.BrushSwirlProperties
    with tempfile.TemporaryDirectory() as d:
        tg = targets(d)
        lay = (getattr(cls, "strike_noise_layers", ()) or ((None, 0.3, 30.0, 0.8),))[0]
        st = dict(attack_time=cls.attack_time, decay_db=cls.decay_db, chiff_volume=cls.chiff_volume,
                  noise_db=30.0, rise_s=lay[1], fall_dbs=lay[2], len_s=lay[3])
        # (the table is re the note's gain, which a snare's is far under: at
        # -30 dB the friction sat far under the head and no step reached it)
        st.update({"trim%d" % i: 0.0 for i in range(len(OCT))})
        if lay[0]:
            # read the table's level and trims back off it
            hz = np.array([b for b, _ in lay[0]]); db = np.array([v for _, v in lay[0]])
            tr = np.interp(np.log2(OCT), np.log2(hz), db)
            st["noise_db"] = float(tr.mean())
            st.update({"trim%d" % i: float(t - tr.mean()) for i, t in enumerate(tr)})
        x0 = np.array([np.log(st[k]) if lg else st[k] for k, lg, _ in KNOBS])

        def setx(x):
            for (k, lg, _), v in zip(KNOBS, x):
                st[k] = float(np.exp(v)) if lg else float(v)
            apply(cls, st)
            P._RING_CLASSES.clear()
        best = [1e9]

        def f(x):
            setx(x)
            s = score(*E.ours(NOTE, d), tg)
            if s < best[0]:
                best[0] = s
                print("   %.2f  %s" % (s, " ".join("%.3f" % v for v in x)), flush=True)
            return s
        s0 = f(x0)
        if "--fit" not in argv:
            print("score %.2f" % s0)
            return 0
        step = np.array([s for _, _, s in KNOBS])
        r = minimize(f, x0, method="Nelder-Mead",
                     options=dict(initial_simplex=np.vstack([x0] + [x0 + np.eye(len(x0))[i] * step[i]
                                                                     for i in range(len(x0))]),
                                  maxfev=int(next((a.split("=")[1] for a in argv
                                                   if a.startswith("--maxfev=")), 400)),
                                  xatol=0.005, fatol=0.02))
        setx(r.x)
        print("FITTED the swirl: %.2f -> %.2f" % (s0, r.fun))
        for k in ("attack_time", "decay_db", "chiff_volume"):
            print("    %s = %.5g" % (k, st[k]))
        print("    strike_noise_layers = (%r,)" % (cls.strike_noise_layers[0],))
        if "--write" in argv:
            import re
            path = os.path.join(HERE, "tonelib.py")
            s = open(path).read()
            i = s.index("class BrushSwirlProperties(")
            end = s.index("\nclass ", i + 1)
            body = s[i:end]
            for k in ("attack_time", "decay_db", "chiff_volume"):
                body = re.sub(r"^    %s = [^#\n]*" % k, "    %s = %.5g" % (k, st[k]), body, count=1, flags=re.M)
            body = re.sub(r"\n    # THE FRICTION.*?strike_noise_fade_s = [^\n]*\n", "\n", body, flags=re.S)
            body = body.rstrip("\n") + (
                "\n    # THE FRICTION (examples/brush_fit.py): a noise layer's band table, its\n"
                "    # linear rise, its fall and length -- the swish GeneralUser GS's swirl is,\n"
                "    # with the texture of Swirly Drums' stirring (CC0)\n"
                "    strike_noise_layers = (%r,)\n"
                "    strike_noise_db = %r\n"
                "    strike_noise_dbs = 600.0\n    strike_noise_len_s = 0.05\n"
                "    strike_noise_fade_s = 0.001\n\n\n" % (cls.strike_noise_layers[0], cls.strike_noise_db))
            open(path, "w").write(s[:i] + body + s[end:])
            print("   wrote BrushSwirlProperties")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
