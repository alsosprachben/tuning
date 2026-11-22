"""The Spectra-Tone's two cones fitted INSIDE Ben's garage, so the garage can
be taken away again (Ben: model the dry side; our room supplies its own).

The garage (Ben, 2026-11-21): 8.5 x 8.5 m, 3.05 m to the ceiling (half of it
plywood, half open to a steep roof), unfinished stud walls, two garage doors
opposite, two cars and clutter. The organ against the back wall, a little left
of centre, its back 0.13 m off the wall; the mic near the floor above the far
end of the pedalboard, ~1 m in front of the console speakers.

The near surfaces are images, in three dimensions: the floor under the mic,
the back wall behind the console, the ceiling, and the floor-and-wall pair.
Each leaves the rotor at its own azimuth AND elevation, so each takes its own
cut through each cone's beam and its own Doppler; each is 1/L and the
surface's reflection. The far side -- the cars, the side walls, the doors --
is scattered, so it is NLOOSE free paths, as spectratone_geometry has them.

Pitch is read only while the note is within 6 dB of its median, through a
0.4% band: at the swirl's nulls the partial sinks under the take's noise and
the instantaneous frequency of noise read as 9-13 cents (it is 3-7).

    python3 examples/spectratone_garage.py
"""
import os, sys, json
import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spectratone_fit as F
from spectratone_geometry import piston, K, NTH, C_SOUND

NLOOSE = int(os.environ.get("NLOOSE", "2"))
CEIL = 3.05
WALL_GAP = 0.13
KEEP_DB = 6.0
REAR_W = float(os.environ.get("REAR_W", "0.2"))   # the fade, in cos(psi): 0.2 ~ 12 deg past side-on


def measure(name, notes, lo=0.0, hi=None, frot_guess=0.605, harmonics=6, floor_db=-70.0):
    x, sr = F.load(name)
    segs = F.segments(x, sr, notes, lo, hi)
    parts = []
    for o, (t0, t1) in sorted(segs.items()):
        xs = x[int(t0 * sr):int(t1 * sr)]
        for h in range(1, harmonics + 1):
            f = F.C[o] * h
            if f > 9000:
                break
            z = F.env_db(F.band(xs, sr, f), sr)[20:-20]
            if z.mean() < floor_db:
                continue
            yn = F.band(xs, sr, f, 0.004)
            zn = F.env_db(yn, sr)[20:-20]
            cn = F.inst_cents(yn, sr, f)[20:-20]
            n = min(len(zn), len(cn)); zn, cn = zn[:n], cn[:n]
            keep = zn > np.median(zn) - KEEP_DB
            parts.append((f, z, float(np.percentile(cn[keep], 95) - np.percentile(cn[keep], 5))))
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
        n = max(int(len(z) * fr / F.FS_ENV) * int(F.FS_ENV / fr), int(F.FS_ENV / fr))
        a = 10 ** (z[:n] / 20); a = a / a.mean()
        c = [2 * abs(np.mean(a * np.exp(-2j * np.pi * k * fr * t[:n]))) for k in range(1, K + 1)]
        rows.append(dict(take=name, f=f, c=c, cents=cents,
                         depth=float(np.percentile(z, 95) - np.percentile(z, 5)), frot=fr))
    return rows


# (name, low, high)
PARAMS = [("radius_m", 0.01, 0.20), ("cone_radius_m", 0.03, 0.06), ("back", 0.0, 1.0),
          ("cone2_gain", 0.3, 1.0), ("cone2_radius_m", 0.01, 0.20),
          ("leak", 0.0, 3.0), ("leak_slope", -2.0, 2.0),
          ("rotor_y_m", WALL_GAP + 0.15, WALL_GAP + 0.6), ("rotor_z_m", 0.5, 1.1),
          ("mic_y_m", 1.0, 2.0), ("mic_z_m", 0.03, 0.30), ("mic_x_m", -0.4, 0.4),
          ("floor_r", 0.5, 1.0), ("wall_r", 0.0, 1.0), ("ceiling_r", 0.0, 1.0)] + \
         [p for m in range(1, NLOOSE + 1) for p in (("loose_azimuth%d" % m, -np.pi, np.pi),
                                                    ("loose_gain%d" % m, 0.0, 1.0),
                                                    ("loose_extra_m%d" % m, 0.0, 10.0))]
NAMES = tuple(p[0] for p in PARAMS)
LO = np.array([p[1] for p in PARAMS]); HI = np.array([p[2] for p in PARAMS])


def rear(cpsi, back):
    """The cone's level from in front (1) round to behind (`back`). A smooth
    turn just past side-on (REAR_W): a hard switch at side-on stepped the level twice
    a turn per cone per path, a click every cycle (Ben heard it)."""
    u = np.clip(-cpsi / REAR_W, 0.0, 1.0)       # 0 side-on .. 1 at REAR_W behind it
    return back + (1 - back) * 0.5 * (1 + np.cos(np.pi * u))


def images(P):
    """[(azimuth, elevation, length, gain)] of the near paths, rotor to mic.
    The rotor turns in the horizontal plane; azimuth 0 points down the garage
    (toward the doors)."""
    src = np.array([0.0, P["rotor_y_m"], P["rotor_z_m"]])
    mic = np.array([P["mic_x_m"], P["mic_y_m"], P["mic_z_m"]])
    out = []
    for flip_z, flip_y, g in ((None, None, 1.0), (0.0, None, P["floor_r"]), (CEIL, None, P["ceiling_r"]),
                              (None, 0.0, P["wall_r"]), (0.0, 0.0, P["floor_r"] * P["wall_r"])):
        m = mic.copy()
        if flip_z is not None:
            m[2] = 2 * flip_z - m[2]
        if flip_y is not None:
            m[1] = 2 * flip_y - m[1]
        d = m - src
        L = float(np.linalg.norm(d))
        az = float(np.arctan2(d[0], d[1]))
        el = float(np.arcsin(d[2] / L))
        out.append((az, el, L, g))
    return out


def response(f, p, nth=NTH):
    """The complex S over one turn (nth angles from 0) for a partial at f:
    every path's two cones summed, with the steady share."""
    P = dict(zip(NAMES, p))
    k = 2 * np.pi * f / C_SOUND
    th = np.linspace(0, 2 * np.pi, nth, endpoint=False)
    paths = images(P)
    L0 = paths[0][2]
    paths = [(az, el, L - L0, g * L0 / L) for az, el, L, g in paths]
    paths += [(P["loose_azimuth%d" % m], 0.0, P["loose_extra_m%d" % m], P["loose_gain%d" % m])
              for m in range(1, NLOOSE + 1)]
    S = np.zeros(nth, complex)
    for az, el, L, g in paths:
        ce = np.cos(el)
        for sgn, gain, rad in ((1.0, 1.0, P["radius_m"]), (-1.0, P["cone2_gain"], P["cone2_radius_m"])):
            cpsi = sgn * ce * np.cos(th - az)
            spsi = np.sqrt(np.maximum(1 - cpsi ** 2, 0.0))
            D = piston(k * P["cone_radius_m"] * spsi)
            D = D * rear(cpsi, P["back"])
            S += g * gain * D * np.exp(1j * k * (sgn * rad * ce * np.cos(th - az) - L))
    lk = P["leak"] * (f / 1000.0) ** P["leak_slope"]
    return S + lk * np.mean(np.abs(S))


def model(f, p, frot=0.605):
    P = dict(zip(NAMES, p))
    k = 2 * np.pi * f / C_SOUND
    th = np.linspace(0, 2 * np.pi, NTH, endpoint=False)
    paths = images(P)
    L0 = paths[0][2]
    paths = [(az, el, L - L0, g * L0 / L) for az, el, L, g in paths]
    paths += [(P["loose_azimuth%d" % m], 0.0, P["loose_extra_m%d" % m], P["loose_gain%d" % m])
              for m in range(1, NLOOSE + 1)]
    S = np.zeros(NTH, complex)
    for az, el, L, g in paths:
        ce = np.cos(el)
        for sgn, gain, rad in ((1.0, 1.0, P["radius_m"]), (-1.0, P["cone2_gain"], P["cone2_radius_m"])):
            cpsi = sgn * ce * np.cos(th - az)               # the cone's axis against the path
            spsi = np.sqrt(np.maximum(1 - cpsi ** 2, 0.0))
            D = piston(k * P["cone_radius_m"] * spsi)
            D = D * rear(cpsi, P["back"])
            S += g * gain * D * np.exp(1j * k * (sgn * rad * ce * np.cos(th - az) - L))
    lk = P["leak"] * (f / 1000.0) ** P["leak_slope"]
    S = S + lk * np.mean(np.abs(S))
    amp = np.abs(S); amp = amp / amp.mean()
    c = 2 * np.abs((np.fft.rfft(amp) / NTH)[1:K + 1])
    ph = np.unwrap(np.angle(S))
    cents = 1200 / np.log(2) * np.gradient(ph, th) * frot / f     # Hz of deviation = frot * dphase/dth
    lv = 20 * np.log10(np.abs(S) + 1e-12)
    keep = lv > np.median(lv) - KEEP_DB
    return c, float(np.percentile(cents[keep], 95) - np.percentile(cents[keep], 5)), \
        float(np.percentile(lv, 95) - np.percentile(lv, 5))


def residuals(p, rows, wc=float(os.environ.get("CENTS_W", "2.0"))):
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
    best = None
    rng = np.random.default_rng(11)
    seed = None
    if os.environ.get("SEED"):                  # start 0 from the saved fit
        Ps = json.load(open(os.path.join(F.DIR, "spectratone_garage.json")))["params"]
        seed = np.clip([Ps[n] for n in NAMES], LO, HI)
    for it in range(int(os.environ.get("STARTS", "40"))):
        p0 = seed if (it == 0 and seed is not None) else LO + (HI - LO) * rng.random(len(LO))
        s = least_squares(residuals, p0, bounds=(LO, HI), args=(rows,), x_scale=HI - LO, max_nfev=400)
        if best is None or s.cost < best.cost:
            best = s
            print("  start %d: cost %.3f" % (it, s.cost), flush=True)
    p = best.x
    print("FIT cost %.3f: %s" % (best.cost, "  ".join("%s=%.4g" % nv for nv in zip(NAMES, p))))
    print("   f Hz   take               measured c1..c6 / cents / depth      |  model c1..c6 / cents / depth")
    for r in sorted(rows, key=lambda r: r["f"]):
        c, cents, depth = model(r["f"], p, r["frot"])
        print("%7.1f %-17s %s %5.1f %5.1f | %s %5.1f %5.1f" % (
            r["f"], r["take"][:17], " ".join("%.2f" % v for v in r["c"]), r["cents"], r["depth"],
            " ".join("%.2f" % v for v in c), cents, depth))
    json.dump(dict(params=dict(zip(NAMES, map(float, p))), rows=rows),
              open(os.path.join(F.DIR, "spectratone_garage.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv)
