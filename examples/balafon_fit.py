#!/usr/bin/env python3
"""GS 12.16 "Barafon" and 12.17 "Barafon 2": the West African balafon --
wooden bars, undercut, over gourd resonators whose membranes BUZZ -- fitted
to marini24's balafon (Freesound pack 6325, CC BY 4.0; sources.md): 17
single strikes, 236 Hz-1.5 kHz, recorded to minidisc.

    python3 examples/balafon_fit.py          each key's modes, levels, decay and buzz
    python3 examples/balafon_fit.py --fit    the class values
    python3 examples/balafon_fit.py --buzz   the membranes' buzz through the renderer (the strike-noise rows)
    python3 examples/balafon_fit.py --ab OUT.wav   five keys, each take then ours (CC BY: kept local)

Read as the gender's bars are (examples/gender_fit.py: key(), band_decay):

  pitch    the strongest peak 0.02-0.12 s after the strike, over 200 Hz (a
           150 Hz hum, the minidisc's mains, runs under most takes)
  modes    the strongest peak in each window, 2.8-4.4 and 6.8-9.6 times
           (undercut bars: the second tuned near 4, lower up the keys)
  decay    each band's slope to 30 dB down (band_decay), dB/s
  buzz     the membranes: the spectrum BETWEEN the partials (each partial
           +-4% left out, the hum's lines +-10 Hz) 1-8 kHz, its power re the
           fundamental's over 0.01-0.1 s, and how fast it falls (0.01-0.06 s
           against 0.06-0.15 s)
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import gender_fit as G  # noqa: E402

PACK = os.path.expanduser("~/Documents/refs/freesound/balafon_marini24")
WINDOWS = ((2.8, 4.4), (6.8, 9.6))
HUM = 150.0


def takes():
    return sorted(glob.glob(os.path.join(PACK, "*.aiff")),
                  key=lambda p: int(p.split("ball-")[1].split(".")[0]))


def buzz(x, sr, k, f0, modes):
    """(buzz re the fundamental, dB, over 0.01-0.1 s; its fall, dB/s)."""
    def between(a, b):
        f, S = G.spectrum(x, sr, k + int(a * sr), k + int(b * sr))
        P = 10 ** (S / 10)
        keep = (f > 1000) & (f < 8000)
        for fm in [f0 * r for r in (1.0,) + tuple(m for m in modes if np.isfinite(m))] + \
                  [f0 * h for h in range(2, 40)]:
            keep &= np.abs(f - fm) > 0.04 * fm
        for h in range(1, 60):
            keep &= np.abs(f - HUM * h) > 10.0
        a0 = P[(f > f0 * 0.98) & (f < f0 * 1.02)].max()
        return 10 * np.log10(P[keep].mean() / a0 + 1e-30)
    if len(x) - k < int(0.16 * sr):
        return np.nan, np.nan
    early, mid = between(0.01, 0.06), between(0.06, 0.15)
    return between(0.01, 0.1), (early - mid) / 0.075


BUZZ_BANDS = 500.0 * 2 ** (np.arange(0, 13) / 3.0)        # 500 Hz .. 8 kHz


def buzz_bands(x, sr, k, f0, ratios, a=0.01, b=0.1):
    """The buzz by third octave: power between the partials (each, the hum
    and its harmonics +-4% left out), re the fundamental's, a..b s."""
    f, S = G.spectrum(x, sr, k + int(a * sr), k + int(b * sr))
    P = 10 ** (S / 10)
    keep = np.ones(len(f), bool)
    for fm in [f0 * r for r in ratios if np.isfinite(r)] + [f0 * h for h in range(1, 40)]:
        keep &= np.abs(f - fm) > 0.04 * fm
    # the hum's lines are narrow: +-10 Hz (+-4% of each emptied every band
    # over 2 kHz, where its harmonics 150 Hz apart overlap)
    for h in range(1, 60):
        keep &= np.abs(f - HUM * h) > 10.0
    a0 = P[(f > f0 * 0.98) & (f < f0 * 1.02)].max()
    out = []
    for c in BUZZ_BANDS:
        m = keep & (f >= c * 2 ** (-1 / 6)) & (f < c * 2 ** (1 / 6))
        out.append(10 * np.log10(P[m].mean() / a0 + 1e-30) if m.sum() > 3 else np.nan)
    return np.array(out)


def survey():
    rows = []
    for p in takes():
        # the pitch EARLY, as the take's own strongest peak over 200 Hz:
        # gender_fit.key() reads it at 0.6-0.7 s, when these bars are gone
        x, sr = G.load(p)
        k = int(np.argmax(np.abs(x)))
        f, S = G.spectrum(x, sr, k + int(0.02 * sr), k + int(0.12 * sr))
        ok = (f > 200) & (f < 1700)
        f0 = float(f[ok][np.argmax(S[ok])])
        a0 = S[ok].max()
        modes = []
        for lo, hi in WINDOWS:
            m = (f > f0 * lo) & (f < f0 * hi) & (f < 0.45 * sr) & (np.abs(f / HUM - np.round(f / HUM)) * HUM > 8)
            if not m.any():
                modes.append((np.nan, np.nan, np.nan))
                continue
            i = np.argmax(S[m]); fm = float(f[m][i])
            modes.append((fm / f0, float(S[m][i] - a0), G.band_decay(x, sr, k, fm)))
        bz, bzd = buzz(x, sr, k, f0, [m[0] for m in modes])
        bb = buzz_bands(x, sr, k, f0, (1.0,) + tuple(m[0] for m in modes))
        rows.append(dict(name=os.path.basename(p).split("__")[-1][:-5], f0=f0, d1=G.band_decay(x, sr, k, f0),
                         modes=modes, buzz=bz, buzz_dbs=bzd, buzz_bands=bb))
    return rows


def fit(rows):
    """The class values. RATIOS: the second and third modes as lines in the
    octave from 415 Hz (undercut by hand, they wander key to key and fall up
    the keyboard: 4.1 at 236 Hz, 2.9 past 700). LEVELS: g2, g3 under one
    roll-off in Hz (bore_corner_hz, its order: the mallet's -- a mode at 1
    kHz stands near the fundamental, at 2.5 kHz 40 dB under). DECAYS: tonelib's
    D (half the band's dB/s) at 415 Hz along one register slope (the
    fundamental's), each mode its median. BUZZ: its level re the fundamental
    against the octave, for the strike-noise table's slope."""
    from scipy.optimize import minimize
    f0 = np.array([r["f0"] for r in rows]); oc = np.log2(f0 / 415.0)
    out = {}
    for j in range(2):
        R = np.array([r["modes"][j][0] for r in rows]); L = np.array([r["modes"][j][1] for r in rows])
        ok = np.isfinite(R) & (L > -40)
        a, b = np.polyfit(oc[ok], R[ok], 1)[::-1]
        out["r%d" % (j + 2)] = (round(float(a), 3), round(float(b), 3))
        print("  mode %d ratio = %.3f %+.3f per octave from 415 Hz  (%d keys; spread %.2f)"
              % (j + 2, a, b, ok.sum(), np.std(R[ok] - (a + b * oc[ok]))))
    # LEVELS BY THE KEY, NOT BY THE Hz: one roll-off in Hz missed by 9.8 dB
    # -- a low key's third mode at 2.1 kHz stands level with its fundamental
    # while a high key's second at 2.5 kHz is 40 dB under. A big bar rings its
    # upper modes and a small one does not: each mode's level a line in the
    # octave, written at anchor pitches (tonelib mode_gains_points)
    L = np.array([[r["modes"][j][1] for j in range(2)] for r in rows])
    lines = []
    for j in range(2):
        ok = np.isfinite(L[:, j]) & (L[:, j] > -60)
        b, a = np.polyfit(oc[ok], L[ok, j], 1)
        miss = float(np.mean(np.abs(L[ok, j] - (a + b * oc[ok]))))
        lines.append((a, b))
        print("  mode %d level = %+.1f dB %+.1f per octave from 415 Hz  (%d keys, miss %.1f dB)" % (j + 2, a, b, ok.sum(), miss))
    anchors = (236.0, 415.0, 830.0, 1500.0)
    pts = tuple((hz, (1.0,) + tuple(round(float(10 ** (max(-80.0, a + b * np.log2(hz / 415.0)) / 20)), 4)
                                    for a, b in lines)) for hz in anchors)
    print("  mode_gains_points = %s" % (pts,))
    d1 = np.array([r["d1"] for r in rows]); ok = np.isfinite(d1) & (d1 > 0.5)
    slope, c = np.polyfit(oc[ok], np.log2(d1[ok] / 2.0), 1)
    decs = [float(2 ** c)]
    for j in range(2):
        D = np.array([r["modes"][j][2] for r in rows])
        okd = np.isfinite(D) & (D > 0.5) & (L[:, j] > -40)
        decs.append(float(np.median(D[okd] / 2.0 / 2.0 ** (slope * oc[okd]))))
    print("  mode_decays = (%.2f, %.2f, %.2f), decay_register_slope = %.3f" % (decs[0], decs[1], decs[2], slope))
    bz = np.array([r["buzz"] for r in rows]); okb = np.isfinite(bz)
    bs, bc = np.polyfit(oc[okb], bz[okb], 1)
    bd = np.array([r["buzz_dbs"] for r in rows])
    print("  buzz re h1: %+.1f dB at 415 Hz, %+.1f dB an octave up; its fall median %.0f dB/s" % (bc, bs, np.nanmedian(bd[okb])))
    return dict(ratios=out, points=pts, decays=decs, slope=slope,
                buzz=(bc, bs, float(np.nanmedian(bd[okb]))))


def buzz_fit(rows, passes=5):
    """THE BUZZ THROUGH THE RENDERER: each key rendered at its pitch (Barafon,
    12.16), its buzz_bands and its fall read as the take's; the strike-noise
    table moved by the median take - ours band by band, its register slope by
    how the keys' mean difference runs with the octave, its decay by the
    falls. The best pass by the bands' mean miss; prints the class values."""
    import tonelib as T
    cls = T.BalafonProperties
    f0 = np.array([r["f0"] for r in rows]); oc = np.log2(f0 / 415.0)
    want = np.array([r["buzz_bands"] for r in rows])
    wfall = np.nanmedian([r["buzz_dbs"] for r in rows])
    best = None
    for it in range(passes + 1):
        got, falls = [], []
        for r in rows:
            y, sr = G._ours_at(12, 16, r["f0"], 0.6)
            k = int(np.argmax(np.abs(y)))
            ratios = (1.0, cls.mode_ratio(cls(r["f0"], 0.0, 0.6, 1.0), 2), cls.mode_ratio(cls(r["f0"], 0.0, 0.6, 1.0), 3))
            got.append(buzz_bands(y, sr, k, r["f0"], ratios))
            falls.append(buzz(y, sr, k, r["f0"], ratios[1:])[1])
        got = np.array(got)
        D = want - got
        band = np.nanmedian(D, 0)
        miss = float(np.nanmean(np.abs(band)))
        km = np.nanmedian(D - band, 1)
        ok = np.isfinite(km)
        sl = float(np.polyfit(oc[ok], km[ok], 1)[0]) if ok.sum() > 2 else 0.0
        gfall = float(np.nanmedian(falls))
        print("  pass %d: by band %s  (mean |miss| %.2f); key slope %+.1f dB/oct; fall ours %.0f, take %.0f dB/s"
              % (it, " ".join("%+4.0f" % v if np.isfinite(v) else "  --" for v in band), miss, sl, gfall, wfall), flush=True)
        if best is None or miss < best[0]:
            best = (miss, cls.strike_noise_db, cls.strike_noise_octave_db, cls.strike_noise_dbs)
        if it == passes:
            break
        cls.strike_noise_db = tuple((hz, round(float(db + 0.7 * np.clip(np.nan_to_num(b), -12, 12)), 1))
                                    for (hz, db), b in zip(cls.strike_noise_db, band))
        cls.strike_noise_octave_db = round(cls.strike_noise_octave_db + 0.7 * sl, 2)
        if np.isfinite(gfall) and gfall > 1:
            cls.strike_noise_dbs = round(float(np.clip(cls.strike_noise_dbs * (wfall / gfall) ** 0.7, 20, 2000)), 1)
    miss, cls.strike_noise_db, cls.strike_noise_octave_db, cls.strike_noise_dbs = best
    print("  best: %.2f dB" % miss)
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))
    print("    strike_noise_octave_db = %.2f" % cls.strike_noise_octave_db)
    print("    strike_noise_dbs = %.1f" % cls.strike_noise_dbs)


AB_KEYS = ("ball-1", "ball-4", "ball-8", "ball-12", "ball-21")


def ab(out):
    """Five keys across the balafon, each take then ours (12.16) at its pitch."""
    jobs = [(glob.glob(os.path.join(PACK, "*__%s.aiff" % n))[0], 12, 16, 1.2, 200, 1700) for n in AB_KEYS]
    G.ab_pairs(jobs, out)


def main(argv):
    if "--ab" in argv:
        ab(argv[argv.index("--ab") + 1])
        return 0
    rows = survey()
    if "--buzz" in argv:
        buzz_fit(rows)
        return 0
    if "--fit" in argv:
        fit(rows)
        return 0
    print("  key       f0   D1 dB/s | mode 2: ratio, dB, dB/s | mode 3          | buzz re h1, its fall")
    for r in rows:
        print("  %-7s %6.1f  %6.1f | %s | %+5.1f dB  %5.0f dB/s" % (
            r["name"], r["f0"], r["d1"],
            " | ".join("%.2f %+4.0f %5.0f" % m for m in r["modes"]), r["buzz"], r["buzz_dbs"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
