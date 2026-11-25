#!/usr/bin/env python3
"""THE VOICER'S REGULATION (Ben 2026-11-25: "a curve ... with a balanced tone
across human loudness sensitivity"). The simulated pipes (examples/
organ_levels.py) speak on full wind with a windway the voicer never set
(1.5% of the diameter, fluepipe_sim: Audsley will not tabulate it), so a
rank's radiated power falls 2.5-4.5 dB an octave up its compass -- exactly
the jet's flow, (f x mouth width x windway)^2. A voicer regulates each pipe
(its windway, its toe) until the rank speaks EVENLY TO THE EAR. Here each
rank is rendered alone across its compass, free-standing (the case and its
projection off: they stand over the regulated rank, as heard), its loudness
read per key, and the per-key correction that makes it even written for
organ_levels.py to fold into the tables. The rank keeps its loudness where its
balance with the others was set by ear (organ_levels.level_keys), so the
registrations combine as they did.

    python3 examples/organ_regulate.py [--rounds=2] [CLASS ...]

LOUDNESS: third-octave band levels, each to phons by ISO 226:2003's equal-
loudness contours, to sones, summed (a plain Zwicker without masking; alike
for every key of a rank, which is all the evening needs). The SPL scale:
REF_SPL at the principal 8's middle C (named: a single 8' in the nave).
Writes examples/organ_regulation.json: {class: [[rank Hz, dB], ...]}.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]

import organ_bake as OB  # noqa: E402
import organ_levels as OL  # noqa: E402

REG = os.path.join(HERE, "organ_regulation.json")
REF_SPL = 72.0                         # dB SPL of the principal 8's middle C, steady
MANUAL_KEYS = tuple(range(36, 97, 4))  # written C2..C7
PEDAL_KEYS = tuple(range(24, 61, 3))   # written C1..C4
TREBLE_ASCENDANCY_DB = 0.0             # phons an octave up the compass (0: even, the voicer's plain aim)
# WHAT A VOICER CAN DO: a pipe's windway and toe move it this far from as
# built, no further (named, for the ear) -- the 16 Hz pipes of a 16' and the
# 4-8 kHz top of a 2' stay as soft to the ear as they physically are
REG_MAX_DB = 12.0

# ISO 226:2003, Table 1
_F = (20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
      2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500)
_AF = (0.532, 0.506, 0.480, 0.455, 0.432, 0.409, 0.387, 0.367, 0.349, 0.330, 0.315, 0.301, 0.288, 0.276,
       0.267, 0.259, 0.253, 0.250, 0.246, 0.244, 0.243, 0.243, 0.243, 0.242, 0.242, 0.245, 0.254, 0.271, 0.301)
_LU = (-31.6, -27.2, -23.0, -19.1, -15.9, -13.0, -10.3, -8.1, -6.2, -4.5, -3.1, -2.0, -1.1, -0.4, 0.0, 0.3,
       0.5, 0.0, -2.7, -4.1, -1.0, 1.7, 2.5, 1.2, -2.1, -7.1, -11.2, -10.7, -3.1)
_TF = (78.5, 68.7, 59.5, 51.1, 44.0, 37.5, 31.5, 26.5, 22.1, 17.9, 14.4, 11.4, 8.6, 6.2, 4.4, 3.0, 2.2,
       2.4, 3.5, 1.7, -1.3, -4.2, -6.0, -5.4, -1.5, 6.0, 12.6, 13.9, 12.3)


def _spl_of_phon(ln, i):
    af, lu, tf = _AF[i], _LU[i], _TF[i]
    a = 4.47e-3 * (10 ** (0.025 * ln) - 1.15) + (0.4 * 10 ** ((tf + lu) / 10.0 - 9)) ** af
    return 10.0 / af * math.log10(a) - lu + 94.0


def phon(spl, f):
    """ISO 226's loudness level of a tone at spl dB, f Hz (held at the table's ends)."""
    i = min(range(len(_F)), key=lambda j: abs(math.log(f / _F[j])))
    if spl <= _TF[i]:
        return 0.0
    lo, hi = 0.0, 120.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if _spl_of_phon(mid, i) < spl:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def sone(ph):
    return 2.0 ** ((ph - 40.0) / 10.0) if ph >= 40.0 else (ph / 40.0) ** 2.642


def bands_db(x, sr):
    """Third-octave band levels (dB re full scale power) of x, 16 Hz-16 kHz."""
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    out = []
    for k in range(-18, 13):
        fc = 1000.0 * 2.0 ** (k / 3.0)
        m = (f >= fc * 2 ** (-1 / 6.0)) & (f < fc * 2 ** (1 / 6.0))
        p = float(X[m].sum())
        out.append((fc, 10 * math.log10(p + 1e-30)))
    return out


def loudness(bands, offset):
    return sum(sone(phon(db + offset, fc)) for fc, db in bands)


def render_note(rank, key):
    import mido
    import blockrender as B
    import tonelib as T
    host = T.FlueOrganProperties
    names = [r[0] for r in host.stop_ranks]
    keep = host.default_stops
    host.default_stops = 1 << names.index(rank)
    try:
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("program_change", channel=0, program=19, time=0))
        t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=2 * 960))
        L, R = B.render(m)[:2]
    finally:
        host.default_stops = keep
    x = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
    return bands_db(x[int(1.0 * B.SR):int(1.9 * B.SR)], B.SR)


def fit_anchors(anc, hz, want):
    """The regulation at the anchors (dB) whose curve -- linear in dB along log
    frequency between them, held past the ends, as the tables blend -- comes
    nearest want at hz (least squares, a little ridge where no key binds an
    anchor), each within REG_MAX_DB."""
    anc = sorted(anc)
    W = np.zeros((len(hz), len(anc)))
    for i, f in enumerate(hz):
        if f <= anc[0]:
            W[i, 0] = 1.0
        elif f >= anc[-1]:
            W[i, -1] = 1.0
        else:
            j = max(q for q in range(len(anc) - 1) if anc[q] <= f)
            w = math.log(f / anc[j]) / math.log(anc[j + 1] / anc[j])
            W[i, j], W[i, j + 1] = 1.0 - w, w
    lam = 1e-3
    A = W.T @ W + lam * np.eye(len(anc))
    # (the ridge toward the neighbours' mean: an anchor no key reaches follows them)
    for j in range(len(anc)):
        nb = [q for q in (j - 1, j + 1) if 0 <= q < len(anc)]
        for q in nb:
            A[j, q] -= lam / len(nb)
    r = np.linalg.solve(A, W.T @ np.asarray(want))
    # past the compass measured, the curve at its edge holds (a GM file may
    # play a Pedal stop on any key)
    lo, hi = min(hz), max(hz)
    cur = {a: float(x) for a, x in zip(anc, r)}
    inside = {a: x for a, x in cur.items() if lo <= a <= hi} or cur
    edge = lambda f: OL._interp_db(inside, min(max(f, lo), hi))
    r = [cur[a] if lo <= a <= hi else edge(a) for a in anc]
    return [[round(a, 3), round(float(max(-REG_MAX_DB, min(REG_MAX_DB, x))), 3)] for a, x in zip(anc, r)]


def keys_of(name):
    return PEDAL_KEYS if OL.level_keys(name) == OL.PEDAL_LEVEL_KEYS else MANUAL_KEYS


def measure(name, offset):
    """{written key: sones} of the rank alone, free-standing."""
    rank = OB.CLASSES[name][1]
    return {k: loudness(render_note(rank, k), offset) for k in keys_of(name)}


def main(argv):
    import tonelib as T
    os.environ.setdefault("TUNING_REFLECT", "0")
    rounds = int(next((a.split("=")[1] for a in argv if a.startswith("--rounds=")), "2"))
    names = [a for a in argv[1:] if not a.startswith("--")] or [n for n in OB.CLASSES if n not in OL.HELD]
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    # free-standing: the case and its projection stand over the regulated rank
    T.FlueOrganProperties.case_scale = 0.0
    T.FlueOrganProperties.case_projection = None
    ref = render_note("principal 8", 60)
    offset = REF_SPL - 10 * math.log10(sum(10 ** (db / 10.0) for _, db in ref))
    for rnd in range(rounds):
        for n in names:
            OL.write_one(n)                                 # (the tables as reg now has them)
            import native as N
            N.forget()
            lv = measure(n, offset)
            bal = [k for k in OL.level_keys(n)]
            nt = float(np.mean([lv[min(lv, key=lambda q: abs(q - k))] for k in bal]))
            rat = OL._ratio(OB.CLASSES[n][1])
            rat = rat if not isinstance(rat, (list, tuple)) else 1.0
            cur = {float(a): b for a, b in reg.get(n, [])}
            hz_k, want_k = [], []
            for k, s in sorted(lv.items()):
                if s < 1e-3 * nt:
                    continue                # (a key the rank has no pipe for)
                hz = 261.63 * rat * 2 ** ((k - 60) / 12.0)
                want = nt * 2.0 ** (TREBLE_ASCENDANCY_DB * (k - 60) / 12.0 / 10.0)
                # phons to go, taken as dB (the rounds close the rest)
                dph = 10.0 * math.log2(want / s)
                c0 = OL._interp_db(cur, hz) if cur else 0.0
                hz_k.append(hz)
                want_k.append(max(-REG_MAX_DB, min(REG_MAX_DB, c0 + dph)))
            reg[n] = fit_anchors(OL.anchor_pitches(n), hz_k, want_k)
            with open(REG, "w") as fh:
                json.dump(reg, fh, indent=1)
            print("  round %d %-30s sones re its balance: %s" % (
                rnd + 1, n, " ".join("%d:%.2f" % (k, lv[k] / nt) for k in sorted(lv))), flush=True)
    cache = json.load(open(OB.CACHE)) if os.path.exists(OB.CACHE) else {}
    OL.write(names, cache)
    print("  examples/organ_regulation.json and tonelib.py written")


if __name__ == "__main__":
    main(sys.argv)
