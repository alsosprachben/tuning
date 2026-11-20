#!/usr/bin/env python3
"""THE WURLITZER 4500'S UPPER TABS AS ITS CIRCUIT (Ben's organ; its service
schematics, ~/Documents/refs/wurlitzer_ben/schematics/straf_upper_653542.md):
each tab is the divider's square waves through that tab's own network, the
component values off the drawing, into its pre-amp -- then one response shared
by every tab (the console's amplifier and speaker, and the garage the takes
were made in), fitted with each tab's level to Ben's recordings.

    python3 examples/wurlitzer_circuit.py [--py] [--plot=OUT.png]

THE SOURCES (typical keying 653544, upper keying 652569): each key switches
the generator's square waves -- one oscillator a note name, octaves divided
down: exact 2:1, in phase -- onto the 16', 8', 5-1/3' and 4' busses (100K
each); and through 2.2K each, the 8', 4' and 2' squares together, the
"complex" signal (no 16': the takes have nothing at the half-harmonics), a
near-sawtooth (every harmonic but the eighths), through the diode keyer; the
"flute" signal is the same through each range's LC filter (notes 1-25, 26-37,
38-49, 50-61, 62-72 of the generator: C1 = 1) and 220K + 220K into 0.022 µF.

THE TABS (straf upper 653542), each a network from its source to its sum,
loaded by the pre-amp's input (RLOAD). Fitted, beside the shared response: each
tab's level (the transistor stages' gains, the keyer's, the Solo/Accent
shunts), the complex signal's octave weights, and the flute filter's corner
factor. Not fitted: every R, C and L, as drawn.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

K, U, M = 1e3, 1e-6, 1e-3
RLOAD = 4.7 * K          # a pre-amp's input: its base divider and 470 Ω, roughly

# NETWORKS: (element, node a, node b, value); "s" the source, "o" the sum (loaded
# by RLOAD), "g" ground. From the drawing; where a far end went up the page and
# joined the ground line, it is "g".
NETS = {
    # 16' bus -> TR1
    "Tibia 16'": [("R", "s", "r", 10 * K), ("C", "r", "g", 0.15 * U), ("L", "r", "n", 3.45),
                  ("C", "n", "g", 0.068 * U), ("R", "n", "o", 33 * K)],
    "Bass Clarinet 16'": [("C", "s", "c", 0.047 * U), ("R", "c", "g", 10 * K), ("R", "c", "a", 10 * K),
                          ("C", "a", "g", 0.027 * U), ("R", "a", "o", 10 * K)],
    "Trombone 16'": [("R", "s", "b", 10 * K), ("C", "b", "g", 0.15 * U), ("L", "b", "n", 1.0),
                     ("C", "n", "g", 0.22 * U), ("R", "n", "o", 47 * K)],
    # 8' -> TR2 (the Flute off the flute bus, the rest off the complex)
    "Flute 8'": [("R", "s", "o", 2.2 * K)],
    "Diapason 8'": [("R", "s", "o", 12 * K)],          # (its 82K branch through the inverter: DIAPASON_INV)
    "String 8'": [("R", "s", "b", 15 * K), ("C", "b", "a", 0.0082 * U), ("R", "a", "g", 10 * K),
                  ("C", "a", "g", 0.01 * U), ("R", "a", "o", 82 * K)],
    "Clarinet 8'": [("R", "s", "a", 10 * K), ("C", "a", "b", 0.022 * U), ("C", "b", "g", 0.033 * U),
                    ("R", "b", "o", 15 * K)],
    "Oboe 8'": [("R", "s", "p", 560.0), ("C", "p", "t", 0.0039 * U), ("L", "t", "g", 0.415),
                ("C", "t", "g", 0.027 * U), ("R", "t", "o", 12 * K)],
    "Trumpet 8'": [("R", "s", "p", 470.0), ("C", "p", "g", 0.022 * U), ("L", "p", "b", 1.0),
                   ("C", "b", "g", 0.01 * U), ("C", "b", "c", 0.0039 * U), ("R", "c", "o", 33 * K)],
    "Kinura 8'": [("R", "s", "a", 3.3 * K), ("C", "a", "t", 0.0039 * U), ("L", "t", "g", 0.415),
                  ("R", "t", "o", 22 * K)],
    # 5-1/3' bus -> TR1; 4' bus -> the 8' sum
    "Quint 5-1/3'": [("R", "s", "a", 5.6 * K), ("C", "a", "g", 0.068 * U), ("R", "a", "b", 5.6 * K),
                     ("C", "b", "g", 0.068 * U), ("R", "b", "o", 4.7 * K)],
    "Clarinet 4'": [("R", "s", "a", 10 * K), ("C", "a", "b", 0.015 * U), ("C", "b", "g", 0.033 * U),
                    ("R", "b", "o", 12 * K)],
}
DIAPASON_INV = [("R", "s", "a", 10 * K), ("C", "a", "g", 0.033 * U), ("R", "a", "b", 10 * K),
                ("C", "b", "g", 0.01 * U), ("R", "b", "o", 82 * K)]
# each tab's source and its footage (x the key's 8' pitch)
SOURCE = {"Tibia 16'": ("sq", 0.5), "Bass Clarinet 16'": ("sq", 0.5), "Trombone 16'": ("sq", 0.5),
          "Flute 8'": ("flute", 1.0), "Diapason 8'": ("cx", 1.0), "String 8'": ("cx", 1.0),
          "Clarinet 8'": ("sq", 1.0), "Oboe 8'": ("cx", 1.0), "Trumpet 8'": ("cx", 1.0),
          "Kinura 8'": ("cx", 1.0), "Quint 5-1/3'": ("sq", 1.5), "Clarinet 4'": ("sq", 2.0)}
# the flute range filters' resonances (Hz) by generator note
FLUTE_RANGES = ((25, (165.0, 202.0)), (37, (280.0, 313.0)), (49, (732.0, 732.0)), (61, (1013.0, 1209.0)),
                (72, (2005.0, 5671.0)))


def transfer(net, f, rload=None):
    """V(o)/V(s) of NET at frequencies F (complex), "o" loaded by RLOAD"""
    rload = RLOAD if rload is None else rload
    nodes = sorted({n for _, a, b, _ in net for n in (a, b)} - {"s", "g"})
    idx = {n: i for i, n in enumerate(nodes)}
    out = np.empty(len(f), complex)
    for k, fk in enumerate(f):
        w = 2 * math.pi * fk
        Y = np.zeros((len(nodes), len(nodes)), complex)
        I = np.zeros(len(nodes), complex)

        def stamp(a, b, y):
            for p, q, s in ((a, a, 1), (b, b, 1), (a, b, -1), (b, a, -1)):
                if p in idx and q in idx:
                    Y[idx[p], idx[q]] += s * y
            # the source node at 1 V: its current into the other node
            if a == "s" and b in idx:
                I[idx[b]] += y
            if b == "s" and a in idx:
                I[idx[a]] += y
        for t, a, b, v in net:
            y = 1 / v if t == "R" else (1j * w * v if t == "C" else 1 / (1j * w * v))
            stamp(a, b, y)
        stamp("o", "g", 1 / rload)
        out[k] = np.linalg.solve(Y, I)[idx["o"]]
    return out


DUTY = [0.5]
# (fitted: the Trombone 16''s share of the 8' square beside its 16' -- its 2nd harmonic is
#  its strongest, which no square makes; and the Diapason's 82K branch's gain against its
#  12K, signed: through the inverter it is negative)
MIX = {"trombone8": 0.0, "diap_inv": -1.0}            # the dividers' duty cycle: a flip-flop's halves never quite equal (fitted)


def square(n, d=None):
    """a pulse wave of duty D's harmonics 1..n (a square at 0.5: 1/k on the odd, 0 on the even)"""
    d = DUTY[0] if d is None else d
    k = np.arange(1, n + 1)
    return np.abs(np.sin(math.pi * k * d)) / k


def complex_series(n, w):
    """the 8', 4' and 2' squares together (weights w8, w4, w2) at the 8''s harmonic numbers"""
    out = np.zeros(n)
    for wt, m in zip(w, (1, 2, 4)):
        sq = square(n // m + 1)
        for j in range(1, n // m + 1):
            out[j * m - 1] += wt * sq[j - 1] if j - 1 < len(sq) else 0.0
    return out


def flute_lp(f, key_hz, fc_scale):
    """the flute range filter of the generator note at KEY_HZ: its two resonances as 2-pole
    low-passes (Q 0.7), the corners x fc_scale; then 440K into 0.022 µF"""
    note = int(round(12 * math.log2(key_hz / 32.703))) + 1
    fr = next((r for top, r in FLUTE_RANGES if note <= top), FLUTE_RANGES[-1][1])   # (past the top: the last)
    h = np.ones(len(f), complex)
    for fc in fr:
        s = 1j * f / (fc * fc_scale)
        h *= 1 / (1 + s / 0.7 + s * s)
    return h / (1 + 1j * f / (1 / (2 * math.pi * 440e3 * 0.022e-6)))


def tab_series(name, key_hz, n, w, fc_scale):
    """the tab's voltage at its sum, harmonics 1..n of its own sounding pitch (complex)"""
    kind, ft = SOURCE[name]
    f0 = key_hz * ft
    f = f0 * np.arange(1, n + 1)
    if kind == "sq":
        src = square(n).astype(complex)
        if name == "Trombone 16'":                    # (and the 8' square, at its even harmonics)
            s8 = np.zeros(n)
            s8[1::2] = square(n // 2 + 1)[:len(s8[1::2])]
            src = src + MIX["trombone8"] * s8
    else:
        src = complex_series(n, w).astype(complex)
        if kind == "flute":
            src = src * flute_lp(f, key_hz, fc_scale)
    h = transfer(NETS[name], f)
    if name == "Diapason 8'":
        h = h + MIX["diap_inv"] * transfer(DIAPASON_INV, f)     # (its 82K branch, through TR3)
    return f, src * h


def measured(nh=24):
    """Ben's take 2 (every Solo and the Accent on): each tab's harmonics (linear) by key"""
    import wurlitzer_fit as WF
    import wurlitzer_survey as WS
    x2 = WS.load("2", WS.REF)
    out = []
    for name, take, (a, b), fac, man in WS.TABS:
        if man != "upper":
            continue
        notes = WS.runs(x2, a, b)
        keys = [WS.C3 * m for m in (1, 2, 4)][3 - len(notes):]
        for (s, e), kh in zip(notes, keys):
            seg = x2[int((s + 0.3) * WS.SR):int((e - 0.12) * WS.SR)]
            f0, _ = WS.spectrum(seg, kh * fac * 0.983)
            tb = np.array(WF.table(seg, f0)[:nh])
            out.append((name, kh * 0.983, f0, tb))
    return out


KNOTS = np.array([40, 63, 100, 160, 250, 400, 630, 1000, 1600, 2500, 4000, 6300, 10000.0])
# THE SPEAKER, NOT THE GARAGE (Ben: the takes were made in a garage, concrete floor and
# full of things; the model is the organ dry). So the shared response is a SPEAKER's few
# parameters, never a free curve that could learn the room's modes: a 2nd-order high-pass
# (the cabinet's low end), a 2nd-order low-pass (the cones' top), and one shelf where the
# 12" hands over to the 6x9" -- its frequency and its step.
SPEAKER = ["fhp", "flp", "fshelf", "shelf_db"]


def response_db(f, r):
    fhp, flp, fsh, sh = np.exp(r[0]), np.exp(r[1]), np.exp(r[2]), r[3]
    s = 1j * f
    hp = (s / fhp) ** 2 / (1 + s / fhp / 0.7 + (s / fhp) ** 2)
    lp = 1 / (1 + s / flp / 0.7 + (s / flp) ** 2)
    shelf = sh / 2 * np.tanh(2 * np.log2(f / fsh))
    return 20 * np.log10(np.abs(hp * lp)) + shelf


def fit(data, nh=24):
    from scipy.optimize import least_squares
    names = sorted({d[0] for d in data})

    def unpack(p):
        g = dict(zip(names, p[:len(names)]))
        w = np.exp(p[len(names):len(names) + 2])
        fcs = math.exp(p[len(names) + 2])
        DUTY[0] = 0.5 - 0.1 / (1 + math.exp(-p[len(names) + 3]))
        MIX["trombone8"] = math.exp(p[len(names) + 4])
        MIX["diap_inv"] = p[len(names) + 5]
        r = p[len(names) + 6:]
        return g, (1.0, w[0], w[1]), fcs, r

    def resid(p):
        g, w, fcs, r = unpack(p)
        out = []
        for name, kh, f0, tb in data:
            f, v = tab_series(name, kh, nh, w, fcs)
            model = 20 * np.log10(np.abs(v) + 1e-12) + response_db(f, r) + g[name]
            m = tb > 0
            meas = 20 * np.log10(tb[m])
            # only harmonics within 45 dB of the note's strongest: the rest is the room's floor
            keep = meas > meas.max() - 45
            out.append(np.clip(model[m][keep] - meas[keep], -30, 30))

        return np.concatenate(out)
    p0 = np.concatenate([np.zeros(len(names)), [0.0, 0.0, 0.0, -2.0, -1.0, -1.0], [math.log(60.0), math.log(6000.0), math.log(800.0), -6.0]])
    # (every fitted number held where the parts allow: the flute filter's coils and caps
    #  within their tolerance, a console cabinet's low end, cones' top, the 12"/6x9" handover)
    n = len(names)
    lo = np.full(len(p0), -np.inf)
    hi = np.full(len(p0), np.inf)
    lo[n:n + 2], hi[n:n + 2] = math.log(0.05), math.log(1.0)          # (the 4' and 2' squares' shares)
    lo[n + 2], hi[n + 2] = math.log(0.8), math.log(1.25)              # (the flute filters: +-20 %)
    lo[n + 4], hi[n + 4] = math.log(0.05), math.log(2.0)
    lo[n + 5], hi[n + 5] = -100.0, 100.0
    r0 = n + 6
    lo[r0], hi[r0] = math.log(30.0), math.log(120.0)
    lo[r0 + 1], hi[r0 + 1] = math.log(3000.0), math.log(10000.0)
    lo[r0 + 2], hi[r0 + 2] = math.log(400.0), math.log(2000.0)
    lo[r0 + 3], hi[r0 + 3] = -12.0, 6.0
    p0 = np.clip(p0, lo + 1e-6, hi - 1e-6)
    sol = least_squares(resid, p0, loss="soft_l1", f_scale=3.0, max_nfev=600, bounds=(lo, hi))
    return unpack(sol.x), sol


def main(argv):
    data = measured()
    (g, w, fcs, r), sol = fit(data)
    if "--py" in argv:
        with open(os.path.expanduser("~/Documents/refs/wurlitzer_ben/circuit_tables.py.txt"), "w") as fh:
            fh.write(emit_py(tables((g, w, fcs, r))) + "\n")
    print("complex octave weights (8', 4', 2'): %.2f %.2f %.2f   flute corner x%.2f   divider duty %.3f"
          % (w + (fcs, DUTY[0])))
    print("Trombone's 8' share %.2f; Diapason's 82K branch %+.2f x its 12K" % (MIX["trombone8"], MIX["diap_inv"]))
    print("speaker: high-pass %.0f Hz, low-pass %.0f Hz, shelf %+.1f dB at %.0f Hz" % (
        math.exp(r[0]), math.exp(r[1]), r[3], math.exp(r[2])))
    print("\n%-18s %8s  %s" % ("tab", "key Hz", "rms dB (harmonics within 45 dB of its strongest)"))
    per = {}
    for name, kh, f0, tb in data:
        f, v = tab_series(name, kh, 24, w, fcs)
        model = 20 * np.log10(np.abs(v) + 1e-12) + response_db(f, r) + g[name]
        m = tb > 0
        meas = 20 * np.log10(tb[m])
        keep = meas > meas.max() - 45
        e = (model[m][keep] - model[m].max()) - (meas[keep] - meas.max())
        per.setdefault(name, []).append(float(np.sqrt(np.mean(e ** 2))))
        print("%-18s %8.1f  %5.1f   model %s\n%-18s %8s         meas  %s" % (
            name, kh, per[name][-1],
            " ".join("%4.0f" % (model[i] - model[m].max()) for i in range(8)), "", "",
            " ".join("%4.0f" % (20 * np.log10(tb[i] + 1e-12) - meas.max()) if tb[i] > 0 else "   ." for i in range(8))))
    print("\nby tab:", ", ".join("%s %.1f" % (k, np.mean(v)) for k, v in per.items()))
    out = os.path.expanduser("~/Documents/refs/wurlitzer_ben/circuit_fit.json")
    with open(out, "w") as fh:
        json.dump(dict(levels_db=g, complex_weights=w, flute_corner=fcs, response_db=list(map(float, r)),
                       knots=KNOTS.tolist(), rms_by_tab={k: float(np.mean(v)) for k, v in per.items()}, duty=DUTY[0], mix=MIX), fh, indent=1)
    print("written", out)


# THE TABLES THE ENGINE PLAYS (--py): each tab's series from the circuit and the speaker
# alone -- no garage -- at the keys C1 to C7 (its sounding pitch: mode_gains_points), its
# fitted level, all on one scale: the Flute 8' at C4 as the tables had it (1.0, its power)
ANCHOR_KEYS = [32.703 * 2 ** i for i in range(7)]          # C1 .. C7, the key's 8' pitch


def tables(fitted, nh=32):
    g, w, fcs, r = fitted
    out = {}
    for name in NETS:
        rows = []
        for kh in ANCHOR_KEYS:
            f, v = tab_series(name, kh, nh, w, fcs)
            a = np.abs(v) * 10 ** ((response_db(f, r) + g[name]) / 20)
            a[f > 16000] = 0.0
            rows.append((float(f[0]), a))
        out[name] = rows
    ref = next(a for f0, a in out["Flute 8'"] if abs(f0 - 261.6) < 1)
    s = 1.0 / np.sqrt(np.sum(ref ** 2))
    return {k: [(f0, a * s) for f0, a in v] for k, v in out.items()}


def emit_py(tb):
    lines = []
    for name, rows in tb.items():
        lines.append("# %s" % name)
        lines.append("    mode_gains_points = (")
        for f0, a in rows:
            vals = ["%.6f" % x for x in a]
            body = ",\n                  ".join(", ".join(vals[i:i + 8]) for i in range(0, len(vals), 8))
            lines.append("        (%.2f, (%s))," % (f0, body))
        lines.append("    )")
    return "\n".join(lines)



# THE PEDALS (straf pedal 652747, traced: schematics/straf_pedal_652747.md): the latch's
# 16' and 8' squares, each tab a resistor (the Bourdon's with .022 µF across) into one
# passive network around the 5 H coil, its node A into TR1's base (10K / 2.7K bias: 2.1K).
# The volume tabs set TR1's gain only. Monophonic: the last pedal pressed sounds.
PED_CORE = [("R", "o", "T", 1 * K), ("C", "T", "g", 0.82 * U), ("C", "T", "g", 0.01 * U),
            ("L", "T", "X", 5.0), ("C", "X", "g", 0.22 * U), ("R", "P", "o", 56 * K),
            ("R", "P", "q", 22 * K), ("C", "q", "X", 0.01 * U), ("R", "X", "Y", 33 * K),
            ("C", "X", "Y", 0.01 * U), ("R", "Y", "T", 22 * K)]
PED_TABS = {"Bourdon 16'": (0.5, [("R", "s", "X", 180 * K), ("C", "s", "X", 0.022 * U)]),
            "Principal 16'": (0.5, [("R", "s", "P", 100 * K)]),
            "Flute 8'": (1.0, [("R", "s", "X", 39 * K)]),
            "String Bass 8'": (1.0, [("R", "s", "Y", 82 * K)])}
PED_RLOAD = 2.1 * K
# THE LATCH'S WAVES ARE NOT SQUARE: the takes' strong even harmonics need the flip-flops'
# halves unequal -- duty 0.425 at 16', 0.45 at 8' (searched over 0.05-0.5, shapes only)
PED_DUTY = {0.5: 0.425, 1.0: 0.45}


def pedal_series(name, key_hz, n):
    """a pedal tab's voltage at TR1's base: harmonics 1..n of its sounding pitch"""
    ft, inj = PED_TABS[name]
    f = key_hz * ft * np.arange(1, n + 1)
    return f, square(n, PED_DUTY[ft]) * transfer(PED_CORE + inj, f, rload=PED_RLOAD)


def pedal_measured(nh=24):
    import wurlitzer_fit as WF
    import wurlitzer_survey as WS
    out = []
    for name, take, (a, b), fac in WS.PEDALS:
        if "Full" in name or "Medium" in name:
            continue                                   # (Normal: the cleanest takes)
        tab = name.split(" (")[0].replace("Pedal Flute", "Flute")
        x = WS.load(take, WS.REF)
        notes = WS.runs(x, a, b)
        keys = [64.2, 96.3, 128.4][:len(notes)]          # (the pedal's 8' pitch, low C, G, C)
        for (s, e), kh in zip(notes, keys):
            seg = x[int((s + 0.3) * WS.SR):int((e - 0.12) * WS.SR)]
            f0, _ = WS.spectrum(seg, kh * PED_TABS[tab][0])
            out.append((tab, kh, f0, np.array(WF.table(seg, f0)[:nh])))
    return out


def pedal_main():
    fit_ = json.load(open(os.path.expanduser("~/Documents/refs/wurlitzer_ben/circuit_fit.json")))
    r = np.array(fit_["response_db"])           # the speaker the upper tabs found: the same console's
    DUTY[0] = fit_.get("duty", 0.5)
    data = pedal_measured()
    per, lv = {}, {}
    for name, kh, f0, tb in data:
        f, v = pedal_series(name, kh, 24)
        model = 20 * np.log10(np.abs(v) + 1e-12) + response_db(f, r)
        m = tb > 0
        meas = 20 * np.log10(tb[m])
        keep = meas > meas.max() - 45
        e = (model[m][keep] - model[m].max()) - (meas[keep] - meas.max())
        per.setdefault(name, []).append(float(np.sqrt(np.mean(e ** 2))))
        lv.setdefault(name, []).append(float(meas.max() - model[m].max()))
        print("%-15s %6.1f  %4.1f dB  model %s\n%-15s %6s           meas  %s" % (
            name, kh, per[name][-1], " ".join("%4.0f" % (model[i] - model[m].max()) for i in range(8)), "", "",
            " ".join("%4.0f" % (20 * np.log10(tb[i] + 1e-12) - meas.max()) if tb[i] > 0 else "   ." for i in range(8))))
    print("by tab:", ", ".join("%s %.1f" % (k, np.mean(v)) for k, v in per.items()))
    return {k: float(np.mean(v)) for k, v in lv.items()}, r


def pedal_tables(levels, r, nh=32):
    out = {}
    keys = [32.703 * 2 ** i for i in range(5)]       # the pedal's 8' pitch, C1 .. C5
    for name in PED_TABS:
        rows = []
        for kh in keys:
            f, v = pedal_series(name, kh, nh)
            a = np.abs(v) * 10 ** ((response_db(f, r) + levels[name]) / 20)
            a[f > 16000] = 0.0
            rows.append((float(f[0]), a))
        out[name] = rows
    return out


if __name__ == "__main__":
    if "--pedal" in sys.argv:
        lv, r = pedal_main()
        if "--py" in sys.argv:
            tb = pedal_tables(lv, r)
            with open(os.path.expanduser("~/Documents/refs/wurlitzer_ben/pedal_tables.py.txt"), "w") as fh:
                fh.write(emit_py(tb) + "\n")
    else:
        main(sys.argv[1:])
