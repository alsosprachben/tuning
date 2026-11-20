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


def transfer(net, f):
    """V(o)/V(s) of NET at frequencies F (complex), "o" loaded by RLOAD"""
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
        stamp("o", "g", 1 / RLOAD)
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
    fr = next(r for top, r in FLUTE_RANGES if note <= top)
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


def response_db(f, r):
    return np.interp(np.log(f), np.log(KNOTS), r)


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
        out.append(3.0 * np.diff(r, 2))                 # (the response smooth)
        out.append([3.0 * np.mean(r)])                  # (its mean 0 dB: the levels are the tabs')
        return np.concatenate(out)
    p0 = np.concatenate([np.zeros(len(names)), [0.0, 0.0, 0.0, -2.0, -1.0, -1.0], np.zeros(len(KNOTS))])
    sol = least_squares(resid, p0, loss="soft_l1", f_scale=3.0, max_nfev=400)
    return unpack(sol.x), sol


def main(argv):
    data = measured()
    (g, w, fcs, r), sol = fit(data)
    print("complex octave weights (8', 4', 2'): %.2f %.2f %.2f   flute corner x%.2f   divider duty %.3f"
          % (w + (fcs, DUTY[0])))
    print("Trombone's 8' share %.2f; Diapason's 82K branch %+.2f x its 12K" % (MIX["trombone8"], MIX["diap_inv"]))
    print("shared response (dB) at", " ".join("%g" % k for k in KNOTS))
    print("   ", " ".join("%5.1f" % v for v in r))
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


if __name__ == "__main__":
    main(sys.argv[1:])
