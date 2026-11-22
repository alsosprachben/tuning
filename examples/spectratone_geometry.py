"""The Spectra-Tone as geometry: two cones back to back on one turning arm.

Wurlitzer's patent US3070660 (and the 4500's schematic 504600: "ROTAT.
SPKR'S", two 4" #118071) puts two small speakers back to back on a rotor. Ben
heard the high notes wobble FASTER than the low ones; measured on the slow
rotor (0.60 turns/s, every take), C2-C5 swell once per turn, C6 three times,
C7 twice -- one beam swept past (the Leslie's model) cannot do that. Two
cones a few cm apart, each a piston that beams at high pitch, summed at the
listener, can: their sounds add and cancel in a pattern whose lobes multiply
as the wavelength comes down to their spacing, and the phase jumps by the
nulls are the 10-55 cents of pitch swing the high notes carry against 1-3 on
the low ones.

For one partial at f, the cones at +-r on the arm (angle th), facing out:

    S(th) = sum_i  D(psi_i) * exp(j k r_i cos th)  +  leak

D the piston's pattern, 2 J1(ka sin psi)/(ka sin psi) in front, and `back`
of it behind (the rear of a cone in a shared box); `leak` the steady share
(the cabinet's openings, the console speakers' crosstalk). Fitted to each
partial's level swing (its harmonics of the rotation, 1..6) and pitch swing.

    python3 examples/spectratone_geometry.py
"""
import os, sys, json
import numpy as np
from scipy.special import j1
from scipy.optimize import least_squares

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spectratone_fit as F

C_SOUND = 343.0
NTH = 720
K = 6


def measure(name, notes, lo=0.0, hi=None, frot_guess=0.605, harmonics=6, floor_db=-70.0):
    """[(f, |c_1..c_K|, cents p-p)] for each partial of each held note, with
    the rotation refined per take on the partials that swing most."""
    x, sr = F.load(name)
    segs = F.segments(x, sr, notes, lo, hi)
    parts = []
    for o, (t0, t1) in sorted(segs.items()):
        xs = x[int(t0 * sr):int(t1 * sr)]
        for h in range(1, harmonics + 1):
            f = F.C[o] * h
            if f > 9000:
                break
            y = F.band(xs, sr, f)
            z = F.env_db(y, sr)[20:-20]
            if z.mean() < floor_db:
                continue
            cents = F.inst_cents(y, sr, f)[20:-20]
            parts.append((f, z, cents))
    # the rotation: the rate whose harmonics hold most of the swings' power
    best = (0, frot_guess)
    for fr in np.linspace(frot_guess * 0.95, frot_guess * 1.05, 101):
        tot = 0.0
        for f, z, _ in parts:
            t = np.arange(len(z)) / F.FS_ENV
            a = 10 ** (z / 20); a = a / a.mean()
            tot += sum(abs(np.mean(a * np.exp(-2j * np.pi * k * fr * t))) ** 2 for k in range(1, K + 1))
        if tot > best[0]:
            best = (tot, fr)
    fr = best[1]
    rows = []
    for f, z, cents in parts:
        t = np.arange(len(z)) / F.FS_ENV
        n = int(len(z) * fr / F.FS_ENV) * int(F.FS_ENV / fr)     # whole turns
        n = max(n, int(F.FS_ENV / fr))
        a = 10 ** (z[:n] / 20); a = a / a.mean()
        c = [2 * abs(np.mean(a * np.exp(-2j * np.pi * k * fr * t[:n]))) for k in range(1, K + 1)]
        rows.append(dict(take=name, f=f, c=c, cents=float(np.percentile(cents, 95) - np.percentile(cents, 5)),
                         depth=float(np.percentile(z, 95) - np.percentile(z, 5)), frot=fr))
    return rows


def piston(ka_sin):
    x = np.where(np.abs(ka_sin) < 1e-6, 1e-6, ka_sin)
    return 2 * j1(x) / x


def model(f, p, frot=0.605):
    """(|c_1..c_K|, cents p-p, depth dB p-p) of one partial under params p.

    The mic hears the rotor along NPATH paths out of the cabinet (its slits on
    top, the floor, the walls): path m leaves the rotor toward azimuth phi_m,
    with gain g_m and extra length L_m (path 0: azimuth 0, gain 1, length 0).
    The two cones may differ (cone2's level, its own radius): with them equal
    the pattern repeats every half turn and holds only even harmonics."""
    r, a, back, leak, lslope, g2, r2 = p[:7]
    paths = [(0.0, 1.0, 0.0)] + [tuple(p[7 + 3 * m:10 + 3 * m]) for m in range(NPATH - 1)]
    k = 2 * np.pi * f / C_SOUND
    th = np.linspace(0, 2 * np.pi, NTH, endpoint=False)
    S = np.zeros(NTH, complex)
    for phi, g, L in paths:
        for sgn, gain, rad in ((1.0, 1.0, r), (-1.0, g2, r2)):
            ang = th - phi if sgn > 0 else th - phi + np.pi     # the cone's facing against the path
            D = piston(k * a * np.abs(np.sin(ang)))
            D = np.where(np.cos(ang) >= 0, D, back * D)
            S += g * gain * D * np.exp(1j * k * (sgn * rad * np.cos(th - phi) - L))
    lk = leak * (f / 1000.0) ** lslope
    S = S + lk * np.mean(np.abs(S))
    amp = np.abs(S); amp = amp / amp.mean()
    sp = np.fft.rfft(amp) / NTH
    c = 2 * np.abs(sp[1:K + 1])
    ph = np.unwrap(np.angle(S))
    dph = np.gradient(ph, th) * 2 * np.pi * frot         # rad/s of phase
    cents = 1200 / np.log(2) * dph / (2 * np.pi * f)   # dph is rad/s: / 2 pi is Hz
    lv = 20 * np.log10(np.abs(S) + 1e-12)
    return c, float(np.percentile(cents, 95) - np.percentile(cents, 5)), float(np.percentile(lv, 95) - np.percentile(lv, 5))


NPATH = int(os.environ.get("NPATH", "3"))
NAMES = ("radius_m", "cone_radius_m", "back", "leak", "leak_slope", "cone2_gain", "cone2_radius_m") + \
    tuple("%s%d" % (n, m) for m in range(1, NPATH) for n in ("path_azimuth", "path_gain", "path_extra_m"))
LO = np.array([0.005, 0.02, 0.0, 0.0, -2.0, 0.3, 0.005] + [-np.pi, 0.0, 0.0] * (NPATH - 1))
HI = np.array([0.20, 0.08, 1.0, 3.0, 2.0, 1.0, 0.20] + [np.pi, 1.5, 2.0] * (NPATH - 1))


def residuals(p, rows, wc=float(os.environ.get("CENTS_W", "1.0"))):
    out = []
    for r in rows:
        c, cents, _ = model(r["f"], p, r["frot"])
        out.extend((c - np.array(r["c"])) * 3.0)
        out.append(wc * (np.log10(1 + cents) - np.log10(1 + r["cents"])))
    return np.array(out)


def main(argv):
    rows = []
    rows += measure("st_warm.wav", (2, 3, 4, 5, 6, 7), 113.0, 226.0)
    rows += measure("st_upper_slow.wav", (5, 6, 7))
    rows += measure("st_lower_slow.wav", (5, 6, 7))
    print("rotation per take:", sorted({(r["take"], round(r["frot"], 4)) for r in rows}))
    best = None
    rng = np.random.default_rng(7)
    for it in range(int(os.environ.get("STARTS", "48"))):
        p0 = LO + (HI - LO) * rng.random(len(LO))
        sres = least_squares(residuals, p0, bounds=(LO, HI), args=(rows,), x_scale=HI - LO, max_nfev=400)
        if best is None or sres.cost < best.cost:
            best = sres
            print("  start %d: cost %.3f" % (it, sres.cost), flush=True)
    p = best.x
    print("FIT cost %.3f: %s" % (best.cost, "  ".join("%s=%.4g" % nv for nv in zip(NAMES, p))))
    print("   f Hz   take               measured c1..c6 / cents / depth      |  model c1..c6 / cents / depth")
    for r in sorted(rows, key=lambda r: r["f"]):
        c, cents, depth = model(r["f"], p, r["frot"])
        print("%7.1f %-17s %s %5.1f %5.1f | %s %5.1f %5.1f" % (
            r["f"], r["take"][:17], " ".join("%.2f" % v for v in r["c"]), r["cents"], r["depth"],
            " ".join("%.2f" % v for v in c), cents, depth))
    json.dump(dict(params=dict(zip(NAMES, map(float, p))), rows=rows),
              open(os.path.join(F.DIR, "spectratone_geometry.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv)
