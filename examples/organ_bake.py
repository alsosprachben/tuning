#!/usr/bin/env python3
"""THE PIPE ORGAN'S STOPS BAKED FROM PIPE PHYSICS (2026-11-24: off the Piteå
recordings, the harmonium's way -- examples/harmonium_bake.py). Each class's
tone and speech come out of examples/fluepipe_sim.py run on the stop's
construction (Audsley; fluepipe_sim.STOPS); judged by Ben's ear, never
against a recording.

    python3 examples/organ_bake.py --simulate [CLASS ...]   solve, cache, print
    python3 examples/organ_bake.py --write [CLASS ...]      ...and write tonelib

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

# class -> (fluepipe_sim.STOPS key, the rank's name on GM 19, writes speech?)
CLASSES = {
    "FlueOrganProperties": ("principal", "principal 8", True),
    "PrincipalOctave4Properties": ("octave", "octave 4", False),
    "PrincipalOctave2Properties": ("superoctave", "super octave 2", False),
    "OrganQuintProperties": ("quint", "quint 2-2/3", True),
    "OrganPrincipal16Properties": ("principal16", "principal 16", True),
    "OrganQuint513Properties": ("quint513", "quint 5-1/3", True),
}


def _key(F, stop):
    s = F.STOPS[stop]
    consts = (F.JET_CP, F.JET_MU, F.JET_SPREAD, F.JET_EXP_MAX, F.ETA_SAT, F.ALPHA_VC, F.FOOT_RISE_S,
              F.PALLET_GENTLE_S, F.PALLET_SHARP_S, F.LIP_THICK_M, F.VOICE_REF_HZ, F.MIN_Q)
    return json.dumps([stop, sorted(s.items()), consts])


def simulate(name, cache):
    """One class's tables and speech, from the cache where its stop and the
    simulator's constants are unchanged."""
    import fluepipe_sim as F
    import tonelib as T
    stop, rank, _ = CLASSES[name]
    k = _key(F, stop) + name
    if k in cache:
        return cache[k]
    cls = getattr(T, name)
    anchors = [a for a, _ in cls.mode_gains_points]
    ratio = next(r[1] for r in T.FlueOrganProperties.stop_ranks if r[0] == rank)
    keys_hz = [261.63 * ratio * 2 ** ((k - 60) / 12.0) for k in np.linspace(36, 96, SPEECH_KEYS)]
    lo, hi = min(anchors + keys_hz) * 0.97, max(anchors + keys_hz) * 1.03
    start = min(anchors, key=lambda a: abs(math.log(a / 250.0)))
    tab = F.sweep(stop, lo, hi, f_start=start)
    top = max(tab)
    # anchors past the highest sounding pipe take its tone (the renderer holds the last anchor's anyway)
    pts = [[a, [round(10 ** (d / 20.0), 5) for d in F.at(tab, min(a, top))[1]]] for a in anchors]
    cyc, exps = [], []
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
    stop, rank, speech = CLASSES[name]
    marker = ("    # SIMULATED (examples/organ_bake.py; fluepipe_sim.STOPS[%r], Audsley's\n"
              "    # construction): the radiated harmonics at the rank's own pitches\n" % stop)
    body = re.sub(r"(?:    # SIMULATED \(examples/organ_bake\.py[^\n]*\n(?:    #[^\n]*\n)*)?    mode_gains_points = \(\n.*?\n    \)\n",
                  lambda _m: marker + _fmt_points(res["points"]) + "\n", body, count=1, flags=re.S)
    if speech:
        sp = ("    # ITS SPEECH, SIMULATED (examples/organ_bake.py: fluepipe_sim.onset over\n"
              "    # the compass, %s cycles): periods of its own pitch, how far its\n"
              "    # upper harmonics lead (rise ~ m^-exp), the pallet's floor\n"
              "    speech_cycles = %.2f\n    speech_harmonic_exp = %.3f\n    attack_time = %.3f\n"
              % ("/".join("%.0f" % c for c in res["cycles_all"]), res["cycles"], res["exp"], SPEECH_FLOOR_S))
        pat = r"(?:    # ITS SPEECH[^\n]*\n(?:    #[^\n]*\n)*)?    speech_cycles = [^\n]*\n    speech_harmonic_exp = [^\n]*\n(?:    attack_time = [^\n]*\n)?"
        if re.search(pat, body):
            body = re.sub(pat, lambda _m: sp, body, count=1)
        else:
            body = body.replace("    mode_gains_low = None\n", "    mode_gains_low = None\n" + sp, 1)
    if gain_expr:
        line = "    initial_gain = %s     # (organ_bake: the console's level re-held)\n" % gain_expr
        if re.search(r"\n    initial_gain = [^\n]*\n", body):
            body = re.sub(r"\n    initial_gain = [^\n]*\n", lambda _m: "\n" + line, body, count=1)
        else:
            body = body.replace("    mode_gains_low = None\n", "    mode_gains_low = None\n" + line, 1)
    return src[:i] + body + src[j:]


def main(argv):
    want = [a for a in argv[1:] if not a.startswith("--")] or list(CLASSES)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
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
        g = cls.initial_gain * 10 ** ((old[n] - new) / 20.0)
        cls.initial_gain = g
        gains[n] = "%.10g" % g
        print("  %s: level %.2f -> %.2f dB, initial_gain -> %s" % (n, new, old[n], gains[n]), flush=True)
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
