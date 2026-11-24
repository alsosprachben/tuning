#!/usr/bin/env python3
"""THE HARMONIUM'S STOPS BAKED INTO THE VOICE (L10, step 3: Ben, 2026-11-23).
Replaces every number examples/debain_registers.py fitted to Jean-Pierre
Silvestre's Debain (no licence stated): each stop's series, speech and level,
and the celeste's two rows, from the stops' construction
(examples/harmonium_stops.py, Mustel 1903) simulated by
examples/freereed_sim.py. The tremolo is not here (Mustel's volume does not
describe it).

THE SERIES: each stop's difference from the simulated foundation (the Cor
anglais / Flute, front), harmonic by harmonic at the stop's own pitches, both
ladders re their own total power, put onto OUR foundation's series at that
pitch (fitted to donyaquick's CC0 harmonium) -- the real case and room come
through the foundation, a case common to every stop cancels in the
difference (as the Debain's registers were fitted, now from physics).
THE SPEECH: speech_cycles = the simulated rise from 10 to 90% (tongue swing)
times the frequency, the median over the stop's pitches; speech_harmonic_exp
from when h4 reaches its level against h1. The foundation's own too.
THE LEVEL: each stop held at its simulated level re the foundation (the same
pressure), measured on our renders (initial_gain).
THE CELESTE: Mustel's own method (p. 145): one rank tuned above and one below
the true pitch, CELESTE_BEATS a second near the middle of its compass, slower
in the bass and faster in the treble.

    python3 examples/harmonium_bake.py --simulate     the stops' ladders, speech, levels (cached)
    python3 examples/harmonium_bake.py --write        into tonelib.py (series, speech, level, celeste)
    python3 examples/harmonium_bake.py --pressure     the stops' answer to the wind (step 4), into tonelib.py
    python3 examples/harmonium_bake.py --wind-simulate  each stop's level and draw, 150-1600 Pa (step 5, cached)
    python3 examples/harmonium_bake.py --wind-write     ...into tonelib.py (pressure_level_db, pressure_draw)

THE PRESSURE (step 4: the Expression stop, the feet the wind): each stop's
middle note simulated at PRESSURES; per stop -- its first 12 harmonics' gain
re 700 Pa at each (dB; the reed's low harmonics rise against its fundamental
while its upper ones fall back, so no single tilt holds), its pitch's slope
(cents a kPa: Cottingham's falling pitch), its speech's exponent (rise ~
p^-exp).
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
import harmonium_stops as H  # noqa: E402
import freereed_sim as F  # noqa: E402

NH = 32
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".harmonium_bake_cache.json")
LEVEL_KEYS = {"bass": (48, 55, 60), "treble": (72, 79, 84)}


def _played(y, f0, sr=48000):
    s = y[len(y) // 2:]
    X = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 18))
    fr = np.fft.rfftfreq(1 << 18, 1.0 / sr)
    b = (fr > f0 * 0.95) & (fr < f0 * 1.03)
    return fr[b][np.argmax(X[b])], X, fr


def ladder(y, f0, sr=48000):
    """h1..NH power (dB re the ladder's total) about the PLAYED pitch."""
    fp, X, fr = _played(y, f0, sr)
    h = np.full(NH, 1e-30)
    for k in range(1, NH + 1):
        if k * fp > 0.45 * sr:
            break
        w = (fr > k * fp * 0.99) & (fr < k * fp * 1.01)
        h[k - 1] = X[w].max() ** 2
    return 10 * np.log10(h / h.sum()), fp


def speech(v, f0, p=None):
    """(rise 10-90 % of the tongue's swing, s; h4's lag re h1 as an exponent)."""
    H._set(v)
    L, _, _ = F.tongue(f0)
    F.CURL_M = v["curl"] * L
    y, tip, fp = F.simulate(f0, (p or H.PRESSURE_PA) * v["pressure"], secs=1.2, vel=0.6)
    hop = max(1, int(48000 / f0))
    e = np.array([np.ptp(tip[i:i + 2 * hop]) for i in range(0, len(tip) - 2 * hop, hop)]) / 2
    pl = np.median(e[int(0.8 * len(e)):])
    t = np.arange(len(e)) * hop / 48000.0
    rise = t[np.argmax(e > 0.9 * pl)] - t[np.argmax(e > 0.1 * pl)]
    # harmonic entry: h1 and h4 reaching 90 % of their steady level
    n = 4096
    hp = 480
    fr = np.fft.rfftfreq(n, 1.0 / 48000)
    rows = []
    for k in range(0, len(y) - n, hp):
        X = np.abs(np.fft.rfft(y[k:k + n] * np.hanning(n)))
        rows.append([X[np.argmin(np.abs(fr - fp * m))] for m in (1, 4)])
    R = np.array(rows)
    tt = (np.arange(len(R)) * hp + n / 2) / 48000.0
    t90 = [tt[np.argmax(c > 0.9 * np.median(c[len(c) // 2:]))] for c in R.T]
    t0 = t[np.argmax(e > 0.1 * pl)]
    lag1, lag4 = max(t90[0] - t0, 1e-3), max(t90[1] - t0, 1e-3)
    return float(rise), float(-np.log(lag4 / lag1) / np.log(4.0))


def simulate():
    import tonelib as T
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    out = {}
    for name, v in [("Foundation", dict(H.FOUNDATION, cls="ReedOrganFreeProperties"))] + list(H.STOPS.items()):
        cls = getattr(T, v["cls"])
        pts = [p[0] for p in (getattr(cls, "mode_gains_points", None) or ((130.81, None), (261.63, None), (523.25, None)))]
        rec = {"points": []}
        for f0 in pts:
            ck = "%s|%.2f" % (name, f0)
            if ck not in cache:
                vv = dict(v, celeste=False)                 # (the celeste's ladder: one of its ranks)
                y = H.sound(vv, f0, secs=1.0)
                y0 = H.sound(H.FOUNDATION, f0, secs=1.0)
                hs, fp = ladder(y, f0)
                h0, _ = ladder(y0, f0)
                lv = 10 * np.log10(np.mean(y[len(y) // 2:] ** 2) / np.mean(y0[len(y0) // 2:] ** 2))
                rise, hexp = speech(vv, f0)
                cache[ck] = dict(f0=f0, played=fp, diff=list(hs - h0), level=lv, rise=rise, hexp=hexp)
                json.dump(cache, open(CACHE, "w"))
            r = cache[ck]
            rec["points"].append(r)
            print("  %-11s %6.1f Hz: level %+5.1f dB, rise %3.0f ms (%.0f cycles), h4 exp %+.2f"
                  % (name, f0, r["level"], r["rise"] * 1e3, r["rise"] * f0, r["hexp"]), flush=True)
        out[name] = rec
    return out


# ---- the write ---------------------------------------------------------------------

def foundation_series(f0):
    """Our foundation's series at f0, h1..NH (amplitude)."""
    import tonelib as T
    p = T.ReedOrganFreeProperties(f0)
    v = np.array([max(p.series_volume(m), 0.0) for m in range(1, NH + 1)])
    return v


def stop_points(rec):
    """[(f0, mode gains)]: our foundation's series times the stop's difference."""
    out = []
    for r in rec["points"]:
        base = foundation_series(r["f0"])
        b = 20 * np.log10(np.maximum(base, 1e-12))
        b -= 10 * np.log10(np.sum(10 ** (b / 10)))
        g = 10 ** ((b + np.array(r["diff"])) / 20.0)
        out.append((r["f0"], g / g.max()))
    return out


def write_class(cls, text):
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    m = re.search(r"\nclass %s\(([A-Za-z]+)\):\n    \"\"\"(.*?)\"\"\"\n" % cls.__name__, s, re.S)
    assert m, cls.__name__
    end = m.end()
    nxt = re.compile(r"\n(class |# THE VOIX CELESTE|# ---- )").search(s, end)
    s = s[:end] + text + "\n" + s[nxt.start():]
    open(p, "w").write(s)


def body(name, pts, cycles, hexp, gain):
    lines = ["    # FROM ITS CONSTRUCTION (examples/harmonium_bake.py, 2026-11-23: Mustel's",
             "    # stops simulated, harmonium_stops.STOPS['%s']; the Debain's no longer" % name,
             "    # read, licences.md L10): its difference from the simulated foundation on",
             "    # ours",
             "    mode_gains_points = ("]
    for f, t in pts:
        lines.append("        (%.1f, (%s))," % (f, ", ".join("%.5f" % v for v in t)))
    lines += ["    )",
              "    mode_gains = mode_gains_points[-1][1]      # (series_volume's switch; the top's)",
              "    mode_gains_low = None",
              "    max_harmonic = 32",
              "    bore_corner_hz = 0.0",
              "    # its own speech and decay, not the host's (blockrender's rank_is_pipe)",
              "    rank_is_pipe = True",
              "    # LEVEL: its simulated level re the foundation, held on our renders",
              "    initial_gain = %.6g" % gain,
              "    # ITS SPEECH, simulated: the tongue's rise 10-90 %% in cycles of the note",
              "    speech_cycles = %.1f" % cycles,
              "    speech_harmonic_exp = %.2f" % hexp,
              "    attack_time = 0.012"]
    return "\n".join(lines) + "\n"


VOICE = {"Bourdon": "bourdon 2", "Clarinette": "clarinette 2", "Basson": "basson 4", "Hautbois": "hautbois 4",
         "Clairon": "clairon 3", "Fifre": "fifre 3", "Musette": "musette", "Violoncelle": "violoncelle",
         "Sourdine": "sourdine", "Celeste": "celeste"}
FOUND_STOP = {"bass": "cor anglais 1", "treble": "flute 1"}


def render(stop, key, secs=2.0):
    """The stop drawn alone on GM 20, key held SECS (our renderer)."""
    import mido
    import blockrender as B
    import tonelib as T
    host = T.ReedOrganFreeProperties
    names = [r[0] for r in host.stop_ranks]
    keep = host.default_stops
    host.default_stops = 1 << names.index(stop)
    try:
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("program_change", channel=0, program=20, time=0))
        t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
        L, R = B.render(m)[:2]
    finally:
        host.default_stops = keep
    x = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
    return x, B.SR


def level_db(stop, side):
    vals = []
    for k in LEVEL_KEYS[side]:
        x, sr = render(stop, k)
        s = x[int(1.0 * sr):int(1.9 * sr)]
        vals.append(np.mean(s ** 2))
    return 10 * np.log10(np.mean(vals))


def write(res):
    import importlib
    import tonelib as T
    # the foundation's speech (the base class's own two lines)
    fr = res["Foundation"]["points"]
    fc = float(np.median([r["rise"] * r["f0"] for r in fr]))
    # (the harmonics' entry is NOT written: the measured h4-vs-h1 lag swung
    # -0.76..+1.02 between neighbouring pitches, mostly h4 FIRST -- against
    # the fundamental-first onset published (Braasch & Cottingham 2023): the
    # turbulence and the pallet's puff in the reading. All together, 0)
    fe = 0.0
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    i = s.index("class ReedOrganFreeProperties(FreeReedProperties):")
    j = s.index("\nclass ", i + 10)
    c = s[i:j]
    block = ("    # ITS SPEECH, simulated (examples/harmonium_bake.py): the tongue's rise\n"
             "    # 10-90 %% in cycles of the note, h4's lag -- the real harmonium's speech\n"
             "    # (donyaquick's, median 140 ms), not the 3 cycles it inherited\n"
             "    speech_cycles = %.1f\n    speech_harmonic_exp = %.2f\n" % (fc, fe))
    if "# ITS SPEECH, simulated (examples/harmonium_bake.py)" in c:
        c2 = re.sub(r"    # ITS SPEECH, simulated \(examples/harmonium_bake\.py\).*?speech_harmonic_exp = [^\n]*\n",
                    block.replace("\\", "\\\\"), c, count=1, flags=re.S)
    else:
        k = c.index("    default_stops = ")
        k = c.index("\n", k) + 1
        c2 = c[:k] + block + c[k:]
    s = s[:i] + c2 + s[j:]
    open(p, "w").write(s)
    print("  foundation: speech_cycles %.1f, speech_harmonic_exp %.2f" % (fc, fe))
    # each stop's series and speech (level held after)
    for name, rec in res.items():
        if name == "Foundation":
            continue
        cls = getattr(T, H.STOPS[name]["cls"])
        pts = stop_points(rec)
        cyc = float(np.median([r["rise"] * r["f0"] for r in rec["points"]]))
        hx = 0.0
        write_class(cls, body(name, pts, cyc, hx, cls.initial_gain))
        print("  %-11s written: speech_cycles %.1f, exp %.2f" % (name, cyc, hx), flush=True)
    # the celeste's rows: Mustel's +/- beats, by key
    write_celeste()
    # the levels, held on our renders against the simulated differences
    for _ in range(2):
        importlib.invalidate_caches()
        for mod in [m for m in list(sys.modules) if m in ("tonelib", "blockrender", "patch_map")]:
            del sys.modules[mod]
        import tonelib as T2  # noqa: F811
        for name, rec in res.items():
            if name == "Foundation":
                continue
            cls = getattr(T2, H.STOPS[name]["cls"])
            stop = VOICE[name]
            side = "bass" if dict((r[0], r) for r in T2.ReedOrganFreeProperties.stop_ranks)[stop][-1][0] == 0 \
                else "treble"
            want = float(np.median([r["level"] for r in rec["points"]]))
            have = level_db(stop, side) - level_db(FOUND_STOP[side], side)
            g = cls.initial_gain * 10 ** ((want - have) / 20.0)
            s = open(p).read()
            k = s.index("class %s(" % cls.__name__)
            m = re.compile(r"    initial_gain = [0-9.e+-]+\n").search(s, k)
            s = s[:m.start()] + "    initial_gain = %.6g\n" % g + s[m.end():]
            open(p, "w").write(s)
            print("  %-11s level: want %+5.1f dB re the foundation, had %+5.1f -> gain %.4g"
                  % (name, want, have, g), flush=True)


CELESTE_BEATS = H.CELESTE_BEATS
CELESTE_REF_HZ = H.CELESTE_REF_HZ
CELESTE_BEAT_EXP = H.CELESTE_BEAT_EXP


def write_celeste():
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    rows = {}
    for k in range(65, 97):
        f = 0.5 * 440.0 * 2.0 ** ((k - 69) / 12.0)          # (16': the key's octave below)
        b = CELESTE_BEATS * (f / CELESTE_REF_HZ) ** CELESTE_BEAT_EXP
        rows[k] = round(1200.0 * np.log2((f + b / 2.0) / f), 2), round(1200.0 * np.log2((f - b / 2.0) / f), 2)
    i = s.index("# THE VOIX CELESTE'S DETUNE, in cents.")
    j = s.index("\n# The split:", i)
    mid = np.median([a - b for a, b in rows.values()])
    s = s[:i] + ("# THE VOIX CELESTE'S DETUNE, in cents: MUSTEL'S OWN METHOD (L'Orgue-Expressif\n"
                 "# p. 145; since 2026-11-23, the Debain's measured rows no longer read,\n"
                 "# licences.md L10): two ranks, one tuned above and one below the true pitch,\n"
                 "# %.0f beats a second at %.0f Hz, slower in the bass, faster in the treble\n"
                 "# (beats ~ f^%.1f, examples/harmonium_bake.py). The nominal spread:\n"
                 "HARMONIUM_CELESTE_CENTS = %.1f\n" % (CELESTE_BEATS, CELESTE_REF_HZ, CELESTE_BEAT_EXP, mid)) + s[j:]
    i = s.index("# THE VOIX CELESTE'S TWO ROWS, key by key")
    j = s.index("\n# (name, footage ratio, gain", i)
    lines = ["# THE VOIX CELESTE'S TWO ROWS, key by key: (above, below) in cents re the",
             "# key's 16-foot (examples/harmonium_bake.py, Mustel's rule)",
             "HARMONIUM_CELESTE_BY_KEY = {"]
    items = sorted(rows.items())
    for n in range(0, len(items), 4):
        lines.append("    " + "  ".join("%d: (%+.2f, %+.2f)," % (k, a, b) for k, (a, b) in items[n:n + 4]))
    lines.append("}")
    s = s[:i] + "\n".join(lines) + "\n" + s[j:]
    s = s.replace("""    ("celeste",       (0.5, 0.5 * 2.0 ** (HARMONIUM_CELESTE_CENTS / 1200.0)), 0.70,""",
                  """    ("celeste",       (0.5 * 2.0 ** (-HARMONIUM_CELESTE_CENTS / 2400.0),
                       0.5 * 2.0 ** (HARMONIUM_CELESTE_CENTS / 2400.0)), 0.70,""")
    s = s.replace("""    (440.0 * 2.0 ** ((_k - 69.5) / 12.0), (0.5, 0.5 * 2.0 ** (_c / 1200.0)))
    for _k, _c in sorted(HARMONIUM_CELESTE_BY_KEY.items())]}""",
                  """    (440.0 * 2.0 ** ((_k - 69.5) / 12.0), (0.5 * 2.0 ** (_b / 1200.0), 0.5 * 2.0 ** (_a / 1200.0)))
    for _k, (_a, _b) in sorted(HARMONIUM_CELESTE_BY_KEY.items())]}""")
    open(p, "w").write(s)
    print("  celeste: rows +/-, %.1f cents apart at the middle" % mid)


PRESSURES = (300.0, 500.0, 700.0, 1000.0, 1500.0)


def pressure_simulate():
    import tonelib as T
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    out = {}
    for name, v in [("Foundation", dict(H.FOUNDATION, cls="ReedOrganFreeProperties"))] + list(H.STOPS.items()):
        pts = getattr(getattr(T, v["cls"]), "mode_gains_points", None)
        f0 = pts[len(pts) // 2][0] if pts else 261.63
        rows = []
        for p in PRESSURES:
            ck = "P|%s|%.2f|%.0f" % (name, f0, p)
            if ck not in cache:
                keep = H.PRESSURE_PA
                H.PRESSURE_PA = p
                vv = dict(v, celeste=False)
                y = H.sound(vv, f0, secs=1.0)
                lad, fp = ladder(y, f0)
                rise, _ = speech(vv, f0, p=p)
                H.PRESSURE_PA = keep
                cache[ck] = dict(p=p, f0=f0, played=fp, lad=list(lad), rise=rise)
                json.dump(cache, open(CACHE, "w"))
            rows.append(cache[ck])
        out[name] = rows
    return out


def pressure_fit(rows):
    """(((p, 12 gains dB re 700 Pa), ...), cents a kPa, speech exponent) --
    pressures where the stop barely speaks (its level far down) left out."""
    ref = next(r for r in rows if r["p"] == 700.0)
    good = [r for r in rows if np.isfinite(r["rise"]) and r["rise"] > 0]
    L0 = np.array(ref["lad"][:12])
    tab = []
    for r in good:
        if r["p"] == 700.0:
            continue
        d = np.array(r["lad"][:12]) - L0
        tab.append((r["p"], tuple(round(float(x), 2) for x in d - d[0])))   # (re its h1: shape, the level CC11's)
    P = np.array([r["p"] for r in good]) / 1000.0
    c = np.array([1200 * np.log2(r["played"] / r["f0"]) for r in good])
    cs = float(np.polyfit(P, c, 1)[0])
    a = float(-np.polyfit(np.log(P), np.log([r["rise"] for r in good]), 1)[0])
    return tuple(tab), cs, a


def pressure_write(res):
    import tonelib as T
    p = os.path.join(HERE, "tonelib.py")
    for name, rows in res.items():
        tab, cs, a = pressure_fit(rows)
        if name == "Sourdine":                       # (its throttle: at 300 Pa it barely speaks)
            tab = tuple(t for t in tab if t[0] >= 500.0)
        cname = "ReedOrganFreeProperties" if name == "Foundation" else H.STOPS[name]["cls"]
        s = open(p).read()
        i = s.index("class %s(" % cname)
        j = s.index("\nclass ", i + 10)
        c = s[i:j]
        c = re.sub(r"    # ITS ANSWER TO THE WIND.*?pressure_speech_exp = [^\n]*\n", "", c, flags=re.S)
        lines = ["    # ITS ANSWER TO THE WIND (examples/harmonium_bake.py --pressure: the",
                 "    # Expression stop, the feet the wind): its first 12 harmonics' gain re",
                 "    # 700 Pa at each pressure (dB, re its h1), its pitch's slope, its speech's",
                 "    # exponent -- simulated",
                 "    pressure_gains_db = ("]
        for pp, g in tab:
            lines.append("        (%.0f, (%s))," % (pp, ", ".join("%.2f" % x for x in g)))
        lines += ["    )",
                  "    pressure_cents_per_kpa = %.2f" % cs,
                  "    pressure_speech_exp = %.3f" % a]
        k = c.index("    initial_gain = ") if "    initial_gain = " in c else c.index("    default_stops = ")
        k = c.index("\n", k) + 1
        c = c[:k] + "\n".join(lines) + "\n" + c[k:]
        s = s[:i] + c + s[j:]
        open(p, "w").write(s)
        print("  %-11s %d pressures, %+.1f cents/kPa, speech exp %.2f" % (name, len(tab), cs, a), flush=True)


# THE WIND (step 5): each stop's absolute level and the wind its reeds draw,
# across the pressures a harmonium's wind reaches -- near each reed's threshold
# too, where its swing collapses ("le Pianissimo, qui disparait meme", Mustel
# p. 78) -- and its draw across the keyboard. The level law and the draw are
# what the shared wind (wind.py's HarmoniumWind) and its rows read.
WIND_PRESSURES = (60.0, 80.0, 100.0, 120.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 700.0, 1000.0, 1300.0, 1600.0)


def _wind_one(job):
    name, v, f0, p = job
    keep = H.PRESSURE_PA
    H.PRESSURE_PA = p
    y = H.sound(dict(v, celeste=False), f0, secs=1.6)
    H.PRESSURE_PA = keep
    s = y[-int(0.3 * 48000):]
    lv = 10.0 * np.log10(np.mean(s ** 2) + 1e-30)
    return "W|%s|%.2f|%.0f" % (name, f0, p), dict(p=p, f0=f0, level_db=float(lv), flow=float(F.LAST_FLOW))


def _stop_keys(cls_name):
    import tonelib as T
    pts = getattr(getattr(T, cls_name), "mode_gains_points", None)
    if not pts:
        return 130.81, 261.63, 523.25
    return pts[0][0], pts[len(pts) // 2][0], pts[-1][0]


def wind_simulate(procs=6):
    from multiprocessing import Pool
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    jobs = []
    for name, v in [("Foundation", dict(H.FOUNDATION, cls="ReedOrganFreeProperties"))] + list(H.STOPS.items()):
        lo, mid, hi = _stop_keys(v["cls"])
        for p in WIND_PRESSURES:
            jobs.append((name, v, mid, p))
        for f0 in (lo, hi):
            jobs.append((name, v, f0, 700.0))
    todo = [j for j in jobs if "W|%s|%.2f|%.0f" % (j[0], j[2], j[3]) not in cache]
    print("  %d runs, %d cached" % (len(jobs), len(jobs) - len(todo)), flush=True)
    with Pool(procs) as pool:
        for k, rec in pool.imap_unordered(_wind_one, todo):
            cache[k] = rec
            json.dump(cache, open(CACHE, "w"))
            print("  %s: %.1f dB, %.3f l/s" % (k, rec["level_db"], rec["flow"] * 1000.0), flush=True)
    return cache


def wind_fit(cache):
    """{stop: (level table ((p, dB re 700),...), (q at f_mid, f_mid, f exponent),
    flow's pressure exponent)}"""
    out = {}
    for name, v in [("Foundation", dict(H.FOUNDATION, cls="ReedOrganFreeProperties"))] + list(H.STOPS.items()):
        lo, mid, hi = _stop_keys(v["cls"])
        rows = [cache["W|%s|%.2f|%.0f" % (name, mid, p)] for p in WIND_PRESSURES]
        L0 = next(r["level_db"] for r in rows if r["p"] == 700.0)
        lev = tuple((r["p"], round(r["level_db"] - L0, 2)) for r in rows)
        fq = [(f, cache["W|%s|%.2f|700" % (name, f)]["flow"]) for f in (lo, mid, hi)]
        fe = float(np.polyfit(np.log([f for f, _ in fq]), np.log([q for _, q in fq]), 1)[0])
        pp = [r for r in rows if r["p"] >= 300.0]          # (where every reed speaks)
        pe = float(np.polyfit(np.log([r["p"] for r in pp]), np.log([r["flow"] for r in pp]), 1)[0])
        out[name] = (lev, (fq[1][1], mid, fe), pe)
    return out


def wind_write(cache):
    p = os.path.join(HERE, "tonelib.py")
    fit = wind_fit(cache)
    for name, (lev, draw, pe) in fit.items():
        cname = "ReedOrganFreeProperties" if name == "Foundation" else H.STOPS[name]["cls"]
        s = open(p).read()
        i = s.index("class %s(" % cname)
        j = s.index("\nclass ", i + 10)
        c = s[i:j]
        c = re.sub(r"    # ITS LEVEL AND ITS DRAW.*?pressure_draw = [^\n]*\n", "", c, flags=re.S)
        lines = ["    # ITS LEVEL AND ITS DRAW (examples/harmonium_bake.py --wind: the harmonium's",
                 "    # wind, wind.HarmoniumWind): its level at each pressure, dB re 700 Pa -- near",
                 "    # threshold its swing collapses -- and the wind its reed draws at 700 Pa",
                 "    # (m3/s at f, f, the exponent across the keyboard) -- simulated",
                 "    pressure_level_db = (" + ", ".join("(%.0f, %.2f)" % x for x in lev) + ")",
                 "    pressure_draw = (%.4e, %.2f, %.3f)" % draw]
        k = c.index("    pressure_speech_exp = ")
        k = c.index("\n", k) + 1
        c = c[:k] + "\n".join(lines) + "\n" + c[k:]
        s = s[:i] + c + s[j:]
        open(p, "w").write(s)
        print("  %-11s level %+.1f dB at 200 Pa, %+.1f at 1600; draw %.2f l/s at %.0f Hz, f^%.2f; flow p^%.2f"
              % (name, dict(lev)[200.0], dict(lev)[1600.0], draw[0] * 1000, draw[1], draw[2], pe), flush=True)
    pes = [pe for _, _, pe in fit.values()]
    print("  the instrument's draw exponent (median): %.3f" % float(np.median(pes)))


if __name__ == "__main__":
    if "--wind-simulate" in sys.argv:
        wind_simulate()
    if "--wind-write" in sys.argv:
        wind_write(json.load(open(CACHE)))
    if "--pressure" in sys.argv:
        pressure_write(pressure_simulate())
    if "--simulate" in sys.argv:
        r = simulate()
    if "--write" in sys.argv:
        write(simulate())
