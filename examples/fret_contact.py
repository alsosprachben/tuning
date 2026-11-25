#!/usr/bin/env python3
"""A SLAPPED OR POPPED BASS STRING AGAINST ITS FRETS, simulated (Ben,
2026-11-23: "build the fret contact physics") -- what the contact does to
each partial, for the voice to carry (GM 36, 37).

THE MODEL (Issanchou, Bilbao, Le Carrou, Touze, Doare, "A modal-based
approach to the nonlinear vibration of strings against a unilateral
obstacle", JSV 393 2017; Issanchou, Acary, Perignon, Touze, Le Carrou,
"Nonsmooth contact dynamics for the numerical simulation of collisions in
musical string instruments", JASA 143(5) 2018): the string as its modes -- each at its stretched frequency, damped
at its own rate, both from ElectricBassProperties' physics (the same string
the voice plays) -- and each fret a point obstacle under it, pushing back
with a Hertzian force K d^1.5 while the string is below the fret's top.
The string speaks from the fret it is stopped on (or the nut) to the
bridge; the frets past it lie under it, the string's height over each the
SETUP's: a straight line from the stop to the saddle (the action at the
12th fret sets it) less the neck's relief, a bow peaking at the 7th fret.

THE STROKE:
  slap -- the thumb strikes DOWN, toward the frets, at the end of the
          fingerboard: an initial velocity over the thumb's width;
  pop  -- a finger hooks the string, pulls it UP and lets go: an initial
          displacement, a triangle over the fingertip's width.
Integrated per mode, exactly between steps (each mode's free motion), the
fret forces as kicks at each step (symplectic, as Issanchou's modal scheme).

THE BAKE (--bake): for each key E1-G3 and four strokes, each mode's
AMPLITUDE envelope from T0 on -- the kernel's two-stage partial,
amp ((1 - share) e^(-fast t) + share e^(-slow t)), slow the string's own
physics rate -- fitted (non-negative least squares on relative error, fast
over a grid). amp is the mode's displacement over the FREE string's first
mode under the same stroke (so a hard slap's lost or gained level is kept);
the voice's pickup reads it as it reads any string. Written to
fretcontact_data.py (tonelib.FretContact reads it).

    python3 examples/fret_contact.py slap E1 [--vel=V]   one stroke: each mode's energy over time, with and without the frets
    python3 examples/fret_contact.py --bake              every key and stroke, both classes -> fretcontact_data.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

# THE SETUP -- each a player's or a tech's choice, named
ACTION_12_MM = 2.5          # the string's height over the 12th fret's top, open (a bass's typical, E side)
RELIEF_MM = 0.3             # the neck's bow at its deepest (the 7th fret)
FRETS = 24
CONTACT_K = 1.0e10          # N / m^1.5, the fret's Hertzian stiffness (steel on nickel-steel; Issanchou's
                            # 1e13 needs their energy scheme -- this one is stiff enough that the
                            # string's penetration stays under ~10 um)
CONTACT_A = 1.5
# THE STROKE
SLAP_FROM_BRIDGE_M = 0.216  # the thumb at the fingerboard's end (the 24th fret, a quarter of the scale)
THUMB_W_M = 0.015
# THE THUMB IS A BODY, not an impulse: a velocity spread over 15 mm moves
# the string ~0.15 mm (its waves carry the impulse off); a thumb is a mass
# driving it down into the frets for a few ms -- its effective mass (the
# thumb and what the wrist puts behind it) on its flesh's spring
THUMB_MASS_KG = 0.02
THUMB_K = 1.0e4             # N/m: with the mass, ~4 ms of contact
SUBSTEPS = 16               # integration steps a step, near a fret or under the thumb
POP_FROM_BRIDGE_M = 0.216
FINGER_W_M = 0.008
SR = 4 * 48000              # the integration rate
F_MAX = 9000.0              # modes up to here...
MODE_CAP = 128              # ...and no more than this many (the voice's 64, and the contact's spill above them)


def string_of(cls, f0):
    """(stopped length, the frets under it from the stop [positions m], the
    string's height over each [m], mu, T, mode freqs Hz, mode decays 1/s)."""
    p = type("Free", (cls,), {"fret_contact": None})(f0, 0.0, 1.0, 1.0)     # (the string alone, no table)
    k, o, Ls = p._string_of(f0)
    d, mu, T = p._string_mu_t(k, o)
    L = p.scale_length_m
    fret = 12.0 * np.log2(L / Ls)
    nut = lambda j: L * (1.0 - 2.0 ** (-j / 12.0))          # fret j's distance from the nut
    stop = nut(fret)
    js = [j for j in range(1, FRETS + 1) if nut(j) > stop + 1e-4]
    xs = np.array([nut(j) - stop for j in js])            # along the speaking length, from the stop
    # the action: open, a line from the nut (0) to the saddle (2 x the 12th's),
    # the relief a sine bow nut-to-joint peaking near the 7th; stopped, the
    # string runs from the stop fret's top to the saddle
    H = 2.0 * ACTION_12_MM * 1e-3
    bow = lambda x: RELIEF_MM * 1e-3 * np.sin(np.pi * np.clip(x / nut(FRETS), 0.0, 1.0))
    xa = stop + xs                                        # from the nut
    line = (H * stop / L) + (H - H * stop / L) * xs / Ls  # the string's height over the fret plane
    plane = -bow(xa) + bow(stop)                          # the fret tops, relative to the stop fret's
    gap = line - plane
    B = p.inharmonicity_coefficient_for_frequency(f0)
    n = min(int(F_MAX / f0), MODE_CAP)
    m = np.arange(1, n + 1)
    fk = f0 * m * np.sqrt(1.0 + B * m * m)
    sig = np.array([2.0 * p.harmonic_decay(int(q)) for q in m]) / (20.0 / np.log(10.0))   # amplitude 1/s
    return Ls, xs, gap, mu, T, fk, sig, p


def simulate(cls, f0, stroke="slap", vel=1.0, secs=0.6, frets=True):
    """Each mode's energy over time (rows: 1 ms frames) -- and the frets'
    total force, for the clatter. vel and frets may be sequences: the strokes
    run together, one row each (a key's strokes cost about what one does)."""
    one = np.ndim(vel) == 0
    vels = np.atleast_1d(np.asarray(vel, float))
    fr = np.broadcast_to(np.atleast_1d(np.asarray(frets, bool)), vels.shape).astype(float)[:, None]
    R = len(vels)
    Ls, xs, gap, mu, T, fk, sig, p = string_of(cls, f0)
    n = len(fk)
    m = np.arange(1, n + 1)
    w = 2.0 * np.pi * fk
    wd = np.sqrt(np.maximum(w * w - sig * sig, 1e-9))
    phi_f = np.sin(np.outer(xs, m) * np.pi / Ls)          # (frets, modes)
    xg = np.linspace(0.0, Ls, 4001)
    phi_g = np.sin(np.outer(xg, m) * np.pi / Ls)
    norm = 2.0 / Ls                                       # projection: q_k = (2/L) int y phi_k dx
    q = np.zeros((R, n))
    v = np.zeros((R, n))
    thumb = stroke == "slap"
    if thumb:
        xc = Ls - SLAP_FROM_BRIDGE_M
        prof = np.exp(-0.5 * ((xg - xc) / (THUMB_W_M / 2.0)) ** 2)
        phi_t = np.trapz(prof[:, None] * phi_g, xg, axis=0) / np.trapz(prof, xg)   # the thumb's reading of each mode
        u, uv = np.zeros(R), -(1.0 + 3.0 * vels)          # the thumb: at the string, moving down, m/s
        live = np.ones(R, bool)
    else:
        xc = Ls - POP_FROM_BRIDGE_M
        tri = np.minimum(xg / xc, (Ls - xg) / (Ls - xc))
        shape = norm * np.trapz(tri[:, None] * phi_g, xg, axis=0)
        q = np.outer((2.0 + 6.0 * vels) * 1e-3, shape)   # m, pulled up
    frame = SR // 1000
    steps = int(secs * SR)
    E = np.zeros((R, steps // frame, n))
    Ff = np.zeros((R, steps // frame))
    mass = mu * Ls / 2.0                                  # each mode's modal mass
    fsum = np.zeros(R)
    coef = {}

    def free(q, v, dt):
        if dt not in coef:
            coef[dt] = (np.cos(wd * dt), np.sin(wd * dt), np.exp(-sig * dt))
        cs, sn, ex = coef[dt]
        a = q
        b = (v + sig * q) / wd
        return ex * (a * cs + b * sn), ex * ((b * wd - a * sig) * cs - (a * wd + b * sig) * sn)
    dt0 = 1.0 / SR
    anyf = bool(fr.any()) and len(xs) > 0           # (a note at the top fret has none under it)
    for i in range(steps):
        # near a fret (within 0.3 mm), or under the thumb: substeps
        near = (anyf and ((q @ phi_f.T + gap).min(1)[fr[:, 0] > 0] < 3e-4).any()) or \
            (thumb and live.any() and (u[live] < (q[live] @ phi_t) + 1e-3).any())
        ns = SUBSTEPS if near else 1
        dt = dt0 / ns
        for _ in range(ns):
            q, v = free(q, v, dt)
            if anyf:
                pen = -(q @ phi_f.T + gap) * fr               # how far under each fret's top (rows with frets)
                if (pen > 0.0).any():
                    F = CONTACT_K * np.where(pen > 0.0, pen, 0.0) ** CONTACT_A
                    v = v + dt * (F @ phi_f) / mass
                    fsum += F.sum(1) / ns
            if thumb and live.any():
                c = np.where(live, q @ phi_t - u, 0.0)        # the thumb under the string's top: pushing
                Ft = THUMB_K * np.where(c > 0.0, c, 0.0)
                v = v - dt * np.outer(Ft, phi_t) / mass
                uv = uv + dt * Ft / THUMB_MASS_KG
                u = u + dt * uv
                live &= u <= 0.02                             # (gone: the wrist has carried it off)
        if (i + 1) % frame == 0:
            r = (i + 1) // frame - 1
            E[:, r] = 0.5 * mass * (v * v + w * w * q * q)
            Ff[:, r] = fsum / frame
            fsum[:] = 0.0
    if one:
        return E[0], Ff[0], fk, p
    return E, Ff, fk, p


T0_S = 0.010                     # the envelope fitted from here (the contact's first strokes over)
BAKE_KEYS = tuple(range(28, 68))  # E1-G3
BAKE_VELS = (0.25, 0.5, 0.75, 1.0)
BAKE_MODES = 64
BAKE_CLASSES = (("SlapBassProperties", "slap"), ("PoppedBassProperties", "pop"))


def amp_env(E, fk, mass):
    """Each mode's displacement amplitude from its energy, frame by frame."""
    w = 2.0 * np.pi * fk
    return np.sqrt(np.maximum(2.0 * E / (mass * w * w), 0.0))


def fit_two_stage(a, t, slow):
    """a(t) ~ c1 e^(-r1 t) + c2 e^(-slow t), c >= 0, r1 > slow on a grid:
    (amp at t=0, share = c2 / (c1 + c2), r1) in 1/s; relative error."""
    from scipy.optimize import nnls
    ok = a > a.max() * 1e-5
    if ok.sum() < 8:
        return 0.0, 1.0, slow, 0.0
    a, t = a[ok], t[ok]
    best = None
    for r1 in np.geomspace(max(1.5 * slow, 3.0), 4000.0, 48):
        M = np.stack([np.exp(-r1 * t), np.exp(-slow * t)], 1) / a[:, None]
        c, res = nnls(M, np.ones_like(a))
        if best is None or res < best[0]:
            best = (res, c, r1)
    res, c, r1 = best
    tot = c[0] + c[1]
    if tot <= 0.0:
        return 0.0, 1.0, slow, 1.0
    # (never above what the mode reached: where the contact only grazes, the
    # envelope jumps, and a fast stage fitted to it extrapolated its start
    # 20-30 x a neighbouring key's -- the fast part trimmed to the peak)
    cap = float(a.max())
    if tot > cap:
        c0 = max(cap - c[1], 0.0)
        c = (c0, min(c[1], cap))
        tot = c[0] + c[1]
    return float(tot), float(c[1] / tot), float(r1), float(res / np.sqrt(len(a)))


def bake_one(cls, stroke, f0, vels):
    """A key's strokes, with the frets and (the reference, its first 20 ms) without."""
    vels = tuple(vels)
    Ec, _, fk, p = simulate(cls, f0, stroke, vels, frets=True)
    E0, _, _, _ = simulate(cls, f0, stroke, vels, secs=0.02, frets=False)
    Ls, xs, gap, mu, T, fk, sig, p = string_of(cls, f0)
    mass = mu * Ls / 2.0
    i0 = int(T0_S * 1000)
    res = []
    for r in range(len(vels)):
        A, A0 = amp_env(Ec[r], fk, mass), amp_env(E0[r], fk, mass)
        t = (np.arange(A.shape[0]) - i0) / 1000.0
        ref = A0[i0, 0]
        out, errs = [], []
        for k in range(min(BAKE_MODES, A.shape[1])):
            amp, share, r1, e = fit_two_stage(A[i0:, k], t[i0:], sig[k])
            out.append((amp / ref, share, r1 * 10.0 / np.log(10.0)))      # (fast: the class's dB, half the envelope's)
            errs.append(e)
        while len(out) < BAKE_MODES:
            out.append((0.0, 1.0, 0.0))
        res.append((out, float(np.median(errs))))
    return res


def bake(path=None, keys=BAKE_KEYS, vels=BAKE_VELS):
    import tonelib as T
    path = path or os.path.join(HERE, "fretcontact_data.py")
    tables = {}
    for name, stroke in BAKE_CLASSES:
        cls = getattr(T, name)
        grid = []
        for key in keys:
            f0 = 440.0 * 2 ** ((key - 69) / 12.0)
            row = []
            # (each key's strokes cached as they come: an interrupted bake resumes)
            cache = os.path.join(os.path.expanduser("~/Documents/refs/idmt/model"), "fretcontact_%s_%d.npy" % (stroke, key))
            if os.path.exists(cache):
                res = [(o, e) for o, e in np.load(cache, allow_pickle=True)]
            else:
                res = bake_one(cls, stroke, f0, vels)
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                np.save(cache, np.array(res, dtype=object), allow_pickle=True)
            for v, (o, e) in zip(vels, res):
                row.append(o)
                print("  %s key %d vel %.2f: fit %.3f, h1 %.2f (share %.2f), h8 %.2f, h24 %.2f"
                      % (stroke, key, v, e, o[0][0], o[0][1], o[7][0], o[23][0]), flush=True)
            grid.append(row)
        tables[name] = grid
    with open(path, "w") as f:
        f.write('"""GENERATED by examples/fret_contact.py --bake: a slapped or popped bass\n'
                'string against its frets, simulated -- TABLES[class][key - KEYS[0]][vel][mode] =\n'
                '(amp over the free string\'s first mode, the share ringing on at the string\'s own\n'
                'rate, the fast stage\'s rate in the class\'s dB). Do not edit."""\n')
        f.write("KEYS = %r\nVELS = %r\nSETUP = %r\n" % (tuple(keys), tuple(vels), dict(
            action_12_mm=ACTION_12_MM, relief_mm=RELIEF_MM, contact_k=CONTACT_K, thumb_mass_kg=THUMB_MASS_KG,
            thumb_k=THUMB_K, thumb_w_m=THUMB_W_M, slap_m=SLAP_FROM_BRIDGE_M, pop_m=POP_FROM_BRIDGE_M,
            finger_w_m=FINGER_W_M, t0_s=T0_S)))
        f.write("TABLES = {\n")
        for name, grid in tables.items():
            f.write("    %r: (\n" % name)
            for row in grid:
                f.write("        (" + ", ".join("(" + ", ".join("(%.4g, %.4g, %.4g)" % m for m in vrow) + ",)"
                                         for vrow in row) + ",),\n")
            f.write("    ),\n")
        f.write("}\n")
    return path


def main(argv):
    import tonelib as T
    if "--bake" in argv:
        print("  written", bake())
        return 0
    stroke = argv[1] if len(argv) > 1 else "slap"
    name = argv[2] if len(argv) > 2 else "E1"
    vel = next((float(a.split("=")[1]) for a in argv if a.startswith("--vel=")), 0.8)
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    midi = names.index(name[:-1]) + 12 * (int(name[-1]) + 1)
    f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
    cls = T.SlapBassProperties if stroke == "slap" else T.PoppedBassProperties
    Ec, Fc, fk, p = simulate(cls, f0, stroke, vel, frets=True)
    E0, _, _, _ = simulate(cls, f0, stroke, vel, frets=False)
    db = lambda e: 10 * np.log10(np.maximum(e, 1e-30))
    ref = db(E0[2, 0])
    print("  %s %s, vel %.2f: %d modes; frets' force, ms 0-20: %s N" % (
        stroke, name, vel, len(fk), " ".join("%.0f" % x for x in Fc[:20])))
    print("   mode  free: 2 / 50 / 300 ms dB      with frets: 2 / 50 / 300 ms dB")
    for k in (0, 1, 2, 3, 4, 5, 7, 9, 14, 19, 29, 39, 59):
        if k >= len(fk):
            break
        print("   h%-3d  %6.1f %6.1f %6.1f        %6.1f %6.1f %6.1f" % (
            k + 1, db(E0[2, k]) - ref, db(E0[50, k]) - ref, db(E0[299, k]) - ref,
            db(Ec[2, k]) - ref, db(Ec[50, k]) - ref, db(Ec[299, k]) - ref))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
