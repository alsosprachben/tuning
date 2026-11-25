#!/usr/bin/env python3
"""THE PIPE ORGAN'S STOPS BAKED FROM PIPE PHYSICS (2026-11-24: off the Piteå
recordings, the harmonium's way -- examples/harmonium_bake.py). Each class's
tone and speech come out of examples/fluepipe_sim.py run on the stop's
construction (Audsley; fluepipe_sim.STOPS); judged by Ben's ear, never
against a recording.

    python3 examples/organ_bake.py --simulate [CLASS ...]   solve, cache, print
    python3 examples/organ_bake.py --write [CLASS ...]      ...and write tonelib

THE FIRST STEP OF THE ORGAN'S BUILD (examples/organ_build.py: bake, wind,
levels, regulate). It writes each class's tables bare (fundamental 1): rerun
it and the levels and the regulation must be rerun after it.

What it writes into each class, the attributes the class already had:
  mode_gains_points   the radiated harmonics h1-h32 (amplitude re h1) at the
                      class's own anchor pitches (its rank's sounding pitch),
                      by harmonic balance followed over the compass
                      (fluepipe_sim.sweep)
  speech_cycles       the fundamental's build (10-90% = 0.608 of the ramp) in
                      periods, the median over written C2-C7 at the rank's
                      own pitch (where its pipes sound); the floor
                      attack_time is the pallet's (SPEECH_FLOOR_S)
  speech_harmonic_exp how much faster the upper harmonics build (rise ~ m^-exp,
                      h1-h3), the median over the compass
  initial_gain        re-held: the stop alone at LEVEL_KEYS renders at the
                      level it had (the console's balance, set by ear)
"""
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]
CACHE = os.path.join(ROOT, ".organ_bake_cache.json")
SPEECH_FLOOR_S = 0.004          # the pallet and the foot's first fill
SPEECH_KEYS = 6                 # written keys C2..C7 the speech is measured at (each rank at its own pitch)
LEVEL_KEYS = (48, 60, 72)

# class -> (fluepipe_sim.STOPS key, the rank's name on GM 19, writes speech?,
# its level: "hold" = where the console has it (set by ear), "sim" = the
# simulated pipe's radiated level against the simulated principal 8's, both
# on the same wind -- for the ranks whose level was a recording's balance)
CLASSES = {
    "FlueOrganProperties": ("principal", "principal 8", True, "hold"),
    "PrincipalOctave4Properties": ("octave", "octave 4", False, "hold"),
    "PrincipalOctave2Properties": ("superoctave", "super octave 2", False, "hold"),
    "OrganQuintProperties": ("quint", "quint 2-2/3", True, "hold"),
    "OrganPrincipal16Properties": ("principal16", "principal 16", True, "hold"),
    "OrganQuint513Properties": ("quint513", "quint 5-1/3", True, "hold"),
    "OrganGedaktProperties": ("gedakt", "flute 8", "modes", "hold"),
    "OrganBourdonProperties": ("bourdon16", "bourdon 16", "modes", "hold"),
    "OrganKoppelfluteProperties": ("rohrflute", "koppelflute 4", "modes", "sim"),
    "OrganWaldfluteProperties": ("waldflute", "waldflute 2", "modes", "sim"),
    "OrganNazardProperties": ("rohrflute", "nazard 2-2/3", "modes", "sim"),
    "OrganTierceProperties": ("tierce", "tierce 1-3/5", "modes", "sim"),
    "OrganSubbassProperties": ("subbass16", "subbass 16", "modes", "sim"),
    "OrganGambaProperties": ("gamba", "gamba 8", "modes", "sim"),
    "OrganCelesteProperties": ("gamba", "celeste 8", "modes", "sim"),
    # THE REEDS (examples/reedpipe_sim.py: the beating tongue against its
    # resonator's modes, in time; tone and speech both from it)
    "OrganTrumpetProperties": ("reed:trumpet", "trumpet 8", "reed", "hold"),
    "OrganClarionProperties": ("reed:clarion", "reed 4", "reed", "hold"),
    "OrganCromorneProperties": ("reed:cromorne", "reed 8", "reed", "hold"),
    "OrganBassonProperties": ("reed:basson", "reed 16", "reed", "hold"),
    "OrganTrompetteProperties": ("reed:trompette", "trompette 8", "reed", "sim"),
    "OrganOboeProperties": ("reed:oboe", "oboe 8", "reed", "sim"),
    "OrganContrabassoonProperties": ("reed:contrabassoon", "contrabassoon 32", "reed", "sim"),
    "OrganVoxHumanaProperties": ("reed:voxhumana", "vox humana 8", "reed", "sim"),
}


def _sweep(F, stop, lo, hi, start):
    """fluepipe_sim.sweep, a stop marked morph reached from the principal's
    solution first (a narrow string will not solve from a cold start)."""
    g0 = F.morph(stop, start) if F.STOPS[stop].get("morph") else None
    return F.sweep(stop, lo, hi, f_start=start, guess0=g0)
# SPEECH BY THE MODES ("modes"): the full onset (fluepipe_sim.onset) holds for
# the open principals but lets a stopped pipe's upper modes win its start; so
# a flute's speech is the PRINCIPAL'S (as written, Ben's approved voice) scaled
# by the pipes' own time constants -- a saturating resonator builds in periods
# as its fundamental mode's Q (2Q/w), its upper harmonics as their modes'
# (fluepipe_sim.mode_times: linear acoustics, from the flute's own geometry)


def _key(F, stop):
    if stop.startswith("reed:"):
        import reedpipe_sim as R
        consts = (R.ALPHA, R.TONGUE_L_CC, R.TONGUE_HALVE, R.WIDTH_RATIO, R.TONGUE_TUNE, R.Q_TONGUE, R.BEAT,
                  R.CONTACT, R.SR, F.PALLET_GENTLE_S, F.PALLET_SHARP_S, F.FOOT_RISE_S)
        return json.dumps([stop, sorted(R.STOPS[stop[5:]].items()), consts])
    s = F.STOPS[stop]
    consts = (F.JET_CP, F.JET_MU, F.JET_SPREAD, F.JET_EXP_MAX, F.ETA_SAT, F.ALPHA_VC, F.FOOT_RISE_S,
              F.PALLET_GENTLE_S, F.PALLET_SHARP_S, F.LIP_THICK_M, F.VOICE_REF_HZ, F.MIN_Q,
              getattr(F, "JET_PHASE_MAX", None))
    return json.dumps([stop, sorted(s.items()), consts])


def simulate(name, cache):
    """One class's tables and speech, from the cache where its stop and the
    simulator's constants are unchanged."""
    import fluepipe_sim as F
    import tonelib as T
    stop, rank = CLASSES[name][:2]
    k = _key(F, stop) + name
    if k in cache:
        return cache[k]
    cls = getattr(T, name)
    anchors = [a for a, _ in cls.mode_gains_points]
    ratio = next(r[1] for r in T.FlueOrganProperties.stop_ranks if r[0] == rank)
    if stop.startswith("reed:"):
        out = _reed(stop[5:], anchors, ratio)
        cache[k] = out
        with open(CACHE, "w") as f:
            json.dump(cache, f)
        return out
    keys_hz = [261.63 * ratio * 2 ** ((k - 60) / 12.0) for k in np.linspace(36, 96, SPEECH_KEYS)]
    lo, hi = min(anchors + keys_hz) * 0.97, max(anchors + keys_hz) * 1.03
    start = min(anchors, key=lambda a: abs(math.log(a / 250.0)))
    tab = _sweep(F, stop, lo, hi, start)
    top = max(tab)
    # anchors past the highest sounding pipe take its tone (the renderer holds the last anchor's anyway)
    pts = [[a, [round(10 ** (d / 20.0), 5) for d in F.at(tab, min(a, top))[1]]] for a in anchors]
    cyc, exps = [], []
    if CLASSES[name][2] == "modes":
        cyc, exps = _modes_speech(stop, [f for f in keys_hz if f <= top * 1.01])
        out = dict(points=pts, cycles=float(np.median(cyc)), exp=float(np.median(exps)),
                   cycles_all=[float(c) for c in cyc], exp_all=[float(e) for e in exps])
        cache[k] = out
        with open(CACHE, "w") as f:
            json.dump(cache, f)
        return out
    for f0 in [f for f in keys_hz if f <= top * 1.01]:
        st = F.at(tab, f0)
        tt, env, fr = F.onset(stop, f0, steady_sol=st, secs=max(0.5, 60.0 / f0))
        sf = F.speech_fit(tt, env, fr, nfit=3)
        cyc.append((sf["rises"][0] / 0.608 - SPEECH_FLOOR_S) * fr)
        exps.append(sf["exp"])
        print("    %s %.1f Hz: %.1f cycles, exp %.2f" % (name, f0, cyc[-1], exps[-1]), flush=True)
    out = dict(points=pts, cycles=float(np.median(cyc)), exp=float(np.median(exps)),
               cycles_all=[float(c) for c in cyc], exp_all=[float(e) for e in exps])
    cache[k] = out
    with open(CACHE, "w") as f:
        json.dump(cache, f)
    return out


def _reed(stop, anchors, ratio):
    """A reed class's tables at its anchors and its speech over written
    C2-C7 at its own pitch, from reedpipe_sim's time-domain tongue."""
    import fluepipe_sim as F
    import reedpipe_sim as R
    pts = []
    for a in anchors:
        # past the highest pitch that speaks, that pipe's tone (as a flue's top)
        f = a
        fp, db, lvl, info = R.tuned_tone(stop, f, secs=0.8)
        while lvl < -100 and f > 60:
            f /= 2 ** (1 / 12.0)
            fp, db, lvl, info = R.tuned_tone(stop, f, secs=0.8)
        a_play = f
        pts.append([a, [round(10 ** (d / 20.0), 5) for d in db]])
        print("    reed %s %.1f Hz (sounded at %.1f): plays %+.0f c, closed %.0f%%, h2-h5 %s" % (
            stop, a, a_play, 1200 * math.log2(fp / a_play), 100 * info["closed"],
            " ".join("%.0f" % d for d in db[1:5])), flush=True)
    cyc, exps = [], []
    for f0 in [261.63 * ratio * 2 ** ((k - 60) / 12.0) for k in np.linspace(36, 96, SPEECH_KEYS)]:
        if f0 > 4200:
            continue
        r = R.tuned_tone(stop, f0, secs=0.6)
        if r[2] < -100:
            continue
        tt, env, fp = R.envelopes(r[3]["stop"], f0, secs=max(0.4, 40.0 / f0))
        sf = F.speech_fit(tt, env, fp, nfit=3)
        if not (np.isfinite(sf["cycles"]) and sf["cycles"] > 0):
            continue
        cyc.append((sf["rises"][0] / 0.608 - SPEECH_FLOOR_S) * fp)
        exps.append(sf["exp"])
        print("    reed %s %.1f Hz: %.1f cycles, exp %.2f" % (stop, f0, cyc[-1], exps[-1]), flush=True)
    return dict(points=pts, cycles=float(np.median(cyc)), exp=float(np.median(exps)),
                cycles_all=[float(c) for c in cyc], exp_all=[float(e) for e in exps])


def _tau_exp(mt):
    """How much faster the upper harmonics build than the fundamental, as the
    exponent of rise ~ m^-exp, from their modes' time constants."""
    ms = sorted(m for m in mt if m <= 5)
    if len(ms) < 2:
        return 0.0
    x = np.log(ms)
    y = np.log([mt[m][1] / mt[1][1] for m in ms])
    return float(-np.polyfit(x, y, 1)[0])


def _modes_speech(stop, keys_hz):
    """Per key: (speech cycles, harmonic exponent) of a flute, the principal's
    as written scaled by the two pipes' mode time constants at the same pitch."""
    import fluepipe_sim as F
    import tonelib as T
    P = T.FlueOrganProperties
    cyc, exps = [], []
    for f0 in keys_hz:
        mp, mf = F.mode_times("principal", f0), F.mode_times(stop, f0)
        if 1 not in mp or 1 not in mf:
            print("    %s %.1f Hz: no fundamental mode found (skipped)" % (stop, f0))
            continue
        cyc.append(P.speech_cycles * mf[1][0] / mp[1][0])
        ep = _tau_exp(mp)
        exps.append(P.speech_harmonic_exp * (_tau_exp(mf) / ep if ep > 0 else 1.0))
        print("    %s %.1f Hz: Q1 %.1f against the principal's %.1f -> %.1f cycles, exp %.2f"
              % (stop, f0, mf[1][0], mp[1][0], cyc[-1], exps[-1]), flush=True)
    return cyc, exps


def sim_level(name, cache):
    """The simulated pipe's radiated level (dB, the simulator's own units --
    alike for every stop on the same wind), mean power over LEVEL_KEYS at the
    rank's own pitch."""
    import fluepipe_sim as F
    import tonelib as T
    stop, rank = CLASSES[name][:2]
    k = "L|" + _key(F, stop) + rank
    if k in cache:
        return cache[k]
    ratio = next(r[1] for r in T.FlueOrganProperties.stop_ranks if r[0] == rank)
    fs = [261.63 * ratio * 2 ** ((key - 60) / 12.0) for key in LEVEL_KEYS]
    if stop.startswith("reed:"):
        import reedpipe_sim as R
        pw = [10 ** (R.tuned_tone(stop[5:], f, secs=0.8)[2] / 10.0) for f in fs]
        cache[k] = float(10 * math.log10(np.mean(pw)))
        with open(CACHE, "w") as f:
            json.dump(cache, f)
        return cache[k]
    tab = _sweep(F, stop, min(fs) * 0.97, max(fs) * 1.03, min(fs, key=lambda f: abs(math.log(f / 250.0))))
    pw = [10 ** (F.at(tab, f)[2] / 10.0) for f in fs]
    cache[k] = float(10 * math.log10(np.mean(pw)))
    with open(CACHE, "w") as f:
        json.dump(cache, f)
    return cache[k]


def render_level(rank):
    """GM 19 with this one rank drawn: mean power over LEVEL_KEYS, dB."""
    import mido
    import blockrender as B
    import tonelib as T
    host = T.FlueOrganProperties
    names = [r[0] for r in host.stop_ranks]
    keep = host.default_stops
    host.default_stops = 1 << names.index(rank)
    vals = []
    try:
        for key in LEVEL_KEYS:
            m = mido.MidiFile(type=1, ticks_per_beat=480)
            t = mido.MidiTrack()
            m.tracks.append(t)
            t.append(mido.Message("program_change", channel=0, program=19, time=0))
            t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
            t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=2 * 960))
            L, R = B.render(m)[:2]
            x = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
            vals.append(np.mean(x[int(1.0 * B.SR):int(1.9 * B.SR)] ** 2))
    finally:
        host.default_stops = keep
    return 10 * np.log10(np.mean(vals))


def _fmt_points(pts):
    lines = ["    mode_gains_points = ("]
    for a, g in pts:
        body = ", ".join("%.5f" % x for x in g)
        # wrap at ~100 columns
        chunks, cur = [], ""
        for tok in body.split(", "):
            if len(cur) + len(tok) + 2 > 86:
                chunks.append(cur)
                cur = tok
            else:
                cur = tok if not cur else cur + ", " + tok
        chunks.append(cur)
        lines.append("        (%s, (%s," % (a, chunks[0]))
        for c in chunks[1:-1]:
            lines.append("                  %s," % c)
        if len(chunks) > 1:
            lines[-1] = lines[-1] if len(chunks) > 2 else lines[-1]
            lines.append("                  %s))," % chunks[-1])
        else:
            lines[-1] = lines[-1][:-1] + ")),"
    lines.append("    )")
    return "\n".join(lines)


def write_class(src, name, res, gain_expr):
    """Splice one class's baked attributes into tonelib's source."""
    i = src.index("\nclass %s(" % name) + 1
    j = src.find("\nclass ", i + 1)
    j = len(src) if j < 0 else j
    body = src[i:j]
    stop, rank, speech = CLASSES[name][:3]
    where = ("reedpipe_sim.STOPS[%r]" % stop[5:]) if stop.startswith("reed:") else ("fluepipe_sim.STOPS[%r]" % stop)
    marker = ("    # SIMULATED (examples/organ_bake.py; %s, Audsley's\n"
              "    # construction): the radiated harmonics at the rank's own pitches\n" % where)
    body = re.sub(r"(?:    # SIMULATED \(examples/organ_bake\.py[^\n]*\n(?:    #[^\n]*\n)*)?    mode_gains_points = \(\n.*?\n    \)\n",
                  lambda _m: marker + _fmt_points(res["points"]) + "\n", body, count=1, flags=re.S)
    if speech:
        how = ("the principal's scaled by\n    # its modes' time constants (fluepipe_sim.mode_times)" if speech == "modes"
               else "the tongue's attack in\n    # reedpipe_sim" if speech == "reed"
               else "fluepipe_sim.onset over\n    # the compass")
        sp = ("    # ITS SPEECH, SIMULATED (examples/organ_bake.py: " + how + ", %s cycles): periods of\n"
              "    # its own pitch, how far its upper harmonics lead (rise ~ m^-exp), the\n"
              "    # pallet's floor\n"
              "    speech_cycles = %.2f\n    speech_harmonic_exp = %.3f\n    attack_time = %.3f\n"
              % ("/".join("%.0f" % c for c in res["cycles_all"]), res["cycles"], res["exp"], SPEECH_FLOOR_S))
        pat = r"(?:    # ITS SPEECH[^\n]*\n(?:    #[^\n]*\n)*)?    speech_cycles = [^\n]*\n    speech_harmonic_exp = [^\n]*\n(?:    attack_time = [^\n]*\n)?"
        if re.search(pat, body):
            body = re.sub(pat, lambda _m: sp, body, count=1)
        else:
            body = body.replace("    mode_gains_low = None\n", "    mode_gains_low = None\n" + sp, 1)
    if gain_expr:
        why = ("the simulated pipe's level against the principal's" if CLASSES[name][3] == "sim"
               else "the console's level re-held")
        line = "    initial_gain = %s     # (organ_bake: %s)\n" % (gain_expr, why)
        if re.search(r"\n    initial_gain = [^\n]*\n", body):
            body = re.sub(r"\n    initial_gain = [^\n]*\n", lambda _m: "\n" + line, body, count=1)
        else:
            body = body.replace("    mode_gains_low = None\n", "    mode_gains_low = None\n" + line, 1)
    return src[:i] + body + src[j:]


WIND_KEYS = (36, 48, 60, 72, 84)       # written keys the wind response is read at (each rank at its pitch)


def wind_response(name, cache):
    """A class's answer to its wind, from its simulated pipe: the medians over
    the compass of its pitch and level exponents (fluepipe_sim / reedpipe_sim
    .pressure_response), and its draw as a power law of frequency, m^3/s."""
    import fluepipe_sim as F
    import tonelib as T
    stop, rank = CLASSES[name][:2]
    k = "W|" + _key(F, stop) + rank + json.dumps(F.PRESSURES)
    if k in cache:
        return cache[k]
    ratio = next(r[1] for r in T.FlueOrganProperties.stop_ranks if r[0] == rank)
    fs = [261.63 * ratio * 2 ** ((key - 60) / 12.0) for key in WIND_KEYS]
    out = []
    if stop.startswith("reed:"):
        import reedpipe_sim as R
        for f in fs:
            if f > 4200:
                continue
            r = R.pressure_response(stop[5:], f)
            if len(r["points"]) > 2:
                out.append((f, r))
    else:
        tab = _sweep(F, stop, min(fs) * 0.97, max(fs) * 1.03, min(fs, key=lambda f: abs(math.log(f / 250.0))))
        top = max(tab)
        for f in fs:
            if f > top * 1.01:
                continue
            r = F.pressure_response(stop, f, table=tab)
            if len(r["points"]) > 2:
                out.append((f, r))
    a = float(np.median([r["a"] for _, r in out]))
    b = float(np.median([r["b"] for _, r in out]))
    lf = np.log([f / 261.6 for f, _ in out])
    ld = np.log([r["draw"] for _, r in out])
    e, l0 = np.polyfit(lf, ld, 1)
    res = dict(a=a, b=b, draw_at_unit=float(math.exp(l0)), draw_exp=float(e),
               keys=[[f, r["a"], r["b"], r["draw"]] for f, r in out])
    print("  %s: pitch exp %.4f, level exp %.2f, draw %.3g m^3/s at 261.6 Hz, exp %.2f" % (
        name, a, b, res["draw_at_unit"], e), flush=True)
    cache[k] = res
    with open(CACHE, "w") as f:
        json.dump(cache, f)
    return res


def write_wind(src, name, res, unit):
    """Splice a class's wind response in: its pitch and level exponents and
    its draw law in units of the principal 8's middle C."""
    i = src.index("\nclass %s(" % name) + 1
    j = src.find("\nclass ", i + 1)
    j = len(src) if j < 0 else j
    body = src[i:j]
    body = re.sub(r"(?:    # ITS WIND, SIMULATED[^\n]*\n(?:    #[^\n]*\n)*)?(?:    wind_pitch_exp = [^\n]*\n)?"
                  r"(?:    wind_level_exp = [^\n]*\n)?(?:    wind_draw_units = [^\n]*\n)?(?:    wind_draw_exp = [^\n]*\n)?",
                  "", body)
    block = ("    # ITS WIND, SIMULATED (examples/organ_bake.py --wind: the pipe at 0.75-1.25 x\n"
             "    # its voiced pressure): pitch ~ p^a, level ~ p^b about the voiced point, and\n"
             "    # its draw (%s) in units of the principal 8's middle C, ~ (f/261.6)^e\n"
             "    wind_pitch_exp = %.5f\n    wind_level_exp = %.4f\n"
             "    wind_draw_units = %.6g\n    wind_draw_exp = %.4f\n"
             % ("the slot's flow" if CLASSES[name][0].startswith("reed:") else "the windway's flow",
                res["a"], res["b"], res["draw_at_unit"] / unit, res["draw_exp"]))
    if "    mode_gains_low = None\n" in body:
        body = body.replace("    mode_gains_low = None\n", "    mode_gains_low = None\n" + block, 1)
    else:
        raise ValueError("no anchor in " + name)
    return src[:i] + body + src[j:]


def main(argv):
    want = [a for a in argv[1:] if not a.startswith("--")] or list(CLASSES)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    if "--wind" in argv:
        res = {n: wind_response(n, cache) for n in want}
        unit = wind_response("FlueOrganProperties", cache)["draw_at_unit"]
        if "--write" in argv:
            p = os.path.join(ROOT, "tonelib.py")
            src = open(p).read()
            for n in want:
                src = write_wind(src, n, res[n], unit)
            open(p, "w").write(src)
            print("  tonelib.py written (wind)")
        return 0
    res = {n: simulate(n, cache) for n in want}
    for n, r in res.items():
        print("  %s: %.1f cycles, exp %.2f; h2-h5 at %s Hz %s" % (
            n, r["cycles"], r["exp"], r["points"][1][0] if len(r["points"]) > 1 else r["points"][0][0],
            " ".join("%.0f" % (20 * math.log10(max(g, 1e-9))) for g in r["points"][min(1, len(r["points"]) - 1)][1][1:5])))
    if "--write" not in argv:
        return 0
    import native as N
    import tonelib as T
    old = {n: render_level(CLASSES[n][1]) for n in want}
    target = dict(old)
    if any(CLASSES[n][3] == "sim" for n in want):
        p8 = render_level("principal 8")
        sp8 = sim_level("FlueOrganProperties", cache)
        for n in want:
            if CLASSES[n][3] == "sim":
                target[n] = p8 + sim_level(n, cache) - sp8
                print("  %s: level by the physics %.2f dB (was %.2f, a recording's balance)" % (n, target[n], old[n]))
    for n in want:
        cls = getattr(T, n)
        pts = tuple((a, tuple(g)) for a, g in res[n]["points"])
        cls.mode_gains_points, cls.mode_gains = pts, pts[-1][1]
        if CLASSES[n][2]:
            cls.speech_cycles, cls.speech_harmonic_exp = res[n]["cycles"], res[n]["exp"]
            cls.attack_time = SPEECH_FLOOR_S
    if "FlueOrganProperties" in want:
        T.FlueOrganProperties.bellows_push_gain = 0.0
    gains = {}
    order = sorted(want, key=lambda n: n != "FlueOrganProperties")     # the host first: the rest inherit its gain
    for n in order:
        cls = getattr(T, n)
        N.forget()
        new = render_level(CLASSES[n][1])
        g = cls.initial_gain * 10 ** ((target[n] - new) / 20.0)
        cls.initial_gain = g
        gains[n] = "%.10g" % g
        print("  %s: level %.2f -> %.2f dB, initial_gain -> %s" % (n, new, target[n], gains[n]), flush=True)
    # ...and the bare tables kept for the levels' step (organ_levels.base_points)
    bp = os.path.join(HERE, "organ_bare_tables.json")
    bare = json.load(open(bp)) if os.path.exists(bp) else {}
    for n in want:
        bare[n] = [[a, list(g)] for a, g in res[n]["points"]]
    with open(bp, "w") as f:
        json.dump(bare, f, indent=0)
    p = os.path.join(ROOT, "tonelib.py")
    src = open(p).read()
    for n in want:
        src = write_class(src, n, res[n], gains[n])
    if "FlueOrganProperties" in want:
        src = re.sub(r"\n    bellows_push_gain = 2\.801\n", "\n    bellows_push_gain = 0.0      # (organ_bake: the simulated pipe shows no overshoot mid-compass)\n", src, count=1)
    open(p, "w").write(src)
    print("  tonelib.py written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
