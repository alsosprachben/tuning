#!/usr/bin/env python3
"""Measure GM 7's Clavinet against the Hohner D6 tones on Aalto's companion
page to Gabrielli, Valimaki & Bilbao, "Real-time emulation of the Clavinet"
(ICMC 2011; measured only, never redistributed -- sources.md), and ours the
same way.

    python3 -I examples/clav_fit.py measure [--ours]
    python3 -I examples/clav_fit.py fit [--params=a,b] [--maxfev=N] [--setting=centre]
    python3 -I examples/clav_fit.py ab OUT.wav [--note-s=3]   take, then ours
    python3 -I examples/clav_fit.py keyup   (writes release_click_db in tonelib.py)
    python3 -I examples/clav_fit.py keyup_ab OUT.wav   the takes' key-ups, then ours

THE TAKES. "Clavinet D6: single tones" is one file of three notes, each
struck twice and held -- Bb2, E4, F#5 -- with the key releases between them
(the tangent leaving the string, 25-35 dB under the strike). Which pickup
setting is not stated; the riff beside it is "with B pickup". So the pickup
is READ from the ladders: a pickup at fraction q of the speaking length
notches harmonic n where n q is whole.

THE PAPERS' GEOMETRY (Remaggi, Gabrielli et al., DAFx-12): a string of 67.8
cm for 161 Hz; the centre pickup ABOVE the strings, 18.5 cm from the
termination at the lowest string to 6.5 at the highest; the bridge pickup
BELOW them at a constant 4 cm, tilted 30 degrees. Flux against the string's
height falls as a gentle negative exponential (0.09 T at contact, ~0.07 at
2 cm) -- a mild nonlinearity, unlike a Rhodes tine's.
"""
import os
import sys

import numpy as np

os.environ.setdefault("TUNING_CABINET", "0")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U
import wurli_fit as W

TAKE = os.path.expanduser("~/Documents/refs/clavinet/aalto_icmc11_wav/wholekeyboard.wav")
PROGRAM = 7
# (start s, key, peak dB): the six strikes, found by onset (each held until
# the next event); the quiet events between are the releases
NOTES = ((0.35, 46), (20.19, 46), (35.37, 64), (41.63, 64), (49.85, 78), (56.20, 78))
RELEASES = (19.16, 34.80, 40.67, 55.52)
VEL = 100


def takes():
    x, sr = U.load(TAKE)
    out = []
    for i, (t, k) in enumerate(NOTES):
        nxt = min([r for r in RELEASES if r > t] + [NOTES[i + 1][0] if i + 1 < len(NOTES) else len(x) / sr])
        a = max(0, int((t - 0.02) * sr))
        out.append((k, x[a:int(nxt * sr)], sr))
    return out


def ours():
    return [(k, *U.render(PROGRAM, k, VEL, 4.0)) for _, k in NOTES[::2]]


def measure_all(mine):
    src = ours() if mine else takes()
    print("  [%s]" % ("OURS" if mine else "Aalto D6"))
    for k, x, sr in src:
        found, f0, B = U.partials(x, sr, k, nmax=40)
        lad = W.ladder(x, sr, k, n=32, a=0.03, b=0.53)
        dec = W.decays(x, sr, k, n=8)
        print("   key %d  f0 %.2f Hz (%+.0f c)  B %.2e  len %.1f s" % (
            k, f0, 1200 * np.log2(f0 / W.hz(k)), B, len(x) / sr))
        print("     ladder h1-h32 re h1:", " ".join("%4.0f" % v for v in lad))
        print("     decay h1-h8 dB/s:   ", " ".join("%5.1f" % v for v in dec))


# THE FIT (`fit`): the string's length law, where the tangent strikes, the
# brightness tilt and the decay, against the six takes -- ladders h2-h24 re
# h1, 0.03-0.53 s, floored at -60 dB (a 128 kb/s mp3: under that it is the
# codec's), and h1-h6's decay as 10 log10 of ours over the take's. The
# switch setting of a take is not given, so each take is scored against
# ours on all four settings and the nearest counts: which one that is, is
# read off the result. The string's stiffness is set, not fitted: B
# measured 3.4-5.4e-5 on the five clean takes (tonelib).
FIT = ("speaking_length_power,strike_point,tonal_dampening,octave_dampening,"
       "decay_db,harmonic_decay_db,decay_register_slope")
STEPS = {"speaking_length_power": 0.15, "strike_point": 0.02, "tonal_dampening": 0.4,
         "octave_dampening": 0.3, "decay_db": 1.0, "harmonic_decay_db": 1.0,
         "decay_register_slope": 0.3}
SETTINGS = ("bridge", "centre", "both", "anti")
LAD_N = 24


def _lad(x, sr, k):
    return np.maximum(W.ladder(x, sr, k, n=LAD_N, a=0.03, b=0.53), -60.0)


def targets():
    return [(k, _lad(x, sr, k), W.decays(x, sr, k, n=6)) for k, x, sr in takes()]


def error(rec, detail=False):
    import tonelib as T
    mine = {}
    for st in SETTINGS:
        T.ClavinetProperties.clav_pickup = st
        for k in sorted({k for k, _, _ in rec}):
            y, sr = U.render(PROGRAM, k, VEL, 3.0)
            mine[(st, k)] = (_lad(y, sr, k), W.decays(y, sr, k, n=6))
    T.ClavinetProperties.clav_pickup = "bridge"
    E, picks, parts = [], [], {"ladder": [], "decay": []}
    for k, rl, rd in rec:
        best = None
        for st in SETTINGS:
            ol, od = mine[(st, k)]
            ok = np.isfinite(rl) & np.isfinite(ol)
            el = list((ol - rl)[ok][1:])
            ed = [10 * np.log10(b / a) for a, b in zip(rd, od)
                  if np.isfinite(a) and np.isfinite(b) and 0.5 < a < 150 and b > 0.5]
            e = el + ed
            r = np.sqrt(np.mean(np.square(e)))
            if best is None or r < best[0]:
                best = (r, st, el, ed)
        picks.append((k, best[1], best[0]))
        E += best[2] + best[3]
        parts["ladder"] += best[2]
        parts["decay"] += best[3]
    if detail:
        for n, e in parts.items():
            print("    %-6s rms %5.1f dB over %d" % (n, np.sqrt(np.mean(np.square(e))), len(e)))
        print("    settings:", ", ".join("%d %s %.1f" % q for q in picks))
    return float(np.sqrt(np.mean(np.square(E))))


def fit(opts):
    import tonelib as T
    import dulcimer_fit as D
    cls = T.ClavinetProperties
    rec = targets()
    names = opts.get("--params", FIT).split(",")
    global SETTINGS
    if "--setting" in opts:          # one setting for every take
        SETTINGS = (opts["--setting"],)
    print("  start:")
    error(rec, detail=True)
    D.nelder(cls, names, lambda: error(rec), STEPS, int(opts.get("--maxfev", 200)), "rms")
    error(rec, detail=True)


def ab(out, note_s):
    """Each take, then ours at v100 on the take's own pickup (the class's
    default, centre), then a rest -- Bb2, E4, F#5, each take of each;
    peak-normalised alike (harpsi_ab.fit_note)."""
    import harpsi_ab as A
    from roomtail import write_wav
    A.NOTE_S = note_s
    gap, rest = np.zeros(int(A.GAP_S * A.SR)), np.zeros(int(0.6 * A.SR))
    parts = []
    for k, x, sr in takes():
        y, sr2 = U.render(PROGRAM, k, VEL, note_s + 0.5)
        parts += [A.fit_note(x, sr), gap, A.fit_note(y, sr2), rest]
    x = np.concatenate(parts)
    write_wav(out, np.stack([x, x], 1), A.SR)


# THE KEY-UP (`keyup`): its level under the strike, the takes' -32 to -39 dB
# (mean -35), calibrated THROUGH the renderer -- the event isolated by
# rendering each note with and without it and differencing, since the
# damper falling at the same instant would otherwise hide it (the
# harpsichord's release click was calibrated the same way). Rewrites
# release_click_db in tonelib.py.
KEYUP_DB = -35.0


def keyup_level(k, hold=1.5):
    import tonelib as T
    cls = T.ClavinetProperties
    y1, sr = U.render(PROGRAM, k, VEL, hold)
    was = cls.release_click_db
    cls.release_click_db = None
    y0, _ = U.render(PROGRAM, k, VEL, hold)
    cls.release_click_db = was
    t0 = U.onset(y0, sr)
    strike = np.mean(y0[t0:t0 + int(0.05 * sr)] ** 2)
    d = (y1 - y0)[t0 + int(hold * sr) - int(0.005 * sr):t0 + int(hold * sr) + int(0.035 * sr)]
    return 10 * np.log10(np.mean(d * d) + 1e-30) - 10 * np.log10(strike)


def fit_keyup():
    import re
    import tonelib as T
    cls = T.ClavinetProperties
    lv = [keyup_level(k) for k in (46, 64, 78)]
    print("  key-up re strike, ours:", " ".join("%.1f" % v for v in lv), "dB; the takes' -35 +- 3")
    new = round(cls.release_click_db + KEYUP_DB - float(np.mean(lv)), 1)
    path = os.path.join(os.path.dirname(HERE), "tonelib.py")
    src = open(path).read()
    a = src.index("class ClavinetProperties(")
    body = re.sub(r"^    release_click_db = .*$", "    release_click_db = %.1f" % new, src[a:], count=1, flags=re.M)
    open(path, "w").write(src[:a] + body)
    cls.release_click_db = new
    print("  release_click_db -> %.1f;" % new, "now", " ".join("%.1f" % keyup_level(k) for k in (46, 64, 78)))


def keyup_ab(out):
    """Each of the takes' four key-ups, 0.5 s either side, then ours: the
    same key held 1 s and let go, the same 0.5 s either side. Each pair
    normalised to the louder of the two -- the thump is what to hear, 30-40
    dB under the strike, so turn it up."""
    from roomtail import write_wav
    from scipy.signal import resample_poly
    x, sr = U.load(TAKE)
    parts = []
    gap = np.zeros(int(0.4 * 48000))
    for t, k in zip(RELEASES, (46, 46, 64, 78)):
        a = x[int((t - 0.5) * sr):int((t + 0.5) * sr)]
        a = resample_poly(a, 48000, sr) if sr != 48000 else a
        y, sr2 = U.render(PROGRAM, k, VEL, 1.0)
        t0 = U.onset(y, sr2)
        b_ = y[t0 + int(0.5 * sr2):t0 + int(1.5 * sr2)]
        m = max(np.abs(a).max(), np.abs(b_).max(), 1e-12)
        parts += [0.5 * a / m, gap, 0.5 * b_ / m, gap, gap]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), 48000)


def main(argv):
    if argv[:1] == ["measure"]:
        measure_all("--ours" in argv)
    elif argv[:1] == ["ab"]:
        ab(argv[1], float(dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
                          .get("--note-s", 3.0)))
    elif argv[:1] == ["keyup_ab"]:
        keyup_ab(argv[1])
    elif argv[:1] == ["keyup"]:
        fit_keyup()
    elif argv[:1] == ["fit"]:
        fit(dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
