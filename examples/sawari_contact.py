#!/usr/bin/env python3
"""THE BIWA'S SAWARI, simulated (Ben, 2026-11-23: "Contact model. Go with the
physics.") -- a silk string buzzing against the nearly flat strip shaved on
its nut or fret, and what that does to each partial, for the voice to carry
(GS 120.12 Biwa Stroke, BiwaProperties).

THE MECHANISM (Taguti, "Dynamics of simple string subject to unilateral
constraint: a model analysis of sawari mechanism", Acoust. Sci. & Tech.
29(3) 2008): the sawari is a solid strip about 1/200 of the open string long
at the string's fixed end -- on the nut (shirabeguchi) and on every fret of
a biwa. The string at rest lies on it; pressed into it, the string pushes
back by its OWN lateral elastic deformation (silk is soft), measured by
loading the strings (his Table 5): a force per unit length K0 times the
compression, K0 2.0-3.6e6 N/m^2 over the five strings. The model there is
lossless; here the string has its losses, so it can be checked against
the instrument.

THE CHECK (Taguti & Tohnai, "Acoustical analysis on the sawari tone of
Chikuzen biwa", Acoust. Sci. & Tech. 22(3) 2001): one biwa's open first
string (C3) recorded in an anechoic room, its nut first unshaved (S0) and
then shaved to a strong sawari (S3, a strip ~3 mm wide): the RMS level's
course over 3 s (their Table 3) -- S3 sustains, -1.3 dB at 0.4 s where S0
is at -10.6 -- and partials 6 and up growing slowly then decaying,
lasting twice as long.

THE MODEL: the string as its modes (each exact between steps, as
examples/fret_contact.py), the strip as P contact points over its width,
each pushing up with K0 dx times the string's compression there. The
string's losses are named: sigma(f) = SIGMA0 + SIGMA2 f^2 (amplitude 1/s;
air and the silk's internal friction), fitted to S0 -- the string without
its sawari -- so that S3 is a prediction.

    python3 examples/sawari_contact.py --check        S0 fitted, S3 predicted, against Taguti & Tohnai's Table 3
    python3 examples/sawari_contact.py --wav=F0 OUT   one stroke, with and without the sawari, as audio
    python3 examples/sawari_contact.py --phrase=K0 OUT three strokes through the body (K0 0: none)
    python3 examples/sawari_contact.py --bake         every key -> sawari_data.py (tonelib.SawariContact)

THE BAKE: each key on its string (TUNING, the open strings, each its
gauge from Taguti's Table 5; a note stopped on the highest open string at
or under it, the sawari at its fret -- every biwa fret has one), struck at
PLUCK_FROM_BRIDGE. The contact leaves each mode's start alone and feeds it
after: its envelope is the free string's fall plus a share that rings on,
fed by the modes under it -- the kernel's two stages, amp ((1 - share)
e^(-fast t) + share e^(-slow t)): fast the free silk's rate (the losses
above), share and slow fitted (log error, to 140 dB down). The contact
is linear on a flat strip (Taguti's), so the stroke's force scales the
motion and leaves the shape: one bake a key, no velocity axis.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

# THE STRING (Taguti 2008, Table 1: the chikuzen biwa's lowest, string "L")
SCALE_M = 0.80              # the open string's vibrating length
MU_KG_M = 1.5e-3            # its linear density (wound silk)
# THE SAWARI -- each a maker's or a restorer's choice, named
SAWARI_WIDTH_MM = 3.0       # the strip's length along the string (Taguti & Tohnai's S3, "strong")
# ITS SHAPE, re the string's straight line from the fixed end (+ = up into
# the string: the string lies pressed onto it). "Highly dependent on very
# small deviations in the contacting angle of surface to string, as well as
# on very small irregularities of the sawari surface, to the accuracy of
# sub-millimeters" (Taguti & Tohnai 2001) -- so both are named:
SAWARI_RISE_MM = 0.0        # the strip's slant: its far edge this high (0 = flat, Taguti 2008's)
SAWARI_RIDGE_MM = 0.0       # a ridge at its far edge, this high over the slant (0 = none)
K0_N_M2 = 2.0e6             # the silk's lateral stiffness, force per length per compression (Table 5, 2nd string)
SAWARI_POINTS = 12
# THE LOSSES (amplitude, 1/s): fitted to the unshaved nut, S0 -- its 24
# partials' durations (Taguti & Tohnai's Table 5, log rms 1.02) and its RMS
# course (Table 3, 4.9 dB) through the body below. Wound silk is lossy high:
# its partials over ~1.2 kHz gone in 0.05-0.4 s, unless the sawari feeds them
SIGMA0 = 1.0
SIGMA2 = 3.0e-6
# THE OPEN STRINGS (a satsuma biwa's four, as a player might tune them)
# and each one's linear density: Taguti's 1.5e-3 kg/m at 1.45 mm, scaled
# by the gauge squared (his Table 5's diameters, thickest lowest)
TUNING = ((110.00, 1.45), (164.81, 1.35), (220.00, 1.02), (246.94, 0.82))
# THE STROKE: the bachi near the body end, a displacement released
PLUCK_FROM_BRIDGE = 0.18    # of the speaking length (BiwaProperties.strike_point)
PLUCK_MM = 1.5
SR = 4 * 48000
F_MAX = 16000.0


def modes(f0, Ls):
    n = int(F_MAX / f0)
    m = np.arange(1, n + 1)
    fk = f0 * m
    sig = SIGMA0 + SIGMA2 * fk * fk
    return m, fk, sig


def simulate(f0, Ls=None, width_mm=SAWARI_WIDTH_MM, rise_mm=None, ridge_mm=None, k0=K0_N_M2,
             pluck_mm=PLUCK_MM, secs=2.0, mu=MU_KG_M, audio=False):
    """Each mode's amplitude (m) in 1 ms frames, (frames, modes), about the
    string's rest on the strip; and, with audio, the force on the bridge at
    48 kHz. width_mm 0: no sawari. A surface raised into the string (rise,
    ridge) presses it: its rest is found first (the string let settle on
    it, heavily damped), and the stroke is from there."""
    rise_mm = SAWARI_RISE_MM if rise_mm is None else rise_mm
    ridge_mm = SAWARI_RIDGE_MM if ridge_mm is None else ridge_mm
    Ls = Ls or SCALE_M
    m, fk, sig = modes(f0, Ls)
    n = len(m)
    w = 2.0 * np.pi * fk
    wd = np.sqrt(np.maximum(w * w - sig * sig, 1e-9))
    T = mu * (2.0 * Ls * f0) ** 2
    mass = mu * Ls / 2.0
    # the stroke: a triangle, apex PLUCK_FROM_BRIDGE from the bridge (x = Ls)
    xg = np.linspace(0.0, Ls, 8001)
    xc = Ls * (1.0 - PLUCK_FROM_BRIDGE)
    tri = np.minimum(xg / xc, (Ls - xg) / (Ls - xc)) * pluck_mm * 1e-3
    qp = (2.0 / Ls) * np.trapz(tri[:, None] * np.sin(np.outer(xg, m) * np.pi / Ls), xg, axis=0)
    q0 = np.zeros(n)
    dt = 1.0 / SR
    if width_mm > 0:
        xs = (np.arange(SAWARI_POINTS) + 0.5) / SAWARI_POINTS * width_mm * 1e-3
        floor = rise_mm * 1e-3 * xs / (width_mm * 1e-3)          # the surface, re the string's straight line
        kd = np.full(SAWARI_POINTS, k0 * width_mm * 1e-3 / SAWARI_POINTS)
        if ridge_mm > 0:
            # the ridge: a point at the strip's far edge, the silk pressed on
            # it over its own diameter's worth of length (2 r0 ~ 1.4 mm)
            xs = np.r_[xs, width_mm * 1e-3]
            floor = np.r_[floor, (rise_mm + ridge_mm) * 1e-3]
            kd = np.r_[kd, k0 * 1.4e-3]
        phi = np.sin(np.outer(xs, m) * np.pi / Ls)              # (points, modes)
        if (floor > 0).any():
            # the rest: settled on the surface, every mode damped hard (60 ms)
            sg = sig + 2000.0
            wds = np.sqrt(np.maximum(w * w - sg * sg, 1e-9))
            c2, s2, e2 = np.cos(wds * dt), np.sin(wds * dt), np.exp(-sg * dt)
            vv = np.zeros(n)
            for _ in range(int(0.06 * SR)):
                b = (vv + sg * q0) / wds
                q0, vv = e2 * (q0 * c2 + b * s2), e2 * ((b * wds - q0 * sg) * c2 - (q0 * wds + b * sg) * s2)
                pen = floor - phi @ q0
                vv = vv + dt * (kd * np.where(pen > 0.0, pen, 0.0)) @ phi / mass
    q = q0 + qp
    v = np.zeros(n)
    cs, sn, ex = np.cos(wd * dt), np.sin(wd * dt), np.exp(-sig * dt)
    frame = SR // 1000
    steps = int(secs * SR)
    A = np.zeros((steps // frame, n))
    dec = SR // 48000
    out = np.zeros(steps // dec) if audio else None
    slope = T * (m * np.pi / Ls) * np.cos(m * np.pi)             # each mode's pull on the bridge
    for i in range(steps):
        b = (v + sig * q) / wd
        q, v = ex * (q * cs + b * sn), ex * ((b * wd - q * sig) * cs - (q * wd + b * sig) * sn)
        if width_mm > 0:
            pen = floor - phi @ q                                  # how far into the strip
            if (pen > 0.0).any():
                v = v + dt * (kd * np.where(pen > 0.0, pen, 0.0)) @ phi / mass
        if audio and i % dec == 0:
            out[i // dec] = slope @ (q - q0)
        if (i + 1) % frame == 0:
            d = q - q0
            A[(i + 1) // frame - 1] = np.sqrt(d * d + (v / w) ** 2)
    return (A, fk, out) if audio else (A, fk)


# TAGUTI & TOHNAI 2001, Table 3: the open first string (C3), RMS (dB, 10 ms
# window) re its peak, S0 (no sawari) and S3 (strong), at these times (s)
T3_T = (0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.5)
T3_S0 = (-8.5, -10.6, -15.2, -21.2, -27.2, -34.8, -35.2, -40.2, -44.2, -47.1, -49.8)
T3_S3 = (-2.8, -1.3, -5.6, -9.8, -16.8, -26.6, -25.0, -31.9, -32.0, -34.4, -43.1)
C3_HZ = 138.6


# THE BODY, for the check: what reaches Taguti & Tohnai's microphone is the
# bridge's force through the body. Taguti's own coupled model (2008, sec. 5)
# had a resonator of two mass-dashpot-spring elements at 850 and 1,900 Hz;
# their Q, and a plate's radiation rising with frequency below them, named
BODY_HZ = (850.0, 1900.0)
BODY_Q = 4.0                # (fitted with the losses, from 4 and 12)
RADIATION_DB_OCT = 6.0


def radiated(y, sr=48000):
    n = 1 << int(np.ceil(np.log2(len(y))))
    f = np.fft.rfftfreq(n, 1.0 / sr)
    H = np.zeros(len(f), complex)
    for f0 in BODY_HZ:
        z = 1j * f / f0
        H += z / (1.0 + z / BODY_Q + z * z)           # each element's velocity per force
    H *= (np.maximum(f, 1.0) / 1000.0) ** (RADIATION_DB_OCT / 6.0)
    return np.fft.irfft(np.fft.rfft(y, n) * H, n)[:len(y)]


def rms_course(y, sr=48000):
    y = radiated(y, sr)
    w = int(0.01 * sr)
    e = 10 * np.log10(np.convolve(y * y, np.ones(w) / w, "same") + 1e-30)
    pk = int(np.argmax(e))
    return np.array([e[min(len(e) - 1, pk + int(t * sr))] - e[pk] for t in T3_T])


def check(fit=True):
    """S0's losses fitted (SIGMA0, SIGMA2), then S3 predicted."""
    global SIGMA0, SIGMA2
    # (their first string: 1.35 mm, the second's 1.45 at 1.5e-3 kg/m)
    mu1 = MU_KG_M * (1.35 / 1.45) ** 2
    if fit:
        best = None
        for s0 in (1.0, 2.0, 3.0, 4.5):
            for s2 in (3e-8, 1e-7, 3e-7, 1e-6):
                SIGMA0, SIGMA2 = s0, s2
                _, _, y = simulate(C3_HZ, width_mm=0.0, secs=2.6, mu=mu1, audio=True)
                e = float(np.sqrt(np.mean((rms_course(y) - np.array(T3_S0)) ** 2)))
                print("    S0 sigma0 %.1f sigma2 %.0e: %.1f dB" % (s0, s2, e), flush=True)
                if best is None or e < best[0]:
                    best = (e, s0, s2)
        SIGMA0, SIGMA2 = best[1], best[2]
    _, _, y0 = simulate(C3_HZ, width_mm=0.0, secs=2.6, mu=mu1, audio=True)
    r0 = rms_course(y0)
    S3 = []
    for kw in (dict(), dict(rise_mm=0.05), dict(ridge_mm=0.05), dict(rise_mm=0.05, ridge_mm=0.05),
               dict(rise_mm=0.15), dict(ridge_mm=0.15)):
        _, _, y3 = simulate(C3_HZ, width_mm=3.0, k0=3.2e6, secs=2.6, mu=mu1, audio=True, **kw)
        S3.append((kw, rms_course(y3)))
    print("  losses: sigma0 %.2f /s, sigma2 %.1e /s/Hz^2" % (SIGMA0, SIGMA2))
    print("  t (s)       " + " ".join("%6.1f" % t for t in T3_T))
    print("  S0 measured " + " ".join("%6.1f" % v for v in T3_S0))
    print("  S0 ours     " + " ".join("%6.1f" % v for v in r0))
    print("  S3 measured " + " ".join("%6.1f" % v for v in T3_S3))
    for kw, r3 in S3:
        print("  S3 %-24s" % (" ".join("%s %.2f" % (k[:-3], v) for k, v in kw.items()) or "flat") +
              " ".join("%6.1f" % v for v in r3) + "   (%.1f dB)" % np.sqrt(np.mean((r3 - np.array(T3_S3)) ** 2)))


BAKE_KEYS = tuple(range(36, 97))
BAKE_MODES = 96


def string_for(f0):
    """(speaking length m, mu kg/m) of a note on the TUNING's strings."""
    fo, d = TUNING[0]
    for fo_, d_ in TUNING:
        if fo_ <= f0 * 1.0001:
            fo, d = fo_, d_
    return SCALE_M * fo / f0 if f0 >= fo else SCALE_M, MU_KG_M * (d / 1.45) ** 2


def fit_fed(a, t, sig):
    """a(t)/a(0) ~ (1 - s) e^(-sig t) + s e^(-r t), r < sig: (s, r), the
    log error over where a is within 140 dB of its start."""
    ok = a > 1e-7
    if ok.sum() < 20:
        return 0.0, sig
    a, t = a[ok], t[ok]
    la = np.log(a)
    best = (np.inf, 0.0, sig)
    free = np.exp(-sig * t)
    for r in np.geomspace(0.05, 0.98 * sig, 40):
        fed = np.exp(-r * t)
        S_ = np.geomspace(1e-7, 0.9, 80)[:, None]
        model = (1.0 - S_) * free[None, :] + S_ * fed[None, :]
        e = np.sqrt(np.mean((np.log(model) - la[None, :]) ** 2, 1))
        j = int(np.argmin(e))
        if e[j] < best[0]:
            best = (float(e[j]), float(S_[j, 0]), float(r))
    e0 = float(np.sqrt(np.mean((np.log(free) - la) ** 2)))
    return (best[1], best[2]) if best[0] < 0.9 * e0 else (0.0, sig)


def bake(path=None, keys=BAKE_KEYS, secs=1.5):
    """sawari_data.py: KEYS, and for each key each mode's (share, fast dB/s,
    slow dB/s) in the class's dB (10 sigma / ln 10, as fretcontact_data)."""
    path = path or os.path.join(HERE, "sawari_data.py")
    rows, errs = [], []
    db = 10.0 / np.log(10.0)
    for key in keys:
        f0 = 440.0 * 2.0 ** ((key - 69) / 12.0)
        Ls, mu = string_for(f0)
        A, fk = simulate(f0, Ls=Ls, mu=mu, secs=secs)
        _, _, sig = modes(f0, Ls)
        t = np.arange(A.shape[0]) / 1000.0
        out = []
        for k in range(min(BAKE_MODES, A.shape[1])):
            a = A[:, k] / max(A[0, k], 1e-30)
            sh, r = fit_fed(a, t, sig[k])
            # (the fed share can not outlast what feeds it: never slower than
            # the fundamental's own fall -- a 1.5 s window read a fed floor as
            # near-zero decay)
            r = max(r, sig[0]) if sh > 0.0 else r
            out.append((round(sh, 7), round(sig[k] * db, 4), round(r * db, 4)))
        while len(out) < BAKE_MODES:
            out.append((0.0, 0.0, 0.0))
        rows.append(out)
        print("  key %d (%.1f Hz, %.3f m): h8 share %.2e slow %.1f dB/s (free %.1f); h16 %.2e %.1f (%.1f)"
              % (key, f0, Ls, out[7][0], out[7][2], out[7][1], out[15][0], out[15][2], out[15][1]), flush=True)
    with open(path, "w") as fh:
        fh.write('"""THE BIWA\'S SAWARI, baked by examples/sawari_contact.py --bake (do not\n'
                 'edit): for each key, each mode\'s (share, fast, slow) -- the free silk\'s\n'
                 'fall (dB/s, the class\'s) and the share fed by the sawari that rings on at\n'
                 'slow. Taguti\'s model (Acoust. Sci. & Tech. 29(3) 2008) with the silk\'s\n'
                 'measured stiffness, its losses fitted to Taguti & Tohnai 2001\'s unshaved\n'
                 'nut."""\n')
        fh.write("SAWARI = %r\n" % (dict(width_mm=SAWARI_WIDTH_MM, rise_mm=SAWARI_RISE_MM, ridge_mm=SAWARI_RIDGE_MM,
                                          k0=K0_N_M2, sigma0=SIGMA0, sigma2=SIGMA2, tuning=TUNING,
                                          pluck_from_bridge=PLUCK_FROM_BRIDGE),))
        fh.write("KEYS = %r\n" % (tuple(keys),))
        fh.write("TABLE = (\n")
        for r_ in rows:
            fh.write("    (%s),\n" % ", ".join("(%r, %r, %r)" % x for x in r_))
        fh.write(")\n")
    print("  wrote", path)


if __name__ == "__main__":
    if "--bake" in sys.argv:
        bake()
    if "--check" in sys.argv:
        check()
    for a in sys.argv:
        if a.startswith("--wav="):
            from scipy.io import wavfile
            f0 = float(a.split("=")[1])
            outp = sys.argv[-1]
            ys = [radiated(simulate(f0, width_mm=wd, audio=True)[2]) for wd in (0.0, SAWARI_WIDTH_MM)]
            y = np.concatenate([ys[0], np.zeros(12000), ys[1]])
            y = y / np.abs(y).max() * 0.8
            wavfile.write(outp, 48000, (y * 32767).astype(np.int16))
        if a.startswith("--phrase="):
            # --phrase=K0 OUT: A2 E3 A3 struck, 1.5 s each, through the body
            # (K0 0: no sawari)
            from scipy.io import wavfile
            k0 = float(a.split("=")[1])
            parts = []
            for f0 in (110.0, 164.81, 220.0):
                y = simulate(f0, width_mm=SAWARI_WIDTH_MM if k0 > 0 else 0.0, k0=k0 or K0_N_M2,
                             secs=1.5, audio=True)[2]
                parts += [radiated(y), np.zeros(4800)]
            y = np.concatenate(parts)
            wavfile.write(sys.argv[-1], 48000, (y / np.abs(y).max() * 0.8 * 32767).astype(np.int16))
